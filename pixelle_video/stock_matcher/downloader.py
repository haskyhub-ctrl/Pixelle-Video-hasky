"""
Module D (backend) - Async downloading and manifest generation.

Files are named `scene_01_<keyword>.mp4`; a `manifest.json` maps every script
sentence to its clip, source metadata and an estimated narration timeline.
"""

import asyncio
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import httpx
from loguru import logger

from .http_utils import backoff_delay
from .models import DownloadItem, SceneAnalysis, StockVideoResult
from .nlp_parser import estimate_narration_seconds
from .stock_searcher import StockSearchEngine

# (scene_index, bytes_downloaded, total_bytes_or_0)
ProgressCallback = Callable[[int, int, int], None]

CHUNK_SIZE = 1 << 16


def slugify(text: str, max_words: int = 3, max_len: int = 40) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())[:max_words]
    return ("_".join(words) or "clip")[:max_len]


def scene_filename(index: int, keyword: str, ext: str = ".mp4") -> str:
    return f"scene_{index:02d}_{slugify(keyword)}{ext}"


@dataclass
class DownloadResult:
    scene: SceneAnalysis
    video: Optional[StockVideoResult]
    path: Optional[Path] = None
    error: str = ""
    custom: bool = False

    @property
    def ok(self) -> bool:
        return self.path is not None and not self.error


@dataclass
class CustomClip:
    """A user-supplied clip replacing stock footage for a scene."""

    scene: SceneAnalysis
    source_path: Path
    keyword: str = "custom"


@dataclass
class Downloader:
    engine: StockSearchEngine
    output_dir: Path
    max_parallel: int = 3
    max_retries: int = 3
    overwrite: bool = False
    words_per_second: float = 2.5
    _results: list[DownloadResult] = field(default_factory=list)

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def _stream_to_file(self, url: str, dest: Path, scene_index: int,
                              on_progress: Optional[ProgressCallback], provider: str) -> None:
        tmp = dest.with_suffix(dest.suffix + ".part")
        for attempt in range(self.max_retries + 1):
            try:
                async with self.engine.client.stream("GET", url, follow_redirects=True) as resp:
                    if resp.status_code == 429 or resp.status_code >= 500:
                        raise httpx.HTTPStatusError(
                            f"HTTP {resp.status_code}", request=resp.request, response=resp
                        )
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length") or 0)
                    done = 0
                    with open(tmp, "wb") as fh:
                        async for chunk in resp.aiter_bytes(CHUNK_SIZE):
                            fh.write(chunk)
                            done += len(chunk)
                            if on_progress:
                                on_progress(scene_index, done, total)
                    if total and done < total:
                        raise httpx.ReadError(f"incomplete download {done}/{total} bytes")
                tmp.replace(dest)
                return
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                tmp.unlink(missing_ok=True)
                status = getattr(getattr(e, "response", None), "status_code", 0)
                retryable = isinstance(e, httpx.TransportError) or status == 429 or status >= 500
                if not retryable or attempt == self.max_retries:
                    raise
                delay = backoff_delay(attempt)
                logger.warning(f"{provider}: download retry {attempt + 1} in {delay:.1f}s ({e})")
                await asyncio.sleep(delay)

    async def download_one(self, item: DownloadItem, sem: asyncio.Semaphore,
                           on_progress: Optional[ProgressCallback] = None) -> DownloadResult:
        scene, video = item.scene, item.video
        keyword = item.keyword or video.matched_query or scene.query or video.title
        dest = self.output_dir / scene_filename(scene.index, keyword)
        result = DownloadResult(scene=scene, video=video)
        async with sem:
            try:
                if dest.exists() and not self.overwrite:
                    logger.info(f"Scene {scene.index}: {dest.name} exists, skipping")
                else:
                    provider = self.engine.provider_for(video)
                    url = await provider.resolve_download_url(video)
                    await self._stream_to_file(url, dest, scene.index, on_progress, video.provider)
                    logger.success(f"Scene {scene.index}: saved {dest.name}")
                result.path = dest
            except Exception as e:
                result.error = str(e) or e.__class__.__name__
                logger.error(f"Scene {scene.index}: download failed - {result.error}")
        return result

    def add_custom_clip(self, clip: CustomClip) -> DownloadResult:
        """Copy a user-provided clip into the output folder with the scene naming scheme."""
        ext = clip.source_path.suffix or ".mp4"
        dest = self.output_dir / scene_filename(clip.scene.index, clip.keyword, ext)
        if clip.source_path.resolve() != dest.resolve():
            shutil.copyfile(clip.source_path, dest)
        return DownloadResult(scene=clip.scene, video=None, path=dest, custom=True)

    async def download(self, items: list[DownloadItem],
                       on_progress: Optional[ProgressCallback] = None,
                       custom_clips: Optional[list[CustomClip]] = None) -> list[DownloadResult]:
        sem = asyncio.Semaphore(self.max_parallel)
        results = list(await asyncio.gather(
            *(self.download_one(item, sem, on_progress) for item in items)
        ))
        results.extend(self.add_custom_clip(c) for c in custom_clips or [])
        results.sort(key=lambda r: r.scene.index)
        self._results = results
        return results

    def write_manifest(self, results: list[DownloadResult],
                       all_scenes: Optional[list[SceneAnalysis]] = None) -> Path:
        """
        Write manifest.json. Scenes without a clip are included with file=null so
        the timeline stays complete.
        """
        by_index = {r.scene.index: r for r in results}
        scenes = all_scenes or [r.scene for r in results]
        entries, cursor = [], 0.0
        for scene in sorted(scenes, key=lambda s: s.index):
            narration = estimate_narration_seconds(scene.sentence, self.words_per_second)
            r = by_index.get(scene.index)
            v = r.video if r else None
            entries.append({
                "scene": scene.index,
                "sentence": scene.sentence,
                "search_query": scene.query,
                "matched_query": v.matched_query if v else None,
                "keywords": {
                    "subjects": scene.subjects,
                    "actions": scene.actions,
                    "descriptors": scene.descriptors,
                },
                "file": str(r.path.relative_to(self.output_dir)) if r and r.path else None,
                "status": ("custom" if r.custom else "ok" if r.ok else "error") if r else "skipped",
                "error": (r.error or None) if r else None,
                "source": {
                    "provider": v.provider,
                    "id": v.id,
                    "title": v.title,
                    "page_url": v.page_url,
                    "author": v.author,
                    "is_premium": v.is_premium,
                    "width": v.width,
                    "height": v.height,
                } if v else None,
                "timing": {
                    "start": round(cursor, 2),
                    "end": round(cursor + narration, 2),
                    "narration_seconds": narration,
                    "clip_seconds": v.duration if v else None,
                    "clip_shorter_than_narration": bool(v and v.duration
                                                        and v.duration < narration),
                },
            })
            cursor += narration

        manifest = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_estimated_seconds": round(cursor, 2),
            "words_per_second": self.words_per_second,
            "scenes": entries,
        }
        path = self.output_dir / "manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
