from __future__ import annotations

import json
import logging
from pathlib import Path

from scraper.app.browsers.playwright_client import PlaywrightClient
from scraper.app.core.entities import ScrapedItem, ScrapingJob, ScrapingResult
from scraper.app.core.exceptions import ParseError

logger = logging.getLogger(__name__)

_DEFAULT_URL = "https://quotes.toscrape.com/js/"
_DEFAULT_OUTPUT = Path("output/quotes_pw.json")

# CSS selectors — isolated here so tests can reference them.
SEL_QUOTE = "div.quote"
SEL_TEXT = "span.text"
SEL_AUTHOR = "small.author"
SEL_TAGS = "div.tags a.tag"
SEL_NEXT = "li.next a"


class QuotesPWSpider:
    """Scrapes quotes.toscrape.com/js/ using Playwright for JS rendering.

    Uses the DOM path (Strategy 2) to contrast with QuotesSpider (Strategy 1,
    API JSON).  Same site, different technique — demonstrates when Playwright
    is necessary and how to use it correctly.
    """

    def __init__(
        self,
        client: PlaywrightClient,
        *,
        start_url: str = _DEFAULT_URL,
        max_pages: int = 20,
        output_path: Path | None = _DEFAULT_OUTPUT,
    ) -> None:
        self._client = client
        self._start_url = start_url
        self._max_pages = max_pages
        self._output_path = output_path

    def crawl(self) -> ScrapingResult:
        job = ScrapingJob(url=self._start_url, max_pages=self._max_pages)
        items: list[ScrapedItem] = []
        errors: list[str] = []

        for page_num, html in enumerate(
            self._client.iter_pages(
                self._start_url,
                next_selector=SEL_NEXT,
                wait_for=SEL_QUOTE,
                max_pages=self._max_pages,
            ),
            start=1,
        ):
            page_items = _extract_quotes(html, self._start_url, page_num, errors)
            items.extend(page_items)
            logger.info("page %d — extracted %d quotes", page_num, len(page_items))

        result = ScrapingResult(job=job, items=items, errors=errors)

        if self._output_path is not None:
            _save_json(result, self._output_path)

        return result


def _extract_quotes(
    html: str,
    url: str,
    page_num: int,
    errors: list[str],
) -> list[ScrapedItem]:
    """Parse all quote blocks from a rendered HTML page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    items: list[ScrapedItem] = []

    for block in soup.select(SEL_QUOTE):
        try:
            data = _extract_one(block, url)
            items.append(ScrapedItem(url=url, data=data))
        except ParseError as exc:
            msg = f"quote error on page {page_num}: {exc}"
            logger.warning(msg)
            errors.append(msg)

    return items


def _extract_one(block: object, url: str) -> dict[str, str]:
    """Extract text/author/tags from a single quote block (BS4 Tag)."""
    from bs4 import Tag

    if not isinstance(block, Tag):
        raise ParseError("quote block is not a Tag")

    text_el = block.select_one(SEL_TEXT)
    author_el = block.select_one(SEL_AUTHOR)

    if text_el is None or not text_el.get_text(strip=True):
        raise ParseError(f"missing or empty text in quote at {url}")
    if author_el is None or not author_el.get_text(strip=True):
        raise ParseError(f"missing or empty author in quote at {url}")

    tags = ", ".join(t.get_text(strip=True) for t in block.select(SEL_TAGS))

    return {
        "text": text_el.get_text(strip=True),
        "author": author_el.get_text(strip=True),
        "tags": tags,
    }


def _save_json(result: ScrapingResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"url": item.url, "data": item.data, "scraped_at": item.scraped_at.isoformat()}
        for item in result.items
    ]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("saved %d items to %s", len(payload), path)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
    with PlaywrightClient() as client:
        spider = QuotesPWSpider(client, output_path=Path("output/quotes_pw.json"))
        result = spider.crawl()
        print(f"done: {len(result)} quotes, {len(result.errors)} errors")
