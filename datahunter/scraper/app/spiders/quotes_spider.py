from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scraper.app.core.entities import ScrapedItem, ScrapingJob, ScrapingResult
from scraper.app.core.exceptions import NetworkError, ParseError
from scraper.app.core.http_client import HTTPClient

if TYPE_CHECKING:
    from scraper.app.storage.service import StorageService

logger = logging.getLogger(__name__)

_DEFAULT_API_URL = "https://quotes.toscrape.com/api/quotes"
_DEFAULT_OUTPUT = Path("output/quotes.json")


class QuotesSpider:
    """Scrapes quotes.toscrape.com via its internal JSON API — no browser required.

    Discovery: visiting quotes.toscrape.com/js/ and inspecting DevTools →
    Network → Fetch/XHR reveals GET /api/quotes?page=N returning paginated JSON.
    Pagination follows the boolean field `has_next` in each response.

    A ParseError on one quote is logged and the crawl continues.
    A NetworkError or response-level ParseError stops the crawl.
    """

    def __init__(
        self,
        client: HTTPClient,
        api_url: str = _DEFAULT_API_URL,
        max_pages: int = 20,
        output_path: Path | None = _DEFAULT_OUTPUT,
        storage: StorageService | None = None,
    ) -> None:
        self._client = client
        self._api_url = api_url
        self._max_pages = max_pages
        self._output_path = output_path
        self._storage = storage

    def crawl(self) -> ScrapingResult:
        job = ScrapingJob(url=self._api_url, max_pages=self._max_pages)
        items: list[ScrapedItem] = []
        errors: list[str] = []

        for page in range(1, self._max_pages + 1):
            url = f"{self._api_url}?page={page}"
            logger.info("fetching page %d: %s", page, url)

            try:
                response = self._client.get(url)
                payload = _parse_response(response.text, url)
            except NetworkError as exc:
                msg = f"network error on {url}: {exc}"
                logger.error(msg)
                errors.append(msg)
                break
            except ParseError as exc:
                msg = f"parse error on {url}: {exc}"
                logger.error(msg)
                errors.append(msg)
                break

            page_items = 0
            for raw_quote in payload.get("quotes", []):
                try:
                    data = _extract_quote(raw_quote, url)
                    items.append(ScrapedItem(url=url, data=data))
                    page_items += 1
                except ParseError as exc:
                    msg = f"quote error on {url}: {exc}"
                    logger.warning(msg)
                    errors.append(msg)

            logger.info("extracted %d quotes from page %d", page_items, page)

            if not payload.get("has_next", False):
                logger.info("no next page — crawl complete after %d page(s)", page)
                break

        result = ScrapingResult(job=job, items=items, errors=errors)

        if self._output_path is not None:
            _save_json(result, self._output_path)

        if self._storage is not None:
            self._storage.save_items(result.items)

        return result


def _parse_response(text: str, url: str) -> dict[str, Any]:
    """Parse and validate the top-level JSON envelope from the API."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON from {url}") from exc
    if not isinstance(data, dict):
        raise ParseError(f"expected JSON object from {url}, got {type(data).__name__}")
    return data


def _extract_quote(raw: object, url: str) -> dict[str, str]:
    """Extract and validate one quote entry from the API payload."""
    if not isinstance(raw, dict):
        raise ParseError(f"quote entry is not a dict at {url}")
    text = raw.get("text")
    author = raw.get("author")
    tags = raw.get("tags", [])
    if not isinstance(text, str) or not text:
        raise ParseError(f"missing or empty 'text' in quote at {url}")
    if not isinstance(author, str) or not author:
        raise ParseError(f"missing or empty 'author' in quote at {url}")
    return {
        "text": text,
        "author": author,
        "tags": ", ".join(str(t) for t in tags) if isinstance(tags, list) else "",
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
    with HTTPClient(requests_per_second=2.0) as client:
        spider = QuotesSpider(client, output_path=Path("output/quotes.json"))
        result = spider.crawl()
        print(f"done: {len(result)} quotes, {len(result.errors)} errors")
