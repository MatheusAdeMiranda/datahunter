from __future__ import annotations

from unittest.mock import call, patch

import httpx
import pytest
import respx

from scraper.app.core.exceptions import NetworkError
from scraper.app.core.http_client import RETRYABLE_STATUS_CODES, HTTPClient
from scraper.app.core.utils import _DEFAULT_HEADERS

URL = "https://example.com/page"


# ── Successful requests ───────────────────────────────────────────────────────


@respx.mock
def test_get_returns_response() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text="ok"))
    with HTTPClient() as client:
        response = client.get(URL)
    assert response.status_code == 200
    assert response.text == "ok"


@respx.mock
def test_post_returns_response() -> None:
    respx.post(URL).mock(return_value=httpx.Response(201, text="created"))
    with HTTPClient() as client:
        response = client.post(URL, content=b"data")
    assert response.status_code == 201


# ── Default headers ───────────────────────────────────────────────────────────


@respx.mock
def test_default_user_agent_is_sent() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200))
    with HTTPClient() as client:
        client.get(URL)
    sent_headers = route.calls.last.request.headers
    assert sent_headers["user-agent"] == _DEFAULT_HEADERS["User-Agent"]


@respx.mock
def test_extra_headers_are_merged() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200))
    with HTTPClient(headers={"X-Custom": "value"}) as client:
        client.get(URL)
    sent_headers = route.calls.last.request.headers
    assert sent_headers["x-custom"] == "value"
    assert "user-agent" in sent_headers


# ── Retry on transient errors ─────────────────────────────────────────────────


@pytest.mark.parametrize("status_code", sorted(RETRYABLE_STATUS_CODES))
@respx.mock
def test_retries_on_retryable_status(status_code: int) -> None:
    # Two failures then success
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(status_code),
            httpx.Response(status_code),
            httpx.Response(200, text="ok"),
        ]
    )
    with HTTPClient(max_attempts=3) as client:
        response = client.get(URL)
    assert response.status_code == 200


@respx.mock
def test_raises_network_error_after_all_retries_exhausted() -> None:
    respx.get(URL).mock(return_value=httpx.Response(500))
    with HTTPClient(max_attempts=3) as client, pytest.raises(NetworkError, match="HTTP 500"):
        client.get(URL)


@respx.mock
def test_exact_retry_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fetch attempts exactly max_attempts times on retryable HTTP status."""
    calls: list[int] = []

    def fake_request(*_: object, **__: object) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    with HTTPClient(max_attempts=4) as client:
        monkeypatch.setattr(client._client, "request", fake_request)
        with pytest.raises(NetworkError):
            client.get(URL)

    assert len(calls) == 4


@respx.mock
def test_exact_retry_count_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fetch attempts exactly max_attempts times on connection-level errors."""
    calls: list[int] = []

    def fake_request(*_: object, **__: object) -> httpx.Response:
        calls.append(1)
        raise httpx.TimeoutException("timed out")

    with HTTPClient(max_attempts=3) as client:
        monkeypatch.setattr(client._client, "request", fake_request)
        with pytest.raises(NetworkError):
            client.get(URL)

    assert len(calls) == 3


# ── Connection-level errors ───────────────────────────────────────────────────


@respx.mock
def test_timeout_raises_network_error() -> None:
    respx.get(URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with HTTPClient(max_attempts=1) as client, pytest.raises(NetworkError, match="timed out"):
        client.get(URL)


@respx.mock
def test_connect_error_raises_network_error() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError("refused"))
    with (
        HTTPClient(max_attempts=1) as client,
        pytest.raises(NetworkError, match="connection failed"),
    ):
        client.get(URL)


@respx.mock
def test_network_error_wraps_original_exception() -> None:
    respx.get(URL).mock(side_effect=httpx.TimeoutException("bang"))
    with HTTPClient(max_attempts=1) as client, pytest.raises(NetworkError) as exc_info:
        client.get(URL)
    assert isinstance(exc_info.value.__cause__, httpx.TimeoutException)


# ── Non-retryable client errors ───────────────────────────────────────────────


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
@respx.mock
def test_non_retryable_4xx_returned_as_is(status_code: int) -> None:
    respx.get(URL).mock(return_value=httpx.Response(status_code))
    with HTTPClient(max_attempts=3) as client:
        response = client.get(URL)
    assert response.status_code == status_code


# ── Context manager ───────────────────────────────────────────────────────────


def test_context_manager_closes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []
    client = HTTPClient()
    monkeypatch.setattr(client._client, "close", lambda: closed.append(True))
    with client:
        pass
    assert closed == [True]


# ── Exponential backoff ───────────────────────────────────────────────────────


@respx.mock
def test_no_sleep_between_retries_when_backoff_base_zero() -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200)])
    with (
        patch("scraper.app.core.http_client.time.sleep") as mock_sleep,
        HTTPClient(max_attempts=3, backoff_base=0.0) as client,
    ):
        client.get(URL)
    mock_sleep.assert_not_called()


@respx.mock
def test_exponential_backoff_between_retries() -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(503)])
    with (
        patch("scraper.app.core.http_client.time.sleep") as mock_sleep,
        HTTPClient(max_attempts=3, backoff_base=1.0) as client,
        pytest.raises(NetworkError),
    ):
        client.get(URL)
    # sleep after attempt 1 (1.0 s) and attempt 2 (2.0 s), not after last attempt
    assert mock_sleep.call_args_list == [call(1.0), call(2.0)]


# ── Per-domain rate limiting ──────────────────────────────────────────────────


@respx.mock
def test_rate_limit_sleeps_between_requests_to_same_domain() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200))
    respx.get(URL + "/2").mock(return_value=httpx.Response(200))

    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    fake_time = 0.0

    def fake_monotonic() -> float:
        return fake_time

    with (
        patch("scraper.app.core.http_client.time.sleep", side_effect=fake_sleep),
        patch("scraper.app.core.http_client.time.monotonic", side_effect=fake_monotonic),
        HTTPClient(requests_per_second=2.0) as client,
    ):
        client.get(URL)  # first request: no sleep
        client.get(URL + "/2")  # second rapid request: should sleep

    assert len(sleep_calls) == 1
    assert sleep_calls[0] > 0


@respx.mock
def test_rate_limit_independent_per_domain() -> None:
    """Requests to different domains should not interfere with each other."""
    url_a = "https://domain-a.com/page"
    url_b = "https://domain-b.com/page"
    respx.get(url_a).mock(return_value=httpx.Response(200))
    respx.get(url_b).mock(return_value=httpx.Response(200))

    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    fake_time = 0.0

    def fake_monotonic() -> float:
        return fake_time

    with (
        patch("scraper.app.core.http_client.time.sleep", side_effect=fake_sleep),
        patch("scraper.app.core.http_client.time.monotonic", side_effect=fake_monotonic),
        HTTPClient(requests_per_second=2.0) as client,
    ):
        client.get(url_a)
        client.get(url_b)  # different domain: no sleep

    assert sleep_calls == []


@respx.mock
def test_no_rate_limit_when_requests_per_second_is_none() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200))
    respx.get(URL + "/2").mock(return_value=httpx.Response(200))

    with (
        patch("scraper.app.core.http_client.time.sleep") as mock_sleep,
        HTTPClient(requests_per_second=None) as client,
    ):
        client.get(URL)
        client.get(URL + "/2")

    mock_sleep.assert_not_called()
