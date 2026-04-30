from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from scraper.app.core.http_client import HTTPClient
from scraper.app.spiders.quotes_spider import QuotesSpider, _extract_quote, _parse_response

FIXTURES = Path(__file__).parent / "fixtures"
API_URL = "https://quotes.toscrape.com/api/quotes"
PAGE1_URL = f"{API_URL}?page=1"
PAGE2_URL = f"{API_URL}?page=2"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ── Pagination and collection ─────────────────────────────────────────────────


@respx.mock
def test_crawl_follows_has_next_and_collects_all_quotes() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_fixture("quotes_page1.json")))
    respx.get(PAGE2_URL).mock(return_value=httpx.Response(200, text=_fixture("quotes_page2.json")))

    with HTTPClient() as client:
        result = QuotesSpider(client, api_url=API_URL, output_path=None).crawl()

    assert len(result) == 3  # 2 from page 1 + 1 from page 2
    assert result.errors == []
    assert result.ok


@respx.mock
def test_stops_when_has_next_is_false() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_fixture("quotes_page2.json")))

    with HTTPClient() as client:
        result = QuotesSpider(client, api_url=API_URL, output_path=None).crawl()

    assert len(result) == 1
    assert result.errors == []


@respx.mock
def test_max_pages_limits_crawl() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_fixture("quotes_page1.json")))

    with HTTPClient() as client:
        result = QuotesSpider(client, api_url=API_URL, max_pages=1, output_path=None).crawl()

    assert len(result) == 2  # only page 1 fetched
    assert result.errors == []


# ── Item content ──────────────────────────────────────────────────────────────


@respx.mock
def test_items_contain_expected_fields() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_fixture("quotes_page2.json")))

    with HTTPClient() as client:
        result = QuotesSpider(client, api_url=API_URL, output_path=None).crawl()

    item = result.items[0]
    assert item.data["author"] == "Mark Twain"
    assert "does not read" in item.data["text"]
    assert item.data["tags"] == "books, reading"


# ── Error handling ────────────────────────────────────────────────────────────


@respx.mock
def test_network_error_stops_crawl_and_records_error() -> None:
    respx.get(PAGE1_URL).mock(side_effect=httpx.ConnectError("refused"))

    with HTTPClient(max_attempts=1) as client:
        result = QuotesSpider(client, api_url=API_URL, output_path=None).crawl()

    assert len(result) == 0
    assert len(result.errors) == 1
    assert "network error" in result.errors[0]


@respx.mock
def test_invalid_json_stops_crawl_and_records_error() -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text="not json {{"))

    with HTTPClient() as client:
        result = QuotesSpider(client, api_url=API_URL, output_path=None).crawl()

    assert len(result) == 0
    assert len(result.errors) == 1
    assert "parse error" in result.errors[0]


@respx.mock
def test_malformed_quote_is_skipped_crawl_continues() -> None:
    # Page has one valid quote and one quote missing 'author'.
    page = json.dumps(
        {
            "has_next": False,
            "page": 1,
            "quotes": [
                {"text": "Valid quote.", "author": "Someone", "tags": []},
                {"text": "No author here.", "tags": []},  # missing author
            ],
        }
    )
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=page))

    with HTTPClient() as client:
        result = QuotesSpider(client, api_url=API_URL, output_path=None).crawl()

    assert len(result) == 1  # only the valid quote
    assert len(result.errors) == 1
    assert "quote error" in result.errors[0]


# ── JSON output ───────────────────────────────────────────────────────────────


@respx.mock
def test_json_output_has_correct_structure(tmp_path: Path) -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_fixture("quotes_page2.json")))

    output = tmp_path / "quotes.json"
    with HTTPClient() as client:
        QuotesSpider(client, api_url=API_URL, output_path=output).crawl()

    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1
    record = data[0]
    assert set(record["data"]) == {"text", "author", "tags"}
    assert "scraped_at" in record


@respx.mock
def test_json_output_creates_parent_directories(tmp_path: Path) -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_fixture("quotes_page2.json")))

    output = tmp_path / "deep" / "nested" / "quotes.json"
    with HTTPClient() as client:
        QuotesSpider(client, api_url=API_URL, output_path=output).crawl()

    assert output.exists()


@respx.mock
def test_no_file_written_when_output_path_is_none(tmp_path: Path) -> None:
    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_fixture("quotes_page2.json")))

    with HTTPClient() as client:
        QuotesSpider(client, api_url=API_URL, output_path=None).crawl()

    assert list(tmp_path.iterdir()) == []


# ── _parse_response unit tests ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "error_match"),
    [
        ("not json", "invalid JSON"),
        ("[1, 2, 3]", "expected JSON object"),
    ],
)
def test_parse_response_raises_on_bad_input(text: str, error_match: str) -> None:
    from scraper.app.core.exceptions import ParseError

    with pytest.raises(ParseError, match=error_match):
        _parse_response(text, "https://example.com/api")


# ── _extract_quote unit tests ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "error_match"),
    [
        ("not a dict", "not a dict"),
        ({"author": "A", "tags": []}, "missing or empty 'text'"),
        ({"text": "", "author": "A", "tags": []}, "missing or empty 'text'"),
        ({"text": "T", "tags": []}, "missing or empty 'author'"),
        ({"text": "T", "author": "", "tags": []}, "missing or empty 'author'"),
    ],
)
def test_extract_quote_raises_on_bad_input(raw: object, error_match: str) -> None:
    from scraper.app.core.exceptions import ParseError

    with pytest.raises(ParseError, match=error_match):
        _extract_quote(raw, "https://example.com/api?page=1")


def test_extract_quote_joins_tags_as_csv() -> None:
    data = _extract_quote(
        {"text": "Hello", "author": "World", "tags": ["a", "b", "c"]},
        "https://example.com",
    )
    assert data["tags"] == "a, b, c"


def test_extract_quote_handles_missing_tags() -> None:
    data = _extract_quote(
        {"text": "Hello", "author": "World"},
        "https://example.com",
    )
    assert data["tags"] == ""


# ── Storage integration ───────────────────────────────────────────────────────
# QuotesSpider passes items to whatever StorageService is injected.
# The StorageService itself is tested in test_storage.py with real SQLite.
# Here we only verify that save_items() is called with the collected items.


@respx.mock
def test_crawl_delegates_to_storage_when_provided() -> None:
    from scraper.app.storage.service import StorageService

    respx.get(PAGE1_URL).mock(return_value=httpx.Response(200, text=_fixture("quotes_page2.json")))

    storage = MagicMock(spec=StorageService)

    with HTTPClient() as client:
        result = QuotesSpider(client, api_url=API_URL, output_path=None, storage=storage).crawl()

    assert len(result) == 1
    storage.save_items.assert_called_once_with(result.items)
