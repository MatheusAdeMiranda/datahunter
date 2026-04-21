from __future__ import annotations

import re
from collections.abc import Callable, Generator, Iterable
from types import MappingProxyType
from typing import Any, cast

# MappingProxyType makes this truly read-only: any attempt to mutate it raises
# TypeError at runtime, so callers cannot corrupt future build_headers() calls.
_DEFAULT_HEADERS: MappingProxyType[str, str] = MappingProxyType(
    {
        "User-Agent": "datahunter/0.1",
        "Accept-Encoding": "gzip",
        "Accept": "text/html,application/xhtml+xml",
    }
)


# ── Mutability ────────────────────────────────────────────────────────────────


def build_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a fresh headers dict merged with any caller-supplied extras."""
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
    """Return a closure that resolves relative paths against a fixed base URL."""

    def normalize(path: str) -> str:
        if path.startswith("http"):
            return path
        return base_url.rstrip("/") + "/" + path.lstrip("/")

    return normalize


def make_request_counter() -> Callable[[], int]:
    """Return a closure that increments and returns an independent call count."""
    count = 0

    def increment() -> int:
        nonlocal count
        count += 1
        return count

    return increment


# ── Generators vs list comprehensions ────────────────────────────────────────


def extract_links_eager(pages: list[str]) -> list[str]:
    """Return all links from all pages as a list (materialises everything in memory)."""
    return [link for page in pages for link in _parse_links(page)]


def extract_links_lazy(pages: Iterable[str]) -> Generator[str, None, None]:
    """Yield links one at a time — memory-safe for arbitrarily large crawls."""
    for page in pages:
        yield from _parse_links(page)


def chunk_urls(urls: list[str], size: int) -> Generator[list[str], None, None]:
    """Yield successive URL batches of `size` for rate-controlled fetching."""
    for i in range(0, len(urls), size):
        yield urls[i : i + size]


def _parse_links(html: str) -> list[str]:
    """Extract href values from a raw HTML snippet (naive regex, for demos)."""
    return cast(list[str], re.findall(r'href="([^"]+)"', html))
