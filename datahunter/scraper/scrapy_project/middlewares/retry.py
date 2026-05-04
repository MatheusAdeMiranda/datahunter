from __future__ import annotations

import logging
import time

from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.http import Request, Response

logger = logging.getLogger(__name__)

_RETRY_HTTP_CODES = frozenset({500, 502, 503, 504, 408, 429})
_RETRY_EXCEPTIONS = (ConnectionError, TimeoutError)


class ExponentialBackoffRetryMiddleware:
    """Retry com backoff exponencial: wait = backoff_base * 2^attempt.

    Substitui o RetryMiddleware padrão do Scrapy (desabilitado em settings.py).
    Usa time.sleep — bloqueia o reactor do Twisted, aceitável para scraping de
    baixo volume com CONCURRENT_REQUESTS_PER_DOMAIN = 1.
    """

    def __init__(self, max_retry_times: int, backoff_base: float) -> None:
        self.max_retry_times = max_retry_times
        self.backoff_base = backoff_base

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> ExponentialBackoffRetryMiddleware:
        return cls(
            max_retry_times=crawler.settings.getint("RETRY_TIMES", 3),
            backoff_base=crawler.settings.getfloat("RETRY_BACKOFF_BASE", 1.0),
        )

    def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Request | Response:
        if response.status in _RETRY_HTTP_CODES:
            retry = self._retry(request, spider)
            return retry if retry is not None else response
        return response

    def process_exception(
        self, request: Request, exception: BaseException, spider: Spider
    ) -> Request | None:
        if isinstance(exception, _RETRY_EXCEPTIONS):
            return self._retry(request, spider)
        return None

    def _retry(self, request: Request, spider: Spider) -> Request | None:
        retries = request.meta.get("retry_times", 0)
        if retries >= self.max_retry_times:
            logger.warning("max retries reached for %s", request.url)
            return None
        wait = self.backoff_base * (2**retries)
        logger.debug(
            "retry %d/%d for %s (wait=%.1fs)",
            retries + 1,
            self.max_retry_times,
            request.url,
            wait,
        )
        time.sleep(wait)
        retry_req = request.copy()
        retry_req.meta["retry_times"] = retries + 1
        retry_req.dont_filter = True
        return retry_req
