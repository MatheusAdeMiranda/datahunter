from __future__ import annotations

import logging
import urllib.parse
import urllib.robotparser

from scraper.app.core.exceptions import NetworkError
from scraper.app.core.http_client import HTTPClient

logger = logging.getLogger(__name__)


class RobotsChecker:
    """Checks whether a URL is allowed to be fetched according to robots.txt.

    Fetches and parses robots.txt once per domain (cached for the lifetime of
    this instance). On network errors or non-200 responses the checker allows
    the URL so scraping is not silently broken by an inaccessible robots.txt.
    """

    def __init__(self, client: HTTPClient, user_agent: str = "datahunter-bot") -> None:
        self._client = client
        self._user_agent = user_agent
        self._cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    def is_allowed(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc
        if domain not in self._cache:
            self._cache[domain] = self._fetch_parser(parsed.scheme, domain)
        return self._cache[domain].can_fetch(self._user_agent, url)

    def _fetch_parser(self, scheme: str, domain: str) -> urllib.robotparser.RobotFileParser:
        robots_url = f"{scheme}://{domain}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        lines: list[str] = []
        try:
            response = self._client.get(robots_url)
            if response.status_code == 200:
                lines = response.text.splitlines()
                logger.debug("loaded robots.txt for %s", domain)
            else:
                logger.debug(
                    "robots.txt for %s returned %d, allowing all",
                    domain,
                    response.status_code,
                )
        except NetworkError:
            logger.warning("could not fetch robots.txt for %s, allowing all", domain)
        # parse() must always be called so last_checked is set; empty list = allow all
        parser.parse(lines)
        return parser
