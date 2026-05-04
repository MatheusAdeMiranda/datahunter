from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Retry

from scraper.app.core.entities import ScrapedItem, ScrapingJob, ScrapingResult
from scraper.app.core.exceptions import NetworkError
from worker.app.jobs.scraping_jobs import scrape_books, scrape_quotes
from worker.app.main import app


@pytest.fixture(autouse=True)
def celery_eager(monkeypatch: pytest.MonkeyPatch) -> None:
    """Executa tasks de forma sincrona (sem broker real) durante os testes."""
    app.conf.update(task_always_eager=True, task_eager_propagates=True)


def _make_result(n_items: int = 2, errors: list[str] | None = None) -> ScrapingResult:
    job = ScrapingJob(url="https://example.com", max_pages=1)
    items = [
        ScrapedItem(url="https://example.com", data={"title": f"Book {i}"}) for i in range(n_items)
    ]
    return ScrapingResult(job=job, items=items, errors=errors or [])


# ---------------------------------------------------------------------------
# scrape_books — sem persistencia
# ---------------------------------------------------------------------------


def test_scrape_books_returns_summary() -> None:
    result = _make_result(n_items=3)
    with patch("worker.app.jobs.scraping_jobs.BooksSpider") as MockSpider:
        MockSpider.return_value.crawl.return_value = result
        outcome: Any = scrape_books.apply(args=[]).get()
    assert outcome["items"] == 3
    assert outcome["errors"] == 0
    assert outcome["error_details"] == []
    assert outcome["persisted"] is False


def test_scrape_books_accepts_custom_url() -> None:
    result = _make_result(n_items=1)
    with patch("worker.app.jobs.scraping_jobs.BooksSpider") as MockSpider:
        MockSpider.return_value.crawl.return_value = result
        scrape_books.apply(args=["https://books.toscrape.com/catalogue/page-2.html"]).get()
    _, kwargs = MockSpider.call_args
    assert kwargs["base_url"] == "https://books.toscrape.com/catalogue/page-2.html"


def test_scrape_books_reports_crawl_errors() -> None:
    result = _make_result(n_items=0, errors=["ParseError on page 2"])
    with patch("worker.app.jobs.scraping_jobs.BooksSpider") as MockSpider:
        MockSpider.return_value.crawl.return_value = result
        outcome: Any = scrape_books.apply(args=[]).get()
    assert outcome["errors"] == 1
    assert "ParseError on page 2" in outcome["error_details"]


def test_scrape_books_creates_http_client_with_rate_limit() -> None:
    result = _make_result()
    with (
        patch("worker.app.jobs.scraping_jobs.HTTPClient") as MockClient,
        patch("worker.app.jobs.scraping_jobs.BooksSpider") as MockSpider,
    ):
        MockSpider.return_value.crawl.return_value = result
        scrape_books.apply(args=[]).get()
    MockClient.assert_called_once_with(requests_per_second=2.0)


def test_scrape_books_retries_on_network_error() -> None:
    """Em modo eager, autoretry_for levanta celery.exceptions.Retry na primeira
    tentativa de reenvio — comportamento correto: o worker re-enfileiraria a task."""
    with patch("worker.app.jobs.scraping_jobs.BooksSpider") as MockSpider:
        MockSpider.return_value.crawl.side_effect = NetworkError("timeout")
        with pytest.raises(Retry):
            scrape_books.apply(args=[]).get()


# ---------------------------------------------------------------------------
# scrape_books — com persistencia (database_url fornecido)
# ---------------------------------------------------------------------------


def test_scrape_books_persists_when_database_url_given() -> None:
    result = _make_result(n_items=2)
    mock_storage = MagicMock()
    with (
        patch("worker.app.jobs.scraping_jobs.BooksSpider") as MockSpider,
        patch("worker.app.jobs.scraping_jobs._make_storage", return_value=mock_storage),
    ):
        MockSpider.return_value.crawl.return_value = result
        outcome: Any = scrape_books.apply(kwargs={"database_url": "sqlite:///:memory:"}).get()
    assert outcome["persisted"] is True
    # storage foi passado ao spider
    _, kwargs = MockSpider.call_args
    assert kwargs["storage"] is mock_storage


def test_scrape_books_no_storage_when_no_database_url() -> None:
    result = _make_result()
    with (
        patch("worker.app.jobs.scraping_jobs.BooksSpider") as MockSpider,
        patch("worker.app.jobs.scraping_jobs.settings") as mock_settings,
    ):
        mock_settings.database_url = None
        MockSpider.return_value.crawl.return_value = result
        outcome: Any = scrape_books.apply(args=[]).get()
    assert outcome["persisted"] is False
    _, kwargs = MockSpider.call_args
    assert kwargs["storage"] is None


def test_make_storage_returns_none_when_no_url() -> None:
    from worker.app.jobs.scraping_jobs import _make_storage

    assert _make_storage(None) is None


def test_make_storage_creates_service_with_sqlite() -> None:
    from worker.app.jobs.scraping_jobs import _make_storage

    with (
        patch("worker.app.jobs.scraping_jobs.create_engine") as mock_engine,
        patch("worker.app.jobs.scraping_jobs.StorageService") as MockService,
    ):
        MockService.return_value.init_db.return_value = None
        _make_storage("sqlite:///:memory:")
    mock_engine.assert_called_once_with("sqlite:///:memory:")
    MockService.assert_called_once_with(mock_engine.return_value)
    MockService.return_value.init_db.assert_called_once()


# ---------------------------------------------------------------------------
# scrape_quotes
# ---------------------------------------------------------------------------


def test_scrape_quotes_returns_summary() -> None:
    result = _make_result(n_items=10)
    with patch("worker.app.jobs.scraping_jobs.QuotesSpider") as MockSpider:
        MockSpider.return_value.crawl.return_value = result
        outcome: Any = scrape_quotes.apply(args=[]).get()
    assert outcome["items"] == 10
    assert outcome["errors"] == 0
    assert outcome["persisted"] is False


def test_scrape_quotes_accepts_custom_api_url() -> None:
    result = _make_result(n_items=1)
    custom_url = "https://quotes.toscrape.com/api/quotes"
    with patch("worker.app.jobs.scraping_jobs.QuotesSpider") as MockSpider:
        MockSpider.return_value.crawl.return_value = result
        scrape_quotes.apply(args=[custom_url]).get()
    _, kwargs = MockSpider.call_args
    assert kwargs["api_url"] == custom_url


def test_scrape_quotes_creates_http_client_with_rate_limit() -> None:
    result = _make_result()
    with (
        patch("worker.app.jobs.scraping_jobs.HTTPClient") as MockClient,
        patch("worker.app.jobs.scraping_jobs.QuotesSpider") as MockSpider,
    ):
        MockSpider.return_value.crawl.return_value = result
        scrape_quotes.apply(args=[]).get()
    MockClient.assert_called_once_with(requests_per_second=2.0)


def test_scrape_quotes_retries_on_network_error() -> None:
    """Em modo eager, autoretry_for levanta celery.exceptions.Retry na primeira
    tentativa de reenvio — comportamento correto: o worker re-enfileiraria a task."""
    with patch("worker.app.jobs.scraping_jobs.QuotesSpider") as MockSpider:
        MockSpider.return_value.crawl.side_effect = NetworkError("connection refused")
        with pytest.raises(Retry):
            scrape_quotes.apply(args=[]).get()


# ---------------------------------------------------------------------------
# Celery Beat schedule
# ---------------------------------------------------------------------------


def test_beat_schedule_contains_books_task() -> None:
    schedule = app.conf.beat_schedule
    assert "scrape-books-hourly" in schedule
    assert schedule["scrape-books-hourly"]["task"] == ("worker.app.jobs.scraping_jobs.scrape_books")


def test_beat_schedule_contains_quotes_task() -> None:
    schedule = app.conf.beat_schedule
    assert "scrape-quotes-hourly" in schedule
    assert schedule["scrape-quotes-hourly"]["task"] == (
        "worker.app.jobs.scraping_jobs.scrape_quotes"
    )


def test_beat_schedule_interval_is_positive() -> None:
    schedule = app.conf.beat_schedule
    for name, entry in schedule.items():
        assert entry["schedule"] > 0, f"{name} tem intervalo invalido"
