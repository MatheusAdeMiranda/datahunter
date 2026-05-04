from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from typing import Any

import scrapy
from scrapy.http import Response

from scraper.scrapy_project.items import QuoteItem


class QuotesScrapySpider(scrapy.Spider):
    """Spider que usa scrapy-playwright para renderizar JS antes de extrair quotes.

    Estratégia: meta={"playwright": True} delega o download ao Playwright;
    o HTML renderizado chega em `response` normalmente — sem mudar o parsing.
    """

    name = "quotes_js"
    start_urls = ["https://quotes.toscrape.com/js/"]

    def start_requests(self) -> Iterator[scrapy.Request]:
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={"playwright": True, "playwright_include_page": True},
            )

    async def parse(
        self, response: Response, **kwargs: Any
    ) -> AsyncGenerator[QuoteItem | scrapy.Request, None]:
        page = kwargs.get("page")
        if page:
            await page.wait_for_selector("div.quote")

        for quote_sel in response.css("div.quote"):
            yield self._parse_quote(quote_sel)

        next_href = response.css("li.next a::attr(href)").get()
        if next_href:
            yield response.follow(
                next_href,
                callback=self.parse,
                meta={"playwright": True, "playwright_include_page": True},
            )

        if page:
            await page.close()

    @staticmethod
    def _parse_quote(selector: Any) -> QuoteItem:
        text = selector.css("span.text::text").get("").strip()
        author = selector.css("small.author::text").get("").strip()
        tags = selector.css("a.tag::text").getall()
        return QuoteItem(text=text, author=author, tags=", ".join(tags))
