from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram

# Registry próprio para evitar colisão com o REGISTRY global do prometheus_client
# nos testes — múltiplos processos de teste importam o módulo, e registrar no
# REGISTRY global causaria "Duplicated timeseries" na segunda importação.
METRICS_REGISTRY: CollectorRegistry = CollectorRegistry()

pages_scraped_total: Counter = Counter(
    "datahunter_pages_scraped_total",
    "Total de itens coletados com sucesso",
    ["spider"],
    registry=METRICS_REGISTRY,
)

scraping_errors_total: Counter = Counter(
    "datahunter_scraping_errors_total",
    "Total de erros durante o scraping por tipo",
    ["spider", "error_type"],
    registry=METRICS_REGISTRY,
)

scraping_duration_seconds: Histogram = Histogram(
    "datahunter_scraping_duration_seconds",
    "Duração dos jobs de scraping em segundos",
    ["spider"],
    registry=METRICS_REGISTRY,
)
