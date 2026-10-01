"""
Module B - Multi-platform stock video search.

Every provider implements BaseStockProvider.search(); StockSearchEngine fans a
query out to all enabled providers concurrently, merges the results, and
retries with progressively simpler queries when nothing matches.
"""

import asyncio
import hashlib
import hmac
import json
import re
import time
from abc import ABC, abstractmethod
from itertools import zip_longest
from pathlib import Path
from typing import Callable, Optional

import httpx
from loguru import logger

from .auth_manager import AuthManager
from .http_utils import StockMatcherError, request_with_retry
from .models import SceneAnalysis, SearchOutcome, StockVideoResult
from .nlp_parser import estimate_narration_seconds, simplify_queries
from .relevance import rank_results

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
# Searches should fail fast so the UI never looks frozen
SEARCH_TIMEOUT = httpx.Timeout(12.0, connect=6.0)
SEARCH_MAX_RETRIES = 2
USER_AGENT = "Pixelle-Video-StockMatcher/1.0"


class BaseStockProvider(ABC):
    """Unified provider interface."""

    name: str = "base"
    is_premium: bool = False

    def __init__(self, auth: AuthManager, client: httpx.AsyncClient, max_width: int = 1920):
        self.auth = auth
        self.client = client
        self.max_width = max_width

    @abstractmethod
    async def search(self, query: str, page: int = 1, per_page: int = 10,
                     lang: Optional[str] = None) -> list[StockVideoResult]:
        """Search videos for a query. lang is an ISO code such as "vi"."""

    async def resolve_download_url(self, video: StockVideoResult,
                                   max_width: Optional[int] = None) -> str:
        """
        Return the URL of the file to download, at most max_width pixels wide
        when the provider offers several renditions. Premium providers
        override this to license the clip first.
        """
        return pick_variant(video, max_width or self.max_width)

    async def _get(self, url: str, **kwargs) -> httpx.Response:
        kwargs.setdefault("timeout", SEARCH_TIMEOUT)
        kwargs.setdefault("max_retries", SEARCH_MAX_RETRIES)
        return await request_with_retry(self.client, "GET", url, provider=self.name, **kwargs)


# ---------------------------------------------------------------- free providers


class PexelsProvider(BaseStockProvider):
    """https://www.pexels.com/api/documentation/#videos-search"""

    name = "Pexels"
    API = "https://api.pexels.com/videos/search"

    async def search(self, query, page=1, per_page=10, lang=None):
        creds = self.auth.get("pexels")
        resp = await self._get(
            self.API,
            params={"query": query, "page": page, "per_page": min(per_page, 80)}
            | ({"locale": LOCALES.get(lang, lang)} if lang else {}),
            headers={"Authorization": creds.get("PEXELS_API_KEY")},
        )
        results = []
        for v in resp.json().get("videos", []):
            files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"]
            if not files:
                continue
            files.sort(key=lambda f: f.get("width") or 0)
            fitting = [f for f in files if (f.get("width") or 0) <= self.max_width]
            best = (fitting or files)[-1]
            preview = next((f for f in files if (f.get("width") or 0) >= 480), files[0])
            variants = {str(f["width"]): f["link"] for f in files if f.get("width")}
            results.append(
                StockVideoResult(
                    id=str(v["id"]),
                    provider=self.name,
                    title=_title_from_url(v.get("url", "")) or query,
                    keywords=_title_from_url(v.get("url", "")),
                    variants=variants,
                    preview_url=preview["link"],
                    download_url=best["link"],
                    duration=float(v.get("duration") or 0),
                    thumbnail_url=v.get("image", ""),
                    page_url=v.get("url", ""),
                    width=best.get("width") or v.get("width") or 0,
                    height=best.get("height") or v.get("height") or 0,
                    author=(v.get("user") or {}).get("name", ""),
                )
            )
        return results


class PixabayProvider(BaseStockProvider):
    """https://pixabay.com/api/docs/#api_search_videos"""

    name = "Pixabay"
    API = "https://pixabay.com/api/videos/"

    async def search(self, query, page=1, per_page=10, lang=None):
        creds = self.auth.get("pixabay")
        resp = await self._get(
            self.API,
            params={
                "key": creds.get("PIXABAY_API_KEY"),
                "q": query[:100],
                "page": page,
                "per_page": max(3, min(per_page, 200)),
                "safesearch": "true",
            } | ({"lang": lang} if lang else {}),
        )
        results = []
        for hit in resp.json().get("hits", []):
            variants = hit.get("videos", {})
            ordered = [variants.get(k) or {} for k in ("large", "medium", "small", "tiny")]
            available = [v for v in ordered if v.get("url")]
            if not available:
                continue
            fitting = [v for v in available if (v.get("width") or 0) <= self.max_width]
            best = (fitting or available)[0]
            preview = next(
                (v for v in reversed(available) if (v.get("width") or 0) >= 480), available[-1]
            )
            thumb = next((v.get("thumbnail") for v in ordered if v.get("thumbnail")), "")
            variants = {str(v["width"]): v["url"] for v in available if v.get("width")}
            if not thumb and hit.get("picture_id"):
                thumb = f"https://i.vimeocdn.com/video/{hit['picture_id']}_640x360.jpg"
            results.append(
                StockVideoResult(
                    id=str(hit["id"]),
                    provider=self.name,
                    title=hit.get("tags", query),
                    keywords=hit.get("tags", ""),
                    variants=variants,
                    preview_url=preview["url"],
                    download_url=best["url"],
                    duration=float(hit.get("duration") or 0),
                    thumbnail_url=thumb,
                    page_url=hit.get("pageURL", ""),
                    width=best.get("width") or 0,
                    height=best.get("height") or 0,
                    author=hit.get("user", ""),
                )
            )
        return results


class MixkitProvider(BaseStockProvider):
    """
    Mixkit has no public API; this reads its public search page and extracts
    asset URLs. Best-effort: it will return nothing if Mixkit changes its markup.
    """

    name = "Mixkit"
    SEARCH = "https://mixkit.co/free-stock-video/{slug}/"
    _ASSET = re.compile(r"https://assets\.mixkit\.co/videos/(\d+)/\1-(\d+)\.mp4")
    _THUMB = re.compile(r"https://assets\.mixkit\.co/videos/(\d+)/\1-thumb-(\d+)-\d+\.jpg")

    async def search(self, query, page=1, per_page=10, lang=None):
        if lang:
            return []
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        if not slug:
            return []
        url = self.SEARCH.format(slug=slug)
        if page > 1:
            url += f"?page={page}"
        try:
            resp = await self._get(url, headers={"User-Agent": USER_AGENT})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise
        html = resp.text
        sizes: dict[str, set[int]] = {}
        for vid, size in self._ASSET.findall(html):
            sizes.setdefault(vid, set()).add(int(size))
        thumbs = {vid: m.group(0) for m in self._THUMB.finditer(html) for vid in [m.group(1)]}
        results = []
        for vid in list(sizes)[:per_page]:
            available = sorted(sizes[vid])
            preview_size = available[0]
            results.append(
                StockVideoResult(
                    id=vid,
                    provider=self.name,
                    title=query,
                    preview_url=f"https://assets.mixkit.co/videos/{vid}/{vid}-{preview_size}.mp4",
                    # Mixkit serves 720p for all free clips
                    download_url=f"https://assets.mixkit.co/videos/{vid}/{vid}-720.mp4",
                    thumbnail_url=thumbs.get(vid, ""),
                    page_url=url,
                    width=1280,
                    height=720,
                )
            )
        return results


# ------------------------------------------------------------- premium providers


class ShutterstockProvider(BaseStockProvider):
    """
    Shutterstock API v2. Search returns watermarked previews; the full clip is
    obtained by licensing it (POST /v2/videos/licenses), which consumes a
    download from your subscription.
    """

    name = "Shutterstock"
    is_premium = True
    API = "https://api.shutterstock.com/v2"

    def _headers(self) -> dict:
        token = self.auth.get("shutterstock").get("SHUTTERSTOCK_API_TOKEN")
        return {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}

    async def search(self, query, page=1, per_page=10, lang=None):
        resp = await self._get(
            f"{self.API}/videos/search",
            params={"query": query, "page": page, "per_page": min(per_page, 500),
                    "view": "full", "sort": "relevance"} | ({"language": lang} if lang else {}),
            headers=self._headers(),
        )
        results = []
        for v in resp.json().get("data", []):
            assets = v.get("assets", {})
            preview = (assets.get("preview_mp4") or assets.get("thumb_mp4") or {}).get("url", "")
            if not preview:
                continue
            hd = assets.get("hd") or assets.get("sd") or {}
            results.append(
                StockVideoResult(
                    id=str(v["id"]),
                    provider=self.name,
                    title=v.get("description", query),
                    keywords=" ".join([v.get("description", "")] + list(v.get("keywords") or [])),
                    preview_url=preview,
                    download_url="",  # resolved at download time via licensing
                    is_premium=True,
                    duration=float(v.get("duration") or 0),
                    thumbnail_url=(assets.get("thumb_jpg") or {}).get("url", ""),
                    width=hd.get("width") or 0,
                    height=hd.get("height") or 0,
                    author=(v.get("contributor") or {}).get("id", ""),
                )
            )
        return results

    async def resolve_download_url(self, video, max_width=None):
        creds = self.auth.get("shutterstock")
        width = max_width or self.max_width
        size = creds.get("SHUTTERSTOCK_VIDEO_SIZE") or (
            "sd" if width <= 1280 else "hd" if width <= 1920 else "4k")
        item = {"video_id": video.id, "size": size}
        if creds.get("SHUTTERSTOCK_SUBSCRIPTION_ID"):
            item["subscription_id"] = creds.get("SHUTTERSTOCK_SUBSCRIPTION_ID")
        resp = await request_with_retry(
            self.client, "POST", f"{self.API}/videos/licenses", provider=self.name,
            headers=self._headers(), json={"videos": [item]},
        )
        data = (resp.json().get("data") or [{}])[0]
        if data.get("error"):
            raise StockMatcherError(f"Shutterstock licensing failed: {data['error']}")
        url = (data.get("download") or {}).get("url")
        if not url:
            raise StockMatcherError("Shutterstock licensing returned no download URL")
        return url


class StoryblocksProvider(BaseStockProvider):
    """
    Storyblocks API v2 (HMAC-signed requests). Downloads go through the
    stock-item download endpoint and count against your plan.
    """

    name = "Storyblocks"
    is_premium = True
    BASE = "https://api.storyblocks.com"

    def _signed_params(self, resource: str) -> dict:
        creds = self.auth.get("storyblocks")
        expires = str(int(time.time()) + 600)
        key = (creds.get("STORYBLOCKS_PRIVATE_KEY") + expires).encode()
        signature = hmac.new(key, resource.encode(), hashlib.sha256).hexdigest()
        return {
            "APIKEY": creds.get("STORYBLOCKS_PUBLIC_KEY"),
            "EXPIRES": expires,
            "HMAC": signature,
            "user_id": creds.get("STORYBLOCKS_USER_ID"),
            "project_id": creds.get("STORYBLOCKS_PROJECT_ID"),
        }

    async def search(self, query, page=1, per_page=10, lang=None):
        if lang:
            return []
        resource = "/api/v2/videos/search"
        params = self._signed_params(resource) | {
            "keywords": query, "page": page, "results_per_page": min(per_page, 100),
        }
        resp = await self._get(self.BASE + resource, params=params)
        results = []
        for v in resp.json().get("results", []):
            previews = v.get("preview_urls") or {}
            preview = (previews.get("_480p") or previews.get("_360p")
                       or next(iter(previews.values()), ""))
            if not preview:
                continue
            results.append(
                StockVideoResult(
                    id=str(v["id"]),
                    provider=self.name,
                    title=v.get("title", query),
                    keywords=" ".join([v.get("title", "")] + list(v.get("keywords") or [])),
                    preview_url=preview,
                    download_url="",
                    is_premium=True,
                    duration=float(v.get("duration") or 0),
                    thumbnail_url=v.get("thumbnail_url", ""),
                )
            )
        return results

    async def resolve_download_url(self, video, max_width=None):
        resource = f"/api/v2/videos/stock-item/download/{video.id}"
        resp = await self._get(self.BASE + resource, params=self._signed_params(resource))
        urls = _collect_mp4_urls(resp.json())
        if not urls:
            raise StockMatcherError("Storyblocks returned no MP4 download URL")
        # Prefer the highest resolution not exceeding max_width's matching height
        return max(urls, key=lambda u: _resolution_hint(u, max_width or self.max_width))


def pick_variant(video: StockVideoResult, max_width: int) -> str:
    """Widest rendition not wider than max_width (else the smallest one)."""
    sized = []
    for width, url in (video.variants or {}).items():
        try:
            sized.append((int(width), url))
        except ValueError:
            continue
    if not sized:
        return video.download_url
    sized.sort()
    fitting = [url for width, url in sized if width <= max_width]
    return fitting[-1] if fitting else sized[0][1]


def _collect_mp4_urls(data) -> list[str]:
    found = []
    if isinstance(data, dict):
        for v in data.values():
            found.extend(_collect_mp4_urls(v))
    elif isinstance(data, list):
        for v in data:
            found.extend(_collect_mp4_urls(v))
    elif isinstance(data, str) and data.startswith("http") and ".mp4" in data.lower():
        found.append(data)
    return found


def _resolution_hint(url: str, max_width: int) -> int:
    m = re.search(r"(\d{3,4})p", url)
    height = int(m.group(1)) if m else 0
    return height if height * 16 / 9 <= max_width else -height


def _title_from_url(url: str) -> str:
    m = re.search(r"/video/([a-z0-9-]+?)-\d+/?$", url)
    return m.group(1).replace("-", " ") if m else ""


PROVIDER_CLASSES: dict[str, type[BaseStockProvider]] = {
    "pexels": PexelsProvider,
    "pixabay": PixabayProvider,
    "mixkit": MixkitProvider,
    "shutterstock": ShutterstockProvider,
    "storyblocks": StoryblocksProvider,
}
DEFAULT_PROVIDERS = ["pexels", "pixabay"]
LOCALES = {"vi": "vi-VN", "en": "en-US"}


# ------------------------------------------------------------------- engine


def _matches_orientation(v: StockVideoResult, orientation: Optional[str]) -> bool:
    if not orientation or not v.width or not v.height:
        return True
    ratio = v.width / v.height
    return {
        "landscape": ratio > 1.1,
        "portrait": ratio < 0.9,
        "square": 0.9 <= ratio <= 1.1,
    }.get(orientation, True)


class SearchCache:
    """
    Small on-disk cache of provider responses. Saves API quota (Pexels allows
    200 requests/hour) when a script is searched again; Pixabay also asks
    clients to cache results for 24 hours.
    """

    def __init__(self, directory: Optional[Path], ttl_seconds: int = 24 * 3600):
        self.directory = Path(directory) if directory else None
        self.ttl = ttl_seconds
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Optional[Path]:
        if not self.directory:
            return None
        return self.directory / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    def get(self, key: str) -> Optional[list[StockVideoResult]]:
        path = self._path(key)
        if not path or not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - data["saved_at"] > self.ttl:
                return None
            return [StockVideoResult.from_dict(item) for item in data["results"]]
        except Exception:
            return None

    def put(self, key: str, results: list[StockVideoResult]) -> None:
        path = self._path(key)
        if not path:
            return
        try:
            path.write_text(json.dumps({"saved_at": time.time(),
                                        "results": [r.to_dict() for r in results]}),
                            encoding="utf-8")
        except OSError as e:
            logger.debug(f"cache write failed: {e}")


class StockSearchEngine:
    """
    Queries all enabled providers concurrently, pools the results of several
    candidate queries per scene and ranks them by relevance to the scene.
    """

    def __init__(
        self,
        auth: Optional[AuthManager] = None,
        providers: Optional[list[str]] = None,
        client: Optional[httpx.AsyncClient] = None,
        max_width: int = 1920,
        orientation: Optional[str] = None,
        min_duration: float = 0.0,
        max_concurrency: int = 4,
        cache_dir: Optional[str | Path] = None,
        words_per_second: float = 2.5,
    ):
        self.auth = auth or AuthManager()
        self._own_client = client is None
        self.client = client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        self.orientation = orientation
        self.min_duration = min_duration
        self.words_per_second = words_per_second
        self.cache = SearchCache(cache_dir)
        self._scene_sem = asyncio.Semaphore(max_concurrency)
        self.providers: dict[str, BaseStockProvider] = {}
        self.skipped: dict[str, str] = {}
        for key in providers or DEFAULT_PROVIDERS:
            key = key.lower()
            cls = PROVIDER_CLASSES.get(key)
            if cls is None:
                raise ValueError(f"Unknown provider '{key}'. Choose from {list(PROVIDER_CLASSES)}")
            if not self.auth.is_configured(key):
                missing = ", ".join(self.auth.missing_vars(key))
                self.skipped[cls.name] = f"missing credentials: {missing}"
                logger.warning(f"{cls.name} disabled: set {missing} in .env")
                continue
            self.providers[cls.name] = cls(self.auth, self.client, max_width=max_width)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    async def aclose(self):
        if self._own_client:
            await self.client.aclose()

    def provider_for(self, video: StockVideoResult) -> BaseStockProvider:
        return self.providers[video.provider]

    async def _search_provider(self, provider: BaseStockProvider, query: str, page: int,
                               per_page: int, lang: Optional[str] = None,
                               ) -> tuple[str, list[StockVideoResult], str]:
        key = f"{provider.name}|{query}|{page}|{per_page}|{lang or ''}"
        cached = self.cache.get(key)
        if cached is not None:
            return provider.name, cached, ""
        try:
            results = await provider.search(query, page=page, per_page=per_page, lang=lang)
        except Exception as e:
            logger.warning(f"{provider.name} search failed for '{query}': {e}")
            return provider.name, [], str(e)
        for rank, r in enumerate(results):
            r.matched_query = query
            r.provider_rank = rank
        self.cache.put(key, results)
        return provider.name, results, ""

    async def search_query(self, query: str, page: int = 1, per_page: int = 8,
                           lang: Optional[str] = None,
                           ) -> tuple[list[StockVideoResult], dict[str, str]]:
        """Search one query on all providers concurrently; results are interleaved."""
        if not self.providers:
            raise StockMatcherError(
                "No stock provider is configured. Add PEXELS_API_KEY or PIXABAY_API_KEY to .env"
            )
        outcomes = await asyncio.gather(
            *(self._search_provider(p, query, page, per_page, lang)
              for p in self.providers.values())
        )
        errors = {name: err for name, _, err in outcomes if err}
        lists = [
            [r for r in results
             if _matches_orientation(r, self.orientation) and r.duration >= self.min_duration]
            for _, results, _ in outcomes
        ]
        merged = [r for group in zip_longest(*lists) for r in group if r is not None]
        return merged, errors

    async def search_scene(self, scene: SceneAnalysis, per_page: int = 8,
                           query_override: Optional[str] = None,
                           parallel_queries: int = 2) -> SearchOutcome:
        """
        Search several candidate queries (most specific first), pool the clips
        and rank them against the scene. More general queries are only tried
        while the pool is still small, which keeps API usage low.
        """
        queries = simplify_queries(scene)
        if query_override:
            queries = [query_override] + [q for q in queries if q != query_override]
        outcome = SearchOutcome(scene=scene)
        pool: dict[str, StockVideoResult] = {}
        target = max(per_page, 6)
        batches = [queries[:parallel_queries]] + [[q] for q in queries[parallel_queries:]]

        async with self._scene_sem:
            for batch in batches:
                if not batch:
                    continue
                found = await asyncio.gather(
                    *(self.search_query(q, per_page=per_page) for q in batch)
                )
                all_failed = True
                for query, (results, errors) in zip(batch, found):
                    outcome.tried_queries.append(query)
                    outcome.errors.update(errors)
                    all_failed &= len(errors) == len(self.providers)
                    if results and not outcome.used_query:
                        outcome.used_query = query
                    for r in results:
                        pool.setdefault(r.uid, r)
                if all_failed or len(pool) >= target:
                    break
            # Also search in the script's own language when there is no LLM
            # translation; providers translate tags on their side
            if scene.native_query and scene.source != "llm" and len(pool) < 2 * target:
                results, errors = await self.search_query(
                    scene.native_query, per_page=per_page, lang=scene.language
                )
                outcome.tried_queries.append(f"{scene.native_query} [{scene.language}]")
                for r in results:
                    pool.setdefault(r.uid, r)

        if pool:
            # Errors from providers that failed only on some queries are noise
            succeeded = {r.provider for r in pool.values()}
            outcome.errors = {p: e for p, e in outcome.errors.items() if p not in succeeded}
        narration = estimate_narration_seconds(scene.sentence, self.words_per_second)
        ranked = rank_results(scene, list(pool.values()), outcome.tried_queries, narration)
        outcome.results = ranked[: per_page * max(1, len(self.providers))]
        return outcome

    async def search_scenes(
        self,
        scenes: list[SceneAnalysis],
        per_page: int = 8,
        overrides: Optional[dict[int, str]] = None,
        on_scene_done: Optional[Callable[[SearchOutcome, int, int], None]] = None,
    ) -> list[SearchOutcome]:
        """Search all scenes; on_scene_done(outcome, finished, total) reports progress."""
        overrides = overrides or {}
        tasks = [
            asyncio.ensure_future(self.search_scene(s, per_page, overrides.get(s.index)))
            for s in scenes
        ]
        for finished, task in enumerate(asyncio.as_completed(tasks), start=1):
            outcome = await task
            if on_scene_done:
                on_scene_done(outcome, finished, len(tasks))
        return [t.result() for t in tasks]
