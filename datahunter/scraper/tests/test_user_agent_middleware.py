from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from scrapy.http import Request

from scraper.scrapy_project.middlewares.user_agent import RandomUserAgentMiddleware


@pytest.fixture()
def spider() -> MagicMock:
    return MagicMock()


def test_from_crawler_reads_user_agent_list() -> None:
    crawler = MagicMock()
    crawler.settings.getlist.return_value = ["Agent1", "Agent2"]
    mw = RandomUserAgentMiddleware.from_crawler(crawler)
    assert mw.user_agents == ["Agent1", "Agent2"]


def test_from_crawler_falls_back_to_user_agent(spider: MagicMock) -> None:
    crawler = MagicMock()
    crawler.settings.getlist.return_value = []
    crawler.settings.get.return_value = "datahunter/0.1"
    mw = RandomUserAgentMiddleware.from_crawler(crawler)
    assert mw.user_agents == ["datahunter/0.1"]


def test_process_request_sets_user_agent_header(spider: MagicMock) -> None:
    mw = RandomUserAgentMiddleware(["AgentA", "AgentB", "AgentC"])
    req = Request("https://example.com")
    mw.process_request(req, spider)
    header = (req.headers.get("User-Agent") or b"").decode()
    assert header in ("AgentA", "AgentB", "AgentC")


def test_process_request_single_agent_always_used(spider: MagicMock) -> None:
    mw = RandomUserAgentMiddleware(["OnlyAgent"])
    req = Request("https://example.com")
    mw.process_request(req, spider)
    assert (req.headers.get("User-Agent") or b"").decode() == "OnlyAgent"


def test_process_request_rotates_across_calls(spider: MagicMock) -> None:
    agents = ["A", "B", "C", "D", "E"]
    mw = RandomUserAgentMiddleware(agents)
    seen: set[str] = set()
    for _ in range(30):
        req = Request("https://example.com")
        mw.process_request(req, spider)
        seen.add((req.headers.get("User-Agent") or b"").decode())
    # com 30 chamadas e 5 agentes a probabilidade de ver só 1 é desprezível
    assert len(seen) > 1
