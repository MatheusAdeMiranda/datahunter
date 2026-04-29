from __future__ import annotations

import logging
import time
import urllib.parse
from types import TracebackType
from typing import Any

import httpx

from scraper.app.core.exceptions import NetworkError
from scraper.app.core.utils import build_headers

logger = logging.getLogger(__name__)

# Status codes that indicate a transient server problem worth retrying.
# 429 = rate-limited, 5xx = server-side failure.
# Client errors (4xx except 429) are returned as-is so the caller can decide.
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class HTTPClient:
    """Synchronous HTTP client wrapping httpx.Client with retry and logging.

    Uses a persistent session for connection pooling (one TCP handshake per
    host instead of one per request). Call close() or use as a context manager.

    Per-domain rate limiting: when *requests_per_second* is set, at most that
    many requests are dispatched per domain per second (sliding window).
    Exponential backoff between retries: sleep backoff_base * 2^(attempt-1) s.
    """

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        max_attempts: int = 3,
        headers: dict[str, str] | None = None,
        requests_per_second: float | None = None,
        backoff_base: float = 0.0,
    ) -> None:
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._requests_per_second = requests_per_second
        self._last_request_time: dict[str, float] = {}
        self._client = httpx.Client(
            headers=build_headers(headers),
            timeout=timeout,
            follow_redirects=True,
        )

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._fetch("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._fetch("POST", url, **kwargs)

    def _wait_for_rate_limit(self, url: str) -> None:
        """Block until dispatching *url* respects the per-domain rate limit."""
        if self._requests_per_second is None:
            return
        domain = urllib.parse.urlparse(url).netloc
        period = 1.0 / self._requests_per_second
        last = self._last_request_time.get(domain)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < period:
                time.sleep(period - elapsed)
        self._last_request_time[domain] = time.monotonic()

    def _fetch(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: NetworkError | None = None
        for attempt in range(1, self._max_attempts + 1):
            self._wait_for_rate_limit(url)
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.TimeoutException as err:
                last_exc = NetworkError(f"{method} {url}: timed out")
                last_exc.__cause__ = err
            except httpx.ConnectError as err:
                last_exc = NetworkError(f"{method} {url}: connection failed")
                last_exc.__cause__ = err
            else:
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    logger.debug("%s %s → %d", method, url, response.status_code)
                    return response
                last_exc = NetworkError(f"{method} {url}: HTTP {response.status_code}")

            logger.warning(
                "attempt %d/%d failed for %s %s: %s",
                attempt,
                self._max_attempts,
                method,
                url,
                last_exc,
            )
            if self._backoff_base > 0 and attempt < self._max_attempts:
                time.sleep(self._backoff_base * (2 ** (attempt - 1)))

        assert last_exc is not None
        raise last_exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HTTPClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
