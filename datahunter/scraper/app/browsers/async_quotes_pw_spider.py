from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from scraper.app.browsers.async_playwright_client import AsyncPlaywrightClient
from scraper.app.browsers.quotes_pw_spider import SEL_QUOTE, _extract_quotes
from scraper.app.core.entities import ScrapedItem, ScrapingJob, ScrapingResult

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT = Path("output/async_quotes_pw.json")


class AsyncQuotesPWSpider:
    """Scrapes a list of JS-rendered pages in parallel using Playwright.

    Unlike QuotesPWSpider (sequential pagination), this spider receives a
    pre-built list of page URLs and scrapes all of them concurrently, bounded
    by *max_concurrent* browser contexts open at any one time.

    Typical usage when page URLs are known in advance (e.g. after a first-pass
    crawl to discover all pages)::

        urls = [
            "https://quotes.toscrape.com/js/page/1/",
            "https://quotes.toscrape.com/js/page/2/",
        ]
        async with AsyncPlaywrightClient() as client:
            spider = AsyncQuotesPWSpider(client, max_concurrent=3)
            result = await spider.crawl(urls)
    """

    def __init__(
        self,
        client: AsyncPlaywrightClient,
        *,
        max_concurrent: int = 3,
        output_path: Path | None = _DEFAULT_OUTPUT,
    ) -> None:
        self._client = client
        self._max_concurrent = max_concurrent
        self._output_path = output_path

    async def crawl(self, urls: list[str]) -> ScrapingResult:
        """Scrape all *urls* in parallel, at most *max_concurrent* at a time."""
        job = ScrapingJob(url=urls[0] if urls else "", max_pages=len(urls))
        all_items: list[ScrapedItem] = []
        all_errors: list[str] = []

        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def scrape_one(url: str) -> None:
            try:
                html = await self._client.fetch_html(url, wait_for=SEL_QUOTE, semaphore=semaphore)
            except Exception as exc:
                msg = f"browser error on {url}: {exc}"
                logger.error(msg)
                all_errors.append(msg)
                return

            page_num = urls.index(url) + 1
            page_items = _extract_quotes(html, url, page_num, all_errors)
            all_items.extend(page_items)
            logger.info("scraped %d quotes from %s", len(page_items), url)

        await asyncio.gather(*[scrape_one(url) for url in urls])

        result = ScrapingResult(job=job, items=all_items, errors=all_errors)

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

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")

    async def main() -> None:
        urls = [f"https://quotes.toscrape.com/js/page/{i}/" for i in range(1, 6)]
        async with AsyncPlaywrightClient() as client:
            spider = AsyncQuotesPWSpider(client, max_concurrent=3)
            result = await spider.crawl(urls)
        print(f"done: {len(result)} quotes, {len(result.errors)} errors")

    asyncio.run(main())
