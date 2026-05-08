from __future__ import annotations

from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter

from api.app.schemas import DispatchResponse, JobStatusResponse
from worker.app.main import app as celery_app

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TASK_SCRAPE_BOOKS = "worker.app.jobs.scraping_jobs.scrape_books"
_TASK_SCRAPE_QUOTES = "worker.app.jobs.scraping_jobs.scrape_quotes"


@router.post("/scrape/books", response_model=DispatchResponse, status_code=202)
def dispatch_scrape_books() -> DispatchResponse:
    """Dispatch a scrape_books task to the Celery worker queue."""
    task = celery_app.send_task(_TASK_SCRAPE_BOOKS)
    return DispatchResponse(task_id=task.id, status="queued")


@router.post("/scrape/quotes", response_model=DispatchResponse, status_code=202)
def dispatch_scrape_quotes() -> DispatchResponse:
    """Dispatch a scrape_quotes task to the Celery worker queue."""
    task = celery_app.send_task(_TASK_SCRAPE_QUOTES)
    return DispatchResponse(task_id=task.id, status="queued")


@router.get("/{task_id}", response_model=JobStatusResponse)
def get_job_status(task_id: str) -> JobStatusResponse:
    """Return the current state and result of a Celery task by ID."""
    result: Any = AsyncResult(task_id, app=celery_app)
    state: str = result.state
    job_result: dict[str, Any] | None = None
    error: str | None = None
    if state == "SUCCESS":
        job_result = result.result
    elif state == "FAILURE":
        error = str(result.result)
    return JobStatusResponse(task_id=task_id, status=state, result=job_result, error=error)
