from __future__ import annotations

import logging
from typing import Any

import httpx
from celery.signals import task_failure, worker_process_init, worker_ready
from prometheus_client import start_http_server

from scraper.app.core.logging import configure_logging
from scraper.app.core.metrics import METRICS_REGISTRY
from worker.app.config import settings

logger = logging.getLogger(__name__)


@worker_process_init.connect
def on_worker_process_init(**kwargs: Any) -> None:
    """Configura logging estruturado JSON ao inicializar cada processo worker."""
    configure_logging(settings.log_level)


@worker_ready.connect
def on_worker_ready(**kwargs: Any) -> None:
    """Sobe o servidor HTTP de métricas Prometheus quando o worker fica pronto."""
    start_http_server(settings.metrics_port, registry=METRICS_REGISTRY)
    logger.info("metrics server started on port %d", settings.metrics_port)


@task_failure.connect
def on_task_failure(
    *,
    task_id: str,
    exception: BaseException,
    sender: Any,
    **kwargs: Any,
) -> None:
    """Envia notificação via webhook quando uma task Celery falha definitivamente.

    Só dispara após esgotar as retentativas (task_failure não é emitido em
    cada tentativa — só quando a task não será mais retentada pelo Celery).
    Se DATAHUNTER_WEBHOOK_URL não estiver configurada, a função retorna em silêncio.
    """
    if not settings.webhook_url:
        return
    try:
        httpx.post(
            settings.webhook_url,
            json={
                "task_id": task_id,
                "task": getattr(sender, "name", str(sender)),
                "error": str(exception),
                "error_type": type(exception).__name__,
            },
            timeout=5.0,
        )
    except Exception:
        logger.warning("webhook delivery failed for task %s", task_id)
