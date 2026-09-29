"""
Relevance ranking of stock clips against a scene.

Each clip's metadata (tags, description, title, URL slug) is compared with the
scene's subjects, action, setting, time of day, weather, season and mood.
Dimensions the scene does not specify are not counted, so a scene without
weather is not penalised for clips without weather tags. Clips whose metadata
contradicts the scene (a "sunny" clip for a night-time rain scene) lose points.

The text score is blended with two priors: the provider's own ranking and how
specific the query that found the clip was.
"""

from typing import Optional

from .lexicon import CONFLICTS, SEASON, SETTING, TIME_OF_DAY, WEATHER, expand, normalize, tokenize
from .models import SceneAnalysis, StockVideoResult

WEIGHTS = {
    "subject": 22.0,
    "subject2": 10.0,
    "action": 12.0,
    "setting": 16.0,
    "time_of_day": 12.0,
    "weather": 12.0,
    "season": 6.0,
    "mood": 5.0,
}
CONFLICT_PENALTY = 18.0
AVOID_PENALTY = 12.0
QUERY_PRIOR = [10.0, 7.0, 5.0, 3.0, 2.0]
PROVIDER_RANK_PRIOR = 8.0

_TABLES = {"time_of_day": TIME_OF_DAY, "weather": WEATHER, "season": SEASON,
           "setting": SETTING}


def clip_text(video: StockVideoResult) -> str:
    slug = video.page_url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
    return " ".join([video.keywords, video.title, slug])


def _match(term: str, tokens: set[str], text: str) -> bool:
    if not term:
        return False
    if " " in term and f" {term} " in text:
        return True
    return bool(expand(term) & tokens)


def _value_in_clip(value: str, table: dict[str, set[str]], tokens: set[str], text: str) -> bool:
    words = {value} | {w for w in table.get(value, set()) if w.isascii()}
    return any(_match(w, tokens, text) for w in words)


def score_video(
    scene: SceneAnalysis,
    video: StockVideoResult,
    query_rank: Optional[int] = None,
    narration_seconds: float = 0.0,
) -> float:
    """Compute and store video.score (0-100), matched_terms and conflicts."""
    raw = clip_text(video).lower()
    text = " " + " ".join(tokenize(raw)) + " "
    tokens = {normalize(t) for t in tokenize(raw)}

    earned = possible = 0.0
    matched: list[str] = []

    def check(weight_key: str, label: str, ok: bool):
        nonlocal earned, possible
        possible += WEIGHTS[weight_key]
        if ok:
            earned += WEIGHTS[weight_key]
            matched.append(label)

    subjects = scene.subjects[:2]
    if subjects:
        check("subject", subjects[0], _match(subjects[0], tokens, text))
    if len(subjects) > 1:
        check("subject2", subjects[1], _match(subjects[1], tokens, text))
    if scene.actions:
        check("action", scene.actions[0], _match(scene.actions[0], tokens, text))
    if scene.setting:
        hit = next((s for s in scene.setting if _value_in_clip(s, SETTING, tokens, text)), "")
        check("setting", hit or scene.setting[0], bool(hit))
    for dim in ("time_of_day", "weather", "season"):
        value = getattr(scene, dim)
        if value:
            check(dim, value, _value_in_clip(value, _TABLES[dim], tokens, text))
    if scene.mood:
        hit = next((m for m in scene.mood if _match(m, tokens, text)), "")
        check("mood", hit or scene.mood[0], bool(hit))

    score = 100.0 * earned / possible if possible else 50.0

    # Contradictions: the clip shows a context the scene rules out
    conflicts: list[str] = []
    scene_values = [scene.time_of_day, scene.weather, scene.season]
    for value in filter(None, scene_values):
        if value in matched:
            continue
        for other in CONFLICTS.get(value, set()):
            table = next((t for t in _TABLES.values() if other in t), None)
            if table and _value_in_clip(other, table, tokens, text):
                conflicts.append(other)
    for term in scene.avoid:
        if _match(term, tokens, text):
            conflicts.append(term)
    score -= CONFLICT_PENALTY * len(set(conflicts) - set(scene.avoid))
    score -= AVOID_PENALTY * len(set(conflicts) & set(scene.avoid))

    # Priors: specific queries and the provider's own ordering carry signal,
    # especially for providers with sparse metadata
    if query_rank is not None:
        score += QUERY_PRIOR[min(query_rank, len(QUERY_PRIOR) - 1)]
    score += PROVIDER_RANK_PRIOR * max(0.0, 1 - video.provider_rank / 10)

    if narration_seconds and video.duration:
        if video.duration >= narration_seconds:
            score += 3
        elif video.duration < 0.6 * narration_seconds:
            score -= 5

    video.score = round(max(0.0, min(100.0, score)), 1)
    video.matched_terms = matched
    video.conflicts = sorted(set(conflicts))
    return video.score


def rank_results(
    scene: SceneAnalysis,
    videos: list[StockVideoResult],
    queries: list[str],
    narration_seconds: float = 0.0,
) -> list[StockVideoResult]:
    """Score every clip and return them best first."""
    order = {q: i for i, q in enumerate(queries)}
    for v in videos:
        score_video(scene, v, order.get(v.matched_query), narration_seconds)
        if v.ai_score is not None:
            # Visual judgement dominates when available
            v.score = round(0.35 * v.score + 0.65 * v.ai_score * 10, 1)
    return sorted(videos, key=lambda v: v.score, reverse=True)
