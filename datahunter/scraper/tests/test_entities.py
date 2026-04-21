from dataclasses import FrozenInstanceError

import pytest

from scraper.app.core.entities import ScrapedItem, ScrapingJob, ScrapingResult
from scraper.app.core.exceptions import NetworkError, ParseError, ScrapingError, StorageError

# ── Exception hierarchy ───────────────────────────────────────────────────────


class TestExceptionHierarchy:
    def test_network_error_is_scraping_error(self) -> None:
        assert issubclass(NetworkError, ScrapingError)

    def test_parse_error_is_scraping_error(self) -> None:
        assert issubclass(ParseError, ScrapingError)

    def test_storage_error_is_scraping_error(self) -> None:
        assert issubclass(StorageError, ScrapingError)

    def test_catch_base_catches_all_subtypes(self) -> None:
        for exc_class in (NetworkError, ParseError, StorageError):
            with pytest.raises(ScrapingError):
                raise exc_class("boom")

    def test_subtypes_do_not_overlap(self) -> None:
        assert not issubclass(NetworkError, ParseError)
        assert not issubclass(ParseError, StorageError)
        assert not issubclass(StorageError, NetworkError)


# ── ScrapingJob ───────────────────────────────────────────────────────────────


class TestScrapingJob:
    def test_repr_is_readable(self) -> None:
        job = ScrapingJob(url="https://example.com")
        assert "https://example.com" in repr(job)
        assert "ScrapingJob" in repr(job)

    def test_defaults_are_sensible(self) -> None:
        job = ScrapingJob(url="https://example.com")
        assert job.max_pages == 50
        assert job.tags == ()

    def test_is_immutable(self) -> None:
        job = ScrapingJob(url="https://example.com")
        with pytest.raises(FrozenInstanceError):
            job.url = "https://other.com"  # type: ignore[misc]

    def test_invalid_url_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="http"):
            ScrapingJob(url="not-a-url")

    def test_max_pages_below_one_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="max_pages"):
            ScrapingJob(url="https://example.com", max_pages=0)

    def test_tags_stored_as_tuple(self) -> None:
        job = ScrapingJob(url="https://example.com", tags=("books", "fiction"))
        assert job.tags == ("books", "fiction")


# ── ScrapedItem ───────────────────────────────────────────────────────────────


class TestScrapedItem:
    def test_repr_shows_url_and_field_names(self) -> None:
        item = ScrapedItem(url="https://example.com/1", data={"title": "Book"})
        assert "https://example.com/1" in repr(item)
        assert "title" in repr(item)

    def test_equality_based_on_url_and_data(self) -> None:
        a = ScrapedItem(url="https://x.com/1", data={"title": "A"})
        b = ScrapedItem(url="https://x.com/1", data={"title": "A"})
        assert a == b

    def test_inequality_when_data_differs(self) -> None:
        a = ScrapedItem(url="https://x.com/1", data={"title": "A"})
        b = ScrapedItem(url="https://x.com/1", data={"title": "B"})
        assert a != b

    def test_hashable_and_usable_in_set(self) -> None:
        a = ScrapedItem(url="https://x.com/1", data={"title": "A"})
        b = ScrapedItem(url="https://x.com/1", data={"title": "A"})
        assert len({a, b}) == 1  # same hash + equal → deduplicated

    def test_is_mutable(self) -> None:
        item = ScrapedItem(url="https://x.com/1", data={"title": " spaces "})
        item.data["title"] = item.data["title"].strip()
        assert item.data["title"] == "spaces"

    def test_eq_with_non_item_returns_not_implemented(self) -> None:
        item = ScrapedItem(url="https://x.com/1", data={"title": "A"})
        # NotImplemented lets Python try the reflected operation instead of
        # silently returning False, which would break mixed-type comparisons.
        assert item.__eq__("not an item") is NotImplemented
        assert item.__eq__(42) is NotImplemented


# ── ScrapingResult ────────────────────────────────────────────────────────────


class TestScrapingResult:
    def _job(self) -> ScrapingJob:
        return ScrapingJob(url="https://books.toscrape.com")

    def _item(self, path: str = "/1") -> ScrapedItem:
        return ScrapedItem(url=f"https://books.toscrape.com{path}", data={"title": "X"})

    def test_len_returns_item_count(self) -> None:
        result = ScrapingResult(job=self._job(), items=[self._item("/1"), self._item("/2")])
        assert len(result) == 2

    def test_len_zero_when_empty(self) -> None:
        assert len(ScrapingResult(job=self._job())) == 0

    def test_contains_url_of_collected_item(self) -> None:
        result = ScrapingResult(job=self._job(), items=[self._item("/1")])
        assert "https://books.toscrape.com/1" in result

    def test_does_not_contain_uncollected_url(self) -> None:
        result = ScrapingResult(job=self._job(), items=[self._item("/1")])
        assert "https://books.toscrape.com/99" not in result

    def test_ok_true_when_items_and_no_errors(self) -> None:
        result = ScrapingResult(job=self._job(), items=[self._item()])
        assert result.ok is True

    def test_ok_false_when_no_items(self) -> None:
        assert ScrapingResult(job=self._job()).ok is False

    def test_ok_false_when_errors_present(self) -> None:
        result = ScrapingResult(job=self._job(), items=[self._item()], errors=["timeout"])
        assert result.ok is False

    def test_repr_shows_counts(self) -> None:
        result = ScrapingResult(job=self._job(), items=[self._item()], errors=["e"])
        r = repr(result)
        assert "items=1" in r
        assert "errors=1" in r
