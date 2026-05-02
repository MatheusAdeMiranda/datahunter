from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import urllib.parse
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any

import httpx

from scraper.app.core.exceptions import NetworkError
from scraper.app.core.http_client import RETRYABLE_STATUS_CODES
from scraper.app.core.utils import build_headers

logger = logging.getLogger(__name__)


class AsyncHTTPClient:
    """Async HTTP client wrapping httpx.AsyncClient with retry and logging.

    Drop-in async equivalent of HTTPClient. Use as an async context manager.
    Pass an asyncio.Semaphore to cap how many requests run concurrently.
    Exponential backoff between retries: sleep backoff_base * 2^(attempt-1) s.

    Note: per-domain rate limiting is not concurrency-safe. When multiple
    coroutines share one client, the sliding window may be violated between
    the check and the update across an await point. Fix in Dia 19+ with an
    asyncio.Lock per domain.
    """

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        max_attempts: int = 3,
        headers: dict[str, str] | None = None,
        requests_per_second: float | None = None,
        backoff_base: float = 0.0,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._requests_per_second = requests_per_second
        self._semaphore = semaphore
        self._last_request_time: dict[str, float] = {}
        self._client = httpx.AsyncClient(
            headers=build_headers(headers),
            timeout=timeout,
            follow_redirects=True,
        )

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._fetch("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._fetch("POST", url, **kwargs)

    async def _wait_for_rate_limit(self, url: str) -> None:
        if self._requests_per_second is None:
            return
        domain = urllib.parse.urlparse(url).netloc
        period = 1.0 / self._requests_per_second
        last = self._last_request_time.get(domain)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < period:
                await asyncio.sleep(period - elapsed)
        self._last_request_time[domain] = time.monotonic()

    async def _fetch(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: NetworkError | None = None
        lock: AbstractAsyncContextManager[Any] = (
            self._semaphore if self._semaphore is not None else contextlib.nullcontext()
        )
        for attempt in range(1, self._max_attempts + 1):
            async with lock:
                await self._wait_for_rate_limit(url)
                try:
                    response = await self._client.request(method, url, **kwargs)
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
                await asyncio.sleep(self._backoff_base * (2 ** (attempt - 1)))

        assert last_exc is not None
        raise last_exc

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncHTTPClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()
