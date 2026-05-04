from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scrapy import Spider
from scrapy.exceptions import DropItem
from sqlalchemy import create_engine

from scraper.app.core.entities import ScrapedItem
from scraper.app.storage.service import StorageService

if TYPE_CHECKING:
    from scraper.scrapy_project.items import BookItem

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ("title", "price", "availability", "rating")


class StoragePipeline:
    """Coleta BookItems durante o crawl e persiste em batch no close_spider."""

    def open_spider(self, spider: Spider) -> None:
        db_url: str = spider.settings.get("DATABASE_URL", "sqlite:///output/books_scrapy.db")
        self.storage = StorageService(create_engine(db_url))
        self.storage.init_db()
        self._items: list[ScrapedItem] = []

    def process_item(self, item: BookItem, spider: Spider) -> BookItem:
        for field in _REQUIRED_FIELDS:
            if not item.get(field):
                raise DropItem(f"campo ausente: {field!r} em {item!r}")
        self._items.append(
            ScrapedItem(
                url=f"https://books.toscrape.com/catalogue/{item['title']}",
                data=dict(item),  # BookItem é um dict em runtime
            )
        )
        return item

    def close_spider(self, spider: Spider) -> None:
        if self._items:
            self.storage.save_items(self._items)
            logger.info("StoragePipeline: %d livros persistidos", len(self._items))
