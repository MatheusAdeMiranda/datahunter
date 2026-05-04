from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from scrapy.exceptions import DropItem

from scraper.scrapy_project.items import BookItem
from scraper.scrapy_project.pipelines import StoragePipeline


def _make_spider(db_url: str = "sqlite:///:memory:") -> MagicMock:
    spider = MagicMock()
    spider.settings.get.return_value = db_url
    return spider


@pytest.fixture()
def spider() -> MagicMock:
    return _make_spider()


@pytest.fixture()
def pipeline(spider: MagicMock) -> StoragePipeline:
    p = StoragePipeline()
    p.open_spider(spider)
    return p


def _valid_item(**overrides: str) -> BookItem:
    defaults = {
        "title": "Test Book",
        "price": "£10.00",
        "availability": "In stock",
        "rating": "3",
    }
    return BookItem(**{**defaults, **overrides})


def test_process_item_returns_item(pipeline: StoragePipeline, spider: MagicMock) -> None:
    item = _valid_item()
    result = pipeline.process_item(item, spider)
    assert result is item


def test_process_item_accumulates(pipeline: StoragePipeline, spider: MagicMock) -> None:
    pipeline.process_item(_valid_item(title="Book A"), spider)
    pipeline.process_item(_valid_item(title="Book B"), spider)
    assert len(pipeline._items) == 2


def test_process_item_drops_missing_title(pipeline: StoragePipeline, spider: MagicMock) -> None:
    with pytest.raises(DropItem):
        pipeline.process_item(_valid_item(title=""), spider)


def test_process_item_drops_missing_price(pipeline: StoragePipeline, spider: MagicMock) -> None:
    with pytest.raises(DropItem):
        pipeline.process_item(_valid_item(price=""), spider)


def test_close_spider_persists_items(pipeline: StoragePipeline, spider: MagicMock) -> None:
    pipeline.process_item(_valid_item(title="Book A"), spider)
    pipeline.process_item(_valid_item(title="Book B"), spider)
    pipeline.close_spider(spider)
    assert pipeline.storage.count() == 2


def test_close_spider_upsert_deduplicates(pipeline: StoragePipeline, spider: MagicMock) -> None:
    pipeline.process_item(_valid_item(title="Same Book"), spider)
    pipeline.process_item(_valid_item(title="Same Book", price="£20.00"), spider)
    pipeline.close_spider(spider)
    assert pipeline.storage.count() == 1


def test_close_spider_empty_no_error(spider: MagicMock) -> None:
    p = StoragePipeline()
    p.open_spider(spider)
    p.close_spider(spider)  # não deve lançar exceção
    assert p.storage.count() == 0
