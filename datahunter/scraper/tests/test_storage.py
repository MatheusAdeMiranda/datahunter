from __future__ import annotations

from collections.abc import Generator
from datetime import datetime

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from scraper.app.core.entities import ScrapedItem
from scraper.app.core.exceptions import StorageError
from scraper.app.storage.models import Base, ScrapedBook
from scraper.app.storage.service import StorageService

_CATALOG_URL = "https://books.toscrape.com/catalogue/page-1.html"
# Naive datetime — SQLite strips timezone info on storage; naive avoids round-trip mismatch.
_SCRAPED_AT = datetime(2026, 4, 28, 12, 0, 0)


def _item(
    title: str,
    price: str = "£10.00",
    url: str = _CATALOG_URL,
    availability: str = "In stock",
    rating: str = "Three",
) -> ScrapedItem:
    return ScrapedItem(
        url=url,
        data={
            "title": title,
            "price": price,
            "availability": availability,
            "rating": rating,
        },
        scraped_at=_SCRAPED_AT,
    )


@pytest.fixture
def engine() -> Generator[Engine, None, None]:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def storage(engine: Engine) -> StorageService:
    return StorageService(engine)


# ── save_items: insert ────────────────────────────────────────────────────────


def test_save_items_returns_count(storage: StorageService) -> None:
    assert storage.save_items([_item("Book A"), _item("Book B")]) == 2


def test_save_items_persists_to_db(storage: StorageService) -> None:
    storage.save_items([_item("Book A"), _item("Book B")])
    assert storage.count() == 2


def test_save_empty_list_is_noop(storage: StorageService) -> None:
    assert storage.save_items([]) == 0
    assert storage.count() == 0


def test_fields_stored_correctly(storage: StorageService, engine: Engine) -> None:
    item = _item("A Light in the Attic", price="£51.77", url="https://example.com/page-5.html")
    storage.save_items([item])
    with Session(engine) as session:
        book = session.get(ScrapedBook, "A Light in the Attic")
        assert book is not None
        assert book.price == "£51.77"
        assert book.availability == "In stock"
        assert book.rating == "Three"
        assert book.source_url == "https://example.com/page-5.html"
        assert book.scraped_at == _SCRAPED_AT


# ── save_items: upsert ────────────────────────────────────────────────────────


def test_upsert_does_not_duplicate_rows(storage: StorageService) -> None:
    storage.save_items([_item("Book A")])
    storage.save_items([_item("Book A", price="£99.99")])
    assert storage.count() == 1


def test_upsert_updates_existing_fields(storage: StorageService, engine: Engine) -> None:
    storage.save_items([_item("Book A", price="£10.00", availability="In stock")])
    storage.save_items([_item("Book A", price="£99.99", availability="Out of stock")])
    with Session(engine) as session:
        book = session.get(ScrapedBook, "Book A")
        assert book is not None
        assert book.price == "£99.99"
        assert book.availability == "Out of stock"


def test_upsert_across_multiple_calls(storage: StorageService) -> None:
    for i in range(3):
        storage.save_items([_item("Book A", price=f"£{i}.00")])
    assert storage.count() == 1


# ── save_items: multiple pages ────────────────────────────────────────────────


def test_books_from_different_pages_all_saved(storage: StorageService) -> None:
    page1 = [
        _item("Book A", url="https://example.com/page-1.html"),
        _item("Book B", url="https://example.com/page-1.html"),
    ]
    page2 = [
        _item("Book C", url="https://example.com/page-2.html"),
        _item("Book D", url="https://example.com/page-2.html"),
    ]
    storage.save_items(page1)
    storage.save_items(page2)
    assert storage.count() == 4


# ── count ─────────────────────────────────────────────────────────────────────


def test_count_returns_zero_on_empty_db(storage: StorageService) -> None:
    assert storage.count() == 0


# ── ScrapedBook repr ──────────────────────────────────────────────────────────


def test_scraped_book_repr(storage: StorageService, engine: Engine) -> None:
    storage.save_items([_item("Book A", price="£10.00")])
    with Session(engine) as session:
        book = session.get(ScrapedBook, "Book A")
        assert book is not None
        assert repr(book) == "ScrapedBook(title='Book A', price='£10.00')"


# ── init_db ───────────────────────────────────────────────────────────────────


def test_init_db_creates_tables_and_db_is_usable() -> None:
    eng = create_engine("sqlite:///:memory:")
    svc = StorageService(eng)
    svc.init_db()
    assert svc.count() == 0
    svc.save_items([_item("Book A")])
    assert svc.count() == 1
    eng.dispose()


# ── error handling ────────────────────────────────────────────────────────────


def test_storage_error_raised_when_table_missing() -> None:
    # Engine exists but init_db was never called — table doesn't exist.
    eng = create_engine("sqlite:///:memory:")
    svc = StorageService(eng)
    with pytest.raises(StorageError, match="failed to save"):
        svc.save_items([_item("Book A")])
    eng.dispose()
