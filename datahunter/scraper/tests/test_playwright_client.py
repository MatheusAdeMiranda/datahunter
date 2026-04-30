from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scraper.app.browsers.playwright_client import PlaywrightClient
from scraper.app.browsers.quotes_pw_spider import (
    SEL_NEXT,
    SEL_QUOTE,
    QuotesPWSpider,
    _extract_one,
)
from scraper.app.core.exceptions import ParseError

FIXTURES = Path(__file__).parent / "fixtures"

_PAGE1 = (FIXTURES / "quotes_pw_page1.html").read_text(encoding="utf-8")
_PAGE2 = (FIXTURES / "quotes_pw_page2.html").read_text(encoding="utf-8")
_MALFORMED = (FIXTURES / "quotes_pw_malformed.html").read_text(encoding="utf-8")

_BASE_URL = "http://quotes.test"
_PAGE1_URL = f"{_BASE_URL}/"
_PAGE2_URL = f"{_BASE_URL}/page/2/"


def _make_router(pages: dict[str, str]) -> Callable[[Any, Any], None]:
    """Return an add_route handler that serves static HTML per URL."""

    def handler(route: Any, request: Any) -> None:
        html = pages.get(request.url)
        if html is None:
            route.abort()
            return
        route.fulfill(status=200, content_type="text/html", body=html)

    return handler


# ── PlaywrightClient basics ───────────────────────────────────────────────────


def test_client_launches_and_closes() -> None:
    with PlaywrightClient() as client:
        assert client._browser is not None
    assert client._browser.is_connected() is False


def test_new_page_returns_isolated_context() -> None:
    with PlaywrightClient() as client:
        p1 = client.new_page()
        p2 = client.new_page()
        assert p1.context is not p2.context
        p1.context.close()
        p2.context.close()


def test_new_page_outside_context_raises() -> None:
    client = PlaywrightClient()
    with pytest.raises(RuntimeError, match="context manager"):
        client.new_page()


# ── fetch_html ────────────────────────────────────────────────────────────────


def test_fetch_html_returns_rendered_content() -> None:
    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router({_PAGE1_URL: _PAGE1}))
        html = client.fetch_html(_PAGE1_URL, wait_for=SEL_QUOTE)

    assert "Albert Einstein" in html
    assert "J.K. Rowling" in html


def test_fetch_html_wait_for_none_does_not_raise() -> None:
    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router({_PAGE1_URL: _PAGE1}))
        html = client.fetch_html(_PAGE1_URL)

    assert "<html" in html.lower()


# ── iter_pages ────────────────────────────────────────────────────────────────


def test_iter_pages_follows_next_and_stops() -> None:
    with PlaywrightClient() as client:
        client.add_route(
            "**/*",
            _make_router({_PAGE1_URL: _PAGE1, _PAGE2_URL: _PAGE2}),
        )
        pages_html = list(
            client.iter_pages(
                _PAGE1_URL,
                next_selector=SEL_NEXT,
                wait_for=SEL_QUOTE,
                max_pages=10,
            )
        )

    assert len(pages_html) == 2
    assert "Einstein" in pages_html[0]
    assert "Mark Twain" in pages_html[1]


def test_iter_pages_respects_max_pages() -> None:
    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router({_PAGE1_URL: _PAGE1}))
        pages_html = list(
            client.iter_pages(
                _PAGE1_URL,
                next_selector=SEL_NEXT,
                wait_for=SEL_QUOTE,
                max_pages=1,
            )
        )

    assert len(pages_html) == 1


# ── QuotesPWSpider integration ────────────────────────────────────────────────


def test_spider_collects_quotes_from_two_pages() -> None:
    with PlaywrightClient() as client:
        client.add_route(
            "**/*",
            _make_router({_PAGE1_URL: _PAGE1, _PAGE2_URL: _PAGE2}),
        )
        result = QuotesPWSpider(
            client,
            start_url=_PAGE1_URL,
            max_pages=10,
            output_path=None,
        ).crawl()

    assert len(result) == 3  # 2 from page1, 1 from page2
    assert result.errors == []
    assert result.ok


def test_spider_item_fields() -> None:
    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router({_PAGE1_URL: _PAGE2}))
        result = QuotesPWSpider(
            client,
            start_url=_PAGE1_URL,
            max_pages=1,
            output_path=None,
        ).crawl()

    item = result.items[0]
    assert item.data["author"] == "Mark Twain"
    assert "does not read" in item.data["text"]
    assert item.data["tags"] == "books, reading"


def test_spider_writes_json_output(tmp_path: Path) -> None:
    import json

    output = tmp_path / "out.json"

    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router({_PAGE1_URL: _PAGE2}))
        QuotesPWSpider(
            client,
            start_url=_PAGE1_URL,
            max_pages=1,
            output_path=output,
        ).crawl()

    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1
    assert set(data[0]["data"]) == {"text", "author", "tags"}
    assert "scraped_at" in data[0]


def test_spider_malformed_quote_is_skipped_crawl_continues() -> None:
    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router({_PAGE1_URL: _MALFORMED}))
        result = QuotesPWSpider(
            client,
            start_url=_PAGE1_URL,
            max_pages=1,
            output_path=None,
        ).crawl()

    assert len(result) == 1  # only the valid quote
    assert len(result.errors) == 1
    assert "quote error" in result.errors[0]


def test_spider_no_file_when_output_path_none(tmp_path: Path) -> None:
    with PlaywrightClient() as client:
        client.add_route("**/*", _make_router({_PAGE1_URL: _PAGE2}))
        QuotesPWSpider(
            client,
            start_url=_PAGE1_URL,
            max_pages=1,
            output_path=None,
        ).crawl()

    assert list(tmp_path.iterdir()) == []


# ── _extract_one unit tests ───────────────────────────────────────────────────


def _make_tag(html: str) -> object:
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "lxml").select_one("div.quote")


@pytest.mark.parametrize(
    ("html", "error_match"),
    [
        (
            '<div class="quote"><small class="author">A</small></div>',
            "missing or empty text",
        ),
        (
            '<div class="quote"><span class="text">T</span></div>',
            "missing or empty author",
        ),
    ],
)
def test_extract_one_raises_on_missing_fields(html: str, error_match: str) -> None:
    tag = _make_tag(html)
    with pytest.raises(ParseError, match=error_match):
        _extract_one(tag, "http://example.com")


def test_extract_one_raises_on_non_tag() -> None:
    with pytest.raises(ParseError, match="not a Tag"):
        _extract_one("not a tag", "http://example.com")


def test_extract_one_joins_tags_as_csv() -> None:
    html = (
        '<div class="quote">'
        '<span class="text">Hello</span>'
        '<small class="author">World</small>'
        '<div class="tags"><a class="tag">a</a><a class="tag">b</a></div>'
        "</div>"
    )
    data = _extract_one(_make_tag(html), "http://example.com")
    assert data["tags"] == "a, b"


def test_extract_one_handles_no_tags() -> None:
    html = (
        '<div class="quote">'
        '<span class="text">Hello</span>'
        '<small class="author">World</small>'
        "</div>"
    )
    data = _extract_one(_make_tag(html), "http://example.com")
    assert data["tags"] == ""
