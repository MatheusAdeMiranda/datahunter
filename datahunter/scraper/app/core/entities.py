from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(frozen=True)
class ScrapingJob:
    """Immutable description of what to scrape.

    frozen=True: a job must not change after creation — if settings need to
    differ, create a new job. This makes jobs safe to pass across threads.
    """

    url: str
    max_pages: int = 50
    tags: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.url.startswith(("http://", "https://")):
            raise ValueError(f"url must start with http(s)://, got: {self.url!r}")
        if self.max_pages < 1:
            raise ValueError(f"max_pages must be >= 1, got: {self.max_pages}")

    def __repr__(self) -> str:
        return f"ScrapingJob(url={self.url!r}, max_pages={self.max_pages})"


@dataclass
class ScrapedItem:
    """A single item extracted during a scrape.

    Mutable so that normalisation steps (strip whitespace, cast types) can
    update fields in place as the item moves through the pipeline.
    """

    url: str
    data: dict[str, str]
    scraped_at: datetime = field(default_factory=_utcnow)

    def __repr__(self) -> str:
        keys = list(self.data.keys())
        return f"ScrapedItem(url={self.url!r}, fields={keys})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ScrapedItem):
            return NotImplemented
        return self.url == other.url and self.data == other.data

    def __hash__(self) -> int:
        return hash((self.url, tuple(sorted(self.data.items()))))


@dataclass
class ScrapingResult:
    """Aggregated outcome of a completed ScrapingJob."""

    job: ScrapingJob
    items: list[ScrapedItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    finished_at: datetime = field(default_factory=_utcnow)

    def __repr__(self) -> str:
        return (
            f"ScrapingResult(job={self.job!r}, items={len(self.items)}, errors={len(self.errors)})"
        )

    def __len__(self) -> int:
        """Number of successfully scraped items."""
        return len(self.items)

    def __contains__(self, url: object) -> bool:
        """Return True if any item was collected from the given URL."""
        return any(item.url == url for item in self.items)

    @property
    def ok(self) -> bool:
        """True when the result has items and no errors."""
        return bool(self.items) and not self.errors
