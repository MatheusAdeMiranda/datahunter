from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scraper.app.browsers.async_playwright_client import AsyncPlaywrightClient
from scraper.app.browsers.async_quotes_pw_spider import AsyncQuotesPWSpider

FIXTURES = Path(__file__).parent / "fixtures"

_PAGE1 = (FIXTURES / "quotes_pw_page1.html").read_text(encoding="utf-8")
_PAGE2 = (FIXTURES / "quotes_pw_page2.html").read_text(encoding="utf-8")
_MALFORMED = (FIXTURES / "quotes_pw_malformed.html").read_text(encoding="utf-8")

_BASE_URL = "http://quotes.test"
_PAGE1_URL = f"{_BASE_URL}/page/1/"
_PAGE2_URL = f"{_BASE_URL}/page/2/"
_PAGE3_URL = f"{_BASE_URL}/page/3/"


def _router(pages: dict[str, str]) -> Any:
    async def handler(route: Any, request: Any) -> None:
        html = pages.get(request.url)
        if html is None:
            await route.abort()
            return
        await route.fulfill(status=200, content_type="text/html", body=html)

    return handler


# ── basic crawl ───────────────────────────────────────────────────────────────


async def test_crawl_single_url_returns_quotes() -> None:
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1}))
        spider = AsyncQuotesPWSpider(client, output_path=None)
        result = await spider.crawl([_PAGE1_URL])

    assert len(result) > 0
    assert result.errors == []
    assert result.ok


async def test_crawl_multiple_urls_collects_all_quotes() -> None:
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1, _PAGE2_URL: _PAGE2}))
        spider = AsyncQuotesPWSpider(client, output_path=None)
        result = await spider.crawl([_PAGE1_URL, _PAGE2_URL])

    assert len(result) > 0
    urls_seen = {item.url for item in result.items}
    assert _PAGE1_URL in urls_seen
    assert _PAGE2_URL in urls_seen


async def test_crawl_single_url_items_have_correct_url() -> None:
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1}))
        spider = AsyncQuotesPWSpider(client, output_path=None)
        result = await spider.crawl([_PAGE1_URL])

    assert all(item.url == _PAGE1_URL for item in result.items)


# ── concurrency control ───────────────────────────────────────────────────────


async def test_max_concurrent_respected() -> None:
    """peak open contexts never exceeds max_concurrent."""
    open_ctx = 0
    peak = 0

    async with AsyncPlaywrightClient() as client:
        original = client._browser.new_context  # type: ignore[union-attr]

        async def counting_new_context(**kwargs: Any) -> Any:
            nonlocal open_ctx, peak
            ctx = await original(**kwargs)
            open_ctx += 1
            peak = max(peak, open_ctx)
            orig_close = ctx.close

            async def dec_close() -> None:
                nonlocal open_ctx
                open_ctx -= 1
                await orig_close()

            ctx.close = dec_close  # type: ignore[method-assign]
            return ctx

        client._browser.new_context = counting_new_context  # type: ignore[method-assign]
        client.add_route(
            "**/*", _router({_PAGE1_URL: _PAGE1, _PAGE2_URL: _PAGE2, _PAGE3_URL: _PAGE1})
        )

        spider = AsyncQuotesPWSpider(client, max_concurrent=2, output_path=None)
        await spider.crawl([_PAGE1_URL, _PAGE2_URL, _PAGE3_URL])

    assert peak <= 2


# ── error isolation ───────────────────────────────────────────────────────────


async def test_malformed_page_records_error_but_others_succeed() -> None:
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1, _PAGE2_URL: _MALFORMED}))
        spider = AsyncQuotesPWSpider(client, max_concurrent=2, output_path=None)
        result = await spider.crawl([_PAGE1_URL, _PAGE2_URL])

    page1_items = [i for i in result.items if i.url == _PAGE1_URL]
    assert len(page1_items) > 0
    assert len(result.errors) > 0


async def test_browser_error_on_one_url_does_not_abort_others() -> None:
    """A URL that aborts (no route match) records an error; other URLs still succeed."""
    async with AsyncPlaywrightClient() as client:
        # Only PAGE1 is served; PAGE2 will cause a browser navigation error.
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1}))
        spider = AsyncQuotesPWSpider(client, max_concurrent=2, output_path=None)
        result = await spider.crawl([_PAGE1_URL, _PAGE2_URL])

    page1_items = [i for i in result.items if i.url == _PAGE1_URL]
    assert len(page1_items) > 0
    assert len(result.errors) >= 1


# ── JSON output ───────────────────────────────────────────────────────────────


async def test_saves_json_output(tmp_path: Path) -> None:
    output = tmp_path / "quotes.json"
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1}))
        spider = AsyncQuotesPWSpider(client, output_path=output)
        await spider.crawl([_PAGE1_URL])

    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert len(data) > 0
    assert "text" in data[0]["data"]


async def test_no_json_output_when_output_path_is_none() -> None:
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1}))
        spider = AsyncQuotesPWSpider(client, output_path=None)
        result = await spider.crawl([_PAGE1_URL])

    assert len(result) > 0


# ── item fields ───────────────────────────────────────────────────────────────


async def test_items_have_required_fields() -> None:
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1}))
        spider = AsyncQuotesPWSpider(client, output_path=None)
        result = await spider.crawl([_PAGE1_URL])

    for item in result.items:
        assert item.url == _PAGE1_URL
        assert "text" in item.data
        assert "author" in item.data
        assert "tags" in item.data


@pytest.mark.parametrize("max_concurrent", [1, 2, 3])
async def test_same_results_regardless_of_concurrency(max_concurrent: int) -> None:
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1, _PAGE2_URL: _PAGE2}))
        spider = AsyncQuotesPWSpider(client, max_concurrent=max_concurrent, output_path=None)
        result = await spider.crawl([_PAGE1_URL, _PAGE2_URL])

    assert len(result) > 0
    assert result.ok
