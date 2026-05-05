from __future__ import annotations

import logging

import pytest
import structlog.contextvars

from scraper.app.core.logging import configure_logging, get_logger, job_context


def test_configure_logging_sets_root_level() -> None:
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING
    # restaura para INFO para nao afetar outros testes
    configure_logging("INFO")


def test_configure_logging_adds_processor_formatter_handler() -> None:
    configure_logging("INFO")
    root = logging.getLogger()
    formatters = [h.formatter for h in root.handlers]
    assert any(isinstance(f, structlog.stdlib.ProcessorFormatter) for f in formatters)


def test_configure_logging_idempotent() -> None:
    """Segunda chamada nao deve duplicar o handler structlog."""
    configure_logging("INFO")
    configure_logging("INFO")
    root = logging.getLogger()
    structlog_handlers = [
        h for h in root.handlers if isinstance(h.formatter, structlog.stdlib.ProcessorFormatter)
    ]
    assert len(structlog_handlers) == 1


def test_get_logger_returns_bound_logger() -> None:
    lg = get_logger("test.module")
    assert lg is not None


def test_get_logger_accepts_log_calls() -> None:
    configure_logging("INFO")
    lg = get_logger("test.module")
    # nao deve lancar excecao
    lg.info("mensagem de teste", key="value")


def test_job_context_binds_job_id() -> None:
    structlog.contextvars.clear_contextvars()
    with job_context("job-abc"):
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("job_id") == "job-abc"


def test_job_context_clears_after_exit() -> None:
    structlog.contextvars.clear_contextvars()
    with job_context("job-xyz"):
        pass
    ctx = structlog.contextvars.get_contextvars()
    assert "job_id" not in ctx


def test_job_context_clears_even_on_exception() -> None:
    structlog.contextvars.clear_contextvars()
    with pytest.raises(RuntimeError), job_context("job-err"):
        raise RuntimeError("boom")
    ctx = structlog.contextvars.get_contextvars()
    assert "job_id" not in ctx
