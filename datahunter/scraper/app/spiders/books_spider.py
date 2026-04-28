from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import cast

from scraper.app.core.entities import ScrapedItem, ScrapingJob, ScrapingResult
from scraper.app.core.exceptions import NetworkError, ParseError
from scraper.app.core.http_client import HTTPClient
from scraper.app.parsers.html_parser import extract_next_page_url, parse_catalog_page

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
    ) -> None:
        self._client = client
        self._base_url = base_url
        self._max_pages = max_pages
        self._output_path = output_path

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

            try:
                response = self._client.get(current_url)
                html = response.text
            except NetworkError as exc:
                msg = f"network error on {current_url}: {exc}"
                logger.error(msg)
                errors.append(msg)
                break

            try:
                books = parse_catalog_page(html)
                for book in books:
                    items.append(ScrapedItem(url=current_url, data=cast(dict[str, str], book)))
                logger.info("extracted %d books from %s", len(books), current_url)
            except ParseError as exc:
                msg = f"parse error on {current_url}: {exc}"
                logger.error(msg)
                errors.append(msg)

            next_url = extract_next_page_url(html, current_url)

        result = ScrapingResult(job=job, items=items, errors=errors)

        if self._output_path is not None:
            _save_json(result, self._output_path)

        return result


def _save_json(result: ScrapingResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"url": item.url, "data": item.data, "scraped_at": item.scraped_at.isoformat()}
        for item in result.items
    ]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("saved %d items to %s", len(payload), path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
    with HTTPClient() as client:
        spider = BooksSpider(client)
        result = spider.crawl()
        print(f"done: {len(result)} items, {len(result.errors)} errors")
