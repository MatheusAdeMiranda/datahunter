from __future__ import annotations

import logging

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from scraper.app.core.entities import ScrapedItem
from scraper.app.core.exceptions import StorageError
from scraper.app.storage.models import Base, ScrapedBook

logger = logging.getLogger(__name__)


class StorageService:
    """Persists ScrapedItems to a relational database.

    Uses session.merge() for upsert: if a book with the same title already
    exists it is updated in-place; otherwise a new row is inserted.
    Compatible with both SQLite (dev) and PostgreSQL (prod).
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def init_db(self) -> None:
        """Create all tables. Use for tests or first-run setup; prefer Alembic in production."""
        Base.metadata.create_all(self._engine)

    def save_items(self, items: list[ScrapedItem]) -> int:
        """Upsert items by title. Returns the number of items processed."""
        if not items:
            return 0
        try:
            with Session(self._engine) as session:
                for item in items:
                    book = ScrapedBook(
                        title=item.data["title"],
                        source_url=item.url,
                        price=item.data["price"],
                        availability=item.data["availability"],
                        rating=item.data["rating"],
                        scraped_at=item.scraped_at,
                    )
                    session.merge(book)
                session.commit()
        except Exception as exc:
            raise StorageError(f"failed to save {len(items)} items: {exc}") from exc
        logger.info("saved %d books to database", len(items))
        return len(items)

    def count(self) -> int:
        """Return the total number of books stored."""
        with Session(self._engine) as session:
            result = session.scalar(select(func.count()).select_from(ScrapedBook))
            return int(result) if result is not None else 0
