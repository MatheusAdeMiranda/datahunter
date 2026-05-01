from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

from playwright.sync_api import Response as PlaywrightResponse

from scraper.app.browsers.playwright_client import PlaywrightClient
from scraper.app.core.entities import ScrapedItem, ScrapingJob, ScrapingResult
from scraper.app.core.exceptions import ParseError

logger = logging.getLogger(__name__)

_DEFAULT_URL = "https://quotes.toscrape.com/js/"
_DEFAULT_OUTPUT = Path("output/quotes_intercept.json")

# URL fragment present in every call to the quotes JSON API.
_API_PATH = "/api/quotes"

# CSS selector for the "Next" pagination button rendered by the SPA.
SEL_NEXT = "li.next a"


def _is_api_response(response: PlaywrightResponse) -> bool:
    """Predicate for page.expect_response(): matches the quotes JSON API."""
    return _API_PATH in response.url


class QuotesInterceptSpider:
    """Captures XHR JSON responses via Playwright network interception (Strategy 3).

    Contrast with the same site scraped two other ways:
    - Day 15 QuotesSpider:     httpx → /api/quotes directly (no browser)
    - Day 16 QuotesPWSpider:   Playwright + DOM HTML parsing
    - Day 17 QuotesInterceptSpider: Playwright + network interception (this class)

    Why this strategy:
    - No HTML parsing at all: data arrives already structured as JSON.
    - Works even if the SPA never renders quotes into the DOM (e.g., canvas).
    - Captures the exact payload the frontend receives, not a re-parse of it.

    Tradeoff: requires a real browser launch; ~10x slower than Strategy 1.
    Prefer Strategy 1 when the API is publicly accessible without a browser.
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
        # Set by crawl() via page.evaluate(); readable in tests.
        self.page_title = ""

    # ── public API ────────────────────────────────────────────────────────────

    def crawl(self) -> ScrapingResult:
        job = ScrapingJob(url=self._start_url, max_pages=self._max_pages)
        items: list[ScrapedItem] = []
        errors: list[str] = []

        page = self._client.new_page()

        # page.expect_response() registers the listener BEFORE the navigation
        # so we never miss the XHR that the SPA fires on DOMContentLoaded.
        with page.expect_response(_is_api_response) as resp_info:
            page.goto(self._start_url, wait_until="domcontentloaded")

        # page.evaluate() reads JS runtime state that is invisible in the HTML
        # source and inaccessible via CSS selectors or XPath.
        self.page_title = str(page.evaluate("() => document.title"))
        logger.info("page title from JS context: %r", self.page_title)

        api_data: dict[str, Any] = cast(dict[str, Any], resp_info.value.json())

        for page_num in range(1, self._max_pages + 1):
            page_items = _parse_response(api_data, self._start_url, page_num, errors)
            items.extend(page_items)
            logger.info(
                "page %d — %d quotes captured from network response",
                page_num,
                len(page_items),
            )

            if not api_data.get("has_next", False) or page_num == self._max_pages:
                break

            next_btn = page.locator(SEL_NEXT)
            if next_btn.count() == 0:
                logger.info("next button absent — stopping after page %d", page_num)
                break

            # Wrap the click inside expect_response so the new XHR is captured
            # atomically: listener is registered before the click fires the fetch.
            with page.expect_response(_is_api_response) as resp_info:
                next_btn.first.click()

            api_data = cast(dict[str, Any], resp_info.value.json())

        page.context.close()

        result = ScrapingResult(job=job, items=items, errors=errors)
        if self._output_path is not None:
            _save_json(result, self._output_path)
        return result


# ── helpers ───────────────────────────────────────────────────────────────────


def _parse_response(
    data: dict[str, Any],
    url: str,
    page_num: int,
    errors: list[str],
) -> list[ScrapedItem]:
    """Convert a raw API payload into ScrapedItems, isolating per-quote errors."""
    items: list[ScrapedItem] = []
    for raw in data.get("quotes", []):
        try:
            quote = _extract_quote(raw, url)
            items.append(ScrapedItem(url=url, data=quote))
        except ParseError as exc:
            msg = f"quote error on page {page_num}: {exc}"
            logger.warning(msg)
            errors.append(msg)
    return items


def _extract_quote(raw: dict[str, Any], url: str) -> dict[str, str]:
    """Extract text/author/tags from a single raw API quote dict."""
    text = str(raw.get("text") or "").strip()
    author = str(raw.get("author") or "").strip()
    if not text:
        raise ParseError(f"empty text in quote at {url}")
    if not author:
        raise ParseError(f"empty author in quote at {url}")
    tags = ", ".join(str(t) for t in raw.get("tags", []))
    return {"text": text, "author": author, "tags": tags}


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
        spider = QuotesInterceptSpider(client, output_path=Path("output/quotes_intercept.json"))
        result = spider.crawl()
        print(f"done: {len(result)} quotes, {len(result.errors)} errors")
        print(f"page title from JS: {spider.page_title!r}")
