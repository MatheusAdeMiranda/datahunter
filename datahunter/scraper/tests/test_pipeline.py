import sys
from collections.abc import Callable

from scraper.app.core.entities import ScrapedItem
from scraper.app.core.pipeline import (
    PageIterator,
    _compile,
    extract_items,
    filter_valid,
    make_take,
    merge_sources,
    normalize,
    run_pipeline,
    take,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

BASE_URL = "https://books.toscrape.com"


def _html(n: int) -> str:
    """Return minimal HTML with n items matching the parser's patterns."""
    items = "".join(
        f'<h3 class="title"> Book {i} </h3><p class="price"> £{i}.99 </p>' for i in range(1, n + 1)
    )
    return f"<html>{items}</html>"


def _make_fetch(pages: dict[str, str]) -> Callable[[str], str]:
    """Return a fetch_fn that serves pages from a dict, empty string otherwise."""

    def fetch(url: str) -> str:
        return pages.get(url, "")

    return fetch


# ── PageIterator ──────────────────────────────────────────────────────────────


class TestPageIterator:
    def test_yields_pages_in_order(self) -> None:
        pages = {
            f"{BASE_URL}/page-1.html": "<html>p1</html>",
            f"{BASE_URL}/page-2.html": "<html>p2</html>",
        }
        result = list(PageIterator(BASE_URL, _make_fetch(pages)))
        assert result == ["<html>p1</html>", "<html>p2</html>"]

    def test_stops_when_fetch_returns_empty(self) -> None:
        pages = {f"{BASE_URL}/page-1.html": "<html>p1</html>"}
        result = list(PageIterator(BASE_URL, _make_fetch(pages)))
        assert len(result) == 1

    def test_stops_at_max_pages(self) -> None:
        # All pages available but max_pages=2 must limit to 2.
        pages = {f"{BASE_URL}/page-{i}.html": f"<html>p{i}</html>" for i in range(1, 10)}
        result = list(PageIterator(BASE_URL, _make_fetch(pages), max_pages=2))
        assert len(result) == 2

    def test_implements_iterator_protocol(self) -> None:
        it = PageIterator(BASE_URL, _make_fetch({}))
        assert iter(it) is it  # __iter__ returns self

    def test_repr_is_readable(self) -> None:
        it = PageIterator(BASE_URL, _make_fetch({}))
        assert BASE_URL in repr(it)
        assert "PageIterator" in repr(it)

    def test_is_lazy_not_eager(self) -> None:
        called: list[str] = []

        def tracking_fetch(url: str) -> str:
            called.append(url)
            return f"<html>{url}</html>"

        it = PageIterator(BASE_URL, tracking_fetch, max_pages=3)
        assert called == []  # nothing fetched until iteration starts
        next(it)
        assert len(called) == 1  # exactly one call per __next__
        next(it)
        assert len(called) == 2


# ── extract_items ─────────────────────────────────────────────────────────────


class TestExtractItems:
    def test_extracts_all_items_from_page(self) -> None:
        items = list(extract_items([_html(3)], BASE_URL))
        assert len(items) == 3
        assert items[0].data["title"] == " Book 1 "  # not yet normalised

    def test_yields_scraped_items(self) -> None:
        items = list(extract_items([_html(1)], BASE_URL))
        assert all(isinstance(i, ScrapedItem) for i in items)

    def test_empty_page_yields_nothing(self) -> None:
        assert list(extract_items(["<html></html>"], BASE_URL)) == []

    def test_processes_multiple_pages(self) -> None:
        items = list(extract_items([_html(2), _html(2)], BASE_URL))
        assert len(items) == 4


# ── filter_valid ──────────────────────────────────────────────────────────────


class TestFilterValid:
    def _item(self, **data: str) -> ScrapedItem:
        return ScrapedItem(url=BASE_URL, data=dict(data))

    def test_passes_items_with_all_required_fields(self) -> None:
        item = self._item(title="Book", price="£9.99")
        assert list(filter_valid([item])) == [item]

    def test_drops_items_missing_required_field(self) -> None:
        item = self._item(title="Book")  # no price
        assert list(filter_valid([item])) == []

    def test_drops_items_with_empty_field(self) -> None:
        item = self._item(title="", price="£9.99")
        assert list(filter_valid([item])) == []

    def test_custom_required_fields(self) -> None:
        item = self._item(title="Book")
        assert list(filter_valid([item], required=frozenset({"title"}))) == [item]


# ── normalize ─────────────────────────────────────────────────────────────────


class TestNormalize:
    def test_strips_whitespace_from_values(self) -> None:
        item = ScrapedItem(url=BASE_URL, data={"title": " Book ", "price": " £9 "})
        result = list(normalize([item]))
        assert result[0].data == {"title": "Book", "price": "£9"}

    def test_mutates_item_in_place_and_yields_same_object(self) -> None:
        item = ScrapedItem(url=BASE_URL, data={"title": " X "})
        result = list(normalize([item]))
        assert result[0] is item  # same object, not a copy


# ── run_pipeline ──────────────────────────────────────────────────────────────


class TestRunPipeline:
    def test_end_to_end_collects_and_cleans_items(self) -> None:
        fetch = _make_fetch({f"{BASE_URL}/page-1.html": _html(3)})
        items = list(run_pipeline(BASE_URL, fetch, max_pages=1))
        assert len(items) == 3
        assert items[0].data["title"] == "Book 1"  # whitespace stripped

    def test_pipeline_is_a_generator(self) -> None:
        fetch = _make_fetch({})
        result = run_pipeline(BASE_URL, fetch)
        assert hasattr(result, "__next__")

    def test_pipeline_uses_less_memory_than_list(self) -> None:
        pages = {f"{BASE_URL}/page-{i}.html": _html(10) for i in range(1, 11)}
        gen = run_pipeline(BASE_URL, _make_fetch(pages), max_pages=10)
        lst = list(run_pipeline(BASE_URL, _make_fetch(pages), max_pages=10))
        # Generator object is a fixed ~120 bytes; materialised list is much larger.
        assert sys.getsizeof(gen) < sys.getsizeof(lst)

    def test_multiple_pages_are_all_collected(self) -> None:
        pages = {
            f"{BASE_URL}/page-1.html": _html(2),
            f"{BASE_URL}/page-2.html": _html(2),
        }
        items = list(run_pipeline(BASE_URL, _make_fetch(pages), max_pages=5))
        assert len(items) == 4


# ── itertools helpers ─────────────────────────────────────────────────────────


class TestMergeSources:
    def _items(self, n: int) -> list[ScrapedItem]:
        return [ScrapedItem(url=f"{BASE_URL}/{i}", data={"title": str(i)}) for i in range(n)]

    def test_chains_multiple_sources(self) -> None:
        a, b = self._items(2), self._items(3)
        assert len(list(merge_sources(a, b))) == 5

    def test_empty_sources_yield_nothing(self) -> None:
        assert list(merge_sources([], [])) == []


class TestTake:
    def _items(self, n: int) -> list[ScrapedItem]:
        return [ScrapedItem(url=f"{BASE_URL}/{i}", data={"title": str(i)}) for i in range(n)]

    def test_limits_to_n_items(self) -> None:
        assert len(list(take(self._items(10), 3))) == 3

    def test_take_more_than_available_returns_all(self) -> None:
        assert len(list(take(self._items(3), 10))) == 3


# ── functools helpers ─────────────────────────────────────────────────────────


class TestMakeTake:
    def _items(self, n: int) -> list[ScrapedItem]:
        return [ScrapedItem(url=f"{BASE_URL}/{i}", data={"title": str(i)}) for i in range(n)]

    def test_returns_a_callable(self) -> None:
        assert callable(make_take(5))

    def test_pre_configured_n_is_applied(self) -> None:
        take_three = make_take(3)
        assert len(list(take_three(self._items(10)))) == 3

    def test_independent_instances_have_independent_n(self) -> None:
        take_two = make_take(2)
        take_five = make_take(5)
        items = self._items(10)
        assert len(list(take_two(items))) == 2
        assert len(list(take_five(items))) == 5


# ── lru_cache ─────────────────────────────────────────────────────────────────


class TestLruCache:
    def test_same_pattern_reuses_compiled_object(self) -> None:
        _compile.cache_clear()
        p1 = _compile(r"\d+")
        p2 = _compile(r"\d+")
        assert p1 is p2  # same object from cache

    def test_different_patterns_compile_separately(self) -> None:
        p1 = _compile(r"\d+")
        p2 = _compile(r"\w+")
        assert p1 is not p2

    def test_cache_info_tracks_hits(self) -> None:
        _compile.cache_clear()
        _compile(r"test")
        _compile(r"test")  # cache hit
        info = _compile.cache_info()
        assert info.hits >= 1
