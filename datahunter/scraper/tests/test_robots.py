from __future__ import annotations

import httpx
import pytest
import respx

from scraper.app.core.exceptions import NetworkError
from scraper.app.core.http_client import HTTPClient
from scraper.app.core.robots import RobotsChecker

BASE_URL = "https://example.com"
ROBOTS_URL = f"{BASE_URL}/robots.txt"


def _make_checker(user_agent: str = "datahunter-bot") -> tuple[HTTPClient, RobotsChecker]:
    client = HTTPClient(max_attempts=1)
    checker = RobotsChecker(client, user_agent=user_agent)
    return client, checker


# ── Basic allow / disallow ────────────────────────────────────────────────────


@respx.mock
def test_allows_url_when_robots_permits() -> None:
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n"))
    _, checker = _make_checker()
    assert checker.is_allowed(f"{BASE_URL}/page") is True


@respx.mock
def test_disallows_url_when_robots_forbids() -> None:
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /\n")
    )
    _, checker = _make_checker()
    assert checker.is_allowed(f"{BASE_URL}/page") is False


@respx.mock
def test_disallows_specific_path_only() -> None:
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
    )
    _, checker = _make_checker()
    assert checker.is_allowed(f"{BASE_URL}/public/page") is True
    assert checker.is_allowed(f"{BASE_URL}/private/secret") is False


# ── User-agent specificity ────────────────────────────────────────────────────


@respx.mock
def test_respects_specific_user_agent_rule() -> None:
    robots_txt = "User-agent: datahunter-bot\nDisallow: /restricted/\n\nUser-agent: *\nAllow: /\n"
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(200, text=robots_txt))
    _, checker = _make_checker(user_agent="datahunter-bot")
    assert checker.is_allowed(f"{BASE_URL}/public") is True
    assert checker.is_allowed(f"{BASE_URL}/restricted/page") is False


# ── Caching ───────────────────────────────────────────────────────────────────


@respx.mock
def test_robots_txt_fetched_only_once_per_domain() -> None:
    route = respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    _, checker = _make_checker()
    checker.is_allowed(f"{BASE_URL}/page1")
    checker.is_allowed(f"{BASE_URL}/page2")
    checker.is_allowed(f"{BASE_URL}/page3")
    assert route.call_count == 1


@respx.mock
def test_different_domains_fetched_independently() -> None:
    url_a = "https://domain-a.com"
    url_b = "https://domain-b.com"
    route_a = respx.get(f"{url_a}/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    route_b = respx.get(f"{url_b}/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    _, checker = _make_checker()
    checker.is_allowed(f"{url_a}/page")
    checker.is_allowed(f"{url_b}/page")
    assert route_a.call_count == 1
    assert route_b.call_count == 1


# ── Fault tolerance ───────────────────────────────────────────────────────────


@respx.mock
def test_allows_all_when_robots_txt_returns_non_200() -> None:
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(404))
    _, checker = _make_checker()
    assert checker.is_allowed(f"{BASE_URL}/any/path") is True


@respx.mock
def test_allows_all_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client, checker = _make_checker()

    def raise_network_error(url: str, **_: object) -> httpx.Response:
        raise NetworkError("connection failed")

    monkeypatch.setattr(client, "get", raise_network_error)
    assert checker.is_allowed(f"{BASE_URL}/page") is True
