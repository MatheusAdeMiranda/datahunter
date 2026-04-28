from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from scraper.app.core.http_client import HTTPClient
from scraper.app.spiders.books_spider import BooksSpider

FIXTURES = Path(__file__).parent / "fixtures"
PAGE1_URL = "https://books.toscrape.com/catalogue/page-1.html"
PAGE2_URL = "https://books.toscrape.com/catalogue/page-2.html"

# HTML with a "next" link pointing back to itself — triggers deduplication guard.
_CIRCULAR_HTML = """\
<!DOCTYPE html><html><body>
<article class="product_pod">
  <p class="star-rating One"></p>
  <h3><a href="loop/index.html" title="Loop Book">Loop Book</a></h3>
  <div class="product_price">
    <p class="price_color">£9.99</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<ul class="pager"><li class="next"><a href="page-1.html">next</a></li></ul>
</body></html>"""

# HTML with a "next" link but no articles — triggers ParseError then follows next.
_BROKEN_WITH_NEXT_HTML = """\
<!DOCTYPE html><html><body>
<p>no articles here</p>
<ul class="pager"><li class="next"><a href="page-2.html">next</a></li></ul>
</body></html>"""


def _page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@respx.mock
def test_crawl_follows_next_link_and_collects_all_items(tmp_path: Path) -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page1.html")))
    respx.get(PAGE2_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    output = tmp_path / "books.json"
    with HTTPClient() as client:
        result = BooksSpider(client, base_url=PAGE1_URL, output_path=output).crawl()

    assert len(result) == 4
    assert result.errors == []
    assert result.ok
    page1_items = [i for i in result.items if i.url == PAGE1_URL]
    page2_items = [i for i in result.items if i.url == PAGE2_URL]
    assert len(page1_items) == 2
    assert len(page2_items) == 2


@respx.mock
def test_stops_on_last_page_without_next_link() -> None:
    # books_page2.html has only a "previous" link, no "next".
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    with HTTPClient() as client:
        result = BooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert len(result) == 2
    assert result.errors == []


@respx.mock
def test_deduplication_prevents_revisiting_same_url() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_CIRCULAR_HTML))

    with HTTPClient() as client:
        result = BooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    # Only one page fetched; circular next link was detected and skipped.
    assert len(result) == 1
    assert result.errors == []


@respx.mock
def test_max_pages_limits_crawl() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page1.html")))

    with HTTPClient() as client:
        result = BooksSpider(client, base_url=PAGE1_URL, max_pages=1, output_path=None).crawl()

    # max_pages=1 stops after the first page even though books_page1 has a next link.
    assert len(result) == 2
    assert result.errors == []


@respx.mock
def test_network_error_stops_crawl_and_records_error() -> None:
    respx.get(PAGE1_URL).mock(side_effect=httpx.ConnectError("connection refused"))

    with HTTPClient(max_attempts=1) as client:
        result = BooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert len(result) == 0
    assert len(result.errors) == 1
    assert "network error" in result.errors[0]


@respx.mock
def test_parse_error_is_recorded_and_crawl_stops_without_next_link() -> None:
    # HTML with no articles and no next link — parse fails, nothing to follow.
    broken_html = "<html><body><p>no articles</p></body></html>"
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=broken_html))

    with HTTPClient() as client:
        result = BooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert len(result) == 0
    assert len(result.errors) == 1
    assert "parse error" in result.errors[0]


@respx.mock
def test_parse_error_on_page_still_follows_next_link() -> None:
    # Page 1 has no articles but does have a next link.
    # The spider should record the parse error AND still visit page 2.
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_BROKEN_WITH_NEXT_HTML))
    respx.get(PAGE2_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    with HTTPClient() as client:
        result = BooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert len(result.errors) == 1
    assert "parse error" in result.errors[0]
    assert len(result) == 2  # 2 books collected from page 2


@respx.mock
def test_json_output_has_correct_structure(tmp_path: Path) -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    output = tmp_path / "out" / "books.json"
    with HTTPClient() as client:
        BooksSpider(client, base_url=PAGE1_URL, output_path=output).crawl()

    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 2
    record = data[0]
    assert record["url"] == PAGE1_URL
    assert set(record["data"]) == {"title", "price", "availability", "rating"}
    assert "scraped_at" in record


@respx.mock
def test_json_output_creates_parent_directories(tmp_path: Path) -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    output = tmp_path / "deep" / "nested" / "books.json"
    with HTTPClient() as client:
        BooksSpider(client, base_url=PAGE1_URL, output_path=output).crawl()

    assert output.exists()


@respx.mock
def test_no_file_written_when_output_path_is_none(tmp_path: Path) -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    with HTTPClient() as client:
        BooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert list(tmp_path.iterdir()) == []


@respx.mock
def test_items_contain_expected_book_fields() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page1.html")))
    respx.get(PAGE2_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    with HTTPClient() as client:
        result = BooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    titles = {item.data["title"] for item in result.items}
    assert "A Light in the Attic" in titles
    assert "Tipping the Velvet" in titles
    assert "Soumission" in titles
    assert "Sharp Objects" in titles
