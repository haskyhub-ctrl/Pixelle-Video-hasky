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
Non-YouTube data sources: Google Trends, Reddit and TikHub (TikTok, Douyin,
Xiaohongshu, Kuaishou, Bilibili, Instagram, Threads, X, Weibo, Zhihu, Lemon8).

TikHub responses differ per platform and change over time, so instead of one
hand-written parser per endpoint we walk the JSON and pick out every object
that looks like a post (has an id, some text and an engagement counter).
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

import httpx
from loguru import logger

from pixelle_video.services.niche.models import VideoItem

# ---------------------------------------------------------------------------
# Platform catalogue
# ---------------------------------------------------------------------------

PLATFORMS = {
    "youtube": {"label": "YouTube", "source": "youtube"},
    "tiktok": {"label": "TikTok", "source": "tikhub"},
    "douyin": {"label": "Douyin", "source": "tikhub", "china": True},
    "xiaohongshu": {"label": "Xiaohongshu", "source": "tikhub", "china": True},
    "kuaishou": {"label": "Kuaishou", "source": "tikhub", "china": True},
    "bilibili": {"label": "Bilibili", "source": "tikhub", "china": True},
    "instagram": {"label": "Instagram", "source": "tikhub"},
    "threads": {"label": "Threads", "source": "tikhub"},
    "twitter": {"label": "X / Twitter", "source": "tikhub"},
    "reddit": {"label": "Reddit", "source": "reddit"},
    "weibo": {"label": "Weibo", "source": "tikhub", "china": True},
    "zhihu": {"label": "Zhihu", "source": "tikhub", "china": True},
    "lemon8": {"label": "Lemon8", "source": "tikhub"},
}

CHINA_PLATFORMS = [k for k, v in PLATFORMS.items() if v.get("china")]

# Default TikHub search endpoints (path, keyword param). Overridable in
# config.yaml → niche.tikhub_endpoints because TikHub renames endpoints.
TIKHUB_ENDPOINTS = {
    "tiktok": ("/api/v1/tiktok/web/fetch_search_video", "keyword"),
    "douyin": ("/api/v1/douyin/web/fetch_video_search_result", "keyword"),
    "xiaohongshu": ("/api/v1/xiaohongshu/web/search_notes", "keyword"),
    "kuaishou": ("/api/v1/kuaishou/web/fetch_search_video", "keyword"),
    "bilibili": ("/api/v1/bilibili/web/fetch_general_search", "keyword"),
    "instagram": ("/api/v1/instagram/web_app/fetch_search", "keyword"),
    "threads": ("/api/v1/threads/web/search_top", "query"),
    "twitter": ("/api/v1/twitter/web/fetch_search_timeline", "keyword"),
    "weibo": ("/api/v1/weibo/web/fetch_search", "keyword"),
    "zhihu": ("/api/v1/zhihu/web/fetch_search", "keyword"),
    "lemon8": ("/api/v1/lemon8/app/fetch_search", "keyword"),
}

# ---------------------------------------------------------------------------
# Generic post extraction
# ---------------------------------------------------------------------------

ID_KEYS = ("aweme_id", "note_id", "photo_id", "bvid", "rest_id", "id_str", "video_id", "pk", "code", "id")
TEXT_KEYS = ("desc", "title", "display_title", "full_text", "caption", "content", "text", "description")
VIEW_KEYS = ("play_count", "playCount", "view_count", "viewCount", "play", "video_view_count",
             "views", "read_count", "impression_count")
LIKE_KEYS = ("digg_count", "diggCount", "like_count", "likeCount", "liked_count", "likes",
             "favorite_count", "attitudes_count", "voteup_count", "like")
COMMENT_KEYS = ("comment_count", "commentCount", "comments_count", "reply_count", "review", "comments")
SHARE_KEYS = ("share_count", "shareCount", "reposts_count", "retweet_count", "share", "shared_count")
TIME_KEYS = ("create_time", "createTime", "pubdate", "created_at", "taken_at", "time", "publish_time")
STAT_CONTAINERS = ("stats", "statistics", "stat", "interact_info", "public_metrics", "statsV2",
                   "legacy", "counts")
AUTHOR_KEYS = ("author", "user", "owner", "user_info", "core")
FOLLOWER_KEYS = ("follower_count", "followerCount", "fans", "followers_count", "fans_count")
AUTHOR_NAME_KEYS = ("nickname", "unique_id", "uniqueId", "username", "name", "screen_name", "uname")


def _first(d: dict, keys: tuple, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _to_int(v: Any) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        s = v.strip().lower().replace(",", "")
        mult = 1
        for suffix, m in (("万", 10_000), ("亿", 100_000_000), ("w", 10_000), ("k", 1_000), ("m", 1_000_000)):
            if s.endswith(suffix):
                s, mult = s[: -len(suffix)], m
                break
        try:
            return int(float(s) * mult)
        except ValueError:
            return 0
    return 0


def _to_time(v: Any) -> Optional[datetime]:
    if isinstance(v, (int, float)) and v > 0:
        ts = v / 1000 if v > 1e11 else v
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(v, str):
        if v.isdigit():
            return _to_time(int(v))
        for fmt in ("%a %b %d %H:%M:%S %z %Y",):
            try:
                return datetime.strptime(v, fmt)
            except ValueError:
                pass
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _counts(d: dict, keys: tuple) -> int:
    val = _first(d, keys)
    if val is None:
        for c in STAT_CONTAINERS:
            if isinstance(d.get(c), dict):
                val = _first(d[c], keys)
                if val is not None:
                    break
    if isinstance(val, dict):  # e.g. {"count": 12}
        val = _first(val, ("count", "value"))
    return _to_int(val)


def _looks_like_post(d: dict) -> bool:
    if _first(d, ID_KEYS) is None:
        return False
    has_text = any(isinstance(d.get(k), (str, dict)) for k in TEXT_KEYS)
    has_count = any(k in d for k in VIEW_KEYS + LIKE_KEYS) or any(
        isinstance(d.get(c), dict) for c in STAT_CONTAINERS)
    return has_text and has_count


def iter_posts(node: Any) -> Iterator[dict]:
    if isinstance(node, dict):
        if _looks_like_post(node):
            yield node
            return
        for v in node.values():
            yield from iter_posts(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_posts(v)


def post_to_video(post: dict, platform: str) -> VideoItem:
    text = _first(post, TEXT_KEYS, "")
    if isinstance(text, dict):
        text = _first(text, ("text", "content"), "")
    author = next((post[k] for k in AUTHOR_KEYS if isinstance(post.get(k), dict)), {})
    followers = _to_int(_first(author, FOLLOWER_KEYS))
    if not followers and isinstance(post.get("authorStats"), dict):
        followers = _to_int(_first(post["authorStats"], FOLLOWER_KEYS))
    video = post.get("video") if isinstance(post.get("video"), dict) else {}
    duration = _to_int(post.get("duration") or video.get("duration") or 0)
    if duration > 10_000:  # milliseconds
        duration //= 1000
    pid = str(_first(post, ID_KEYS))
    views = _counts(post, VIEW_KEYS)
    likes = _counts(post, LIKE_KEYS)
    return VideoItem(
        platform=platform,
        video_id=pid,
        title=str(text)[:500],
        url=_first(post, ("share_url", "url", "link", "permalink"), "") or "",
        channel_id=str(_first(author, ("sec_uid", "uid", "id", "mid", "user_id", "pk"), "")),
        channel_title=str(_first(author, AUTHOR_NAME_KEYS, "")),
        published_at=_to_time(_first(post, TIME_KEYS)),
        duration_sec=duration,
        # Platforms without public view counts use likes × 20 as a rough proxy
        views=views or likes * 20,
        likes=likes,
        comments=_counts(post, COMMENT_KEYS),
        shares=_counts(post, SHARE_KEYS),
        channel_subscribers=followers,
    )


# ---------------------------------------------------------------------------
# TikHub
# ---------------------------------------------------------------------------

class TikHubClient:
    BASE = "https://api.tikhub.io"

    def __init__(self, api_key: str, endpoints: Optional[dict] = None, timeout: float = 30.0):
        self.api_key = api_key
        self.endpoints = dict(TIKHUB_ENDPOINTS)
        for k, v in (endpoints or {}).items():
            self.endpoints[k] = tuple(v) if isinstance(v, (list, tuple)) else (v, "keyword")
        self.timeout = timeout
        self.requests = 0

    async def search(self, platform: str, query: str, extra: Optional[dict] = None) -> list[VideoItem]:
        if not self.api_key:
            raise RuntimeError(f"{PLATFORMS[platform]['label']}: chưa cấu hình TikHub API key")
        if platform not in self.endpoints:
            raise RuntimeError(f"TikHub chưa hỗ trợ {platform}")
        path, param = self.endpoints[platform]
        params = {param: query, **(extra or {})}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(self.BASE + path, params=params,
                                    headers={"Authorization": f"Bearer {self.api_key}"})
        self.requests += 1
        if resp.status_code != 200:
            raise RuntimeError(f"TikHub {platform} lỗi {resp.status_code}: {resp.text[:200]}")
        seen: set[str] = set()
        out: list[VideoItem] = []
        for post in iter_posts(resp.json()):
            item = post_to_video(post, platform)
            if item.video_id not in seen:
                seen.add(item.video_id)
                out.append(item)
        return out


# ---------------------------------------------------------------------------
# Reddit (public JSON, no key)
# ---------------------------------------------------------------------------

REDDIT_PERIOD = {"24h": "day", "7d": "week", "30d": "month", "90d": "year", "1y": "year", "all": "all"}


async def reddit_search(query: str, period: str = "30d", limit: int = 50) -> list[VideoItem]:
    params = {"q": query, "sort": "top", "t": REDDIT_PERIOD.get(period, "month"), "limit": min(limit, 100)}
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "pixelle-video-niche/1.0"}) as c:
        resp = await c.get("https://www.reddit.com/search.json", params=params)
    resp.raise_for_status()
    out = []
    for child in resp.json().get("data", {}).get("children", []):
        d = child.get("data", {})
        out.append(VideoItem(
            platform="reddit",
            video_id=d.get("id", ""),
            title=d.get("title", ""),
            description=d.get("selftext", "")[:1000],
            url="https://www.reddit.com" + d.get("permalink", ""),
            channel_id=d.get("subreddit", ""),
            channel_title="r/" + d.get("subreddit", ""),
            published_at=_to_time(d.get("created_utc")),
            # Reddit exposes no views: upvotes × 30 is a common reach heuristic
            views=int(d.get("ups", 0)) * 30,
            likes=int(d.get("ups", 0)),
            comments=int(d.get("num_comments", 0)),
            age_restricted=bool(d.get("over_18")),
            channel_subscribers=int(d.get("subreddit_subscribers", 0) or 0),
        ))
    return out


# ---------------------------------------------------------------------------
# Google Trends
# ---------------------------------------------------------------------------

async def google_trending(geo: str = "VN") -> list[dict]:
    """Daily trending searches from the public Google Trends RSS feed."""
    async with httpx.AsyncClient(timeout=20) as c:
        resp = await c.get("https://trends.google.com/trending/rss", params={"geo": geo})
    resp.raise_for_status()
    ns = {"ht": "https://trends.google.com/trending/rss"}
    root = ET.fromstring(resp.content)
    out = []
    for item in root.iter("item"):
        traffic = item.findtext("ht:approx_traffic", default="", namespaces=ns)
        news = [n.findtext("ht:news_item_title", default="", namespaces=ns)
                for n in item.findall("ht:news_item", ns)]
        out.append({
            "keyword": item.findtext("title", default=""),
            "traffic": traffic,
            "traffic_num": _to_int(traffic.replace("+", "")),
            "published": item.findtext("pubDate", default=""),
            "news": [n for n in news if n][:3],
        })
    return out


def google_trends_interest(keywords: list[str], geo: str = "VN", timeframe: str = "today 3-m") -> dict:
    """
    Average Google Trends interest (0–100) per keyword. Requires the optional
    `pytrends` package; returns {} when unavailable or rate-limited.
    """
    try:
        from pytrends.request import TrendReq  # type: ignore
    except ImportError:
        logger.info("pytrends not installed — skipping Google Trends interest")
        return {}
    try:
        tr = TrendReq(hl="vi-VN", tz=-420)
        out = {}
        for i in range(0, len(keywords), 5):
            batch = keywords[i:i + 5]
            tr.build_payload(batch, timeframe=timeframe, geo=geo)
            df = tr.interest_over_time()
            for k in batch:
                if not df.empty and k in df:
                    out[k] = float(df[k].mean())
        return out
    except Exception as e:
        logger.warning(f"Google Trends failed: {e}")
        return {}
