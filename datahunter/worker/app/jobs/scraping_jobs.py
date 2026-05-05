from __future__ import annotations

import logging
import time
from typing import Any

import structlog.contextvars
from sqlalchemy import create_engine

from scraper.app.core.exceptions import NetworkError
from scraper.app.core.http_client import HTTPClient
from scraper.app.core.metrics import (
    pages_scraped_total,
    scraping_duration_seconds,
    scraping_errors_total,
)
from scraper.app.spiders.books_spider import BooksSpider
from scraper.app.spiders.quotes_spider import QuotesSpider
from scraper.app.storage.service import StorageService
from worker.app.config import settings
from worker.app.main import app

logger = logging.getLogger(__name__)

_BOOKS_START_URL = "https://books.toscrape.com/catalogue/page-1.html"
_QUOTES_API_URL = "https://quotes.toscrape.com/api/quotes"


def _make_storage(database_url: str | None) -> StorageService | None:
    """Cria um StorageService se database_url for fornecida, senao retorna None."""
    if not database_url:
        return None
    engine = create_engine(database_url)
    storage = StorageService(engine)
    storage.init_db()
    return storage


@app.task(
    bind=True,
    name="worker.app.jobs.scraping_jobs.scrape_books",
    autoretry_for=(NetworkError, ConnectionError, TimeoutError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def scrape_books(
    self: Any,
    start_url: str = _BOOKS_START_URL,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Dispara o BooksSpider e persiste os resultados no banco se database_url for fornecida.

    Usa DATAHUNTER_DATABASE_URL das settings como fallback quando database_url nao e passado.
    Em caso de NetworkError, ConnectionError ou TimeoutError a task e
    re-enfileirada com backoff exponencial (retry_backoff=True).
    """
    job_id: str = self.request.id or "eager"
    structlog.contextvars.bind_contextvars(job_id=job_id, spider="books")
    t0 = time.monotonic()
    try:
        db_url = database_url or settings.database_url
        logger.info(
            "scrape_books iniciado: url=%s tentativa=%d persist=%s",
            start_url,
            self.request.retries,
            db_url is not None,
        )
        client = HTTPClient(requests_per_second=2.0)
        storage = _make_storage(db_url)
        spider = BooksSpider(
            client=client, base_url=start_url, output_path=None, storage=storage
        )
        result = spider.crawl()

        pages_scraped_total.labels(spider="books").inc(len(result.items))
        if result.errors:
            scraping_errors_total.labels(spider="books", error_type="parse").inc(
                len(result.errors)
            )

        summary: dict[str, Any] = {
            "items": len(result.items),
            "errors": len(result.errors),
            "error_details": result.errors,
            "persisted": storage is not None,
        }
        logger.info("scrape_books concluido: %s", summary)
        return summary
    finally:
        scraping_duration_seconds.labels(spider="books").observe(time.monotonic() - t0)
        structlog.contextvars.clear_contextvars()


@app.task(
    bind=True,
    name="worker.app.jobs.scraping_jobs.scrape_quotes",
    autoretry_for=(NetworkError, ConnectionError, TimeoutError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def scrape_quotes(self: Any, api_url: str = _QUOTES_API_URL) -> dict[str, Any]:
    """Dispara o QuotesSpider (API JSON) e retorna um resumo do resultado.

    Quotes nao sao persistidas ainda: o modelo ScrapedQuote sera criado no Dia 27+
    junto com a API REST. Por enquanto apenas o resumo e retornado.
    Em caso de NetworkError, ConnectionError ou TimeoutError a task e
    re-enfileirada com backoff exponencial.
    """
    job_id: str = self.request.id or "eager"
    structlog.contextvars.bind_contextvars(job_id=job_id, spider="quotes")
    t0 = time.monotonic()
    try:
        logger.info(
            "scrape_quotes iniciado: url=%s tentativa=%d", api_url, self.request.retries
        )
        client = HTTPClient(requests_per_second=2.0)
        spider = QuotesSpider(client=client, api_url=api_url, output_path=None)
        result = spider.crawl()

        pages_scraped_total.labels(spider="quotes").inc(len(result.items))
        if result.errors:
            scraping_errors_total.labels(spider="quotes", error_type="parse").inc(
                len(result.errors)
            )

        summary: dict[str, Any] = {
            "items": len(result.items),
            "errors": len(result.errors),
            "error_details": result.errors,
            "persisted": False,
        }
        logger.info("scrape_quotes concluido: %s", summary)
        return summary
    finally:
        scraping_duration_seconds.labels(spider="quotes").observe(time.monotonic() - t0)
        structlog.contextvars.clear_contextvars()
