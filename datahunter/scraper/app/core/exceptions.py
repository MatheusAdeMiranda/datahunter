from __future__ import annotations


class ScrapingError(Exception):
    """Base for all datahunter errors — catch this to avoid coupling to specific libraries."""


class NetworkError(ScrapingError):
    """HTTP failure, connection timeout, or DNS error."""


class ParseError(ScrapingError):
    """HTML structure did not match expectations."""


class StorageError(ScrapingError):
    """Database write, read, or migration failure."""


class RobotsDisallowedError(ScrapingError):
    """Target URL is forbidden by the site's robots.txt."""
