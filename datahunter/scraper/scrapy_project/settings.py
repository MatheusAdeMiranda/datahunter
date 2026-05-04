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

# desabilita telemetria do Scrapy
TELEMETRY_ENABLED = False

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
