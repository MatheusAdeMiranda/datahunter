from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, Route, async_playwright

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_MS = 30_000
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Route handlers may be async or sync; Playwright supports both.
RouteHandler = Callable[[Route, Any], Awaitable[None] | None]


class AsyncPlaywrightClient:
    """Async context manager that owns a single headless Chromium browser process.

    Each fetch_html() call opens an isolated BrowserContext and closes it when
    done — no cookie or storage leakage between concurrent requests.

    Pass an asyncio.Semaphore to cap how many contexts run simultaneously::

        sem = asyncio.Semaphore(3)
        htmls = await asyncio.gather(
            *[client.fetch_html(url, semaphore=sem) for url in urls]
        )

    Routes registered via add_route() are applied to every page created by
    this client — useful in tests to serve static HTML without real network.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
        user_agent: str = _DEFAULT_USER_AGENT,
    ) -> None:
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._user_agent = user_agent
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._routes: list[tuple[str, RouteHandler]] = []

    # ── context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> AsyncPlaywrightClient:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        logger.info("browser launched (headless=%s)", self._headless)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            await self._browser.close()
            logger.info("browser closed")
        if self._playwright is not None:
            await self._playwright.stop()

    # ── public API ────────────────────────────────────────────────────────────

    def add_route(self, url_pattern: str, handler: RouteHandler) -> None:
        """Register a route handler applied to every future page."""
        self._routes.append((url_pattern, handler))

    async def new_page(self, *, extra_headers: dict[str, str] | None = None) -> Page:
        """Return a fresh Page inside its own isolated BrowserContext."""
        if self._browser is None:
            raise RuntimeError("AsyncPlaywrightClient must be used as a context manager")
        context: BrowserContext = await self._browser.new_context(
            user_agent=self._user_agent,
            extra_http_headers=extra_headers or {},
        )
        page: Page = await context.new_page()
        page.set_default_timeout(self._timeout_ms)
        for pattern, handler in self._routes:
            await page.route(pattern, handler)
        return page

    async def fetch_html(
        self,
        url: str,
        *,
        wait_for: str | None = None,
        semaphore: asyncio.Semaphore | None = None,
    ) -> str:
        """Navigate to *url*, optionally wait for a CSS selector, return HTML.

        The BrowserContext is always closed on return — even on exception.
        Acquire *semaphore* before opening the context to limit concurrency.
        """
        if self._browser is None:
            raise RuntimeError("AsyncPlaywrightClient must be used as a context manager")

        lock: AbstractAsyncContextManager[Any] = (
            semaphore if semaphore is not None else contextlib.nullcontext()
        )
        async with lock:
            ctx: BrowserContext = await self._browser.new_context(
                user_agent=self._user_agent,
            )
            try:
                page: Page = await ctx.new_page()
                page.set_default_timeout(self._timeout_ms)
                for pattern, handler in self._routes:
                    await page.route(pattern, handler)

                logger.info("navigating to %s", url)
                await page.goto(url, wait_until="domcontentloaded")

                if wait_for is not None:
                    logger.debug("waiting for selector %r", wait_for)
                    await page.wait_for_selector(wait_for, state="visible")

                html: str = await page.content()
            finally:
                await ctx.close()

        return html
