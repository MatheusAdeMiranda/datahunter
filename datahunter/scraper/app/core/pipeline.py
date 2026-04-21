from __future__ import annotations

import functools
import itertools
import re
from collections.abc import Callable, Generator, Iterable, Iterator

from scraper.app.core.entities import ScrapedItem

FetchFn = Callable[[str], str]

_REQUIRED_FIELDS: frozenset[str] = frozenset({"title", "price"})


@functools.lru_cache(maxsize=128)
def _compile(pattern: str) -> re.Pattern[str]:
    # Compiled patterns are cached — scrapers call the same regex on every page.
    return re.compile(pattern)


def _parse_items(html: str, source_url: str) -> list[ScrapedItem]:
    titles = _compile(r'class="title">([^<]+)<').findall(html)
    prices = _compile(r'class="price">([^<]+)<').findall(html)
    return [
        ScrapedItem(url=source_url, data={"title": str(t), "price": str(p)})
        for t, p in zip(titles, prices, strict=False)
    ]


class PageIterator:
    """Iterate pages of a paginated site lazily using __iter__ / __next__.

    Each __next__ call fetches exactly one page — nothing is pre-loaded.
    Stops when fetch_fn returns empty HTML or max_pages is reached.
    """

    def __init__(self, base_url: str, fetch_fn: FetchFn, max_pages: int = 50) -> None:
        self._base_url = base_url
        self._fetch_fn = fetch_fn
        self._max_pages = max_pages
        self._page = 1

    def __iter__(self) -> Iterator[str]:
        return self

    def __next__(self) -> str:
        if self._page > self._max_pages:
            raise StopIteration
        url = f"{self._base_url}/page-{self._page}.html"
        html = self._fetch_fn(url)
        if not html:
            raise StopIteration
        self._page += 1
        return html

    def __repr__(self) -> str:
        return f"PageIterator(base_url={self._base_url!r}, page={self._page}/{self._max_pages})"


# ── Generator pipeline steps ──────────────────────────────────────────────────


def fetch_pages(
    base_url: str, fetch_fn: FetchFn, max_pages: int = 50
) -> Generator[str, None, None]:
    """Yield HTML pages one at a time via PageIterator."""
    yield from PageIterator(base_url, fetch_fn, max_pages)


def extract_items(pages: Iterable[str], source_url: str) -> Generator[ScrapedItem, None, None]:
    """Yield ScrapedItems parsed from each HTML page."""
    for html in pages:
        yield from _parse_items(html, source_url)


def filter_valid(
    items: Iterable[ScrapedItem],
    required: frozenset[str] = _REQUIRED_FIELDS,
) -> Generator[ScrapedItem, None, None]:
    """Yield only items that have all required fields with non-empty values."""
    for item in items:
        if all(item.data.get(field) for field in required):
            yield item


def normalize(items: Iterable[ScrapedItem]) -> Generator[ScrapedItem, None, None]:
    """Yield items with whitespace stripped from all field values."""
    for item in items:
        item.data = {k: v.strip() for k, v in item.data.items()}
        yield item


def run_pipeline(
    base_url: str, fetch_fn: FetchFn, max_pages: int = 50
) -> Generator[ScrapedItem, None, None]:
    """Chain fetch → extract → filter → normalize into one lazy pipeline."""
    pages = fetch_pages(base_url, fetch_fn, max_pages)
    items = extract_items(pages, base_url)
    valid = filter_valid(items)
    return normalize(valid)


# ── itertools helpers ─────────────────────────────────────────────────────────


def merge_sources(*sources: Iterable[ScrapedItem]) -> Generator[ScrapedItem, None, None]:
    """Combine multiple item streams into one using itertools.chain."""
    yield from itertools.chain(*sources)


def take(items: Iterable[ScrapedItem], n: int) -> Generator[ScrapedItem, None, None]:
    """Yield at most n items from a stream using itertools.islice."""
    yield from itertools.islice(items, n)


# ── functools.partial ─────────────────────────────────────────────────────────


def make_take(n: int) -> Callable[[Iterable[ScrapedItem]], Generator[ScrapedItem, None, None]]:
    """Return a take() step pre-configured with n via functools.partial.

    Why partial: lets callers build reusable pipeline pieces without repeating
    arguments. `take_five = make_take(5)` works as a drop-in pipeline step.
    """
    return functools.partial(take, n=n)
