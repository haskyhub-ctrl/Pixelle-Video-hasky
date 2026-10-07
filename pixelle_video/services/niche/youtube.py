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
YouTube Data API v3 client (async, httpx) with quota accounting.

Quota costs (default daily quota is 10,000 units):
    search.list = 100, videos.list / channels.list / playlistItems.list = 1
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx
from loguru import logger

from pixelle_video.services.niche.models import ChannelItem, VideoItem

API_BASE = "https://www.googleapis.com/youtube/v3"
SUGGEST_URL = "https://suggestqueries.google.com/complete/search"

QUOTA_COST = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1, "videoCategories": 1}

PERIOD_DELTAS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "1y": timedelta(days=365),
}

_DURATION_RE = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


class YouTubeError(RuntimeError):
    pass


def parse_iso_duration(value: str) -> int:
    """'PT1H2M3S' -> 3723 seconds."""
    m = _DURATION_RE.fullmatch(value or "")
    if not m:
        return 0
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_channel_ref(text: str) -> dict:
    """
    Accepts a channel id, @handle, channel URL or video URL and returns one of
    {"id": ...}, {"handle": ...}, {"video_id": ...}, {"query": ...}.
    """
    text = text.strip()
    if re.fullmatch(r"UC[\w-]{22}", text):
        return {"id": text}
    if text.startswith("@"):
        return {"handle": text}
    if "youtu" in text:
        url = urlparse(text if "://" in text else "https://" + text)
        path = url.path.rstrip("/")
        if url.netloc.endswith("youtu.be"):
            return {"video_id": path.lstrip("/")}
        if path.startswith("/channel/"):
            return {"id": path.split("/")[2]}
        if path.startswith("/@"):
            return {"handle": path.split("/")[1]}
        if path.startswith("/shorts/"):
            return {"video_id": path.split("/")[2]}
        qs = parse_qs(url.query)
        if "v" in qs:
            return {"video_id": qs["v"][0]}
        if path.startswith(("/c/", "/user/")):
            return {"query": path.split("/")[2]}
    return {"query": text}


def parse_video_ref(text: str) -> str:
    ref = parse_channel_ref(text)
    if "video_id" in ref:
        return ref["video_id"]
    text = text.strip()
    if re.fullmatch(r"[\w-]{11}", text):
        return text
    raise YouTubeError(f"Không nhận ra link video: {text}")


class YouTubeClient:
    def __init__(self, api_key: str, timeout: float = 20.0):
        if not api_key:
            raise YouTubeError("Chưa cấu hình YouTube API key (Cài đặt nghiên cứu → YouTube API key)")
        self.api_key = api_key
        self.timeout = timeout
        self.units_used = 0
        self.requests = 0

    async def _get(self, endpoint: str, params: dict) -> dict:
        params = {k: v for k, v in params.items() if v not in (None, "")}
        params["key"] = self.api_key
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{API_BASE}/{endpoint}", params=params)
        self.units_used += QUOTA_COST.get(endpoint, 1)
        self.requests += 1
        if resp.status_code != 200:
            try:
                err = resp.json()["error"]
                reason = err.get("errors", [{}])[0].get("reason", "")
                msg = f"{err.get('message', resp.text)} ({reason})"
            except Exception:
                msg = resp.text[:300]
            raise YouTubeError(f"YouTube API {endpoint} lỗi {resp.status_code}: {msg}")
        return resp.json()

    # ------------------------------------------------------------------ search

    async def search_video_ids(
        self,
        query: str,
        max_results: int = 50,
        order: str = "relevance",
        period: str = "30d",
        duration: str = "any",
        region: str = "",
        language: str = "",
        safe: bool = True,
    ) -> tuple[list[str], int]:
        """Returns (video_ids, total_results_estimate)."""
        published_after = None
        if period in PERIOD_DELTAS:
            published_after = (datetime.now(timezone.utc) - PERIOD_DELTAS[period]).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
        # API "short" = < 4 min; we post-filter to the ≤ 3 min Shorts definition
        video_duration = {"short": "short", "long": None}.get(duration)
        ids: list[str] = []
        total = 0
        page_token = None
        while len(ids) < max_results:
            data = await self._get("search", {
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": min(50, max_results - len(ids)),
                "order": order,
                "publishedAfter": published_after,
                "regionCode": region,
                "relevanceLanguage": language,
                "videoDuration": video_duration,
                "safeSearch": "strict" if safe else "none",
                "pageToken": page_token,
            })
            total = data.get("pageInfo", {}).get("totalResults", total)
            ids += [it["id"]["videoId"] for it in data.get("items", []) if it.get("id", {}).get("videoId")]
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return ids, total

    async def search_channels(self, query: str, max_results: int = 25, region: str = "",
                              language: str = "") -> list[str]:
        data = await self._get("search", {
            "part": "snippet", "q": query, "type": "channel",
            "maxResults": min(max_results, 50), "regionCode": region, "relevanceLanguage": language,
        })
        return [it["id"]["channelId"] for it in data.get("items", []) if it.get("id", {}).get("channelId")]

    # ------------------------------------------------------------------ videos

    async def videos(self, ids: list[str]) -> list[VideoItem]:
        out: list[VideoItem] = []
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            if not chunk:
                continue
            data = await self._get("videos", {
                "part": "snippet,statistics,contentDetails,status",
                "id": ",".join(chunk),
            })
            out += [self._to_video(it) for it in data.get("items", [])]
        return out

    async def most_popular(self, region: str = "VN", category_id: str = "",
                           max_results: int = 50) -> list[VideoItem]:
        data = await self._get("videos", {
            "part": "snippet,statistics,contentDetails,status",
            "chart": "mostPopular",
            "regionCode": region,
            "videoCategoryId": category_id,
            "maxResults": min(max_results, 50),
        })
        return [self._to_video(it) for it in data.get("items", [])]

    @staticmethod
    def _to_video(it: dict) -> VideoItem:
        sn = it.get("snippet", {})
        st = it.get("statistics", {})
        cd = it.get("contentDetails", {})
        thumbs = sn.get("thumbnails", {})
        thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
        return VideoItem(
            platform="youtube",
            video_id=it["id"],
            title=sn.get("title", ""),
            description=sn.get("description", ""),
            url=f"https://www.youtube.com/watch?v={it['id']}",
            thumbnail=thumb,
            channel_id=sn.get("channelId", ""),
            channel_title=sn.get("channelTitle", ""),
            published_at=parse_time(sn.get("publishedAt")),
            duration_sec=parse_iso_duration(cd.get("duration", "")),
            views=int(st.get("viewCount", 0) or 0),
            likes=int(st.get("likeCount", 0) or 0),
            comments=int(st.get("commentCount", 0) or 0),
            tags=sn.get("tags", []) or [],
            language=sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "",
            category_id=sn.get("categoryId", ""),
            made_for_kids=bool(it.get("status", {}).get("madeForKids", False)),
            age_restricted=cd.get("contentRating", {}).get("ytRating") == "ytAgeRestricted",
        )

    # ---------------------------------------------------------------- channels

    async def channels(self, ids: list[str]) -> list[ChannelItem]:
        out: list[ChannelItem] = []
        unique = list(dict.fromkeys(i for i in ids if i))
        for i in range(0, len(unique), 50):
            data = await self._get("channels", {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(unique[i:i + 50]),
            })
            out += [self._to_channel(it) for it in data.get("items", [])]
        return out

    async def resolve_channel(self, ref_text: str) -> ChannelItem:
        ref = parse_channel_ref(ref_text)
        params = {"part": "snippet,statistics,contentDetails"}
        if "id" in ref:
            params["id"] = ref["id"]
        elif "handle" in ref:
            params["forHandle"] = ref["handle"]
        elif "video_id" in ref:
            vids = await self.videos([ref["video_id"]])
            if not vids:
                raise YouTubeError("Không tìm thấy video")
            params["id"] = vids[0].channel_id
        else:
            ids = await self.search_channels(ref["query"], max_results=1)
            if not ids:
                raise YouTubeError(f"Không tìm thấy kênh: {ref_text}")
            params["id"] = ids[0]
        data = await self._get("channels", params)
        items = data.get("items", [])
        if not items:
            raise YouTubeError(f"Không tìm thấy kênh: {ref_text}")
        return self._to_channel(items[0])

    async def channel_uploads(self, channel: ChannelItem, max_videos: int = 50) -> list[VideoItem]:
        playlist = channel.uploads_playlist or ("UU" + channel.channel_id[2:])
        ids: list[str] = []
        page_token = None
        while len(ids) < max_videos:
            try:
                data = await self._get("playlistItems", {
                    "part": "contentDetails", "playlistId": playlist,
                    "maxResults": min(50, max_videos - len(ids)), "pageToken": page_token,
                })
            except YouTubeError as e:
                logger.warning(f"Uploads playlist unavailable for {channel.channel_id}: {e}")
                break
            ids += [it["contentDetails"]["videoId"] for it in data.get("items", [])]
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        videos = await self.videos(ids)
        for v in videos:
            v.channel_subscribers = channel.subscribers
        return videos

    @staticmethod
    def _to_channel(it: dict) -> ChannelItem:
        sn = it.get("snippet", {})
        st = it.get("statistics", {})
        thumbs = sn.get("thumbnails", {})
        thumb = (thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
        handle = sn.get("customUrl", "")
        return ChannelItem(
            platform="youtube",
            channel_id=it["id"],
            title=sn.get("title", ""),
            handle=handle,
            description=sn.get("description", ""),
            country=sn.get("country", ""),
            published_at=parse_time(sn.get("publishedAt")),
            subscribers=0 if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0) or 0),
            total_views=int(st.get("viewCount", 0) or 0),
            video_count=int(st.get("videoCount", 0) or 0),
            thumbnail=thumb,
            uploads_playlist=it.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", ""),
            url=f"https://www.youtube.com/{handle}" if handle else f"https://www.youtube.com/channel/{it['id']}",
        )


async def youtube_suggestions(query: str, language: str = "vi", region: str = "VN",
                              timeout: float = 10.0) -> list[str]:
    """YouTube autocomplete (free, unofficial endpoint, no quota)."""
    params = {"client": "firefox", "ds": "yt", "q": query, "hl": language, "gl": region}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(SUGGEST_URL, params=params)
        data = resp.json()
        return [s for s in data[1] if isinstance(s, str)]
    except Exception as e:
        logger.warning(f"YouTube suggest failed for '{query}': {e}")
        return []
