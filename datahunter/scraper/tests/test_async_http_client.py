from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, call, patch

import httpx
import pytest
import respx

from scraper.app.core.async_http_client import AsyncHTTPClient
from scraper.app.core.exceptions import NetworkError
from scraper.app.core.http_client import RETRYABLE_STATUS_CODES
from scraper.app.core.utils import _DEFAULT_HEADERS

URL = "https://example.com/page"


# ── Successful requests ───────────────────────────────────────────────────────


@respx.mock
async def test_get_returns_response() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text="ok"))
    async with AsyncHTTPClient() as client:
        response = await client.get(URL)
    assert response.status_code == 200
    assert response.text == "ok"


@respx.mock
async def test_post_returns_response() -> None:
    respx.post(URL).mock(return_value=httpx.Response(201, text="created"))
    async with AsyncHTTPClient() as client:
        response = await client.post(URL, content=b"data")
    assert response.status_code == 201


# ── Default headers ───────────────────────────────────────────────────────────


@respx.mock
async def test_default_user_agent_is_sent() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200))
    async with AsyncHTTPClient() as client:
        await client.get(URL)
    sent_headers = route.calls.last.request.headers
    assert sent_headers["user-agent"] == _DEFAULT_HEADERS["User-Agent"]


@respx.mock
async def test_extra_headers_are_merged() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200))
    async with AsyncHTTPClient(headers={"X-Custom": "value"}) as client:
        await client.get(URL)
    sent_headers = route.calls.last.request.headers
    assert sent_headers["x-custom"] == "value"
    assert "user-agent" in sent_headers


# ── Retry on transient errors ─────────────────────────────────────────────────


@pytest.mark.parametrize("status_code", sorted(RETRYABLE_STATUS_CODES))
@respx.mock
async def test_retries_on_retryable_status(status_code: int) -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(status_code),
            httpx.Response(status_code),
            httpx.Response(200, text="ok"),
        ]
    )
    async with AsyncHTTPClient(max_attempts=3) as client:
        response = await client.get(URL)
    assert response.status_code == 200


@respx.mock
async def test_raises_network_error_after_all_retries_exhausted() -> None:
    respx.get(URL).mock(return_value=httpx.Response(500))
    with pytest.raises(NetworkError, match="HTTP 500"):
        async with AsyncHTTPClient(max_attempts=3) as client:
            await client.get(URL)


@respx.mock
async def test_exact_retry_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fetch attempts exactly max_attempts times on retryable HTTP status."""
    calls: list[int] = []

    async def fake_request(*_: object, **__: object) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    async with AsyncHTTPClient(max_attempts=4) as client:
        monkeypatch.setattr(client._client, "request", fake_request)
        with pytest.raises(NetworkError):
            await client.get(URL)

    assert len(calls) == 4


@respx.mock
async def test_exact_retry_count_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fetch attempts exactly max_attempts times on connection-level errors."""
    calls: list[int] = []

    async def fake_request(*_: object, **__: object) -> httpx.Response:
        calls.append(1)
        raise httpx.TimeoutException("timed out")

    async with AsyncHTTPClient(max_attempts=3) as client:
        monkeypatch.setattr(client._client, "request", fake_request)
        with pytest.raises(NetworkError):
            await client.get(URL)

    assert len(calls) == 3


# ── Connection-level errors ───────────────────────────────────────────────────


@respx.mock
async def test_timeout_raises_network_error() -> None:
    respx.get(URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(NetworkError, match="timed out"):
        async with AsyncHTTPClient(max_attempts=1) as client:
            await client.get(URL)


@respx.mock
async def test_connect_error_raises_network_error() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(NetworkError, match="connection failed"):
        async with AsyncHTTPClient(max_attempts=1) as client:
            await client.get(URL)


@respx.mock
async def test_network_error_wraps_original_exception() -> None:
    respx.get(URL).mock(side_effect=httpx.TimeoutException("bang"))
    with pytest.raises(NetworkError) as exc_info:
        async with AsyncHTTPClient(max_attempts=1) as client:
            await client.get(URL)
    assert isinstance(exc_info.value.__cause__, httpx.TimeoutException)


# ── Non-retryable client errors ───────────────────────────────────────────────


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
@respx.mock
async def test_non_retryable_4xx_returned_as_is(status_code: int) -> None:
    respx.get(URL).mock(return_value=httpx.Response(status_code))
    async with AsyncHTTPClient(max_attempts=3) as client:
        response = await client.get(URL)
    assert response.status_code == status_code


# ── Context manager ───────────────────────────────────────────────────────────


async def test_context_manager_closes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []
    client = AsyncHTTPClient()
    mock_close = AsyncMock(side_effect=lambda: closed.append(True))
    monkeypatch.setattr(client._client, "aclose", mock_close)
    async with client:
        pass
    assert closed == [True]


# ── Exponential backoff ───────────────────────────────────────────────────────


@respx.mock
async def test_no_sleep_between_retries_when_backoff_base_zero() -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200)])
    with patch(
        "scraper.app.core.async_http_client.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        async with AsyncHTTPClient(max_attempts=3, backoff_base=0.0) as client:
            await client.get(URL)
    mock_sleep.assert_not_called()


@respx.mock
async def test_exponential_backoff_between_retries() -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(503)])
    with patch(
        "scraper.app.core.async_http_client.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        async with AsyncHTTPClient(max_attempts=3, backoff_base=1.0) as client:
            with pytest.raises(NetworkError):
                await client.get(URL)
    # sleep after attempt 1 (1.0 s) and attempt 2 (2.0 s), not after last attempt
    assert mock_sleep.await_args_list == [call(1.0), call(2.0)]


# ── Per-domain rate limiting ──────────────────────────────────────────────────


@respx.mock
async def test_rate_limit_sleeps_between_requests_to_same_domain() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200))
    respx.get(URL + "/2").mock(return_value=httpx.Response(200))

    sleep_calls: list[float] = []
    fake_time = 0.0

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    def fake_monotonic() -> float:
        return fake_time

    with (
        patch("scraper.app.core.async_http_client.asyncio.sleep", side_effect=fake_sleep),
        patch("scraper.app.core.async_http_client.time.monotonic", side_effect=fake_monotonic),
    ):
        async with AsyncHTTPClient(requests_per_second=2.0) as client:
            await client.get(URL)
            await client.get(URL + "/2")

    assert len(sleep_calls) == 1
    assert sleep_calls[0] > 0


@respx.mock
async def test_rate_limit_independent_per_domain() -> None:
    url_a = "https://domain-a.com/page"
    url_b = "https://domain-b.com/page"
    respx.get(url_a).mock(return_value=httpx.Response(200))
    respx.get(url_b).mock(return_value=httpx.Response(200))

    sleep_calls: list[float] = []
    fake_time = 0.0

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    def fake_monotonic() -> float:
        return fake_time

    with (
        patch("scraper.app.core.async_http_client.asyncio.sleep", side_effect=fake_sleep),
        patch("scraper.app.core.async_http_client.time.monotonic", side_effect=fake_monotonic),
    ):
        async with AsyncHTTPClient(requests_per_second=2.0) as client:
            await client.get(url_a)
            await client.get(url_b)  # different domain: no sleep

    assert sleep_calls == []


@respx.mock
async def test_no_rate_limit_when_requests_per_second_is_none() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200))
    respx.get(URL + "/2").mock(return_value=httpx.Response(200))

    with patch(
        "scraper.app.core.async_http_client.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        async with AsyncHTTPClient(requests_per_second=None) as client:
            await client.get(URL)
            await client.get(URL + "/2")

    mock_sleep.assert_not_called()


# ── Semaphore ─────────────────────────────────────────────────────────────────


async def test_semaphore_limits_concurrency() -> None:
    """At most semaphore N requests run concurrently."""
    in_flight = 0
    peak_in_flight = 0

    async def slow_request(*args: Any, **kwargs: Any) -> httpx.Response:
        nonlocal in_flight, peak_in_flight
        in_flight += 1
        peak_in_flight = max(peak_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, text="ok")

    semaphore = asyncio.Semaphore(2)
    async with AsyncHTTPClient(semaphore=semaphore) as client:
        with patch.object(client._client, "request", slow_request):
            urls = [f"https://example.com/{i}" for i in range(6)]
            await asyncio.gather(*[client.get(url) for url in urls])

    assert peak_in_flight <= 2


async def test_no_semaphore_allows_full_concurrency() -> None:
    """Without a semaphore all requests can run concurrently."""
    peak_in_flight = 0
    in_flight = 0

    async def slow_request(*args: Any, **kwargs: Any) -> httpx.Response:
        nonlocal in_flight, peak_in_flight
        in_flight += 1
        peak_in_flight = max(peak_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, text="ok")

    async with AsyncHTTPClient() as client:
        with patch.object(client._client, "request", slow_request):
            urls = [f"https://example.com/{i}" for i in range(4)]
            await asyncio.gather(*[client.get(url) for url in urls])

    assert peak_in_flight > 1
