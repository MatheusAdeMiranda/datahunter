from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scraper.app.browsers.playwright_client import PlaywrightClient
from scraper.app.browsers.quotes_intercept_spider import (
    QuotesInterceptSpider,
    _extract_quote,
    _parse_response,
)
from scraper.app.core.exceptions import ParseError

FIXTURES = Path(__file__).parent / "fixtures"

_HTML = (FIXTURES / "quotes_intercept.html").read_text(encoding="utf-8")
_JSON_PAGE1 = (FIXTURES / "quotes_page1.json").read_text(encoding="utf-8")
_JSON_PAGE2 = (FIXTURES / "quotes_page2.json").read_text(encoding="utf-8")

_BASE_URL = "http://quotes.test"
_START_URL = f"{_BASE_URL}/js/"
_API_PATH = "/api/quotes"

# Minimal SPA HTML that fires the XHR but never renders a "Next" button.
# Used to cover the defensive branch where has_next=True but DOM has no button.
_HTML_NO_NEXT_BTN = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"/><title>Quotes to Scrape (JS)</title></head>
<body>
  <div id="quotes"></div>
  <script>
    document.addEventListener('DOMContentLoaded', function() {
      fetch('/api/quotes?page=1').then(function(r) { return r.json(); });
    });
  </script>
</body>
</html>"""


def _make_router() -> Callable[[Any, Any], None]:
    """Route handler: serves the SPA HTML and the quotes JSON API."""

    def handler(route: Any, request: Any) -> None:
        if _API_PATH in request.url:
            # Parse the page number from ?page=N
            try:
                page_num = int(request.url.split("page=")[1].split("&")[0])
            except (IndexError, ValueError):
                page_num = 1
            body = _JSON_PAGE1 if page_num == 1 else _JSON_PAGE2
            route.fulfill(status=200, content_type="application/json", body=body)
        else:
            route.fulfill(status=200, content_type="text/html", body=_HTML)

    return handler


# ── integration tests (require a real browser via Playwright) ─────────────────


def test_spider_captures_quotes_from_two_pages_via_xhr() -> None:
    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router())
        result = QuotesInterceptSpider(
            client,
            start_url=_START_URL,
            max_pages=10,
            output_path=None,
        ).crawl()

    assert len(result) == 3  # 2 from page 1, 1 from page 2
    assert result.errors == []
    assert result.ok


def test_spider_respects_max_pages() -> None:
    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router())
        result = QuotesInterceptSpider(
            client,
            start_url=_START_URL,
            max_pages=1,
            output_path=None,
        ).crawl()

    assert len(result) == 2  # only page 1 quotes


def test_spider_item_fields() -> None:
    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router())
        result = QuotesInterceptSpider(
            client,
            start_url=_START_URL,
            max_pages=1,
            output_path=None,
        ).crawl()

    first = result.items[0]
    assert first.data["author"] == "Albert Einstein"
    assert "process of our thinking" in first.data["text"]
    assert first.data["tags"] == "change, deep-thoughts, thinking"


def test_evaluate_reads_page_title_from_js_context() -> None:
    """page.evaluate() accesses JS runtime state invisible to CSS/XPath selectors."""
    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router())
        spider = QuotesInterceptSpider(
            client,
            start_url=_START_URL,
            max_pages=1,
            output_path=None,
        )
        spider.crawl()

    assert spider.page_title == "Quotes to Scrape (JS)"


def test_spider_writes_json_output(tmp_path: Path) -> None:
    output = tmp_path / "out.json"

    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router())
        QuotesInterceptSpider(
            client,
            start_url=_START_URL,
            max_pages=1,
            output_path=output,
        ).crawl()

    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 2
    assert set(data[0]["data"]) == {"text", "author", "tags"}
    assert "scraped_at" in data[0]


def test_spider_stops_when_next_button_absent_despite_has_next() -> None:
    """Covers defensive guard: API says has_next=True but DOM has no next button."""

    def handler(route: Any, request: Any) -> None:
        if _API_PATH in request.url:
            # Page 1 has has_next=True, so spider will look for the next button.
            route.fulfill(status=200, content_type="application/json", body=_JSON_PAGE1)
        else:
            route.fulfill(status=200, content_type="text/html", body=_HTML_NO_NEXT_BTN)

    with PlaywrightClient() as client:
        client.add_route("**/*", handler)
        result = QuotesInterceptSpider(
            client,
            start_url=_START_URL,
            max_pages=10,
            output_path=None,
        ).crawl()

    assert len(result) == 2  # only page 1 items; spider stopped at absent button


# ── unit tests (_extract_quote and _parse_response — no browser required) ─────


def test_extract_quote_raises_on_empty_text() -> None:
    with pytest.raises(ParseError, match="empty text"):
        _extract_quote({"text": "", "author": "A", "tags": []}, "http://test")


def test_extract_quote_raises_on_empty_author() -> None:
    with pytest.raises(ParseError, match="empty author"):
        _extract_quote({"text": "T", "author": "", "tags": []}, "http://test")


def test_extract_quote_joins_tags_as_csv() -> None:
    result = _extract_quote({"text": "T", "author": "A", "tags": ["a", "b", "c"]}, "http://test")
    assert result["tags"] == "a, b, c"


def test_parse_response_skips_bad_quote_and_records_error() -> None:
    data: dict[str, Any] = {
        "quotes": [
            {"text": "", "author": "A", "tags": []},  # bad: empty text
            {"text": "Valid", "author": "B", "tags": ["x"]},  # good
        ],
        "has_next": False,
    }
    errors: list[str] = []
    items = _parse_response(data, "http://test", 1, errors)

    assert len(items) == 1
    assert items[0].data["author"] == "B"
    assert len(errors) == 1
    assert "quote error on page 1" in errors[0]
