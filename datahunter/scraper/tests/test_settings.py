from __future__ import annotations

import pytest
from pydantic import ValidationError

from scraper.app.core.settings import ScraperSettings


def test_defaults_are_sane() -> None:
    s = ScraperSettings()
    assert s.requests_per_second == 2.0
    assert s.max_retries == 3
    assert s.request_timeout == 10.0
    assert s.log_level == "INFO"
    assert s.database_url is None
    assert s.webhook_url is None


def test_env_prefix_is_datahunter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUNTER_REQUESTS_PER_SECOND", "5.0")
    monkeypatch.setenv("DATAHUNTER_MAX_RETRIES", "5")
    monkeypatch.setenv("DATAHUNTER_LOG_LEVEL", "DEBUG")
    s = ScraperSettings()
    assert s.requests_per_second == 5.0
    assert s.max_retries == 5
    assert s.log_level == "DEBUG"


def test_database_url_loaded_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUNTER_DATABASE_URL", "sqlite:///test.db")
    s = ScraperSettings()
    assert s.database_url == "sqlite:///test.db"


def test_log_level_normalised_to_uppercase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUNTER_LOG_LEVEL", "warning")
    s = ScraperSettings()
    assert s.log_level == "WARNING"


def test_zero_requests_per_second_raises() -> None:
    with pytest.raises(ValidationError, match="requests_per_second must be positive"):
        ScraperSettings(requests_per_second=0)


def test_negative_requests_per_second_raises() -> None:
    with pytest.raises(ValidationError, match="requests_per_second must be positive"):
        ScraperSettings(requests_per_second=-1.0)


def test_zero_max_retries_raises() -> None:
    with pytest.raises(ValidationError, match="max_retries must be >= 1"):
        ScraperSettings(max_retries=0)


def test_invalid_log_level_raises() -> None:
    with pytest.raises(ValidationError, match="log_level must be one of"):
        ScraperSettings(log_level="VERBOSE")
