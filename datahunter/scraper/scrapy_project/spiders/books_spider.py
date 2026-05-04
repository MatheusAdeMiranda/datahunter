from __future__ import annotations

from collections.abc import Generator

import scrapy
from scrapy.http import Response

from scraper.scrapy_project.items import BookItem

_RATING_MAP = {
    "One": "1",
    "Two": "2",
    "Three": "3",
    "Four": "4",
    "Five": "5",
}


class BooksScrapySpider(scrapy.Spider):
    """Spider Scrapy equivalente à BooksSpider do Dia 10.

    O que o Scrapy entrega de graça aqui:
    - DupeFilter: nunca visita a mesma URL duas vezes
    - RetryMiddleware: retry automático em 5xx/timeout
    - DOWNLOAD_DELAY + AUTOTHROTTLE: rate limit sem código manual
    - ROBOTSTXT_OBEY: respeito automático ao robots.txt
    """

    name = "books"
    start_urls = ["https://books.toscrape.com/catalogue/page-1.html"]

    def parse(self, response: Response) -> Generator[BookItem | scrapy.Request, None, None]:
        for article in response.css("article.product_pod"):
            rating_word = article.css("p.star-rating::attr(class)").get("").split()[-1]
            title = article.css("h3 a::attr(title)").get("")
            price = article.css("p.price_color::text").get("").strip()
            availability = article.css("p.availability::text").getall()
            availability_text = " ".join(t.strip() for t in availability if t.strip())

            yield BookItem(
                title=title,
                price=price,
                availability=availability_text,
                rating=_RATING_MAP.get(rating_word, "0"),
            )

        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)
