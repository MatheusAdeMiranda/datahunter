from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from scraper.app.core.async_http_client import AsyncHTTPClient
from scraper.app.spiders.async_books_spider import AsyncBooksSpider

FIXTURES = Path(__file__).parent / "fixtures"
PAGE1_URL = "https://books.toscrape.com/catalogue/page-1.html"
PAGE2_URL = "https://books.toscrape.com/catalogue/page-2.html"

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

_BROKEN_WITH_NEXT_HTML = """\
<!DOCTYPE html><html><body>
<p>no articles here</p>
<ul class="pager"><li class="next"><a href="page-2.html">next</a></li></ul>
</body></html>"""


def _page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ── Pagination and collection ─────────────────────────────────────────────────


@respx.mock
async def test_crawl_follows_next_link_and_collects_all_items(tmp_path: Path) -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page1.html")))
    respx.get(PAGE2_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    output = tmp_path / "books.json"
    async with AsyncHTTPClient() as client:
        result = await AsyncBooksSpider(client, base_url=PAGE1_URL, output_path=output).crawl()

    assert len(result) == 4
    assert result.errors == []
    assert result.ok
    assert len([i for i in result.items if i.url == PAGE1_URL]) == 2
    assert len([i for i in result.items if i.url == PAGE2_URL]) == 2


@respx.mock
async def test_stops_on_last_page_without_next_link() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    async with AsyncHTTPClient() as client:
        result = await AsyncBooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert len(result) == 2
    assert result.errors == []


@respx.mock
async def test_deduplication_prevents_revisiting_same_url() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_CIRCULAR_HTML))

    async with AsyncHTTPClient() as client:
        result = await AsyncBooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert len(result) == 1
    assert respx.calls.call_count == 1


@respx.mock
async def test_max_pages_limits_crawl() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page1.html")))

    async with AsyncHTTPClient() as client:
        result = await AsyncBooksSpider(
            client, base_url=PAGE1_URL, max_pages=1, output_path=None
        ).crawl()

    assert len(result) == 2
    assert respx.calls.call_count == 1


# ── Error handling ────────────────────────────────────────────────────────────


@respx.mock
async def test_network_error_stops_crawl_and_records_error() -> None:
    from scraper.app.core.exceptions import NetworkError

    respx.get(PAGE1_URL).mock(side_effect=NetworkError("timeout"))

    async with AsyncHTTPClient(max_attempts=1) as client:
        result = await AsyncBooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert len(result) == 0
    assert len(result.errors) == 1
    assert "network error" in result.errors[0]


@respx.mock
async def test_parse_error_is_recorded_but_crawl_continues() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_BROKEN_WITH_NEXT_HTML))
    respx.get(PAGE2_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    async with AsyncHTTPClient() as client:
        result = await AsyncBooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert len(result) == 2
    assert len(result.errors) == 1
    assert "parse error" in result.errors[0]


# ── JSON output ───────────────────────────────────────────────────────────────


@respx.mock
async def test_saves_json_output(tmp_path: Path) -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page1.html")))

    output = tmp_path / "out.json"
    async with AsyncHTTPClient() as client:
        await AsyncBooksSpider(client, base_url=PAGE1_URL, max_pages=1, output_path=output).crawl()

    assert output.exists()
    data = json.loads(output.read_text())
    assert len(data) == 2
    assert "title" in data[0]["data"]


@respx.mock
async def test_no_json_output_when_output_path_is_none() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    async with AsyncHTTPClient() as client:
        result = await AsyncBooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert len(result) == 2


# ── Storage integration ───────────────────────────────────────────────────────


@respx.mock
async def test_saves_to_storage_when_provided() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page1.html")))
    respx.get(PAGE2_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    mock_storage = AsyncMock()
    mock_storage.save_items = AsyncMock(return_value=2)

    async with AsyncHTTPClient() as client:
        result = await AsyncBooksSpider(
            client, base_url=PAGE1_URL, output_path=None, storage=mock_storage
        ).crawl()

    assert len(result) == 4
    assert mock_storage.save_items.await_count == 2


@respx.mock
async def test_no_storage_call_when_storage_is_none() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    async with AsyncHTTPClient() as client:
        result = await AsyncBooksSpider(
            client, base_url=PAGE1_URL, output_path=None, storage=None
        ).crawl()

    assert len(result) == 2


# ── Item data ─────────────────────────────────────────────────────────────────


@respx.mock
async def test_items_have_correct_url_and_fields() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page1.html")))

    async with AsyncHTTPClient() as client:
        result = await AsyncBooksSpider(
            client, base_url=PAGE1_URL, max_pages=1, output_path=None
        ).crawl()

    for item in result.items:
        assert item.url == PAGE1_URL
        assert "title" in item.data
        assert "price" in item.data
        assert "availability" in item.data
        assert "rating" in item.data


@respx.mock
async def test_empty_result_when_single_page_has_no_books() -> None:
    respx.get(PAGE1_URL).mock(
        return_value=httpx.Response(
            200, text="<!DOCTYPE html><html><body><p>nothing</p></body></html>"
        )
    )

    async with AsyncHTTPClient() as client:
        result = await AsyncBooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert len(result) == 0
    assert len(result.errors) == 1
    assert "parse error" in result.errors[0]


# ── Respx call count assertions ───────────────────────────────────────────────


@respx.mock
async def test_two_page_crawl_makes_exactly_two_requests() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_page("books_page1.html")))
    respx.get(PAGE2_URL).mock(return_value=httpx.Response(200, text=_page("books_page2.html")))

    async with AsyncHTTPClient() as client:
        await AsyncBooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert respx.calls.call_count == 2


@pytest.mark.parametrize(
    "status_code",
    [pytest.param(200, id="ok"), pytest.param(404, id="not-found")],
)
@respx.mock
async def test_non_retryable_response_processed_as_html(status_code: int) -> None:
    """Non-retryable 4xx responses are returned to the spider and treated as HTML."""
    respx.get(PAGE1_URL).mock(
        return_value=httpx.Response(status_code, text=_page("books_page2.html"))
    )

    async with AsyncHTTPClient(max_attempts=1) as client:
        result = await AsyncBooksSpider(client, base_url=PAGE1_URL, output_path=None).crawl()

    assert result.errors == []
    assert len(result) == 2
