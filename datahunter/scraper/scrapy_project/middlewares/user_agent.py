from __future__ import annotations

import random

from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.http import Request


class RandomUserAgentMiddleware:
    """Rotaciona User-Agent a cada request a partir de USER_AGENT_LIST.

    Substitui o UserAgentMiddleware padrão do Scrapy (desabilitado em settings.py).
    Se USER_AGENT_LIST estiver vazio, usa USER_AGENT como único agente.
    """

    def __init__(self, user_agents: list[str]) -> None:
        self.user_agents = user_agents

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> RandomUserAgentMiddleware:
        agents: list[str] = crawler.settings.getlist("USER_AGENT_LIST", [])
        if not agents:
            agents = [crawler.settings.get("USER_AGENT", "datahunter/0.1")]
        return cls(agents)

    def process_request(self, request: Request, spider: Spider) -> None:
        request.headers["User-Agent"] = random.choice(self.user_agents)
