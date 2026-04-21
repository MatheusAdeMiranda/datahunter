import sys

import pytest

from scraper.app.core.utils import (
    _DEFAULT_HEADERS,
    build_headers,
    chunk_urls,
    extract_links_eager,
    extract_links_lazy,
    make_request_counter,
    make_url_normalizer,
    merge_settings,
)

_PAGES = [
    '<a href="/page-1">one</a><a href="/page-2">two</a>',
    '<a href="/page-3">three</a>',
]


# ── build_headers ─────────────────────────────────────────────────────────────


class TestBuildHeaders:
    def test_includes_user_agent(self) -> None:
        assert "datahunter" in build_headers()["User-Agent"]

    def test_extra_headers_are_merged(self) -> None:
        headers = build_headers({"Authorization": "Bearer token"})
        assert headers["Authorization"] == "Bearer token"
        assert "User-Agent" in headers

    def test_calls_do_not_share_state(self) -> None:
        h1 = build_headers()
        h2 = build_headers()
        h1["X-Poison"] = "mutated"
        # If the function used a mutable default, h2 would also have X-Poison.
        assert "X-Poison" not in h2

    def test_extra_none_returns_defaults(self) -> None:
        assert build_headers() == build_headers(None)

    def test_default_headers_constant_is_immutable(self) -> None:
        with pytest.raises(TypeError):
            _DEFAULT_HEADERS["X-Inject"] = "attack"  # type: ignore[index]


# ── merge_settings ────────────────────────────────────────────────────────────


class TestMergeSettings:
    def test_override_is_applied(self) -> None:
        result = merge_settings({"timeout": 10}, {"timeout": 30})
        assert result["timeout"] == 30

    def test_defaults_not_mutated(self) -> None:
        defaults = {"timeout": 10, "retries": 3}
        merge_settings(defaults, {"timeout": 30})
        assert defaults["timeout"] == 10  # must be unchanged

    def test_no_overrides_returns_copy(self) -> None:
        defaults = {"timeout": 10}
        result = merge_settings(defaults)
        result["extra"] = True
        assert "extra" not in defaults  # result is a copy, not the same object


# ── make_url_normalizer ───────────────────────────────────────────────────────


class TestMakeUrlNormalizer:
    def test_relative_path_gets_base_url(self) -> None:
        normalize = make_url_normalizer("https://books.toscrape.com")
        assert normalize("/catalogue/page-2.html") == (
            "https://books.toscrape.com/catalogue/page-2.html"
        )

    def test_absolute_url_is_returned_unchanged(self) -> None:
        normalize = make_url_normalizer("https://books.toscrape.com")
        assert normalize("https://other.com/page") == "https://other.com/page"

    def test_trailing_slash_on_base_is_handled(self) -> None:
        normalize = make_url_normalizer("https://example.com/")
        assert normalize("/page") == "https://example.com/page"

    def test_closures_are_independent(self) -> None:
        norm_a = make_url_normalizer("https://site-a.com")
        norm_b = make_url_normalizer("https://site-b.com")
        # Each closure captured a different base_url.
        assert norm_a("/x") == "https://site-a.com/x"
        assert norm_b("/x") == "https://site-b.com/x"


# ── make_request_counter ──────────────────────────────────────────────────────


class TestMakeRequestCounter:
    def test_increments_on_each_call(self) -> None:
        counter = make_request_counter()
        assert counter() == 1
        assert counter() == 2
        assert counter() == 3

    def test_counters_are_independent(self) -> None:
        c1 = make_request_counter()
        c2 = make_request_counter()
        c1()
        c1()
        c2()
        # c1 was called twice, c2 once — they must not share state.
        assert c1() == 3
        assert c2() == 2


# ── extract_links ─────────────────────────────────────────────────────────────


class TestExtractLinks:
    def test_eager_returns_all_links(self) -> None:
        assert extract_links_eager(_PAGES) == ["/page-1", "/page-2", "/page-3"]

    def test_lazy_yields_same_links(self) -> None:
        assert list(extract_links_lazy(_PAGES)) == ["/page-1", "/page-2", "/page-3"]

    def test_lazy_returns_a_generator(self) -> None:
        gen = extract_links_lazy(_PAGES)
        assert hasattr(gen, "__next__")  # generator, not a list

    def test_lazy_generator_object_is_smaller_than_materialised_list(self) -> None:
        large_pages = [f'<a href="/p-{i}">link</a>' for i in range(1000)]
        gen = extract_links_lazy(large_pages)
        lst = extract_links_eager(large_pages)
        # The generator frame is a fixed ~120 bytes.
        # The list holds 1000 pointers — orders of magnitude larger.
        assert sys.getsizeof(gen) < sys.getsizeof(lst)


# ── chunk_urls ────────────────────────────────────────────────────────────────


class TestChunkUrls:
    def test_splits_into_correct_batches(self) -> None:
        urls = [f"/page-{i}" for i in range(7)]
        batches = list(chunk_urls(urls, 3))
        assert batches == [
            ["/page-0", "/page-1", "/page-2"],
            ["/page-3", "/page-4", "/page-5"],
            ["/page-6"],
        ]

    def test_chunk_size_larger_than_list(self) -> None:
        assert list(chunk_urls(["/a", "/b"], 10)) == [["/a", "/b"]]

    def test_empty_list_produces_no_batches(self) -> None:
        assert list(chunk_urls([], 5)) == []
