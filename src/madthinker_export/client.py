"""HTTP client for the MadThinker Catch Reports Export API.

The endpoint is a single ``GET`` that returns a page of rows plus an opaque
cursor. This module encodes the wire contract exactly:

* auth via the ``x-tca-api-key`` header,
* ``since`` on the first-ever call, ``cursor`` on every later call,
* a ``limit`` (default 1000, max 5000),
* error mapping: 401/400 are the caller's fault and never retried; 429 and
  5xx (and raw connection failures) are transient and retried with bounded
  exponential backoff plus jitter.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

import requests

DEFAULT_LIMIT = 1000
MAX_LIMIT = 5000
DEFAULT_TIMEOUT = 30


class ExportError(Exception):
    """Base class for every error raised by the client."""

    retryable = False


class AuthError(ExportError):
    """401 — missing, wrong, or revoked API key. Caller's fault."""


class BadRequestError(ExportError):
    """400 — malformed cursor / since / limit. Caller's fault."""


class RateLimitError(ExportError):
    """429 — server rate limit (60 req/min). Transient; back off and retry."""

    retryable = True


class ServerError(ExportError):
    """5xx or a raw connection failure. Transient; retry."""

    retryable = True


def _error_message(response) -> str:
    """Pull the ``{"error": "..."}`` message, tolerating a non-JSON body."""
    try:
        body = response.json()
    except Exception:
        return ""
    if isinstance(body, dict):
        return body.get("error", "")
    return ""


class ExportClient:
    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        limit: int = DEFAULT_LIMIT,
        session=None,
        max_retries: int = 4,
        base_backoff: float = 1.0,
        max_backoff: float = 60.0,
        timeout: float = DEFAULT_TIMEOUT,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}, got {limit}")
        self.url = url
        self.api_key = api_key
        self.limit = limit
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self.timeout = timeout
        self._sleep = sleep
        self._rng = rng or random.Random()

    def fetch(self, *, since: str | None = None, cursor: str | None = None) -> dict:
        """Fetch one page. ``cursor`` wins over ``since`` when both are given."""
        params: dict[str, object] = {"limit": self.limit}
        if cursor is not None:
            params["cursor"] = cursor
        elif since is not None:
            params["since"] = since

        attempt = 0
        while True:
            try:
                return self._request(params)
            except ExportError as exc:
                if not exc.retryable or attempt >= self.max_retries:
                    raise
                self._sleep(self._backoff(attempt))
                attempt += 1

    def _request(self, params: dict) -> dict:
        headers = {"x-tca-api-key": self.api_key}
        try:
            response = self.session.get(
                self.url, headers=headers, params=params, timeout=self.timeout
            )
        except requests.exceptions.RequestException as exc:
            raise ServerError(f"Connection error: {exc}") from exc

        status = response.status_code
        if status == 200:
            return response.json()

        message = _error_message(response) or f"HTTP {status}"
        if status == 401:
            raise AuthError(message)
        if status == 400:
            raise BadRequestError(message)
        if status == 429:
            raise RateLimitError(message)
        if status >= 500:
            raise ServerError(message)
        raise ExportError(f"Unexpected status {status}: {message}")

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter, capped at ``max_backoff``."""
        ceiling = min(self.max_backoff, self.base_backoff * (2**attempt))
        return self._rng.uniform(0, ceiling)
