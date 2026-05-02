from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from scraper.app.core.entities import ScrapedItem
from scraper.app.core.exceptions import StorageError
from scraper.app.storage.async_service import AsyncStorageService
from scraper.app.storage.models import Base, ScrapedBook

_CATALOG_URL = "https://books.toscrape.com/catalogue/page-1.html"
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
        data={"title": title, "price": price, "availability": availability, "rating": rating},
        scraped_at=_SCRAPED_AT,
    )


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def storage(engine: AsyncEngine) -> AsyncStorageService:
    return AsyncStorageService(engine)


# ── save_items: insert ────────────────────────────────────────────────────────


async def test_save_items_returns_count(storage: AsyncStorageService) -> None:
    assert await storage.save_items([_item("Book A"), _item("Book B")]) == 2


async def test_save_items_persists_to_db(storage: AsyncStorageService) -> None:
    await storage.save_items([_item("Book A"), _item("Book B")])
    assert await storage.count() == 2


async def test_save_empty_list_is_noop(storage: AsyncStorageService) -> None:
    assert await storage.save_items([]) == 0
    assert await storage.count() == 0


async def test_fields_stored_correctly(storage: AsyncStorageService, engine: AsyncEngine) -> None:
    item = _item("A Light in the Attic", price="£51.77", url="https://example.com/page-5.html")
    await storage.save_items([item])
    async with AsyncSession(engine) as session:
        book = await session.get(ScrapedBook, "A Light in the Attic")
        assert book is not None
        assert book.price == "£51.77"
        assert book.availability == "In stock"
        assert book.rating == "Three"
        assert book.source_url == "https://example.com/page-5.html"
        assert book.scraped_at == _SCRAPED_AT


# ── save_items: upsert ────────────────────────────────────────────────────────


async def test_upsert_does_not_duplicate_rows(storage: AsyncStorageService) -> None:
    await storage.save_items([_item("Book A")])
    await storage.save_items([_item("Book A", price="£99.99")])
    assert await storage.count() == 1


async def test_upsert_updates_existing_fields(
    storage: AsyncStorageService, engine: AsyncEngine
) -> None:
    await storage.save_items([_item("Book A", price="£10.00", availability="In stock")])
    await storage.save_items([_item("Book A", price="£99.99", availability="Out of stock")])
    async with AsyncSession(engine) as session:
        book = await session.get(ScrapedBook, "Book A")
        assert book is not None
        assert book.price == "£99.99"
        assert book.availability == "Out of stock"


async def test_upsert_across_multiple_calls(storage: AsyncStorageService) -> None:
    for i in range(3):
        await storage.save_items([_item("Book A", price=f"£{i}.00")])
    assert await storage.count() == 1


# ── save_items: multiple pages ────────────────────────────────────────────────


async def test_books_from_different_pages_all_saved(storage: AsyncStorageService) -> None:
    page1 = [
        _item("Book A", url="https://example.com/page-1.html"),
        _item("Book B", url="https://example.com/page-1.html"),
    ]
    page2 = [
        _item("Book C", url="https://example.com/page-2.html"),
        _item("Book D", url="https://example.com/page-2.html"),
    ]
    await storage.save_items(page1)
    await storage.save_items(page2)
    assert await storage.count() == 4


# ── count ─────────────────────────────────────────────────────────────────────


async def test_count_returns_zero_on_empty_db(storage: AsyncStorageService) -> None:
    assert await storage.count() == 0


# ── ScrapedBook repr ──────────────────────────────────────────────────────────


async def test_scraped_book_repr(storage: AsyncStorageService, engine: AsyncEngine) -> None:
    await storage.save_items([_item("Book A", price="£10.00")])
    async with AsyncSession(engine) as session:
        book = await session.get(ScrapedBook, "Book A")
        assert book is not None
        assert repr(book) == "ScrapedBook(title='Book A', price='£10.00')"


# ── init_db ───────────────────────────────────────────────────────────────────


async def test_init_db_creates_tables_and_db_is_usable() -> None:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    svc = AsyncStorageService(eng)
    await svc.init_db()
    assert await svc.count() == 0
    await svc.save_items([_item("Book A")])
    assert await svc.count() == 1
    await eng.dispose()


# ── error handling ────────────────────────────────────────────────────────────


async def test_storage_error_raised_when_table_missing() -> None:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    svc = AsyncStorageService(eng)
    with pytest.raises(StorageError, match="failed to save"):
        await svc.save_items([_item("Book A")])
    await eng.dispose()


async def test_count_raises_storage_error_when_table_missing() -> None:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    svc = AsyncStorageService(eng)
    with pytest.raises(StorageError, match="failed to count"):
        await svc.count()
    await eng.dispose()
