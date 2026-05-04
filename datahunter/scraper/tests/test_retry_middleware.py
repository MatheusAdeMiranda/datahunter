from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from scrapy.http import Request, Response

from scraper.scrapy_project.middlewares.retry import ExponentialBackoffRetryMiddleware


def _middleware(
    max_retry_times: int = 3, backoff_base: float = 1.0
) -> ExponentialBackoffRetryMiddleware:
    return ExponentialBackoffRetryMiddleware(
        max_retry_times=max_retry_times, backoff_base=backoff_base
    )


@pytest.fixture()
def spider() -> MagicMock:
    return MagicMock()


def test_from_crawler_reads_settings() -> None:
    crawler = MagicMock()
    crawler.settings.getint.return_value = 5
    crawler.settings.getfloat.return_value = 2.0
    mw = ExponentialBackoffRetryMiddleware.from_crawler(crawler)
    assert mw.max_retry_times == 5
    assert mw.backoff_base == 2.0


def test_process_response_passes_through_200(spider: MagicMock) -> None:
    mw = _middleware()
    req = Request("https://example.com")
    resp = Response("https://example.com", status=200)
    assert mw.process_response(req, resp, spider) is resp


def test_process_response_retries_429(spider: MagicMock) -> None:
    mw = _middleware(backoff_base=1.0)
    req = Request("https://example.com")
    resp = Response("https://example.com", status=429)
    with patch("time.sleep") as mock_sleep:
        result = mw.process_response(req, resp, spider)
    assert isinstance(result, Request)
    assert result.meta["retry_times"] == 1
    mock_sleep.assert_called_once_with(1.0)  # backoff_base * 2^0


def test_process_response_backoff_doubles_each_attempt(spider: MagicMock) -> None:
    mw = _middleware(backoff_base=2.0)
    req = Request("https://example.com", meta={"retry_times": 2})
    resp = Response("https://example.com", status=503)
    with patch("time.sleep") as mock_sleep:
        mw.process_response(req, resp, spider)
    mock_sleep.assert_called_once_with(8.0)  # 2.0 * 2^2


def test_process_response_returns_response_on_max_retries(spider: MagicMock) -> None:
    mw = _middleware(max_retry_times=2)
    req = Request("https://example.com", meta={"retry_times": 2})
    resp = Response("https://example.com", status=500)
    result = mw.process_response(req, resp, spider)
    assert result is resp


def test_process_exception_retries_connection_error(spider: MagicMock) -> None:
    mw = _middleware()
    req = Request("https://example.com")
    with patch("time.sleep"):
        result = mw.process_exception(req, ConnectionError(), spider)
    assert isinstance(result, Request)
    assert result.meta["retry_times"] == 1


def test_process_exception_retries_timeout(spider: MagicMock) -> None:
    mw = _middleware()
    req = Request("https://example.com")
    with patch("time.sleep"):
        result = mw.process_exception(req, TimeoutError(), spider)
    assert isinstance(result, Request)


def test_process_exception_ignores_other_errors(spider: MagicMock) -> None:
    mw = _middleware()
    req = Request("https://example.com")
    result = mw.process_exception(req, ValueError("not retried"), spider)
    assert result is None
