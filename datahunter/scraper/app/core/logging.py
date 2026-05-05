from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import cast

import structlog
import structlog.contextvars
import structlog.stdlib
from structlog.types import Processor


def configure_logging(log_level: str = "INFO") -> None:
    """Configura structlog com saída JSON e bridge para stdlib logging.

    Todos os loggers criados com logging.getLogger() passam pelo pipeline
    do structlog e emitem JSON estruturado — sem precisar alterar os módulos
    existentes. Idealmente chamada uma única vez na inicialização do processo.
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Evita duplicar handler se configure_logging for chamada mais de uma vez
    if not any(
        isinstance(h.formatter, structlog.stdlib.ProcessorFormatter) for h in root.handlers
    ):
        root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Retorna um BoundLogger structlog tipado para uso nos módulos do projeto."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


@contextmanager
def job_context(job_id: str) -> Generator[None, None, None]:
    """Context manager que associa job_id a todos os logs dentro do bloco.

    Usa contextvars do asyncio para propagar o contexto de forma thread-safe
    e async-safe sem passar o job_id explicitamente para cada chamada de log.
    """
    structlog.contextvars.bind_contextvars(job_id=job_id)
    try:
        yield
    finally:
        structlog.contextvars.clear_contextvars()
