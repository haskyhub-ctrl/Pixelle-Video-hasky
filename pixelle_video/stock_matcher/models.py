"""
Data models shared across the stock matcher modules.
"""

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class SceneAnalysis:
    """One visual scene derived from a script sentence."""

    index: int
    sentence: str
    subjects: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    descriptors: list[str] = field(default_factory=list)
    query: str = ""
    language: str = "en"
    source: str = "heuristic"  # "spacy" | "heuristic" | "llm"
    # Visual context used for multi-query search and relevance ranking
    setting: list[str] = field(default_factory=list)  # office, street, beach...
    time_of_day: str = ""  # night, sunset, morning, day...
    weather: str = ""  # rain, snow, fog, sunny...
    season: str = ""  # winter, summer...
    mood: list[str] = field(default_factory=list)
    visual_description: str = ""
    # Candidate search queries, most specific first
    queries: list[str] = field(default_factory=list)
    # Terms that should not appear in the footage (e.g. "daylight" for a night scene)
    avoid: list[str] = field(default_factory=list)
    # Original-language keywords, searched with the provider's language option
    native_query: str = ""
    # Context fields inherited from earlier scenes rather than stated in this one
    inherited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StockVideoResult:
    """A single stock video returned by a provider search."""

    id: str
    provider: str
    title: str
    preview_url: str
    download_url: str
    is_premium: bool = False
    duration: float = 0.0
    thumbnail_url: str = ""
    page_url: str = ""
    width: int = 0
    height: int = 0
    author: str = ""
    # Query that actually produced this result (may be a simplified fallback)
    matched_query: str = ""
    # Free-text metadata (tags / description / URL slug) used for ranking
    keywords: str = ""
    # Position in the provider's own ranking for matched_query (0 = best)
    provider_rank: int = 0
    # Relevance ranking output
    score: float = 0.0
    matched_terms: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    ai_score: Optional[float] = None
    ai_reason: str = ""

    @property
    def uid(self) -> str:
        """Globally unique key across providers."""
        return f"{self.provider}:{self.id}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchOutcome:
    """Aggregated search result for one scene."""

    scene: SceneAnalysis
    results: list[StockVideoResult] = field(default_factory=list)
    used_query: str = ""
    tried_queries: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # provider -> message


@dataclass
class DownloadItem:
    """A clip selected for download for a scene."""

    scene: SceneAnalysis
    video: StockVideoResult
    keyword: Optional[str] = None
