from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from worker.app.config import settings
from worker.app.signals import on_task_failure, on_worker_process_init, on_worker_ready

# ---------------------------------------------------------------------------
# on_worker_process_init
# ---------------------------------------------------------------------------


def test_on_worker_process_init_calls_configure_logging() -> None:
    with patch("worker.app.signals.configure_logging") as mock_configure:
        on_worker_process_init()
    mock_configure.assert_called_once_with(settings.log_level)


# ---------------------------------------------------------------------------
# on_worker_ready
# ---------------------------------------------------------------------------


def test_on_worker_ready_starts_metrics_server() -> None:
    from scraper.app.core.metrics import METRICS_REGISTRY

    with patch("worker.app.signals.start_http_server") as mock_server:
        on_worker_ready()
    mock_server.assert_called_once_with(settings.metrics_port, registry=METRICS_REGISTRY)


# ---------------------------------------------------------------------------
# on_task_failure — webhook
# ---------------------------------------------------------------------------


def _make_sender(name: str = "my_task") -> Any:
    sender = MagicMock()
    sender.name = name
    return sender


def test_on_task_failure_skips_when_no_webhook_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", None)
    with patch("worker.app.signals.httpx.post") as mock_post:
        on_task_failure(task_id="abc", exception=ValueError("boom"), sender=_make_sender())
    mock_post.assert_not_called()


def test_on_task_failure_posts_to_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "http://example.com/hook")
    with patch("worker.app.signals.httpx.post") as mock_post:
        on_task_failure(
            task_id="task-123",
            exception=RuntimeError("algo errado"),
            sender=_make_sender("worker.app.jobs.scraping_jobs.scrape_books"),
        )
    mock_post.assert_called_once()
    _, call_kwargs = mock_post.call_args
    payload = call_kwargs["json"]
    assert payload["task_id"] == "task-123"
    assert payload["error"] == "algo errado"
    assert payload["error_type"] == "RuntimeError"
    assert "scrape_books" in payload["task"]


def test_on_task_failure_uses_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "http://example.com/hook")
    with patch("worker.app.signals.httpx.post") as mock_post:
        on_task_failure(task_id="t1", exception=ValueError("x"), sender=_make_sender())
    _, call_kwargs = mock_post.call_args
    assert call_kwargs["timeout"] == 5.0


def test_on_task_failure_handles_webhook_error_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falha no webhook nao deve propagar excecao — o job ja falhou, nao queremos mascarar."""
    monkeypatch.setattr(settings, "webhook_url", "http://bad.url")
    with patch(
        "worker.app.signals.httpx.post",
        side_effect=httpx.ConnectError("connection refused"),
    ):
        # nao deve lancar
        on_task_failure(task_id="t2", exception=ValueError("y"), sender=_make_sender())


def test_on_task_failure_handles_sender_without_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "webhook_url", "http://example.com/hook")
    sender_without_name = object()  # nao tem atributo .name
    with patch("worker.app.signals.httpx.post") as mock_post:
        on_task_failure(task_id="t3", exception=ValueError("z"), sender=sender_without_name)
    _, call_kwargs = mock_post.call_args
    assert "task" in call_kwargs["json"]
