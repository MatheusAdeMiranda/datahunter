from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from types import TracebackType
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Route,
    sync_playwright,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_MS = 30_000
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Type alias for route handlers: (route, request) -> None
RouteHandler = Callable[[Route, Any], None]


class PlaywrightClient:
    """Sync context manager that owns a headless Chromium browser lifecycle.

    Usage::

        with PlaywrightClient() as client:
            page = client.new_page()
            page.goto("https://example.com")
            title = page.title()

    A new BrowserContext is created per ``new_page()`` call so cookies and
    storage are isolated between pages.  The browser is closed when the
    ``with`` block exits.

    Route handlers registered via ``add_route()`` are applied to every page
    created by this client — useful for intercepting requests in tests.
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

    def __enter__(self) -> PlaywrightClient:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        logger.info("browser launched (headless=%s)", self._headless)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            self._browser.close()
            logger.info("browser closed")
        if self._playwright is not None:
            self._playwright.stop()

    # ── public API ────────────────────────────────────────────────────────────

    def add_route(self, url_pattern: str, handler: RouteHandler) -> None:
        """Register a route handler applied to every future page.

        Handlers are applied in registration order.  Useful in tests to serve
        static HTML without a real network::

            client.add_route("**/*", lambda route, req: route.fulfill(...))
        """
        self._routes.append((url_pattern, handler))

    def new_page(self, *, extra_headers: dict[str, str] | None = None) -> Page:
        """Return a fresh Page inside its own isolated BrowserContext."""
        if self._browser is None:
            raise RuntimeError("PlaywrightClient must be used as a context manager")

        context: BrowserContext = self._browser.new_context(
            user_agent=self._user_agent,
            extra_http_headers=extra_headers or {},
        )
        page = context.new_page()
        page.set_default_timeout(self._timeout_ms)
        for pattern, handler in self._routes:
            page.route(pattern, handler)
        return page

    def fetch_html(self, url: str, *, wait_for: str | None = None) -> str:
        """Navigate to *url*, optionally wait for a CSS selector, return HTML.

        ``wait_for`` is a CSS selector that must be visible before the HTML is
        captured.  Omit it for pages that signal readiness via
        ``load`` / ``networkidle``.
        """
        page = self.new_page()
        logger.info("navigating to %s", url)
        page.goto(url, wait_until="domcontentloaded")

        if wait_for is not None:
            logger.debug("waiting for selector %r", wait_for)
            page.wait_for_selector(wait_for, state="visible")

        html = page.content()
        page.context.close()
        return html

    def iter_pages(
        self,
        first_url: str,
        *,
        next_selector: str,
        wait_for: str | None = None,
        max_pages: int = 20,
    ) -> Iterator[str]:
        """Yield the HTML of each page, following *next_selector* pagination.

        Stops when the selector is absent or *max_pages* is reached.
        """
        page = self.new_page()
        page.goto(first_url, wait_until="domcontentloaded")
        if wait_for is not None:
            page.wait_for_selector(wait_for, state="visible")

        for page_num in range(1, max_pages + 1):
            logger.info("yielding page %d", page_num)
            yield page.content()

            if page_num == max_pages:
                logger.info("max_pages=%d reached — stopping", max_pages)
                break

            next_btn = page.locator(next_selector)
            if next_btn.count() == 0:
                logger.info("no next button — pagination done after %d page(s)", page_num)
                break

            next_btn.first.click()
            page.wait_for_load_state("domcontentloaded")
            if wait_for is not None:
                page.wait_for_selector(wait_for, state="visible")

        page.context.close()
