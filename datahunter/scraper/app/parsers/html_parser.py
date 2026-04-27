from __future__ import annotations

from typing import TypedDict

from bs4 import BeautifulSoup, Tag
from lxml import etree  # type: ignore[import-untyped]

from scraper.app.core.exceptions import ParseError


class BookData(TypedDict):
    title: str
    price: str
    availability: str
    rating: str


def parse_catalog_page(html: str) -> list[BookData]:
    """Parse a books.toscrape.com catalog page and return all books found."""
    soup = BeautifulSoup(html, "lxml")
    articles = soup.select("article.product_pod")
    if not articles:
        raise ParseError("no article.product_pod elements found — page structure may have changed")
    return [_parse_article(article) for article in articles]


# ── XPath alternative ─────────────────────────────────────────────────────────
# CSS selectors cannot filter by text content or traverse upward in the tree.
# XPath handles both, making it the right tool for queries like
# "titles of books that are currently in stock".


def extract_available_titles_xpath(html: str) -> list[str]:
    """Return titles of in-stock books using XPath.

    Demonstrates where XPath beats CSS:
    - CSS has no equivalent of contains(text(), "In stock")
    - CSS cannot walk from a child element back up to an ancestor
    """
    root = etree.fromstring(html.encode(), etree.HTMLParser())
    in_stock_articles = root.xpath(
        '//article[.//p[contains(@class,"availability") and contains(.,"In stock")]]'
    )
    titles: list[str] = []
    for article in in_stock_articles:
        found = article.xpath(".//h3/a/@title")
        if found:
            titles.append(str(found[0]))
    return titles


# ── Internal helpers ──────────────────────────────────────────────────────────


def _require(tag: Tag, selector: str) -> Tag:
    """Return the first match for *selector* or raise ParseError."""
    found = tag.select_one(selector)
    if not isinstance(found, Tag):
        raise ParseError(f"selector '{selector}' matched nothing")
    return found


def _parse_article(article: Tag) -> BookData:
    return BookData(
        title=_extract_title(article),
        price=_extract_price(article),
        availability=_extract_availability(article),
        rating=_extract_rating(article),
    )


def _extract_title(article: Tag) -> str:
    a = _require(article, "h3 > a")
    # Prefer the `title` attribute — it holds the full title when the visible
    # text is truncated (e.g. "A Light in the ..." vs "A Light in the Attic").
    title_attr = a.get("title")
    if isinstance(title_attr, str) and title_attr:
        return title_attr
    return a.get_text(strip=True)


def _extract_price(article: Tag) -> str:
    return _require(article, "p.price_color").get_text(strip=True)


def _extract_availability(article: Tag) -> str:
    return _require(article, "p.availability").get_text(strip=True)


def _extract_rating(article: Tag) -> str:
    p = _require(article, "p.star-rating")
    classes = p.get("class")
    if not isinstance(classes, list):  # pragma: no cover
        raise ParseError("star-rating element has no class attribute")
    # Class list is ["star-rating", "Three"] — the rating word is the second class.
    rating = next((c for c in classes if c != "star-rating"), None)
    if rating is None:
        raise ParseError("rating word not found in star-rating class list")
    return rating
