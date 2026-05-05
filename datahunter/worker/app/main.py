from __future__ import annotations

from celery import Celery

from worker.app.config import settings

app = Celery(
    "datahunter",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.app.jobs.scraping_jobs", "worker.app.signals"],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Beat: agenda scraping periodico
    beat_schedule={
        "scrape-books-hourly": {
            "task": "worker.app.jobs.scraping_jobs.scrape_books",
            "schedule": settings.scraping_interval_seconds,
            "args": [],
        },
        "scrape-quotes-hourly": {
            "task": "worker.app.jobs.scraping_jobs.scrape_quotes",
            "schedule": settings.scraping_interval_seconds,
            "args": [],
        },
    },
)
