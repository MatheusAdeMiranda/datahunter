from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import scrapy
from scrapy.http import HtmlResponse
from scrapy.selector import Selector

from scraper.scrapy_project.items import QuoteItem
from scraper.scrapy_project.spiders.quotes_spider import QuotesScrapySpider

FIXTURES = Path(__file__).parent / "fixtures"


def _response(filename: str, url: str = "https://quotes.toscrape.com/js/") -> HtmlResponse:
    body = (FIXTURES / filename).read_bytes()
    return HtmlResponse(url=url, body=body, encoding="utf-8")


@pytest.fixture()
def spider() -> QuotesScrapySpider:
    return QuotesScrapySpider()


# --- start_requests ---


def test_start_requests_yields_playwright_request(spider: QuotesScrapySpider) -> None:
    requests = list(spider.start_requests())
    assert len(requests) == 1
    assert requests[0].meta["playwright"] is True
    assert requests[0].meta["playwright_include_page"] is True


# --- _parse_quote (static, sem browser) ---


def test_parse_quote_extracts_fields(spider: QuotesScrapySpider) -> None:
    html = (
        '<div class="quote">'
        '<span class="text">“Life is what happens”</span>'
        '<small class="author">John Lennon</small>'
        '<a class="tag">life</a><a class="tag">beatles</a>'
        "</div>"
    )
    sel = Selector(text=html).css("div.quote")[0]
    item = QuotesScrapySpider._parse_quote(sel)
    assert item["text"] == "“Life is what happens”"
    assert item["author"] == "John Lennon"
    assert item["tags"] == "life, beatles"


def test_parse_quote_empty_tags(spider: QuotesScrapySpider) -> None:
    html = (
        '<div class="quote">'
        '<span class="text">“No tags”</span>'
        '<small class="author">Nobody</small>'
        "</div>"
    )
    sel = Selector(text=html).css("div.quote")[0]
    item = QuotesScrapySpider._parse_quote(sel)
    assert item["tags"] == ""


# --- parse (async, sem page) ---


async def test_parse_yields_items_and_next_request(spider: QuotesScrapySpider) -> None:
    response = _response("quotes_pw_page1.html")
    items: list[QuoteItem] = []
    requests: list[scrapy.Request] = []
    async for result in spider.parse(response):
        if isinstance(result, QuoteItem):
            items.append(result)
        elif isinstance(result, scrapy.Request):
            requests.append(result)
    assert len(items) == 2
    assert items[0]["author"] == "Albert Einstein"
    assert len(requests) == 1
    assert "/page/2/" in requests[0].url


async def test_parse_last_page_no_next_request(spider: QuotesScrapySpider) -> None:
    response = _response("quotes_pw_page2.html")
    requests = [r async for r in spider.parse(response) if isinstance(r, scrapy.Request)]
    assert len(requests) == 0


# --- parse com page (AsyncMock — cobre os branches playwright) ---


async def test_parse_with_page_waits_and_closes(spider: QuotesScrapySpider) -> None:
    page = AsyncMock()
    response = _response("quotes_pw_page1.html")
    results = [r async for r in spider.parse(response, page=page)]
    page.wait_for_selector.assert_called_once_with("div.quote")
    page.close.assert_called_once()
    assert any(isinstance(r, QuoteItem) for r in results)
