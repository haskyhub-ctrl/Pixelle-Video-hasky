"""
Credential management for stock providers and the LLM backend.

All secrets are read from environment variables, optionally loaded from a
`.env` file via python-dotenv. Nothing is written back to disk.

Premium providers are accessed only through their official, licensed APIs:
full-resolution, watermark-free files come from the provider's licensing /
download endpoint and count against your subscription.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from .http_utils import MissingCredentialsError

# Environment variable names per provider
PROVIDER_ENV_VARS: dict[str, list[str]] = {
    "pexels": ["PEXELS_API_KEY"],
    "pixabay": ["PIXABAY_API_KEY"],
    "mixkit": [],
    "shutterstock": ["SHUTTERSTOCK_API_TOKEN"],
    "storyblocks": [
        "STORYBLOCKS_PUBLIC_KEY",
        "STORYBLOCKS_PRIVATE_KEY",
        "STORYBLOCKS_USER_ID",
        "STORYBLOCKS_PROJECT_ID",
    ],
}

OPTIONAL_ENV_VARS: dict[str, list[str]] = {
    "shutterstock": ["SHUTTERSTOCK_SUBSCRIPTION_ID", "SHUTTERSTOCK_VIDEO_SIZE"],
}


def load_env_file(path: Optional[str | Path] = None) -> bool:
    """Load a .env file into os.environ (existing variables win)."""
    env_path = Path(path) if path else Path.cwd() / ".env"
    if not env_path.exists():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:
        # Minimal fallback parser: KEY=VALUE lines
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return True
    return load_dotenv(env_path, override=False)


@dataclass
class ProviderCredentials:
    provider: str
    values: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)


@dataclass
class LLMSettings:
    backend: str = ""  # "openai" | "anthropic" | "" (disabled)
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    # Optional separate model for thumbnail rating (must accept images)
    vision_model: str = ""

    @property
    def enabled(self) -> bool:
        if self.backend == "anthropic":
            return True  # SDK resolves ANTHROPIC_API_KEY / profiles itself
        return bool(self.backend and self.model and (self.api_key or self.base_url))


class AuthManager:
    """Reads provider and LLM credentials from the environment."""

    def __init__(self, env_file: Optional[str | Path] = None, overrides: Optional[dict] = None):
        load_env_file(env_file)
        self._overrides = dict(overrides or {})

    def _env(self, key: str) -> str:
        if key in self._overrides:
            return str(self._overrides[key] or "")
        return os.environ.get(key, "").strip()

    def set_override(self, key: str, value: str) -> None:
        """Set a credential for this session only (e.g. from the UI)."""
        self._overrides[key] = value

    def is_configured(self, provider: str) -> bool:
        return all(self._env(k) for k in PROVIDER_ENV_VARS.get(provider, []))

    def missing_vars(self, provider: str) -> list[str]:
        return [k for k in PROVIDER_ENV_VARS.get(provider, []) if not self._env(k)]

    def get(self, provider: str) -> ProviderCredentials:
        """Return credentials, raising MissingCredentialsError if incomplete."""
        missing = self.missing_vars(provider)
        if missing:
            raise MissingCredentialsError(provider, missing)
        keys = PROVIDER_ENV_VARS.get(provider, []) + OPTIONAL_ENV_VARS.get(provider, [])
        return ProviderCredentials(provider, {k: self._env(k) for k in keys})

    def status(self) -> dict[str, dict]:
        """Human-readable configuration status for every provider."""
        return {
            p: {"configured": self.is_configured(p), "missing": self.missing_vars(p)}
            for p in PROVIDER_ENV_VARS
        }

    def llm_settings(self) -> LLMSettings:
        """
        LLM settings from STOCK_LLM_* env vars, falling back to the Pixelle-Video
        config.yaml `llm` section (OpenAI-compatible) when present.
        """
        backend = self._env("STOCK_LLM_BACKEND").lower()
        settings = LLMSettings(
            backend=backend,
            api_key=self._env("STOCK_LLM_API_KEY"),
            base_url=self._env("STOCK_LLM_BASE_URL"),
            model=self._env("STOCK_LLM_MODEL"),
        )
        vision_model = self._env("STOCK_LLM_VISION_MODEL")
        settings.vision_model = vision_model
        if backend == "anthropic":
            settings.model = settings.model or "claude-opus-5-5"
            return settings
        if backend in ("", "openai", "ollama") and not settings.model:
            try:
                from pixelle_video.config import config_manager

                llm = config_manager.config.llm
                if llm.api_key or llm.base_url:
                    settings = LLMSettings("openai", llm.api_key, llm.base_url, llm.model,
                                           vision_model)
            except Exception as e:  # config.yaml absent or invalid
                logger.debug(f"No Pixelle LLM config available: {e}")
        if backend == "ollama":
            settings.backend = "openai"
            settings.base_url = settings.base_url or "http://localhost:11434/v1"
            settings.api_key = settings.api_key or "ollama"
        if not settings.backend and settings.model:
            settings.backend = "openai"  # model + key given without a backend
        return settings
