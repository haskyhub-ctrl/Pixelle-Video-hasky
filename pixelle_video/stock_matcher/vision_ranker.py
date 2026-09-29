"""
Optional visual re-ranking: a vision-capable LLM looks at the thumbnails of the
top candidates for a scene and rates how well each matches the scene's subject,
action, place, time of day and weather. Tags on free stock sites are sparse, so
this is the most reliable way to pick the closest clip.

Works with OpenAI-compatible vision models (gpt-4o-mini, gemini-2.x-flash via
its OpenAI endpoint, qwen-vl...) and Claude. Thumbnails are downloaded and
downscaled locally, then sent inline, so providers never have to fetch URLs.
"""

import asyncio
import base64
import io
from typing import Callable, Optional

import httpx
from loguru import logger

from .auth_manager import LLMSettings
from .llm_extractor import _parse_json_payload
from .models import SearchOutcome, StockVideoResult
from .nlp_parser import estimate_narration_seconds
from .relevance import rank_results

THUMB_SIZE = (448, 448)

VISION_PROMPT = """You are choosing stock footage for one scene of a narrated video.

Narration: "{sentence}"
Wanted shot: {brief}

Below are {n} candidate clips (one thumbnail each). Rate each 0-10 for how well
the shot fits the scene: the right kind of subject and action matter most, then
place, time of day, weather and mood. An exact match is not required; a clip that
conveys the same situation and atmosphere deserves a good score. A clip that
contradicts the scene (daylight for a night scene, sun for rain) scores low.

Answer ONLY with JSON: {{"ratings": [{{"clip": 1, "score": 7, "reason": "short"}}]}}"""

RATINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "ratings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clip": {"type": "integer"},
                    "score": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["clip", "score", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ratings"],
    "additionalProperties": False,
}


def scene_brief(outcome: SearchOutcome) -> str:
    s = outcome.scene
    parts = [s.visual_description] if s.visual_description else []
    facts = {
        "subject": ", ".join(s.subjects), "action": ", ".join(s.actions),
        "place": ", ".join(s.setting), "time": s.time_of_day, "weather": s.weather,
        "season": s.season, "mood": ", ".join(s.mood), "avoid": ", ".join(s.avoid),
    }
    parts.append("; ".join(f"{k}: {v}" for k, v in facts.items() if v))
    return " | ".join(p for p in parts if p) or s.sentence


async def _fetch_thumb(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Download a thumbnail and return it as base64 JPEG, downscaled."""
    try:
        from PIL import Image

        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        img.thumbnail(THUMB_SIZE)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.debug(f"thumbnail fetch failed for {url}: {e}")
        return None


def _rate_openai(settings: LLMSettings, prompt: str, images: list[str]) -> list[dict]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.api_key or "none", base_url=settings.base_url or None)
    content: list[dict] = [{"type": "text", "text": prompt}]
    for n, b64 in enumerate(images, start=1):
        content.append({"type": "text", "text": f"Clip {n}:"})
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    resp = client.chat.completions.create(
        model=settings.vision_model or settings.model,
        messages=[{"role": "user", "content": content}],
        temperature=0,
    )
    return _parse_json_payload(resp.choices[0].message.content or "", key="ratings")


def _rate_anthropic(settings: LLMSettings, prompt: str, images: list[str]) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.api_key) if settings.api_key \
        else anthropic.Anthropic()
    content: list[dict] = [{"type": "text", "text": prompt}]
    for n, b64 in enumerate(images, start=1):
        content.append({"type": "text", "text": f"Clip {n}:"})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg", "data": b64}})
    response = client.messages.create(
        model=settings.vision_model or settings.model or "claude-opus-5-5",
        max_tokens=4000,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": RATINGS_SCHEMA},
        },
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined the rating request")
    text = next((b.text for b in response.content if b.type == "text"), "")
    return _parse_json_payload(text, key="ratings")


async def rerank_outcome(
    settings: LLMSettings,
    outcome: SearchOutcome,
    client: httpx.AsyncClient,
    top_n: int = 8,
    words_per_second: float = 2.5,
) -> SearchOutcome:
    """Score the top_n clips of one scene visually and re-sort all results."""
    candidates: list[StockVideoResult] = [r for r in outcome.results if r.thumbnail_url][:top_n]
    if not candidates:
        return outcome
    thumbs = await asyncio.gather(*(_fetch_thumb(client, r.thumbnail_url) for r in candidates))
    pairs = [(r, t) for r, t in zip(candidates, thumbs) if t]
    if not pairs:
        return outcome
    prompt = VISION_PROMPT.format(sentence=outcome.scene.sentence,
                                  brief=scene_brief(outcome), n=len(pairs))
    rate = _rate_anthropic if settings.backend == "anthropic" else _rate_openai
    ratings = await asyncio.to_thread(rate, settings, prompt, [t for _, t in pairs])
    for item in ratings:
        try:
            idx = int(item.get("clip", 0)) - 1
            if 0 <= idx < len(pairs):
                video = pairs[idx][0]
                video.ai_score = max(0.0, min(10.0, float(item.get("score", 0))))
                video.ai_reason = str(item.get("reason", ""))[:200]
        except (TypeError, ValueError):
            continue
    narration = estimate_narration_seconds(outcome.scene.sentence, words_per_second)
    outcome.results = rank_results(outcome.scene, outcome.results, outcome.tried_queries,
                                   narration)
    return outcome


async def rerank_outcomes(
    settings: LLMSettings,
    outcomes: list[SearchOutcome],
    top_n: int = 8,
    max_parallel: int = 3,
    on_done: Optional[Callable[[SearchOutcome, int, int, str], None]] = None,
) -> list[SearchOutcome]:
    """Visually re-rank many scenes; failures leave that scene's text ranking intact."""
    sem = asyncio.Semaphore(max_parallel)
    finished = 0
    todo = [o for o in outcomes if o.results]

    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def one(outcome: SearchOutcome):
            nonlocal finished
            error = ""
            async with sem:
                try:
                    await rerank_outcome(settings, outcome, client, top_n)
                except Exception as e:
                    error = str(e)
                    logger.warning(f"Scene {outcome.scene.index}: visual rerank failed: {e}")
            finished += 1
            if on_done:
                on_done(outcome, finished, len(todo), error)

        await asyncio.gather(*(one(o) for o in todo))
    return outcomes

