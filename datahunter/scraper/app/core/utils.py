from __future__ import annotations

import re
from collections.abc import Callable, Generator, Iterable
from typing import Any

# Module-level constant avoids the mutable-default-argument trap entirely.
_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": "datahunter/0.1",
    "Accept-Encoding": "gzip",
    "Accept": "text/html,application/xhtml+xml",
}


# ── Mutability ────────────────────────────────────────────────────────────────

def build_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a fresh headers dict, optionally merged with caller-supplied extras.

    Why: using `def f(extra={})` shares the same dict across every call.
    A caller adding a key would silently corrupt all future calls.
    """
    base = dict(_DEFAULT_HEADERS)
    if extra:
        base.update(extra)
    return base


def merge_settings(
    defaults: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a new dict with overrides applied — never mutates defaults."""
    result = dict(defaults)
    if overrides:
        result.update(overrides)
    return result


# ── Closures ──────────────────────────────────────────────────────────────────

def make_url_normalizer(base_url: str) -> Callable[[str], str]:
    """Return a closure that resolves relative paths against base_url.

    Useful when a spider is scoped to one domain: the base URL is captured
    once and reused across thousands of calls without being passed every time.
    """
    def normalize(path: str) -> str:
        if path.startswith("http"):
            return path
        return base_url.rstrip("/") + "/" + path.lstrip("/")

    return normalize


def make_request_counter() -> Callable[[], int]:
    """Return a closure that tracks how many requests have been made.

    Each call to make_request_counter() creates an independent counter,
    so two spiders running in the same process never share state.
    """
    count = 0

    def increment() -> int:
        nonlocal count
        count += 1
        return count

    return increment


# ── Generators vs list comprehensions ────────────────────────────────────────

def extract_links_eager(pages: list[str]) -> list[str]:
    """Return ALL links from all pages as a list.

    Simple and readable, but materialises the entire result in memory.
    Fine for small crawls; avoid when pages can be in the thousands.
    """
    return [link for page in pages for link in _parse_links(page)]


def extract_links_lazy(pages: Iterable[str]) -> Generator[str, None, None]:
    """Yield links one at a time without holding the full result in memory.

    The caller controls how many items are consumed at once, which is what
    makes pipeline composition (`fetch | parse | store`) memory-safe.
    """
    for page in pages:
        yield from _parse_links(page)


def chunk_urls(urls: list[str], size: int) -> Generator[list[str], None, None]:
    """Yield successive batches of `size` URLs.

    Useful for rate-controlled fetching: fetch one batch, wait, fetch next.
    """
    for i in range(0, len(urls), size):
        yield urls[i : i + size]


def _parse_links(html: str) -> list[str]:
    """Extract href values from a raw HTML snippet (naive regex, for demos)."""
    return [str(m) for m in re.findall(r'href="([^"]+)"', html)]
