from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ScrapedBook(Base):
    __tablename__ = "scraped_books"

    # title is the natural key for books.toscrape.com — titles are unique site-wide.
    # Using it as PK makes session.merge() upsert without a separate lookup column.
    title: Mapped[str] = mapped_column(primary_key=True)
    source_url: Mapped[str]
    price: Mapped[str]
    availability: Mapped[str]
    rating: Mapped[str]
    scraped_at: Mapped[datetime]

    def __repr__(self) -> str:
        return f"ScrapedBook(title={self.title!r}, price={self.price!r})"
