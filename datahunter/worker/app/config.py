from __future__ import annotations

from pydantic_settings import BaseSettings


class WorkerSettings(BaseSettings):
    """Configuracoes do worker Celery lidas do ambiente."""

    redis_url: str = "redis://localhost:6379/0"
    # URL de conexao com o banco de dados (None = sem persistencia)
    # Ex.: postgresql+psycopg2://user:pass@host:5432/db
    database_url: str | None = None
    # Intervalo do Beat em segundos (padrao: 1 hora)
    scraping_interval_seconds: int = 3600
    # Webhook para alertas de falha de task (None = desabilitado)
    webhook_url: str | None = None
    # Nivel de log: DEBUG, INFO, WARNING, ERROR
    log_level: str = "INFO"
    # Porta do servidor HTTP de metricas Prometheus
    metrics_port: int = 8001

    model_config = {"env_prefix": "DATAHUNTER_"}


settings = WorkerSettings()
