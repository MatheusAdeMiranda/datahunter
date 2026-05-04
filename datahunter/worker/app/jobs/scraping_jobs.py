from __future__ import annotations

import logging
from typing import Any

from scraper.app.core.exceptions import NetworkError
from scraper.app.core.http_client import HTTPClient
from scraper.app.spiders.books_spider import BooksSpider
from scraper.app.spiders.quotes_spider import QuotesSpider
from worker.app.main import app

logger = logging.getLogger(__name__)

_BOOKS_START_URL = "https://books.toscrape.com/catalogue/page-1.html"
_QUOTES_API_URL = "https://quotes.toscrape.com/api/quotes"


@app.task(
    bind=True,
    name="worker.app.jobs.scraping_jobs.scrape_books",
    autoretry_for=(NetworkError, ConnectionError, TimeoutError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def scrape_books(self: Any, start_url: str = _BOOKS_START_URL) -> dict[str, Any]:
    """Dispara o BooksSpider e retorna um resumo do resultado.

    Em caso de NetworkError, ConnectionError ou TimeoutError a task e
    re-enfileirada com backoff exponencial (retry_backoff=True).
    """
    logger.info("scrape_books iniciado: url=%s tentativa=%d", start_url, self.request.retries)
    client = HTTPClient(requests_per_second=2.0)
    spider = BooksSpider(client=client, base_url=start_url, output_path=None)
    result = spider.crawl()
    summary: dict[str, Any] = {
        "items": len(result.items),
        "errors": len(result.errors),
        "error_details": result.errors,
    }
    logger.info("scrape_books concluido: %s", summary)
    return summary


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

    Em caso de NetworkError, ConnectionError ou TimeoutError a task e
    re-enfileirada com backoff exponencial.
    """
    logger.info("scrape_quotes iniciado: url=%s tentativa=%d", api_url, self.request.retries)
    client = HTTPClient(requests_per_second=2.0)
    spider = QuotesSpider(client=client, api_url=api_url, output_path=None)
    result = spider.crawl()
    summary: dict[str, Any] = {
        "items": len(result.items),
        "errors": len(result.errors),
        "error_details": result.errors,
    }
    logger.info("scrape_quotes concluido: %s", summary)
    return summary
