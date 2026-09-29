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
