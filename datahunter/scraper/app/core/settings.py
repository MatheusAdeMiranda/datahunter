from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class ScraperSettings(BaseSettings):
    """Scraper configuration loaded from environment variables.

    All vars use the DATAHUNTER_ prefix:
        DATAHUNTER_REQUESTS_PER_SECOND=2.0
        DATAHUNTER_DATABASE_URL=sqlite:///datahunter.db
    """

    # HTTP behaviour
    requests_per_second: float = 2.0
    max_retries: int = 3
    request_timeout: float = 10.0

    # Storage
    database_url: str | None = None

    # Observability
    log_level: str = "INFO"
    webhook_url: str | None = None

    model_config = {"env_prefix": "DATAHUNTER_"}

    @field_validator("requests_per_second")
    @classmethod
    def _positive_rps(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("requests_per_second must be positive")
        return v

    @field_validator("max_retries")
    @classmethod
    def _min_retries(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_retries must be >= 1")
        return v

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}")
        return upper


settings = ScraperSettings()
