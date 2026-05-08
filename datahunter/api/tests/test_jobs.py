from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.app.main import app

client = TestClient(app)


# ── Health ────────────────────────────────────────────────────────────────────


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── POST /jobs/scrape/books ───────────────────────────────────────────────────


def test_dispatch_books_returns_202() -> None:
    mock_task = MagicMock()
    mock_task.id = "books-task-id"
    with patch("api.app.jobs.celery_app.send_task", return_value=mock_task):
        response = client.post("/jobs/scrape/books")
    assert response.status_code == 202


def test_dispatch_books_returns_task_id_and_status() -> None:
    mock_task = MagicMock()
    mock_task.id = "books-task-id"
    with patch("api.app.jobs.celery_app.send_task", return_value=mock_task):
        response = client.post("/jobs/scrape/books")
    data = response.json()
    assert data["task_id"] == "books-task-id"
    assert data["status"] == "queued"


def test_dispatch_books_calls_correct_task_name() -> None:
    mock_task = MagicMock()
    mock_task.id = "books-task-id"
    with patch("api.app.jobs.celery_app.send_task", return_value=mock_task) as mock_send:
        client.post("/jobs/scrape/books")
    mock_send.assert_called_once_with("worker.app.jobs.scraping_jobs.scrape_books")


# ── POST /jobs/scrape/quotes ──────────────────────────────────────────────────


def test_dispatch_quotes_returns_202() -> None:
    mock_task = MagicMock()
    mock_task.id = "quotes-task-id"
    with patch("api.app.jobs.celery_app.send_task", return_value=mock_task):
        response = client.post("/jobs/scrape/quotes")
    assert response.status_code == 202


def test_dispatch_quotes_returns_task_id_and_status() -> None:
    mock_task = MagicMock()
    mock_task.id = "quotes-task-id"
    with patch("api.app.jobs.celery_app.send_task", return_value=mock_task):
        response = client.post("/jobs/scrape/quotes")
    data = response.json()
    assert data["task_id"] == "quotes-task-id"
    assert data["status"] == "queued"


def test_dispatch_quotes_calls_correct_task_name() -> None:
    mock_task = MagicMock()
    mock_task.id = "quotes-task-id"
    with patch("api.app.jobs.celery_app.send_task", return_value=mock_task) as mock_send:
        client.post("/jobs/scrape/quotes")
    mock_send.assert_called_once_with("worker.app.jobs.scraping_jobs.scrape_quotes")


# ── GET /jobs/{task_id} ───────────────────────────────────────────────────────


def _mock_async_result(state: str, result: object = None) -> MagicMock:
    mock = MagicMock()
    mock.state = state
    mock.result = result
    return mock


def test_get_job_status_pending() -> None:
    with patch("api.app.jobs.AsyncResult", return_value=_mock_async_result("PENDING")):
        response = client.get("/jobs/some-task-id")
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "some-task-id"
    assert data["status"] == "PENDING"
    assert data["result"] is None
    assert data["error"] is None


def test_get_job_status_success() -> None:
    job_result = {"items": 100, "errors": 0, "error_details": [], "persisted": True}
    with patch(
        "api.app.jobs.AsyncResult",
        return_value=_mock_async_result("SUCCESS", job_result),
    ):
        response = client.get("/jobs/done-task-id")
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["result"]["items"] == 100
    assert data["error"] is None


def test_get_job_status_failure() -> None:
    exc = RuntimeError("connection refused")
    with patch(
        "api.app.jobs.AsyncResult",
        return_value=_mock_async_result("FAILURE", exc),
    ):
        response = client.get("/jobs/failed-task-id")
    data = response.json()
    assert data["status"] == "FAILURE"
    assert data["result"] is None
    assert "connection refused" in data["error"]


def test_get_job_status_started() -> None:
    with patch("api.app.jobs.AsyncResult", return_value=_mock_async_result("STARTED")):
        response = client.get("/jobs/running-task-id")
    data = response.json()
    assert data["status"] == "STARTED"
    assert data["result"] is None
    assert data["error"] is None


def test_get_job_uses_correct_task_id() -> None:
    with patch("api.app.jobs.AsyncResult", return_value=_mock_async_result("PENDING")) as mock_cls:
        client.get("/jobs/my-specific-id")
    mock_cls.assert_called_once_with("my-specific-id", app=mock_cls.call_args[1]["app"])
