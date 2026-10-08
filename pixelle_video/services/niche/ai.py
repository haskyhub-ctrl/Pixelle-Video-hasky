# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
LLM-powered analyses for niche research. Every function takes the shared
LLMService and returns a typed Pydantic result.
"""

import json
from typing import Sequence

from pydantic import BaseModel, Field

from pixelle_video.services.llm_service import LLMService
from pixelle_video.services.niche.models import VideoItem


def _video_lines(videos: Sequence[VideoItem], limit: int = 40) -> str:
    lines = []
    for v in videos[:limit]:
        s = v.scores
        lines.append(
            f"- [{v.platform}] \"{v.title}\" | views={v.views:,} | subs={v.channel_subscribers:,} "
            f"| outlier={s.get('outlier', '?')}x | age={s.get('age_days', '?')}d | dur={v.duration_sec}s")
    return "\n".join(lines)


# --------------------------------------------------------------- keywords

class SubNiche(BaseModel):
    name: str
    description: str = ""
    example_titles: list[str] = Field(default_factory=list)


class KeywordInsights(BaseModel):
    short_keywords: list[str] = Field(default_factory=list, description="2-3 word head terms, high volume")
    long_tail_keywords: list[str] = Field(default_factory=list, description="4+ word specific phrases, low competition")
    sub_niches: list[SubNiche] = Field(default_factory=list)
    summary: str = ""


async def keyword_insights(llm: LLMService, query: str, videos: Sequence[VideoItem],
                           language: str = "vi") -> KeywordInsights:
    prompt = f"""Bạn là chuyên gia nghiên cứu ngách YouTube/TikTok.
Chủ đề: "{query}". Dưới đây là các video đúng chủ đề, đã xếp theo điểm vượt trội (outlier = views / view trung vị của kênh):

{_video_lines(videos)}

Nhiệm vụ:
1. short_keywords: 8-12 từ khoá ngắn (2-3 từ), lượng tìm lớn.
2. long_tail_keywords: 10-15 từ khoá dài (4+ từ), cụ thể, ít cạnh tranh, dễ lên top.
3. sub_niches: 4-6 ngách con đang lặp lại ở các video thắng, mỗi ngách có mô tả ngắn và 1-3 tiêu đề ví dụ lấy từ danh sách.
4. summary: 2-3 câu nhận định cơ hội của ngách.
Trả lời bằng ngôn ngữ: {language}."""
    return await llm(prompt, response_type=KeywordInsights, temperature=0.4, max_tokens=3000)


# ------------------------------------------------------------ translation

class Translations(BaseModel):
    items: list[str]


async def translate_texts(llm: LLMService, texts: Sequence[str], target: str = "Vietnamese") -> list[str]:
    if not texts:
        return []
    out: list[str] = []
    for i in range(0, len(texts), 40):
        batch = list(texts[i:i + 40])
        prompt = (f"Translate each item to {target}. Keep the meaning natural for video titles. "
                  f"Return exactly {len(batch)} items in the same order.\n\n"
                  + json.dumps(batch, ensure_ascii=False))
        res = await llm(prompt, response_type=Translations, temperature=0.2, max_tokens=4000)
        items = res.items + batch[len(res.items):]
        out += items[:len(batch)]
    return out


class MarketKeywords(BaseModel):
    keywords: dict[str, str] = Field(description="language code -> translated search keyword")


async def translate_keyword(llm: LLMService, keyword: str, languages: Sequence[str]) -> dict[str, str]:
    prompt = (f"Translate the video search keyword \"{keyword}\" into the most natural search phrase "
              f"native speakers would type on YouTube/TikTok for each language code: {', '.join(languages)}. "
              "Return a mapping language code -> keyword.")
    res = await llm(prompt, response_type=MarketKeywords, temperature=0.2, max_tokens=800)
    return res.keywords


# ---------------------------------------------------------- winning topics

class TopicIdea(BaseModel):
    title: str
    hook: str = Field(description="First 3 seconds hook line")
    angle: str = ""
    based_on: str = Field(default="", description="Which outlier video/pattern inspired it")
    format: str = Field(default="short", description="short | long")


class WinningTopics(BaseModel):
    patterns: list[str] = Field(default_factory=list, description="Recurring formulas behind the winners")
    title_formulas: list[str] = Field(default_factory=list)
    topics: list[TopicIdea] = Field(default_factory=list)


async def winning_topics(llm: LLMService, niche: str, outliers: Sequence[VideoItem],
                         count: int = 15, language: str = "vi") -> WinningTopics:
    prompt = f"""Bạn là strategist nội dung. Ngách: "{niche}".
Các video vượt trội nhất (đã lọc theo outlier và views/sub):

{_video_lines(outliers, 30)}

1. patterns: rút ra 5-8 "công thức thắng" (góc nhìn, cảm xúc, cấu trúc, độ dài, đối tượng).
2. title_formulas: 5 mẫu tiêu đề dạng template, ví dụ "[Con số] lý do ... khiến ...".
3. topics: đề xuất {count} chủ đề MỚI (không chép), mỗi chủ đề có tiêu đề, hook 3 giây đầu, góc nhìn, dựa trên video/pattern nào, định dạng short/long.
Ngôn ngữ trả lời: {language}."""
    return await llm(prompt, response_type=WinningTopics, temperature=0.8, max_tokens=4000)


# ----------------------------------------------------------------- script

class VideoScript(BaseModel):
    title: str
    hook: str
    script: str = Field(description="Full narration; one paragraph per scene, separated by blank lines")
    cta: str = ""
    scene_visuals: list[str] = Field(default_factory=list, description="Visual description per paragraph")
    hashtags: list[str] = Field(default_factory=list)


async def write_script(llm: LLMService, topic: str, hook: str = "", duration_sec: int = 60,
                       style: str = "kể chuyện cuốn hút", language: str = "vi",
                       reference: str = "") -> VideoScript:
    words = int(duration_sec * 2.6)
    prompt = f"""Viết kịch bản video {duration_sec} giây (~{words} từ lời thoại) cho chủ đề: "{topic}".
Hook gợi ý: {hook or '(tự đề xuất)'}
Phong cách: {style}. Ngôn ngữ: {language}.
{('Tham khảo cấu trúc video thắng: ' + reference) if reference else ''}
Yêu cầu:
- Hook 3 giây đầu gây tò mò mạnh, không chào hỏi.
- Mỗi đoạn là một cảnh (cách nhau bằng dòng trống), câu ngắn, dễ đọc thành giọng nói.
- Có vòng lặp mở (open loop) giữ chân người xem, kết thúc bằng CTA tự nhiên.
- scene_visuals: mô tả hình ảnh cho từng đoạn theo đúng thứ tự."""
    return await llm(prompt, response_type=VideoScript, temperature=0.8, max_tokens=4000)


# ---------------------------------------------------------------- channel

class ChannelReport(BaseModel):
    positioning: str = ""
    content_pillars: list[str] = Field(default_factory=list)
    what_works: list[str] = Field(default_factory=list)
    what_fails: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)


async def channel_report(llm: LLMService, channel_title: str, stats: dict,
                         top: Sequence[VideoItem], flops: Sequence[VideoItem], language: str = "vi") -> ChannelReport:
    prompt = f"""Phân tích chiến lược kênh "{channel_title}".
Số liệu: {json.dumps(stats, ensure_ascii=False, default=str)}
Video tốt nhất (so với trung vị kênh):
{_video_lines(top, 10)}
Video kém nhất:
{_video_lines(flops, 10)}
Trả lời bằng {language}: định vị kênh, các trụ cột nội dung, điều gì hiệu quả, điều gì thất bại, cơ hội để vượt kênh này."""
    return await llm(prompt, response_type=ChannelReport, temperature=0.5, max_tokens=3000)


class DoctorIssue(BaseModel):
    severity: str = Field(description="high | medium | low")
    problem: str
    evidence: str = ""
    fix: str


class DoctorReport(BaseModel):
    diagnosis: str
    issues: list[DoctorIssue] = Field(default_factory=list)
    action_plan_30_days: list[str] = Field(default_factory=list)


async def channel_doctor(llm: LLMService, channel_title: str, diagnostics: dict,
                         top: Sequence[VideoItem], flops: Sequence[VideoItem],
                         language: str = "vi") -> DoctorReport:
    prompt = f"""Bạn là "bác sĩ kênh" YouTube. Chẩn đoán kênh "{channel_title}" dựa trên số liệu đo được
(đã kèm kết quả kiểm tra tự động, có so sánh với kênh đối thủ nếu có):
{json.dumps(diagnostics, ensure_ascii=False, default=str, indent=1)}

Video tốt nhất:
{_video_lines(top, 8)}
Video kém nhất:
{_video_lines(flops, 8)}

Trả lời bằng {language}: chẩn đoán tổng quát, danh sách vấn đề (mức độ, bằng chứng từ số liệu, cách sửa cụ thể),
kế hoạch hành động 30 ngày."""
    return await llm(prompt, response_type=DoctorReport, temperature=0.4, max_tokens=3500)


# -------------------------------------------------------------------- SEO

class SEOSuggestion(BaseModel):
    titles: list[str] = Field(default_factory=list)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    thumbnail_text: list[str] = Field(default_factory=list)


async def seo_rewrite(llm: LLMService, title: str, description: str, tags: Sequence[str],
                      keyword: str, competitor_titles: Sequence[str] = (), language: str = "vi") -> SEOSuggestion:
    prompt = f"""Tối ưu SEO YouTube cho video.
Từ khoá chính: "{keyword}"
Tiêu đề hiện tại: {title}
Mô tả hiện tại: {description[:1500]}
Tags hiện tại: {', '.join(tags)}
Tiêu đề top đối thủ: {json.dumps(list(competitor_titles)[:15], ensure_ascii=False)}

Trả lời bằng {language}:
- titles: 5 tiêu đề 40-70 ký tự, có từ khoá ở đầu, gây tò mò, không clickbait sai sự thật.
- description: mô tả 150-300 từ, từ khoá trong 2 dòng đầu, có mục chapters mẫu (00:00 ...), kết thúc 3-5 hashtag.
- tags: 10-15 tags từ rộng tới hẹp.
- hashtags: 3-5 hashtag.
- thumbnail_text: 3 phương án chữ trên thumbnail (≤ 4 từ)."""
    return await llm(prompt, response_type=SEOSuggestion, temperature=0.6, max_tokens=3000)


# ------------------------------------------------------- video teardown (mổ băng)

class Teardown(BaseModel):
    framework: str = Field(description="The structural formula of why this video works")
    hook_breakdown: str = Field(description="How the first 3 seconds grab attention")
    structure: list[str] = Field(default_factory=list, description="Beat-by-beat structure")
    psychology: list[str] = Field(default_factory=list, description="Psychological triggers used")
    audience: str = Field(default="", description="Who this targets")
    remakes: list[TopicIdea] = Field(default_factory=list, description="3 differentiated remakes, policy-safe")


async def video_teardown(llm: LLMService, video: VideoItem, comments: Sequence[str] = (),
                         language: str = "vi") -> Teardown:
    """Mổ băng đối thủ — learn the framework of a winning video, output 3 remakes."""
    cmt = ("\nBình luận nổi bật của người xem:\n" + "\n".join(f"- {c}" for c in list(comments)[:30])) if comments else ""
    prompt = f"""Mổ xẻ video đang thắng để học CÁI KHUNG (không chép nội dung).
Tiêu đề: "{video.title}"
Nền tảng: {video.platform} · views: {video.views:,} · outlier: {video.scores.get('outlier', '?')}x · thời lượng: {video.duration_sec}s
Mô tả: {video.description[:800]}{cmt}

Trả lời bằng {language}:
- framework: công thức vì sao video này thắng (1-2 câu).
- hook_breakdown: 3 giây đầu níu người xem thế nào.
- structure: cấu trúc theo từng nhịp (mở đầu → thân → cao trào → kết).
- psychology: các đòn tâm lý (tò mò, FOMO, phản bác, bất ngờ...).
- audience: video nhắm tới ai.
- remakes: 3 chủ đề làm lại KHÁC BIỆT, đúng chính sách (không vi phạm bản quyền/nhạy cảm), mỗi cái có title, hook (3 giây đầu), angle, based_on, format (short/long)."""
    return await llm(prompt, response_type=Teardown, temperature=0.7, max_tokens=4000)


# ------------------------------------------------------- AI image/video prompts

class MediaPrompts(BaseModel):
    image_prompts: list[str] = Field(default_factory=list, description="English image prompts, one per scene")
    video_prompts: list[str] = Field(default_factory=list, description="English video/motion prompts, one per scene")
    negative_prompt: str = Field(default="", description="Shared negative prompt")
    style_note: str = Field(default="", description="Consistent style/character note to reuse")


async def media_prompts(llm: LLMService, title: str, scenes: Sequence[str], style: str = "cinematic",
                        tool: str = "generic") -> MediaPrompts:
    """Turn each scene into an English image prompt and a video/motion prompt."""
    scene_list = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(scenes))
    prompt = f"""You are a prompt engineer for AI image/video tools (target tool: {tool}).
Video title: "{title}". Visual style: {style}.
Scenes (in order):
{scene_list}

Return ENGLISH prompts:
- image_prompts: one detailed image prompt per scene (subject, composition, lighting, lens, mood, style), keep the same character/style consistent across scenes.
- video_prompts: one motion/video prompt per scene (camera movement, action, pacing), matching each image.
- negative_prompt: one shared negative prompt.
- style_note: a short reusable style+character description to keep all scenes consistent.
Exactly {len(scenes)} items in image_prompts and video_prompts, same order."""
    return await llm(prompt, response_type=MediaPrompts, temperature=0.6, max_tokens=4000)


# ------------------------------------------------------- affiliate: sales script

class SalesScript(BaseModel):
    title: str
    hook: str = Field(description="First 3 seconds pain-point hook")
    script: str = Field(description="Short sales video script: hook → demo → benefit → objection → offer → CTA")
    scene_visuals: list[str] = Field(default_factory=list)
    on_screen_text: list[str] = Field(default_factory=list, description="Text overlays per beat")
    cta: str = ""
    hashtags: list[str] = Field(default_factory=list)


async def sales_script(llm: LLMService, product: str, pain_points: str = "", benefits: str = "",
                       duration_sec: int = 45, language: str = "vi") -> SalesScript:
    prompt = f"""Viết kịch bản video ngắn BÁN HÀNG affiliate TikTok Shop cho sản phẩm: "{product}".
Thời lượng ~{duration_sec}s. Ngôn ngữ: {language}.
Điểm đau khách hàng: {pain_points or '(tự suy luận)'}
Lợi ích chính: {benefits or '(tự suy luận)'}
Cấu trúc bắt buộc: hook nỗi đau (3s) → demo sản phẩm → lợi ích → xử lý phản đối → ưu đãi → bấm giỏ hàng (CTA).
Trả lời: title, hook, script (mỗi cảnh cách nhau dòng trống), scene_visuals, on_screen_text (chữ overlay từng nhịp), cta, hashtags.
Không cam kết công dụng quá mức (tránh vi phạm chính sách TikTok Shop với thuốc/thực phẩm chức năng)."""
    return await llm(prompt, response_type=SalesScript, temperature=0.75, max_tokens=4000)
