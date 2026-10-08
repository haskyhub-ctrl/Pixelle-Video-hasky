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
NicheService — orchestrates data sources, scoring formulas, storage and the
LLM for every niche-research feature (web pages and API share this class).
"""

import asyncio
import math
import re
import statistics
import string
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from typing import Optional, Sequence

from loguru import logger
from pydantic import BaseModel, Field

from pixelle_video.services.llm_service import LLMService
from pixelle_video.services.niche import ai, formulas
from pixelle_video.services.niche.models import ChannelItem, SearchFilters, VideoItem
from pixelle_video.services.niche.sources import (
    PLATFORMS,
    TikHubClient,
    google_trending,
    google_trends_interest,
    reddit_search,
)
from pixelle_video.services.niche.storage import NicheStorage
from pixelle_video.services.niche.youtube import YouTubeClient, YouTubeError, youtube_suggestions

ADULT_WORDS = ("18+", "sex", "nude", "porn", "khiêu dâm", "nóng bỏng", "gợi cảm", "onlyfans", "nsfw", "r18")

MARKETS = {
    "VN": ("vi", "Việt Nam"), "US": ("en", "Mỹ"), "GB": ("en", "Anh"), "IN": ("hi", "Ấn Độ"),
    "ID": ("id", "Indonesia"), "TH": ("th", "Thái Lan"), "PH": ("en", "Philippines"),
    "JP": ("ja", "Nhật Bản"), "KR": ("ko", "Hàn Quốc"), "TW": ("zh-Hant", "Đài Loan"),
    "BR": ("pt", "Brazil"), "MX": ("es", "Mexico"), "ES": ("es", "Tây Ban Nha"),
    "DE": ("de", "Đức"), "FR": ("fr", "Pháp"),
}

WEEKDAYS_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d")


def topic_match(query: str, video: VideoItem, threshold: float = 0.6) -> bool:
    """Lexical relevance: ≥60% of query tokens appear in title / tags / description head."""
    q = normalize_text(query).strip()
    haystack = normalize_text(" ".join([video.title, " ".join(video.tags), video.description[:300]]))
    if not q:
        return True
    if " " not in q:  # single word or CJK phrase
        return q in haystack
    tokens = [t for t in re.split(r"\s+", q) if len(t) > 1]
    if not tokens:
        return True
    words = set(re.findall(r"\w+", haystack))
    hits = sum(1 for t in tokens if t in words)
    return hits / len(tokens) >= threshold


def is_adult(video: VideoItem) -> bool:
    if video.age_restricted:
        return True
    text = (video.title + " " + " ".join(video.tags)).lower()
    return any(w in text for w in ADULT_WORDS)


class NicheSearchResult(BaseModel):
    filters: SearchFilters
    videos: list[VideoItem] = Field(default_factory=list)
    hidden_off_topic: list[VideoItem] = Field(default_factory=list)
    hidden_adult: int = 0
    hidden_channel_cap: int = 0
    platform_counts: dict[str, int] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)
    niche: dict = Field(default_factory=dict)
    verdict: str = ""
    trend_interest: Optional[float] = None
    usage: dict = Field(default_factory=dict)


class NicheService:
    def __init__(self, storage: Optional[NicheStorage] = None, llm: Optional[LLMService] = None):
        self._storage = storage
        self.llm = llm or LLMService({})

    # ------------------------------------------------------------ plumbing

    @property
    def cfg(self):
        from pixelle_video.config import config_manager
        return config_manager.config.niche

    @property
    def storage(self) -> NicheStorage:
        if self._storage is None:
            self._storage = NicheStorage(self.cfg.db_path)
        return self._storage

    def youtube(self) -> YouTubeClient:
        return YouTubeClient(self.cfg.youtube_api_key)

    def tikhub(self) -> TikHubClient:
        return TikHubClient(self.cfg.tikhub_api_key, self.cfg.tikhub_endpoints)

    def llm_ready(self) -> bool:
        from pixelle_video.config import config_manager
        return config_manager.config.is_llm_configured()

    def _log_yt(self, yt: YouTubeClient) -> dict:
        self.storage.log_usage("youtube", yt.requests, yt.units_used)
        return {"youtube_units": yt.units_used, "youtube_requests": yt.requests}

    def _log_tikhub(self, th: TikHubClient) -> dict:
        cost = th.requests * self.cfg.tikhub_cost_per_request_usd
        self.storage.log_usage("tikhub", th.requests, 0, cost)
        return {"tikhub_requests": th.requests, "tikhub_cost_usd": cost,
                "tikhub_cost_vnd": round(cost * self.cfg.usd_to_vnd)}

    def estimate_cost(self, filters: SearchFilters, channel_baseline: bool = True) -> dict:
        pages = math.ceil(filters.max_results / 50)
        yt_units = 0
        if "youtube" in filters.platforms:
            n_channels = min(filters.max_results, 30)
            yt_units = pages * 100 + pages + math.ceil(filters.max_results / 50) + (
                2 * n_channels if channel_baseline else 0)
        th_requests = sum(1 for p in filters.platforms if PLATFORMS.get(p, {}).get("source") == "tikhub")
        cost = th_requests * self.cfg.tikhub_cost_per_request_usd
        requests = (pages * 2 + 1 + (2 * min(filters.max_results, 30) if channel_baseline else 0)
                    if "youtube" in filters.platforms else 0) + th_requests + (1 if "reddit" in filters.platforms else 0)
        return {"youtube_units": yt_units, "requests": requests, "tikhub_requests": th_requests,
                "cost_usd": cost, "cost_vnd": round(cost * self.cfg.usd_to_vnd)}

    # ------------------------------------------------------- enrichment

    async def enrich_youtube(self, yt: YouTubeClient, videos: list[VideoItem],
                             baseline_channels: int = 30, baseline_uploads: int = 15) -> dict[str, ChannelItem]:
        """Attach subscriber counts and channel median views (the outlier baseline)."""
        channels = {c.channel_id: c for c in await yt.channels([v.channel_id for v in videos])}
        for v in videos:
            if v.channel_id in channels:
                v.channel_subscribers = channels[v.channel_id].subscribers

        # Baseline only for the channels of the most viewed results to bound quota
        ranked = sorted(videos, key=lambda v: v.views, reverse=True)
        targets = list(dict.fromkeys(v.channel_id for v in ranked if v.channel_id in channels))[:baseline_channels]
        sem = asyncio.Semaphore(6)

        async def fetch(cid: str):
            async with sem:
                try:
                    return cid, await yt.channel_uploads(channels[cid], baseline_uploads)
                except Exception as e:
                    logger.warning(f"Baseline failed for {cid}: {e}")
                    return cid, []

        uploads = dict(await asyncio.gather(*(fetch(cid) for cid in targets)))
        for v in videos:
            ups = uploads.get(v.channel_id)
            if ups:
                v.channel_median_views = formulas.channel_median_views(ups, exclude_id=v.video_id)
        return channels

    # ------------------------------------------------------------ search

    async def _fetch_platform(self, platform: str, f: SearchFilters, yt: Optional[YouTubeClient],
                              th: TikHubClient) -> list[VideoItem]:
        source = PLATFORMS.get(platform, {}).get("source")
        if source == "youtube":
            ids, _total = await yt.search_video_ids(
                f.query, max_results=f.max_results, order=f.order, period=f.period,
                duration=f.duration, region=f.region, language=f.language, safe=f.hide_adult)
            videos = await yt.videos(ids)
            await self.enrich_youtube(yt, videos)
            return videos
        if source == "reddit":
            return await reddit_search(f.query, f.period, f.max_results)
        if source == "tikhub":
            return await th.search(platform, f.query)
        raise ValueError(f"Nền tảng không hỗ trợ: {platform}")

    async def search(self, f: SearchFilters, with_trends: bool = False) -> NicheSearchResult:
        result = NicheSearchResult(filters=f)
        platforms = list(f.platforms)
        yt = None
        if "youtube" in platforms:
            try:
                yt = self.youtube()
            except YouTubeError as e:
                result.errors["youtube"] = str(e)
                platforms.remove("youtube")
        th = self.tikhub()

        async def run(p):
            try:
                return p, await self._fetch_platform(p, f, yt, th), None
            except Exception as e:
                logger.warning(f"Niche search failed on {p}: {e}")
                return p, [], str(e)

        all_videos: list[VideoItem] = []
        for p, vids, err in await asyncio.gather(*(run(p) for p in platforms)):
            if err:
                result.errors[p] = err
            all_videos += vids

        # Post filters ---------------------------------------------------
        kept: list[VideoItem] = []
        for v in all_videos:
            if f.duration == "short" and v.duration_sec and not v.is_short:
                continue
            if f.duration == "long" and v.duration_sec and v.is_short:
                continue
            if f.hide_adult and is_adult(v):
                result.hidden_adult += 1
                continue
            if f.strict_topic and v.platform not in ("douyin", "xiaohongshu", "kuaishou", "bilibili",
                                                     "weibo", "zhihu") and not topic_match(f.query, v):
                result.hidden_off_topic.append(v)
                continue
            kept.append(v)

        scored = formulas.score_videos(kept)
        if f.max_per_channel > 0:
            per_channel: Counter = Counter()
            capped = []
            for v in scored:
                key = (v.platform, v.channel_id or v.channel_title)
                if key[1] and per_channel[key] >= f.max_per_channel:
                    result.hidden_channel_cap += 1
                    continue
                per_channel[key] += 1
                capped.append(v)
            scored = capped
        formulas.score_videos(result.hidden_off_topic)

        result.videos = scored
        result.platform_counts = dict(Counter(v.platform for v in scored))
        if with_trends:
            interest = await asyncio.to_thread(google_trends_interest, [f.query], f.region)
            result.trend_interest = interest.get(f.query)
        result.niche = formulas.niche_score(scored, result.trend_interest)
        result.verdict = formulas.niche_verdict(result.niche["niche_score"])
        if yt:
            result.usage.update(self._log_yt(yt))
        result.usage.update(self._log_tikhub(th))
        return result

    def save_niche(self, result: NicheSearchResult, insights: Optional[dict] = None) -> int:
        top = [{"title": v.title, "url": v.url, "views": v.views, "viral_score": v.scores.get("viral_score")}
               for v in result.videos[:10]]
        return self.storage.save_niche(result.filters.query, result.filters.platforms,
                                       result.niche.get("niche_score", 0),
                                       {"niche": result.niche, "verdict": result.verdict, "top": top,
                                        "insights": insights or {}})

    # ------------------------------------------------------- keywords

    async def keyword_suggestions(self, seed: str, language: str = "vi", region: str = "VN",
                                  deep: bool = True) -> list[str]:
        prefixes = [""]
        if deep:
            prefixes += list(string.ascii_lowercase)
        question_words = {"vi": ["cách", "tại sao", "là gì", "có nên", "top"],
                          "en": ["how to", "why", "what is", "best", "top"]}.get(language, [])
        queries = [f"{seed} {p}".strip() for p in prefixes] + [f"{q} {seed}" for q in question_words]
        sem = asyncio.Semaphore(8)

        async def one(q):
            async with sem:
                return await youtube_suggestions(q, language, region)

        results = await asyncio.gather(*(one(q) for q in queries))
        seen = dict.fromkeys(s.strip() for batch in results for s in batch if s.strip())
        return list(seen)

    async def keyword_research(self, seed: str, region: str = "VN", language: str = "vi",
                               analyze_top: int = 5, deep: bool = True,
                               with_trends: bool = False) -> dict:
        suggestions = await self.keyword_suggestions(seed, language, region, deep)
        rows = [{"keyword": k, "type": formulas.classify_keyword(k)} for k in suggestions]
        to_analyze = [seed] + [k for k in suggestions if k != seed][: max(analyze_top - 1, 0)]
        trends = await asyncio.to_thread(google_trends_interest, to_analyze, region) if with_trends else {}
        analyzed = []
        yt = self.youtube() if analyze_top > 0 else None
        for kw in to_analyze if yt else []:
            try:
                ids, total = await yt.search_video_ids(kw, max_results=20, period="all",
                                                        region=region, language=language)
                videos = await yt.videos(ids)
                await self.enrich_youtube(yt, videos, baseline_channels=0)
                med_views = formulas.median(v.views for v in videos)
                med_subs = formulas.median(v.channel_subscribers for v in videos if v.channel_subscribers)
                ks = formulas.keyword_score(med_views, med_subs, total, trends.get(kw))
                analyzed.append({"keyword": kw, "type": formulas.classify_keyword(kw),
                                 "total_results": total, "median_views": round(med_views),
                                 "median_subs": round(med_subs), "trend_interest": trends.get(kw), **ks,
                                 "top_titles": [v.title for v in sorted(videos, key=lambda x: -x.views)[:5]]})
            except YouTubeError as e:
                logger.warning(f"Keyword analysis failed for {kw}: {e}")
                analyzed.append({"keyword": kw, "error": str(e)})
                break
        usage = self._log_yt(yt) if yt else {}
        analyzed.sort(key=lambda r: r.get("keyword_score", -1), reverse=True)
        return {"seed": seed, "suggestions": rows, "analyzed": analyzed, "usage": usage}

    # -------------------------------------------------------- channels

    async def channel_analysis(self, ref: str, max_videos: int = 50, track: bool = True,
                               is_mine: bool = False) -> dict:
        yt = self.youtube()
        channel = await yt.resolve_channel(ref)
        videos = await yt.channel_uploads(channel, max_videos)
        for v in videos:
            v.channel_median_views = formulas.channel_median_views(videos, exclude_id=v.video_id)
        scored = formulas.score_videos(videos)
        stats = self._channel_stats(channel, scored)
        if track:
            self.storage.track_channel(channel.channel_id, channel.title, is_mine=is_mine,
                                       data={"url": channel.url, "thumbnail": channel.thumbnail})
            self.storage.add_snapshot(channel.channel_id, channel.subscribers, channel.total_views,
                                      channel.video_count)
        snaps = self.storage.snapshots(channel.channel_id)
        growth = formulas.sub_growth_rate([(s["ts"], s["subscribers"]) for s in snaps])
        breakout = formulas.breakout_channel_score(channel, scored[:15] if len(scored) > 15 else scored,
                                                   sub_growth_per_day=growth)
        by_outlier = sorted(scored, key=lambda v: v.scores.get("outlier", 0), reverse=True)
        return {
            "channel": channel,
            "videos": scored,
            "stats": stats,
            "breakout": breakout,
            "sub_growth_per_day": growth,
            "snapshots": snaps,
            "top": by_outlier[:10],
            "flops": by_outlier[::-1][:10],
            "posting_slots": formulas.best_posting_slots(scored),
            "usage": self._log_yt(yt),
        }

    @staticmethod
    def _channel_stats(channel: ChannelItem, videos: Sequence[VideoItem]) -> dict:
        views = [v.views for v in videos]
        gaps = formulas.upload_gaps_days(videos)
        shorts = [v for v in videos if v.is_short]
        weekdays = Counter(v.published_at.weekday() for v in videos if v.published_at)
        last = max((v.published_at for v in videos if v.published_at), default=None)
        return {
            "subscribers": channel.subscribers,
            "total_views": channel.total_views,
            "video_count": channel.video_count,
            "sample_size": len(videos),
            "median_views": round(formulas.median(views)),
            "mean_views": round(statistics.mean(views)) if views else 0,
            "views_per_sub_median": round(formulas.median(views) / max(channel.subscribers, 100), 3),
            "uploads_per_week": round(7 / statistics.mean(gaps), 2) if gaps and statistics.mean(gaps) > 0 else 0,
            "upload_gap_cv": round(statistics.pstdev(gaps) / statistics.mean(gaps), 2)
            if len(gaps) > 1 and statistics.mean(gaps) > 0 else 0,
            "days_since_last_upload": round((datetime.now(timezone.utc) - last).total_seconds() / 86400, 1)
            if last else None,
            "shorts_share": round(len(shorts) / len(videos), 2) if videos else 0,
            "avg_duration_sec": round(statistics.mean(v.duration_sec for v in videos)) if videos else 0,
            "avg_engagement": round(statistics.mean(v.scores.get("engagement", 0) for v in videos), 4)
            if videos else 0,
            "avg_title_length": round(statistics.mean(len(v.title) for v in videos)) if videos else 0,
            "avg_description_length": round(statistics.mean(len(v.description) for v in videos)) if videos else 0,
            "share_without_tags": round(sum(1 for v in videos if not v.tags) / len(videos), 2) if videos else 0,
            "top_weekday": WEEKDAYS_VI[weekdays.most_common(1)[0][0]] if weekdays else "",
            "hit_rate_2x": round(sum(1 for v in videos if v.scores.get("outlier", 0) >= 2) / len(videos), 2)
            if videos else 0,
            "flop_rate": round(sum(1 for v in videos if v.scores.get("outlier", 0) < 0.3) / len(videos), 2)
            if videos else 0,
        }

    async def channel_ai_report(self, analysis: dict) -> ai.ChannelReport:
        return await ai.channel_report(self.llm, analysis["channel"].title, analysis["stats"],
                                       analysis["top"], analysis["flops"])

    async def monetization(self, ref: str, niche: str = "general", country: str = "",
                           max_videos: int = 200) -> dict:
        yt = self.youtube()
        channel = await yt.resolve_channel(ref)
        videos = await yt.channel_uploads(channel, max_videos)
        country = country or channel.country or self.cfg.default_region
        check = formulas.monetization_check(channel, videos, self.cfg.avd_ratio, country, niche)
        check["usd_to_vnd"] = self.cfg.usd_to_vnd
        return {"channel": channel, "videos": len(videos), "country": country, "check": check,
                "usage": self._log_yt(yt)}

    async def hunt_channels(self, query: str, period: str = "30d", max_subs: int = 100_000,
                            region: str = "VN", language: str = "vi", duration: str = "any",
                            pool: int = 50) -> dict:
        """Find small channels whose recent uploads punch far above their size."""
        yt = self.youtube()
        ids, _ = await yt.search_video_ids(query, max_results=pool, order="viewCount", period=period,
                                           region=region, language=language, duration=duration)
        hits = await yt.videos(ids)
        channels = {c.channel_id: c for c in await yt.channels([v.channel_id for v in hits])}
        candidates = [c for c in channels.values() if 0 < c.subscribers <= max_subs]
        sem = asyncio.Semaphore(6)

        async def evaluate(c: ChannelItem):
            async with sem:
                try:
                    recent = await yt.channel_uploads(c, 15)
                except Exception as e:
                    return None, str(e)
            for v in recent:
                v.channel_median_views = formulas.channel_median_views(recent, v.video_id)
            formulas.score_videos(recent)
            snaps = self.storage.snapshots(c.channel_id)
            growth = formulas.sub_growth_rate([(s["ts"], s["subscribers"]) for s in snaps])
            self.storage.add_snapshot(c.channel_id, c.subscribers, c.total_views, c.video_count)
            score = formulas.breakout_channel_score(c, recent, sub_growth_per_day=growth)
            best = max(recent, key=lambda v: v.scores.get("outlier", 0), default=None)
            hit = next((v for v in hits if v.channel_id == c.channel_id), None)
            return {"channel": c, **score, "sub_growth_per_day": growth,
                    "best_video": best, "trigger_video": hit}, None

        rows = [r for r, _ in await asyncio.gather(*(evaluate(c) for c in candidates)) if r]
        rows.sort(key=lambda r: r["breakout_score"], reverse=True)
        return {"query": query, "channels": rows, "scanned_videos": len(hits),
                "usage": self._log_yt(yt)}

    # ------------------------------------------------- multi-market

    async def multi_market(self, keyword: str, regions: Sequence[str], period: str = "30d",
                           translate: bool = True, max_results: int = 25) -> dict:
        langs = {r: MARKETS.get(r, ("en", r))[0] for r in regions}
        translated = {}
        if translate and self.llm_ready():
            try:
                translated = await ai.translate_keyword(self.llm, keyword, sorted(set(langs.values())))
            except Exception as e:
                logger.warning(f"Keyword translation failed: {e}")
        yt = self.youtube()
        rows = []
        for r in regions:
            lang = langs[r]
            kw = translated.get(lang, keyword)
            try:
                ids, total = await yt.search_video_ids(kw, max_results=max_results, period=period,
                                                        region=r, language=lang)
                videos = await yt.videos(ids)
                await self.enrich_youtube(yt, videos, baseline_channels=10, baseline_uploads=10)
                scored = formulas.score_videos(videos)
                ns = formulas.niche_score(scored)
                rpm = formulas.RPM_BY_COUNTRY.get(r, formulas.RPM_BY_COUNTRY["OTHER"])
                rows.append({"region": r, "market": MARKETS.get(r, ("", r))[1], "language": lang,
                             "keyword": kw, "total_results": total, **ns, "rpm_usd": rpm,
                             # Revenue-weighted opportunity: niche score × relative RPM
                             "market_score": round(ns["niche_score"] * (0.6 + 0.4 * min(rpm / 5, 1)), 1),
                             "top": scored[:5]})
            except YouTubeError as e:
                rows.append({"region": r, "keyword": kw, "error": str(e)})
                break
        rows.sort(key=lambda x: x.get("market_score", -1), reverse=True)
        return {"keyword": keyword, "markets": rows, "usage": self._log_yt(yt)}

    # ---------------------------------------------------------- trends

    async def trends(self, region: str = "VN", category_id: str = "",
                     include: Sequence[str] = ("youtube", "google", "reddit")) -> dict:
        out: dict = {"errors": {}}
        if "youtube" in include:
            try:
                yt = self.youtube()
                vids = await yt.most_popular(region, category_id)
                await self.enrich_youtube(yt, vids, baseline_channels=0)
                out["youtube"] = formulas.score_videos(vids)
                out["usage"] = self._log_yt(yt)
            except Exception as e:
                out["errors"]["youtube"] = str(e)
        if "google" in include:
            try:
                out["google"] = await google_trending(region)
            except Exception as e:
                out["errors"]["google"] = str(e)
        if "reddit" in include:
            try:
                out["reddit"] = await self._reddit_popular()
            except Exception as e:
                out["errors"]["reddit"] = str(e)
        tikhub_platforms = [p for p in include if PLATFORMS.get(p, {}).get("source") == "tikhub"]
        if tikhub_platforms:
            th = self.tikhub()
            for p in tikhub_platforms:
                try:
                    out[p] = formulas.score_videos(await th.search(p, self._trend_seed(region)))
                except Exception as e:
                    out["errors"][p] = str(e)
            out["tikhub_usage"] = self._log_tikhub(th)
        # Cross-platform keywords: words that appear on ≥ 2 sources
        out["cross_platform"] = self._cross_platform_terms(out)
        return out

    @staticmethod
    def _trend_seed(region: str) -> str:
        return {"VN": "xu hướng", "CN": "热门", "TW": "熱門", "JP": "トレンド", "KR": "트렌드"}.get(region, "trending")

    async def _reddit_popular(self) -> list[VideoItem]:
        import httpx
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "pixelle-video-niche/1.0"}) as c:
            resp = await c.get("https://www.reddit.com/r/popular/top.json", params={"t": "day", "limit": 50})
        resp.raise_for_status()
        from pixelle_video.services.niche.sources import _to_time
        out = []
        for child in resp.json().get("data", {}).get("children", []):
            d = child.get("data", {})
            out.append(VideoItem(platform="reddit", video_id=d.get("id", ""), title=d.get("title", ""),
                                 url="https://www.reddit.com" + d.get("permalink", ""),
                                 channel_title="r/" + d.get("subreddit", ""),
                                 published_at=_to_time(d.get("created_utc")),
                                 views=int(d.get("ups", 0)) * 30, likes=int(d.get("ups", 0)),
                                 comments=int(d.get("num_comments", 0)),
                                 age_restricted=bool(d.get("over_18"))))
        return formulas.score_videos([v for v in out if not v.age_restricted])

    @staticmethod
    def _cross_platform_terms(data: dict, top_n: int = 30) -> list[dict]:
        stop = set("the a an of and or to in on for with is are la va cua cho nhung cac mot voi khi "
                   "trong tren duoc co khong nay do thi ma de".split())
        sources: dict[str, set] = {}
        for key, items in data.items():
            if not isinstance(items, list):
                continue
            for it in items:
                title = it.title if isinstance(it, VideoItem) else it.get("keyword", "")
                for w in set(re.findall(r"\w{3,}", normalize_text(title))):
                    if w not in stop and not w.isdigit():
                        sources.setdefault(w, set()).add(key)
        rows = [{"term": w, "sources": sorted(s), "n_sources": len(s)} for w, s in sources.items() if len(s) >= 2]
        return sorted(rows, key=lambda r: r["n_sources"], reverse=True)[:top_n]

    # -------------------------------------------------------- creation

    async def winning_topics(self, query: str, filters: Optional[SearchFilters] = None,
                             count: int = 15) -> dict:
        f = filters or SearchFilters(query=query, region=self.cfg.default_region,
                                     language=self.cfg.default_language)
        res = await self.search(f)
        winners = [v for v in res.videos if v.scores.get("viral_score", 0) >= 55] or res.videos[:20]
        topics = await ai.winning_topics(self.llm, query, winners, count, f.language)
        return {"search": res, "winners": winners, "topics": topics}

    async def write_script(self, topic: str, hook: str = "", duration_sec: int = 60,
                           style: str = "kể chuyện cuốn hút", language: str = "vi",
                           reference: str = "") -> ai.VideoScript:
        return await ai.write_script(self.llm, topic, hook, duration_sec, style, language, reference)

    async def media_prompts(self, title: str, scenes: Sequence[str], style: str = "cinematic",
                            tool: str = "generic") -> ai.MediaPrompts:
        return await ai.media_prompts(self.llm, title, list(scenes), style, tool)

    async def teardown(self, video_ref: str, language: str = "vi") -> dict:
        """Mổ băng đối thủ: fetch a video + its top comments, then AI framework + 3 remakes."""
        from pixelle_video.services.niche.youtube import parse_video_ref
        yt = self.youtube()
        vids = await yt.videos([parse_video_ref(video_ref)])
        if not vids:
            raise YouTubeError("Không tìm thấy video")
        video = vids[0]
        if video.channel_id:
            chans = await yt.channels([video.channel_id])
            if chans:
                video.channel_subscribers = chans[0].subscribers
                ups = await yt.channel_uploads(chans[0], 15)
                video.channel_median_views = formulas.channel_median_views(ups, video.video_id)
        video.scores = formulas.viral_score(video)
        result = await ai.video_teardown(self.llm, video, [], language) if self.llm_ready() else None
        return {"video": video, "teardown": result, "usage": self._log_yt(yt)}

    def posting_heatmap(self, videos: Sequence[VideoItem]) -> dict:
        return formulas.posting_heatmap(videos)

    # ----------------------------------------------------- affiliate

    def product_provider(self):
        from pixelle_video.services.niche import products
        return products.get_provider(self.cfg.tikhub_api_key, self.cfg.tikhub_endpoints)

    async def hunt_products(self, keyword: str = "", region: str = "VN", limit: int = 40) -> dict:
        from pixelle_video.services.niche import products
        prov = self.product_provider()
        items = products.fill_derived(await prov.search(keyword, region, limit))
        scored = formulas.score_products(items)
        th_requests = getattr(prov, "requests", 0)
        if th_requests:
            self.storage.log_usage("tikhub", th_requests, 0, th_requests * self.cfg.tikhub_cost_per_request_usd)
        return {"products": scored, "source": prov.name, "is_sample": not prov.available or prov.name == "sample",
                "region": region}

    async def sales_script(self, product: str, pain_points: str = "", benefits: str = "",
                           duration_sec: int = 45, language: str = "vi") -> ai.SalesScript:
        return await ai.sales_script(self.llm, product, pain_points, benefits, duration_sec, language)

    # ----------------------------------------------------- optimization

    def doctor_checks(self, stats: dict, competitor_stats: Sequence[dict] = (),
                      videos: Sequence[VideoItem] = ()) -> list[dict]:
        """Rule-based diagnostics; each finding carries the metric that triggered it."""
        out = []

        def add(sev, problem, metric, fix):
            out.append({"severity": sev, "problem": problem, "metric": metric, "fix": fix})

        dsl = stats.get("days_since_last_upload")
        if dsl is not None and dsl > 14:
            add("high", "Kênh ngừng đăng quá lâu", f"{dsl} ngày chưa có video mới",
                "Đăng lại tối thiểu 2 video/tuần trong 4 tuần để thuật toán test lại kênh")
        if stats.get("uploads_per_week", 0) < 1:
            add("medium", "Tần suất đăng thấp", f"{stats.get('uploads_per_week')} video/tuần",
                "Tăng lên ≥ 2 video/tuần hoặc bổ sung Shorts cắt từ video dài")
        if stats.get("upload_gap_cv", 0) > 1:
            add("medium", "Lịch đăng không đều", f"Hệ số biến thiên khoảng cách đăng = {stats['upload_gap_cv']}",
                "Cố định ngày/giờ đăng (xem trang Lịch đăng)")
        if stats.get("flop_rate", 0) > 0.3:
            add("high", "Nhiều video flop", f"{int(stats['flop_rate'] * 100)}% video < 0.3× view trung vị",
                "Dừng các chủ đề flop, nhân bản format của video có outlier ≥ 2×")
        if stats.get("views_per_sub_median", 0) < 0.05 and stats.get("subscribers", 0) > 5000:
            add("high", "Người đăng ký không còn xem", f"view trung vị / sub = {stats['views_per_sub_median']}",
                "Sub cũ không còn khớp nội dung: làm lại định vị hoặc tập trung vào traffic từ Browse/Shorts")
        if stats.get("avg_engagement", 0) < 0.02:
            add("medium", "Tương tác thấp", f"ER trung bình {stats.get('avg_engagement', 0):.2%}",
                "Thêm câu hỏi kêu gọi bình luận, ghim bình luận, trả lời bình luận trong 1 giờ đầu")
        if not 40 <= stats.get("avg_title_length", 50) <= 70:
            add("low", "Độ dài tiêu đề chưa tối ưu", f"Trung bình {stats.get('avg_title_length')} ký tự",
                "Giữ tiêu đề 40–70 ký tự, từ khoá ở đầu")
        if stats.get("avg_description_length", 300) < 200:
            add("low", "Mô tả quá ngắn", f"Trung bình {stats.get('avg_description_length')} ký tự",
                "Viết mô tả ≥ 200 ký tự, có từ khoá ở 2 dòng đầu và chapters")
        if stats.get("share_without_tags", 0) > 0.5:
            add("low", "Thiếu tags", f"{int(stats['share_without_tags'] * 100)}% video không có tags",
                "Thêm 5–15 tags từ rộng tới hẹp (dùng trang Tối ưu SEO)")
        if len(videos) >= 20:
            ordered = sorted((v for v in videos if v.published_at), key=lambda v: v.published_at, reverse=True)
            recent = formulas.median(v.views for v in ordered[:10])
            before = formulas.median(v.views for v in ordered[10:20])
            if before and recent / before < 0.7:
                add("high", "View đang giảm", f"10 video gần nhất = {recent / before:.0%} so với 10 video trước",
                    "Xem lại chủ đề/thumbnail của 10 video gần nhất so với giai đoạn trước")
        if competitor_stats:
            comp_med = formulas.median(c.get("median_views", 0) for c in competitor_stats)
            comp_freq = formulas.median(c.get("uploads_per_week", 0) for c in competitor_stats)
            if comp_med and stats.get("median_views", 0) < 0.5 * comp_med:
                add("medium", "Thua đối thủ về view", f"view trung vị {stats.get('median_views'):,} vs đối thủ {comp_med:,.0f}",
                    "Phân tích video thắng của đối thủ ở trang Phân tích kênh / Chủ đề thắng")
            if comp_freq and stats.get("uploads_per_week", 0) < 0.5 * comp_freq:
                add("medium", "Đăng ít hơn đối thủ", f"{stats.get('uploads_per_week')} vs {comp_freq} video/tuần",
                    "Tăng tần suất hoặc dùng Studio kịch bản để sản xuất nhanh hơn")
        return out

    @staticmethod
    def health_score(checks: Sequence[dict]) -> int:
        penalty = {"high": 20, "medium": 10, "low": 4}
        return max(0, 100 - sum(penalty.get(c["severity"], 0) for c in checks))

    async def channel_doctor(self, ref: str, competitors: Sequence[str] = (), use_ai: bool = True) -> dict:
        analysis = await self.channel_analysis(ref, 50)
        comp_stats = []
        for c in competitors:
            if not c.strip():
                continue
            try:
                ca = await self.channel_analysis(c, 30)
                comp_stats.append({"title": ca["channel"].title, **ca["stats"]})
            except Exception as e:
                logger.warning(f"Competitor {c} failed: {e}")
        checks = self.doctor_checks(analysis["stats"], comp_stats, analysis["videos"])
        report = None
        if use_ai and self.llm_ready():
            report = await ai.channel_doctor(self.llm, analysis["channel"].title,
                                             {"stats": analysis["stats"], "auto_checks": checks,
                                              "competitors": comp_stats}, analysis["top"], analysis["flops"])
        return {**analysis, "checks": checks, "health_score": self.health_score(checks),
                "competitors": comp_stats, "report": report}

    async def seo(self, video_ref: str = "", title: str = "", description: str = "",
                  tags: Sequence[str] = (), keyword: str = "", use_ai: bool = True,
                  competitor_search: bool = True) -> dict:
        video = None
        yt = None
        if video_ref:
            from pixelle_video.services.niche.youtube import parse_video_ref
            yt = self.youtube()
            vids = await yt.videos([parse_video_ref(video_ref)])
            if not vids:
                raise YouTubeError("Không tìm thấy video")
            video = vids[0]
            title, description, tags = video.title, video.description, video.tags
        audit = formulas.seo_audit(title, description, list(tags), keyword)
        competitor_titles = []
        if keyword and competitor_search and self.cfg.youtube_api_key:
            yt = yt or self.youtube()
            try:
                ids, _ = await yt.search_video_ids(keyword, max_results=15, period="1y",
                                                   order="viewCount", region=self.cfg.default_region,
                                                   language=self.cfg.default_language)
                competitor_titles = [v.title for v in await yt.videos(ids)]
            except YouTubeError as e:
                logger.warning(f"Competitor titles failed: {e}")
        suggestion = None
        if use_ai and self.llm_ready():
            suggestion = await ai.seo_rewrite(self.llm, title, description, list(tags), keyword, competitor_titles)
        return {"video": video, "audit": audit, "competitor_titles": competitor_titles,
                "suggestion": suggestion, "usage": self._log_yt(yt) if yt else {}}

    # -------------------------------------------------------- overview

    def overview(self) -> dict:
        s = self.storage
        cal = s.list_calendar()
        now = datetime.now(timezone.utc).isoformat()
        return {
            "saved_niches": s.list_niches()[:10],
            "tracked_channels": s.list_channels(),
            "my_channels": s.list_channels(mine_only=True),
            "upcoming": [c for c in cal if c["scheduled_at"] >= now[:10]][:10],
            "calendar_total": len(cal),
            "usage_today": s.usage_today(),
            "youtube_ready": bool(self.cfg.youtube_api_key),
            "tikhub_ready": bool(self.cfg.tikhub_api_key),
            "llm_ready": self.llm_ready(),
        }
