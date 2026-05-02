from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scraper.app.core.async_http_client import AsyncHTTPClient
from scraper.app.core.entities import ScrapedItem, ScrapingJob, ScrapingResult
from scraper.app.core.exceptions import NetworkError, ParseError
from scraper.app.parsers.html_parser import extract_next_page_url, parse_catalog_page

if TYPE_CHECKING:
    from scraper.app.storage.async_service import AsyncStorageService

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://books.toscrape.com/catalogue/page-1.html"
_DEFAULT_OUTPUT = Path("output/async_books.json")


class AsyncBooksSpider:
    """Async version of BooksSpider using a producer-consumer pipeline.

    Producer fetches pages sequentially (pagination is inherently serial —
    each page's URL comes from the previous page). Consumer parses and stores
    concurrently with the next fetch via asyncio.Queue.

    The concurrency benefit: while the producer awaits the HTTP response for
    page N+1, the consumer is parsing and persisting page N.
    """

    def __init__(
        self,
        client: AsyncHTTPClient,
        base_url: str = _DEFAULT_BASE_URL,
        max_pages: int = 50,
        output_path: Path | None = _DEFAULT_OUTPUT,
        storage: AsyncStorageService | None = None,
    ) -> None:
        self._client = client
        self._base_url = base_url
        self._max_pages = max_pages
        self._output_path = output_path
        self._storage = storage

    async def crawl(self) -> ScrapingResult:
        job = ScrapingJob(url=self._base_url, max_pages=self._max_pages)
        items: list[ScrapedItem] = []
        errors: list[str] = []

        # Queue carries (page_url, html) pairs; None is the stop sentinel.
        queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

        async def producer() -> None:
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
                    response = await self._client.get(current_url)
                    html = response.text
                except NetworkError as exc:
                    msg = f"network error on {current_url}: {exc}"
                    logger.error(msg)
                    errors.append(msg)
                    break

                # Extract next URL before queuing so consumer can start parsing immediately.
                next_url = extract_next_page_url(html, current_url)
                await queue.put((current_url, html))

            await queue.put(None)  # signal consumer to stop

        async def consumer() -> None:
            while True:
                payload = await queue.get()
                if payload is None:
                    break

                url, html = payload
                try:
                    books = parse_catalog_page(html)
                except ParseError as exc:
                    msg = f"parse error on {url}: {exc}"
                    logger.error(msg)
                    errors.append(msg)
                    continue

                page_items = [
                    ScrapedItem(url=url, data=cast(dict[str, str], book)) for book in books
                ]
                items.extend(page_items)
                logger.info("extracted %d books from %s", len(page_items), url)

                if self._storage is not None:
                    await self._storage.save_items(page_items)

        await asyncio.gather(producer(), consumer())

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


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    from scraper.app.storage.async_service import AsyncStorageService

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")

    async def main() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///datahunter_async.db")
        storage = AsyncStorageService(engine)
        await storage.init_db()
        async with AsyncHTTPClient(requests_per_second=2.0) as client:
            spider = AsyncBooksSpider(client, output_path=None, storage=storage)
            result = await spider.crawl()
        await engine.dispose()
        print(f"done: {len(result)} items, {len(result.errors)} errors")

    asyncio.run(main())
