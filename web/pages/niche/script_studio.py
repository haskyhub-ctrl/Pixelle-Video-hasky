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

"""Studio kịch bản — AI script writing connected to the video generator."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from datetime import datetime, time, timedelta

import streamlit as st

from web.components.niche_ui import (
    get_service,
    page_header,
    require_llm,
    run,
    send_to_video_generator,
)

page_header("Sáng tạo", "Studio kịch bản",
            "Viết kịch bản có hook, open-loop và CTA từ một chủ đề thắng, rồi gửi thẳng sang trình tạo video "
            "của Pixelle-Video.")

svc = get_service()
ss = st.session_state
if not require_llm():
    st.stop()

STYLES = ["kể chuyện cuốn hút", "review nhanh, hài hước", "giải thích kiến thức dễ hiểu", "top / danh sách",
          "drama, plot twist", "truyền cảm hứng", "tin tức ngắn gọn"]

with st.form("studio"):
    topic = st.text_input("Chủ đề", value=ss.get("studio_topic", ""))
    hook = st.text_input("Hook (tuỳ chọn)", value=ss.get("studio_hook", ""))
    reference = st.text_input("Video tham khảo (tuỳ chọn)", value=ss.get("studio_reference", ""))
    c1, c2, c3 = st.columns(3)
    duration = c1.select_slider("Thời lượng", [30, 45, 60, 90, 180, 300, 600, 900], value=60,
                                format_func=lambda s: f"{s}s" if s < 60 else f"{s // 60} phút")
    style = c2.selectbox("Phong cách", STYLES)
    language = c3.selectbox("Ngôn ngữ", ["vi", "en", "zh", "ja", "ko", "id", "th"])
    submitted = st.form_submit_button("✍️ Viết kịch bản", type="primary")

if submitted and topic.strip():
    ss.studio_topic, ss.studio_hook, ss.studio_reference = topic, hook, reference
    ss.pop("studio_script_text", None)  # let the editor pick up the new script
    ss.pop("studio_prompts", None)
    ss.studio_script = run(svc.write_script(topic.strip(), hook, duration, style, language, reference),
                           "AI đang viết kịch bản...")

sc = ss.get("studio_script")
if not sc:
    st.stop()

st.markdown(f"### {sc.title}")
st.markdown(f"🎣 **Hook:** {sc.hook}")
script_text = st.text_area("Kịch bản (sửa trực tiếp được — mỗi đoạn là một cảnh)", value=sc.script, height=360,
                           key="studio_script_text")
st.markdown(f"📣 **CTA:** {sc.cta}  \n" + " ".join(sc.hashtags))

# --- Prompt ảnh / video (English) for AI tools ---
st.markdown("#### 🎨 Prompt ảnh & video (cho công cụ AI)")
pc1, pc2 = st.columns([3, 1])
ptool = pc1.selectbox("Công cụ đích", ["generic", "Midjourney", "Flux", "Stable Diffusion", "Sora", "Kling", "Runway", "Veo"])
if pc2.button("✨ Sinh prompt", width="stretch"):
    scenes = sc.scene_visuals or [p for p in script_text.split("\n\n") if p.strip()]
    ss.studio_prompts = run(svc.media_prompts(sc.title, scenes, style=style, tool=ptool),
                            "AI đang viết prompt ảnh/video...")
mp = ss.get("studio_prompts")
if mp:
    if mp.style_note:
        st.caption(f"🎭 Giữ đồng nhất: {mp.style_note}")
    it = st.tabs(["🖼️ Prompt ảnh", "🎞️ Prompt video", "🚫 Negative"])
    with it[0]:
        for i, pr in enumerate(mp.image_prompts, 1):
            st.code(f"{i}. {pr}", language=None)
    with it[1]:
        for i, pr in enumerate(mp.video_prompts, 1):
            st.code(f"{i}. {pr}", language=None)
    with it[2]:
        st.code(mp.negative_prompt or "—", language=None)
elif sc.scene_visuals:
    with st.expander("🎨 Gợi ý hình ảnh từng cảnh (từ kịch bản)"):
        for i, vis in enumerate(sc.scene_visuals, 1):
            st.markdown(f"{i}. {vis}")

a, b, c = st.columns(3)
if a.button("🎬 Tạo video từ kịch bản", type="primary", width="stretch"):
    send_to_video_generator(script_text, sc.title, fixed=True)
b.download_button("⬇️ Tải .txt", f"{sc.title}\n\n{sc.hook}\n\n{script_text}\n\n{sc.cta}\n{' '.join(sc.hashtags)}",
                  file_name="kich_ban.txt", width="stretch")
with c.popover("📅 Thêm vào lịch đăng", width="stretch"):
    d = st.date_input("Ngày", datetime.now().date() + timedelta(days=1))
    t = st.time_input("Giờ", time(19, 0))
    if st.button("Lưu"):
        svc.storage.add_calendar(sc.title, datetime.combine(d, t), status="script", topic=ss.get("studio_topic", ""),
                                 script=script_text)
        st.toast("Đã thêm vào Lịch đăng")
