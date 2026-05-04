from __future__ import annotations

from pydantic_settings import BaseSettings


class WorkerSettings(BaseSettings):
    """Configuracoes do worker Celery lidas do ambiente."""

    redis_url: str = "redis://localhost:6379/0"
    # Intervalo do Beat em segundos (padrao: 1 hora)
    scraping_interval_seconds: int = 3600

    model_config = {"env_prefix": "DATAHUNTER_"}


settings = WorkerSettings()
