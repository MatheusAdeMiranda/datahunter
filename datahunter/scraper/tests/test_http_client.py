from __future__ import annotations

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
    with HTTPClient(max_retries=3) as client:
        response = client.get(URL)
    assert response.status_code == 200


@respx.mock
def test_raises_network_error_after_all_retries_exhausted() -> None:
    respx.get(URL).mock(return_value=httpx.Response(500))
    with HTTPClient(max_retries=3) as client, pytest.raises(NetworkError, match="HTTP 500"):
        client.get(URL)


@respx.mock
def test_exact_retry_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that _fetch attempts exactly max_retries times, no more."""
    calls: list[int] = []

    def fake_request(*_: object, **__: object) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    with HTTPClient(max_retries=4) as client:
        monkeypatch.setattr(client._client, "request", fake_request)
        with pytest.raises(NetworkError):
            client.get(URL)

    assert len(calls) == 4


# ── Connection-level errors ───────────────────────────────────────────────────


@respx.mock
def test_timeout_raises_network_error() -> None:
    respx.get(URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with HTTPClient(max_retries=1) as client, pytest.raises(NetworkError, match="timed out"):
        client.get(URL)


@respx.mock
def test_connect_error_raises_network_error() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError("refused"))
    with (
        HTTPClient(max_retries=1) as client,
        pytest.raises(NetworkError, match="connection failed"),
    ):
        client.get(URL)


@respx.mock
def test_network_error_wraps_original_exception() -> None:
    respx.get(URL).mock(side_effect=httpx.TimeoutException("bang"))
    with HTTPClient(max_retries=1) as client, pytest.raises(NetworkError) as exc_info:
        client.get(URL)
    assert isinstance(exc_info.value.__cause__, httpx.TimeoutException)


# ── Non-retryable client errors ───────────────────────────────────────────────


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
@respx.mock
def test_non_retryable_4xx_returned_as_is(status_code: int) -> None:
    respx.get(URL).mock(return_value=httpx.Response(status_code))
    with HTTPClient(max_retries=3) as client:
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
