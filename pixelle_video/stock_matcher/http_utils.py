"""
HTTP helpers: typed errors and retry with exponential backoff on 429 / 5xx.
"""

import asyncio
import random
from typing import Any, Optional

import httpx
from loguru import logger

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class StockMatcherError(Exception):
    """Base error for the stock matcher."""


class MissingCredentialsError(StockMatcherError):
    """Raised when a provider needs an API key that is not configured."""

    def __init__(self, provider: str, env_vars: list[str]):
        self.provider = provider
        self.env_vars = env_vars
        super().__init__(
            f"{provider}: missing credentials. Set {', '.join(env_vars)} in your .env file."
        )


class InvalidCredentialsError(StockMatcherError):
    """Raised on 401/403 from a provider."""

    def __init__(self, provider: str, status: int, detail: str = ""):
        self.provider = provider
        self.status = status
        msg = f"{provider}: API key rejected (HTTP {status})."
        if detail:
            msg += f" {detail[:200]}"
        super().__init__(msg)


class RateLimitExceededError(StockMatcherError):
    """Raised when retries are exhausted on HTTP 429."""


def _retry_after_seconds(response: httpx.Response) -> Optional[float]:
    value = response.headers.get("retry-after")
    if not value:
        # Pixabay exposes X-RateLimit-Reset (seconds until reset)
        value = response.headers.get("x-ratelimit-reset")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    """Exponential backoff with full jitter."""
    return min(cap, base * (2**attempt)) * (0.5 + random.random() / 2)


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    provider: str,
    max_retries: int = 4,
    base_delay: float = 1.0,
    **kwargs: Any,
) -> httpx.Response:
    """
    Perform a request, retrying on 429/5xx and transport errors.

    Raises InvalidCredentialsError on 401/403, RateLimitExceededError when 429
    persists, and httpx.HTTPStatusError for other non-2xx responses.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.TransportError as e:
            last_exc = e
            if attempt == max_retries:
                raise
            delay = backoff_delay(attempt, base_delay)
            logger.warning(f"{provider}: network error {e!r}, retrying in {delay:.1f}s")
            await asyncio.sleep(delay)
            continue

        if response.status_code in (401, 403):
            raise InvalidCredentialsError(provider, response.status_code, response.text)

        if response.status_code in RETRYABLE_STATUS:
            if attempt == max_retries:
                if response.status_code == 429:
                    raise RateLimitExceededError(
                        f"{provider}: rate limit still exceeded after {max_retries} retries"
                    )
                response.raise_for_status()
            delay = _retry_after_seconds(response) or backoff_delay(attempt, base_delay)
            logger.warning(
                f"{provider}: HTTP {response.status_code}, retry {attempt + 1}/{max_retries} "
                f"in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
            continue

        response.raise_for_status()
        return response

    # Unreachable, kept for type checkers
    raise last_exc or StockMatcherError(f"{provider}: request failed")
