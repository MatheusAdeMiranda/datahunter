# datahunter

[![CI](https://github.com/MatheusAdeMiranda/datahunter/actions/workflows/ci.yml/badge.svg)](https://github.com/MatheusAdeMiranda/datahunter/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/testes-439%20%7C%20100%25%20coverage-brightgreen)](#qualidade-de-codigo)
[![mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Sistema profissional de web scraping construido em Python 3.12 com httpx, Playwright, Scrapy, SQLAlchemy, Celery, Redis e Docker Compose.

O projeto foi desenvolvido em 30 dias como exercicio deliberado de engenharia: cada modulo cobre um conceito avancado de Python (generators, decorators, asyncio, ORM, filas distribuidas) e cada decisao tecnica esta documentada com o motivo.

---

## O que este projeto demonstra

| Area | O que foi implementado |
|---|---|
| **Python avancado** | generators, decorators com state, context managers, dataclasses, Protocol, asyncio producer-consumer, ExitStack |
| **Scraping em 3 camadas** | httpx puro (sync e async), Playwright headless (DOM + interceptacao XHR), Scrapy framework |
| **Concorrencia** | `asyncio.Queue` producer-consumer, `asyncio.Semaphore` para browsers paralelos, rate limit por dominio (sliding-window) |
| **Storage** | SQLAlchemy 2.0 com `Mapped`/`mapped_column`, upsert via `session.merge()`, Alembic migrations, async via `aiosqlite`/`asyncpg` |
| **Arquitetura distribuida** | Celery tasks com retry exponencial e jitter, Beat scheduler, Redis broker, Flower monitoring |
| **Observabilidade** | structlog JSON com bridge stdlib, Prometheus metrics (Counter, Histogram), Grafana dashboards, webhook alerts |
| **CI/CD** | GitHub Actions matrix (3.11+3.12), coverage floor 90%, deploy condicional no GHCR |
| **Qualidade** | 439 testes, 100% coverage, mypy --strict, ruff check + ruff format |

---

## Arquitetura

```mermaid
graph TD
    Beat["Celery Beat\nagendador"] -->|dispara tasks| Queue[("Redis\nbroker + cache")]
    Queue --> Worker["Celery Worker\nexecuta scraping"]

    Worker --> BS["BooksSpider\nhttpx + BS4"]
    Worker --> QS["QuotesSpider\nJSON API"]
    Worker --> PW["PlaywrightSpider\nheadless browser"]
    Worker --> SC["ScrapySpider\nframework"]

    BS --> DB[("PostgreSQL\nscraped_books")]
    QS --> DB
    SC --> DB

    Worker --> M["Prometheus\nmetrics"]
    M --> Prom["Prometheus\n:9090"]
    Prom --> Graf["Grafana\n:3000"]
    Worker --> Flower["Flower\n:5555"]

    classDef service fill:#2d6a4f,color:#fff,stroke:#1b4332
    classDef storage fill:#1d3557,color:#fff,stroke:#0d2035
    classDef spider fill:#e76f51,color:#fff,stroke:#c1440e
    classDef monitor fill:#457b9d,color:#fff,stroke:#2c5f7d

    class Worker,Beat service
    class Queue,DB storage
    class BS,QS,PW,SC spider
    class M,Prom,Graf,Flower monitor
```

---

## Requisitos

- Python 3.11+ (ou 3.12)
- [uv](https://docs.astral.sh/uv/)
- Docker e Docker Compose

---

## Instalacao rapida

```bash
git clone https://github.com/MatheusAdeMiranda/datahunter.git
cd datahunter
cp .env.example .env
docker compose up --build -d
```

Apos subir, verifique os servicos nas portas abaixo.

---

## Servicos e portas

| Servico    | URL                        | Descricao                                     |
|------------|----------------------------|-----------------------------------------------|
| Flower     | http://localhost:5555       | Monitoramento de tasks Celery em tempo real    |
| Grafana    | http://localhost:3000       | Dashboards de metricas (admin / datahunter)    |
| Prometheus | http://localhost:9090       | Coleta de metricas do worker                  |
| PostgreSQL | localhost:5432              | Banco de dados (usuario/senha: datahunter)     |
| Redis      | localhost:6379              | Broker Celery e rate limiting                  |

---

## Verificar que esta funcionando

```bash
# 1. Todos os containers devem estar healthy/running
docker compose ps

# 2. Disparar um job de scraping manualmente
docker compose exec worker celery -A worker.app.main call worker.app.jobs.scraping_jobs.scrape_books

# 3. Acompanhar o resultado no Flower
#    Abra http://localhost:5555 → Tasks
```

O Beat agenda `scrape_books` e `scrape_quotes` automaticamente no intervalo definido em
`DATAHUNTER_SCRAPING_INTERVAL_SECONDS` (padrao: 3600 segundos).

---

## Desenvolvimento local (sem Docker)

```bash
# Instalar dependencias
uv sync

# Instalar browsers do Playwright (necessario para spiders com JS)
uv run playwright install chromium

# Rodar testes
uv run pytest

# Lint
uv run ruff check .
uv run ruff format --check .

# Type check
uv run mypy scraper/ --strict
```

Para spiders que precisam do banco, suba apenas a infra:

```bash
docker compose up postgres redis -d

# Exportar a URL para o ambiente local
export DATAHUNTER_DATABASE_URL=postgresql+psycopg2://datahunter:datahunter@localhost:5432/datahunter

# Rodar migracao (cria a tabela scraped_books)
uv run alembic upgrade head
```

---

## Migrations (Alembic)

O worker cria as tabelas automaticamente via `init_db()` na primeira execucao.
Para gerenciar o schema com Alembic em producao:

```bash
# Aplicar todas as migrations pendentes
DATAHUNTER_DATABASE_URL=postgresql+psycopg2://... uv run alembic upgrade head

# Gerar nova migration apos alterar models.py
uv run alembic revision --autogenerate -m "descricao"
```

---

## Modo dev vs producao

O arquivo `docker-compose.override.yml` e carregado automaticamente pelo Docker Compose
quando existe. Ele sobrescreve o compose principal com configuracoes de desenvolvimento:

- codigo-fonte montado como volume (hot reload sem rebuild)
- Celery com `--pool=solo` e `--concurrency=1` (stack trace completo)
- variaveis de debug ativas

Para simular producao sem o override:

```bash
docker compose -f docker-compose.yml up --build -d
```

---

## Qualidade de codigo

```
439 testes | 100% coverage | mypy --strict | ruff clean
```

CI matrix roda em Python 3.11 e 3.12. Coverage floor configurado em `pyproject.toml`
(`fail_under = 90`) — PRs que derrubar a cobertura abaixo desse limite falham automaticamente.

---

## Estrutura do projeto

```
datahunter/
  scraper/app/
    core/        # HTTPClient (retry, rate limit, robots.txt), decorators, settings, logging, metrics
    parsers/     # HTML parser (BS4 + lxml), XPath helpers
    spiders/     # BooksSpider e QuotesSpider (sync e async)
    browsers/    # Playwright sync/async, interceptacao XHR
    storage/     # StorageService, AsyncStorageService, SQLAlchemy models
    benchmarks/  # sync vs async, parallel browsers
  scraper/scrapy_project/  # BooksSpider e QuotesSpider via Scrapy
  worker/app/
    main.py      # App Celery + Beat schedule
    jobs/        # scrape_books e scrape_quotes tasks
    signals.py   # Prometheus HTTP server, structlog, webhook alerts
  alembic/       # Migrations do banco de dados
  prometheus.yml # Configuracao de scrape
  grafana/       # Datasource Prometheus provisionado automaticamente
```

---

## Proximos passos

- **API de gerenciamento de jobs**: endpoint FastAPI para disparar e consultar status de scraping jobs via HTTP (sem precisar do CLI do Celery)
- **Dashboard Grafana provisionado**: `grafana/dashboards/datahunter.json` com paineis de `pages_scraped_total`, `scraping_errors_total` e `scraping_duration_seconds`
- **Modelo ScrapedQuote**: persistir resultados do `scrape_quotes` no banco (atualmente retornados apenas no resultado da task)
- **Prometheus multiprocessing**: fix para coletar metricas dos processos filho do Celery worker via `multiprocessing_registry`
