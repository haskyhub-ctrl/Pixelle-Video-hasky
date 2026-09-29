"""
Script-to-stock-video matcher.

    script text -> ScriptParser (scenes + search queries)
                -> StockSearchEngine (Pexels / Pixabay / Mixkit / Shutterstock / Storyblocks)
                -> Downloader (scene_NN_keyword.mp4 + manifest.json)

Entry points:
    python -m pixelle_video.stock_matcher --help         (CLI)
    streamlit run pixelle_video/stock_matcher/app.py     (standalone web UI)
    web/pages/3_🎞️_Stock_Matcher.py                      (inside the Pixelle-Video web UI)
"""

from .auth_manager import AuthManager, LLMSettings
from .downloader import CustomClip, Downloader, DownloadResult
from .http_utils import (
    InvalidCredentialsError,
    MissingCredentialsError,
    RateLimitExceededError,
    StockMatcherError,
)
from .models import DownloadItem, SceneAnalysis, SearchOutcome, StockVideoResult
from .nlp_parser import ScriptParser, simplify_queries
from .stock_searcher import (
    PROVIDER_CLASSES,
    BaseStockProvider,
    StockSearchEngine,
)

__all__ = [
    "AuthManager",
    "LLMSettings",
    "ScriptParser",
    "simplify_queries",
    "StockSearchEngine",
    "BaseStockProvider",
    "PROVIDER_CLASSES",
    "Downloader",
    "DownloadResult",
    "CustomClip",
    "SceneAnalysis",
    "StockVideoResult",
    "SearchOutcome",
    "DownloadItem",
    "StockMatcherError",
    "MissingCredentialsError",
    "InvalidCredentialsError",
    "RateLimitExceededError",
]
