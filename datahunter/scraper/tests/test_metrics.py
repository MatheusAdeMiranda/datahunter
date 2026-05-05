from __future__ import annotations

from prometheus_client import generate_latest

from scraper.app.core.metrics import (
    METRICS_REGISTRY,
    pages_scraped_total,
    scraping_duration_seconds,
    scraping_errors_total,
)


def _metrics_text() -> str:
    return generate_latest(METRICS_REGISTRY).decode()


def test_pages_scraped_counter_exists() -> None:
    assert pages_scraped_total is not None


def test_scraping_errors_counter_exists() -> None:
    assert scraping_errors_total is not None


def test_scraping_duration_histogram_exists() -> None:
    assert scraping_duration_seconds is not None


def test_pages_scraped_counter_increments() -> None:
    pages_scraped_total.labels(spider="test_spider").inc(3)
    output = _metrics_text()
    assert "datahunter_pages_scraped_total" in output
    assert 'spider="test_spider"' in output


def test_scraping_errors_counter_increments() -> None:
    scraping_errors_total.labels(spider="test_spider", error_type="parse").inc(1)
    output = _metrics_text()
    assert "datahunter_scraping_errors_total" in output
    assert 'error_type="parse"' in output


def test_scraping_duration_histogram_observes() -> None:
    scraping_duration_seconds.labels(spider="test_spider").observe(1.5)
    output = _metrics_text()
    assert "datahunter_scraping_duration_seconds" in output


def test_metrics_registry_is_isolated() -> None:
    """METRICS_REGISTRY nao deve ser o registry global do prometheus_client."""
    from prometheus_client import REGISTRY as GLOBAL_REGISTRY

    assert METRICS_REGISTRY is not GLOBAL_REGISTRY
