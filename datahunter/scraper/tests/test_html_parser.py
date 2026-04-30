from __future__ import annotations

from pathlib import Path

import pytest

from scraper.app.core.exceptions import ParseError
from scraper.app.parsers.html_parser import (
    BookData,
    extract_available_titles_xpath,
    extract_next_page_url,
    parse_catalog_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def catalog_html() -> str:
    return (FIXTURES / "books_catalog.html").read_text(encoding="utf-8")


# ── parse_catalog_page ────────────────────────────────────────────────────────


def test_returns_all_books(catalog_html: str) -> None:
    books = parse_catalog_page(catalog_html)
    assert len(books) == 4


def test_book_is_typed_dict(catalog_html: str) -> None:
    book: BookData = parse_catalog_page(catalog_html)[0]
    assert set(book.keys()) == {"title", "price", "availability", "rating"}


@pytest.mark.parametrize(
    ("index", "expected_title"),
    [
        (0, "A Light in the Attic"),  # full title from `title` attr, not truncated text
        (1, "Tipping the Velvet"),
        (2, "Soumission"),
        (3, "Sharp Objects"),
    ],
)
def test_title(catalog_html: str, index: int, expected_title: str) -> None:
    assert parse_catalog_page(catalog_html)[index]["title"] == expected_title


@pytest.mark.parametrize(
    ("index", "expected_price"),
    [
        (0, "£51.77"),
        (1, "£53.74"),
        (2, "£50.10"),
        (3, "£47.82"),
    ],
)
def test_price(catalog_html: str, index: int, expected_price: str) -> None:
    assert parse_catalog_page(catalog_html)[index]["price"] == expected_price


@pytest.mark.parametrize(
    ("index", "expected_availability"),
    [
        (0, "In stock"),
        (1, "In stock"),
        (2, "Out of stock"),
        (3, "In stock"),
    ],
)
def test_availability(catalog_html: str, index: int, expected_availability: str) -> None:
    assert parse_catalog_page(catalog_html)[index]["availability"] == expected_availability


@pytest.mark.parametrize(
    ("index", "expected_rating"),
    [
        (0, "Three"),
        (1, "One"),
        (2, "Five"),
        (3, "Four"),
    ],
)
def test_rating(catalog_html: str, index: int, expected_rating: str) -> None:
    assert parse_catalog_page(catalog_html)[index]["rating"] == expected_rating


# ── ParseError on broken structure ────────────────────────────────────────────
# Each tuple is (html_fragment, error_pattern).
# This table is the first line of defence: if books.toscrape.com changes its
# markup, adding a row here documents the new failure mode before fixing it.

_BROKEN_HTML_CASES: list[tuple[str, str]] = [
    (
        "<html><body><p>nothing here</p></body></html>",
        r"no article\.product_pod",
    ),
    (
        """<article class="product_pod">
          <p class="price_color">£10.00</p>
          <p class="availability">In stock</p>
          <p class="star-rating Three"></p>
        </article>""",
        "h3 > a",
    ),
    (
        """<article class="product_pod">
          <h3><a href="#" title="Some Book">Some Book</a></h3>
          <p class="availability">In stock</p>
          <p class="star-rating Two"></p>
        </article>""",
        r"p\.price_color",
    ),
    (
        """<article class="product_pod">
          <h3><a href="#" title="Some Book">Some Book</a></h3>
          <p class="price_color">£10.00</p>
          <p class="star-rating Two"></p>
        </article>""",
        r"p\.availability",
    ),
    (
        """<article class="product_pod">
          <h3><a href="#" title="Some Book">Some Book</a></h3>
          <p class="price_color">£10.00</p>
          <p class="availability">In stock</p>
        </article>""",
        r"p\.star-rating",
    ),
    (
        # <p class="star-rating"> with no second class — rating word absent.
        """<article class="product_pod">
          <h3><a href="#" title="Some Book">Some Book</a></h3>
          <p class="price_color">£10.00</p>
          <p class="availability">In stock</p>
          <p class="star-rating"></p>
        </article>""",
        "rating word not found",
    ),
]


@pytest.mark.parametrize(("html_fragment", "error_match"), _BROKEN_HTML_CASES)
def test_parse_error_on_broken_html(html_fragment: str, error_match: str) -> None:
    with pytest.raises(ParseError, match=error_match):
        parse_catalog_page(html_fragment)


def test_title_falls_back_to_text_when_attribute_absent() -> None:
    # <a> without a title= attribute: should use the visible text instead.
    html = """
    <article class="product_pod">
      <h3><a href="#">Visible Title</a></h3>
      <p class="price_color">£10.00</p>
      <p class="availability">In stock</p>
      <p class="star-rating Two"></p>
    </article>
    """
    books = parse_catalog_page(html)
    assert books[0]["title"] == "Visible Title"


# ── XPath alternative ─────────────────────────────────────────────────────────


def test_xpath_returns_only_in_stock_titles(catalog_html: str) -> None:
    # Fixture has 4 books: 3 in stock, 1 out of stock (Soumission).
    titles = extract_available_titles_xpath(catalog_html)
    assert len(titles) == 3
    assert "Soumission" not in titles
    assert "A Light in the Attic" in titles


def test_xpath_returns_empty_for_no_matches() -> None:
    html = "<html><body><p>nothing</p></body></html>"
    assert extract_available_titles_xpath(html) == []


# ── extract_next_page_url ─────────────────────────────────────────────────────


_BASE = "https://books.toscrape.com/catalogue/page-1.html"
_NEXT_HTML = (
    '<html><body><ul class="pager">'
    '<li class="next"><a href="page-2.html">next</a></li>'
    "</ul></body></html>"
)
_PREV_ONLY_HTML = (
    '<html><body><ul class="pager">'
    '<li class="previous"><a href="page-1.html">previous</a></li>'
    "</ul></body></html>"
)
_EMPTY_HREF_HTML = (
    '<html><body><ul class="pager"><li class="next"><a href="">next</a></li></ul></body></html>'
)


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (_NEXT_HTML, "https://books.toscrape.com/catalogue/page-2.html"),
        (_PREV_ONLY_HTML, None),
        (_EMPTY_HREF_HTML, None),
        # No pager element at all.
        ("<html><body></body></html>", None),
        # Root-relative href — urljoin must resolve against the origin, not the path.
        (
            '<ul class="pager"><li class="next">'
            '<a href="/catalogue/page-3.html">next</a></li></ul>',
            "https://books.toscrape.com/catalogue/page-3.html",
        ),
    ],
)
def test_next_page_url(html: str, expected: str | None) -> None:
    assert extract_next_page_url(html, _BASE) == expected
