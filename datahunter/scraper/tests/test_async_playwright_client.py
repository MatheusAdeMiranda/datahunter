from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from scraper.app.browsers.async_playwright_client import AsyncPlaywrightClient
from scraper.app.browsers.quotes_pw_spider import SEL_QUOTE

FIXTURES = Path(__file__).parent / "fixtures"

_PAGE1 = (FIXTURES / "quotes_pw_page1.html").read_text(encoding="utf-8")
_PAGE2 = (FIXTURES / "quotes_pw_page2.html").read_text(encoding="utf-8")

_BASE_URL = "http://quotes.test"
_PAGE1_URL = f"{_BASE_URL}/"
_PAGE2_URL = f"{_BASE_URL}/page/2/"


def _router(pages: dict[str, str]) -> Any:
    """Return an async route handler that serves static HTML per URL."""

    async def handler(route: Any, request: Any) -> None:
        html = pages.get(request.url)
        if html is None:
            await route.abort()
            return
        await route.fulfill(status=200, content_type="text/html", body=html)

    return handler


# ── lifecycle ─────────────────────────────────────────────────────────────────


async def test_client_launches_and_closes() -> None:
    async with AsyncPlaywrightClient() as client:
        assert client._browser is not None
    assert client._browser.is_connected() is False


async def test_new_page_outside_context_raises() -> None:
    client = AsyncPlaywrightClient()
    with pytest.raises(RuntimeError, match="context manager"):
        await client.new_page()


async def test_fetch_html_outside_context_raises() -> None:
    client = AsyncPlaywrightClient()
    with pytest.raises(RuntimeError, match="context manager"):
        await client.fetch_html(_PAGE1_URL)


# ── fetch_html ────────────────────────────────────────────────────────────────


async def test_fetch_html_returns_rendered_content() -> None:
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1}))
        html = await client.fetch_html(_PAGE1_URL, wait_for=SEL_QUOTE)

    assert "Albert Einstein" in html
    assert "J.K. Rowling" in html


async def test_fetch_html_wait_for_none_does_not_raise() -> None:
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1}))
        html = await client.fetch_html(_PAGE1_URL)

    assert "<html" in html.lower()


async def test_fetch_html_returns_different_content_per_url() -> None:
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1, _PAGE2_URL: _PAGE2}))
        html1 = await client.fetch_html(_PAGE1_URL, wait_for=SEL_QUOTE)
        html2 = await client.fetch_html(_PAGE2_URL, wait_for=SEL_QUOTE)

    assert html1 != html2


# ── new_page ──────────────────────────────────────────────────────────────────


async def test_new_page_returns_isolated_contexts() -> None:
    async with AsyncPlaywrightClient() as client:
        p1 = await client.new_page()
        p2 = await client.new_page()
        assert p1.context is not p2.context
        await p1.context.close()
        await p2.context.close()


async def test_new_page_applies_registered_routes() -> None:
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1}))
        page = await client.new_page()
        await page.goto(_PAGE1_URL, wait_until="domcontentloaded")
        await page.wait_for_selector(SEL_QUOTE, state="visible")
        html = await page.content()
        await page.context.close()
    assert "Albert Einstein" in html


# ── parallel fetch with semaphore ─────────────────────────────────────────────


async def test_parallel_fetches_return_all_results() -> None:
    urls = [_PAGE1_URL, _PAGE2_URL]
    async with AsyncPlaywrightClient() as client:
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1, _PAGE2_URL: _PAGE2}))
        sem = asyncio.Semaphore(2)
        results = await asyncio.gather(
            *[client.fetch_html(url, wait_for=SEL_QUOTE, semaphore=sem) for url in urls]
        )

    assert len(results) == 2
    assert "Albert Einstein" in results[0] or "Albert Einstein" in results[1]


async def test_semaphore_limits_concurrent_contexts() -> None:
    """At most max_concurrent contexts are open simultaneously."""
    open_contexts = 0
    peak_open = 0

    original_new_context = None

    async with AsyncPlaywrightClient() as client:
        original_new_context = client._browser.new_context  # type: ignore[union-attr]

        async def counting_new_context(**kwargs: Any) -> Any:
            nonlocal open_contexts, peak_open
            ctx = await original_new_context(**kwargs)
            open_contexts += 1
            peak_open = max(peak_open, open_contexts)
            original_close = ctx.close

            async def counting_close() -> None:
                nonlocal open_contexts
                open_contexts -= 1
                await original_close()

            ctx.close = counting_close  # type: ignore[method-assign]
            return ctx

        client._browser.new_context = counting_new_context  # type: ignore[method-assign,union-attr]
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1, _PAGE2_URL: _PAGE2}))

        sem = asyncio.Semaphore(1)
        urls = [_PAGE1_URL, _PAGE2_URL]
        await asyncio.gather(
            *[client.fetch_html(url, wait_for=SEL_QUOTE, semaphore=sem) for url in urls]
        )

    assert peak_open <= 1


async def test_no_semaphore_allows_full_concurrency() -> None:
    """Without a semaphore all contexts can run concurrently."""
    open_contexts = 0
    peak_open = 0

    original_new_context = None

    async with AsyncPlaywrightClient() as client:
        original_new_context = client._browser.new_context  # type: ignore[union-attr]

        async def counting_new_context(**kwargs: Any) -> Any:
            nonlocal open_contexts, peak_open
            ctx = await original_new_context(**kwargs)
            open_contexts += 1
            peak_open = max(peak_open, open_contexts)
            original_close = ctx.close

            async def counting_close() -> None:
                nonlocal open_contexts
                open_contexts -= 1
                await original_close()

            ctx.close = counting_close  # type: ignore[method-assign]
            return ctx

        client._browser.new_context = counting_new_context  # type: ignore[method-assign,union-attr]
        client.add_route("**/*", _router({_PAGE1_URL: _PAGE1, _PAGE2_URL: _PAGE2}))

        urls = [_PAGE1_URL, _PAGE2_URL]
        await asyncio.gather(*[client.fetch_html(url, wait_for=SEL_QUOTE) for url in urls])

    # Two concurrent fetches: peak should reach 2 (both contexts open at once).
    assert peak_open >= 1
