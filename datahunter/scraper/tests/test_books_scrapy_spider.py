from __future__ import annotations

from pathlib import Path

import pytest
import scrapy
from scrapy.http import HtmlResponse

from scraper.scrapy_project.items import BookItem
from scraper.scrapy_project.spiders.books_spider import BooksScrapySpider

FIXTURES = Path(__file__).parent / "fixtures"


def _response(filename: str, url: str) -> HtmlResponse:
    body = (FIXTURES / filename).read_bytes()
    return HtmlResponse(url=url, body=body, encoding="utf-8")


@pytest.fixture()
def spider() -> BooksScrapySpider:
    return BooksScrapySpider()


def test_parse_extracts_all_books(spider: BooksScrapySpider) -> None:
    response = _response("books_page1.html", "https://books.toscrape.com/catalogue/page-1.html")
    items = [r for r in spider.parse(response) if isinstance(r, BookItem)]
    assert len(items) == 2


def test_parse_book_fields(spider: BooksScrapySpider) -> None:
    response = _response("books_page1.html", "https://books.toscrape.com/catalogue/page-1.html")
    items = [r for r in spider.parse(response) if isinstance(r, BookItem)]
    first = items[0]
    assert first["title"] == "A Light in the Attic"
    assert first["price"] == "£51.77"
    assert first["availability"] == "In stock"
    assert first["rating"] == "3"


def test_parse_follows_next_page(spider: BooksScrapySpider) -> None:
    response = _response("books_page1.html", "https://books.toscrape.com/catalogue/page-1.html")
    requests = [r for r in spider.parse(response) if isinstance(r, scrapy.Request)]
    assert len(requests) == 1
    assert "page-2.html" in requests[0].url


def test_parse_last_page_no_next(spider: BooksScrapySpider) -> None:
    response = _response("books_page2.html", "https://books.toscrape.com/catalogue/page-2.html")
    requests = [r for r in spider.parse(response) if isinstance(r, scrapy.Request)]
    assert len(requests) == 0


def test_rating_mapping(spider: BooksScrapySpider) -> None:
    response = _response("books_page2.html", "https://books.toscrape.com/catalogue/page-2.html")
    items = {r["title"]: r for r in spider.parse(response) if isinstance(r, BookItem)}
    assert items["Soumission"]["rating"] == "5"
    assert items["Sharp Objects"]["rating"] == "4"


def test_unknown_rating_maps_to_zero(spider: BooksScrapySpider) -> None:
    body = (
        b'<html><body><section><ol class="row">'
        b'<li><article class="product_pod">'
        b'<p class="star-rating Unknown"><i></i></p>'
        b'<h3><a href="x" title="Mystery Book">Mystery Book</a></h3>'
        b'<div class="product_price">'
        b'<p class="price_color">9.99</p>'
        b'<p class="instock availability"><i></i>In stock</p>'
        b"</div></article></li>"
        b"</ol></section></body></html>"
    )
    response = HtmlResponse(url="https://books.toscrape.com/catalogue/page-1.html", body=body)
    items = [r for r in spider.parse(response) if isinstance(r, BookItem)]
    assert items[0]["rating"] == "0"
