from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scraper.app.core.entities import ScrapedItem, ScrapingJob, ScrapingResult
from scraper.app.core.exceptions import NetworkError, ParseError
from scraper.app.core.http_client import HTTPClient
from scraper.app.parsers.html_parser import extract_next_page_url, parse_catalog_page

if TYPE_CHECKING:
    from scraper.app.core.robots import RobotsChecker
    from scraper.app.storage.service import StorageService

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://books.toscrape.com/catalogue/page-1.html"
_DEFAULT_OUTPUT = Path("output/books.json")


class BooksSpider:
    """Crawls books.toscrape.com catalogue pages and collects all book data.

    Pagination is followed by detecting the "next" link in each page.
    Already-visited URLs are skipped to prevent infinite loops.
    A ParseError on one page is logged and the crawl continues to the next page.
    A NetworkError stops the crawl for the remaining pages and is recorded.
    """

    def __init__(
        self,
        client: HTTPClient,
        base_url: str = _DEFAULT_BASE_URL,
        max_pages: int = 50,
        output_path: Path | None = _DEFAULT_OUTPUT,
        storage: StorageService | None = None,
        robots_checker: RobotsChecker | None = None,
    ) -> None:
        self._client = client
        self._base_url = base_url
        self._max_pages = max_pages
        self._output_path = output_path
        self._storage = storage
        self._robots_checker = robots_checker

    def crawl(self) -> ScrapingResult:
        job = ScrapingJob(url=self._base_url, max_pages=self._max_pages)
        items: list[ScrapedItem] = []
        errors: list[str] = []
        visited: set[str] = set()

        next_url: str | None = self._base_url

        while next_url and len(visited) < self._max_pages:
            if next_url in visited:
                logger.warning("skipping already-visited URL: %s", next_url)
                break

            current_url = next_url
            visited.add(current_url)
            logger.info("fetching page %d/%d: %s", len(visited), self._max_pages, current_url)

            if self._robots_checker and not self._robots_checker.is_allowed(current_url):
                logger.warning("robots.txt disallows %s, stopping crawl", current_url)
                break

            try:
                response = self._client.get(current_url)
                html = response.text
            except NetworkError as exc:
                msg = f"network error on {current_url}: {exc}"
                logger.error(msg)
                errors.append(msg)
                break

            next_url = extract_next_page_url(html, current_url)

            try:
                books = parse_catalog_page(html)
            except ParseError as exc:
                msg = f"parse error on {current_url}: {exc}"
                logger.error(msg)
                errors.append(msg)
                continue

            page_items = 0
            for book in books:
                items.append(ScrapedItem(url=current_url, data=cast(dict[str, str], book)))
                page_items += 1
            logger.info("extracted %d books from %s", page_items, current_url)

        result = ScrapingResult(job=job, items=items, errors=errors)

        if self._output_path is not None:
            _save_json(result, self._output_path)

        if self._storage is not None:
            self._storage.save_items(result.items)

        return result


def _save_json(result: ScrapingResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"url": item.url, "data": item.data, "scraped_at": item.scraped_at.isoformat()}
        for item in result.items
    ]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("saved %d items to %s", len(payload), path)


if __name__ == "__main__":  # pragma: no cover
    from sqlalchemy import create_engine

    from scraper.app.storage.service import StorageService

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
    _engine = create_engine("sqlite:///datahunter.db")
    _storage = StorageService(_engine)
    _storage.init_db()
    with HTTPClient() as client:
        spider = BooksSpider(client, output_path=None, storage=_storage)
        result = spider.crawl()
        print(f"done: {len(result)} items, {len(result.errors)} errors")
