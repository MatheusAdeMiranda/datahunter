from __future__ import annotations

import contextlib
import logging
from collections.abc import Generator, Mapping
from dataclasses import dataclass, field
from types import TracebackType

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Lightweight handle yielded by managed_session — will wrap httpx.Client in Week 2."""

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    is_open: bool = False


@contextlib.contextmanager
def managed_session(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
) -> Generator[Session, None, None]:
    """Open a scraping session for *url*, yield it, then close it unconditionally."""
    session = Session(url=url, headers=dict(headers) if headers else {})
    session.is_open = True
    logger.debug("session opened for %s", url)
    try:
        yield session
    finally:
        session.is_open = False
        logger.debug("session closed for %s", url)


class BrowserContext:
    """Class-based context manager that models a browser lifecycle.

    Parameters
    ----------
    headless:
        Run the browser without a visible window (default True).
    timeout:
        Maximum seconds to wait for a page load (default 30.0).
    suppress:
        Exception types to swallow on __exit__ instead of propagating.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout: float = 30.0,
        suppress: tuple[type[BaseException], ...] = (),
    ) -> None:
        self.headless = headless
        self.timeout = timeout
        self.suppress = suppress
        self.is_open = False

    def __enter__(self) -> BrowserContext:
        self.is_open = True
        logger.debug("browser opened (headless=%s, timeout=%.1f)", self.headless, self.timeout)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        self.is_open = False
        logger.debug("browser closed")
        if exc_type is not None and self.suppress:
            return issubclass(exc_type, self.suppress)
        return False
