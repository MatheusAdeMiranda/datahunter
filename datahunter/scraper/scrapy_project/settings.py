BOT_NAME = "datahunter"

SPIDER_MODULES = ["scraper.scrapy_project.spiders"]
NEWSPIDER_MODULE = "scraper.scrapy_project.spiders"

USER_AGENT = "datahunter/0.1"

ROBOTSTXT_OBEY = True

# max 2 req/s por domínio conforme política de acesso
DOWNLOAD_DELAY = 0.5
CONCURRENT_REQUESTS_PER_DOMAIN = 1

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.5
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

ITEM_PIPELINES = {
    "scraper.scrapy_project.pipelines.StoragePipeline": 300,
}

# substitui RetryMiddleware e UserAgentMiddleware padrões pelos nossos
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": None,
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scraper.scrapy_project.middlewares.retry.ExponentialBackoffRetryMiddleware": 200,
    "scraper.scrapy_project.middlewares.user_agent.RandomUserAgentMiddleware": 150,
}

RETRY_TIMES = 3
RETRY_BACKOFF_BASE = 1.0  # wait = backoff_base * 2^attempt (1s, 2s, 4s)

USER_AGENT_LIST = [
    "datahunter/0.1",
    "Mozilla/5.0 (compatible; datahunter/0.1; +https://github.com/MatheusAdeMiranda/datahunter)",
]

# scrapy-playwright: delega downloads com meta={"playwright": True} ao Playwright
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}

# desabilita telemetria do Scrapy
TELEMETRY_ENABLED = False

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
