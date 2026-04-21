from __future__ import annotations


class ScrapingError(Exception):
    """Base for all datahunter errors.

    Catching ScrapingError lets callers handle any scraping failure without
    coupling to specific libraries (httpx, sqlalchemy, bs4, etc.).
    """


class NetworkError(ScrapingError):
    """HTTP failure, connection timeout, or DNS error."""


class ParseError(ScrapingError):
    """HTML structure did not match expectations."""


class StorageError(ScrapingError):
    """Database write, read, or migration failure."""
