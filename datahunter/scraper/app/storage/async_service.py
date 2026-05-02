from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from scraper.app.core.entities import ScrapedItem
from scraper.app.core.exceptions import StorageError
from scraper.app.storage.models import Base, ScrapedBook

logger = logging.getLogger(__name__)


class AsyncStorageService:
    """Async counterpart of StorageService using SQLAlchemy AsyncSession.

    Same upsert semantics via session.merge(), but all I/O is non-blocking.
    Use create_async_engine("sqlite+aiosqlite:///...") for SQLite (dev) or
    create_async_engine("postgresql+asyncpg://...") for PostgreSQL (prod).
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def init_db(self) -> None:
        """Create all tables. Prefer Alembic in production."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def save_items(self, items: list[ScrapedItem]) -> int:
        """Upsert items by title. Returns the number of items processed."""
        if not items:
            return 0
        try:
            async with AsyncSession(self._engine) as session:
                for item in items:
                    book = ScrapedBook(
                        title=item.data["title"],
                        source_url=item.url,
                        price=item.data["price"],
                        availability=item.data["availability"],
                        rating=item.data["rating"],
                        scraped_at=item.scraped_at,
                    )
                    await session.merge(book)
                await session.commit()
        except Exception as exc:
            raise StorageError(f"failed to save {len(items)} items: {exc}") from exc
        logger.info("saved %d books to database", len(items))
        return len(items)

    async def count(self) -> int:
        """Return the total number of books stored."""
        try:
            async with AsyncSession(self._engine) as session:
                result = await session.execute(select(func.count()).select_from(ScrapedBook))
                return int(result.scalar() or 0)
        except Exception as exc:
            raise StorageError(f"failed to count books: {exc}") from exc
