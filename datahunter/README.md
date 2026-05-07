# datahunter

[![CI](https://github.com/MatheusAdeMiranda/datahunter/actions/workflows/ci.yml/badge.svg)](https://github.com/MatheusAdeMiranda/datahunter/actions/workflows/ci.yml)

Sistema profissional de web scraping construido com Python 3.12, httpx, Playwright, Scrapy, SQLAlchemy, Celery, Redis e Docker Compose.

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker e Docker Compose

## Instalacao rapida

```bash
git clone https://github.com/MatheusAdeMiranda/datahunter.git
cd datahunter
cp .env.example .env
docker compose up --build -d
```

Apos subir, verifique os servicos nas portas abaixo.

## Servicos e portas

| Servico    | URL                        | Descricao                              |
|------------|----------------------------|----------------------------------------|
| Flower     | http://localhost:5555       | Monitoramento de tasks Celery          |
| Grafana    | http://localhost:3000       | Dashboards de metricas (admin/datahunter) |
| Prometheus | http://localhost:9090       | Coleta de metricas do worker           |
| PostgreSQL | localhost:5432              | Banco de dados (usuario/senha: datahunter) |
| Redis      | localhost:6379              | Broker Celery e rate limiting          |

## Verificar que esta funcionando

```bash
# 1. Todos os containers devem estar healthy/running
docker compose ps

# 2. Disparar um job de scraping manualmente
docker compose exec worker celery -A worker.app.main call worker.app.jobs.scraping_jobs.scrape_books

# 3. Acompanhar o resultado no Flower
# Abra http://localhost:5555 -> Tasks
```

O Beat agenda `scrape_books` e `scrape_quotes` automaticamente no intervalo definido em
`DATAHUNTER_SCRAPING_INTERVAL_SECONDS` (padrao: 3600 segundos).

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

Para spiders que precisam do banco, suba apenas a infra e rode o scraper localmente:

```bash
docker compose up postgres redis -d

# Exportar a URL para o ambiente local
export DATAHUNTER_DATABASE_URL=postgresql+psycopg2://datahunter:datahunter@localhost:5432/datahunter

# Rodar migracao (cria a tabela scraped_books)
uv run alembic upgrade head
```

## Migrations (Alembic)

O worker cria as tabelas automaticamente via `init_db()` na primeira execucao.
Para gerenciar o schema com Alembic em producao:

```bash
# Aplicar todas as migrations pendentes
DATAHUNTER_DATABASE_URL=postgresql+psycopg2://... uv run alembic upgrade head

# Gerar nova migration apos alterar models.py
uv run alembic revision --autogenerate -m "descricao"
```

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

## Arquitetura

```
datahunter/
  scraper/app/
    core/        # HTTPClient, decoradores, entidades, settings, logging, metricas
    parsers/     # HTML parser (BS4 + lxml)
    spiders/     # BooksSpider, QuotesSpider (sync e async)
    browsers/    # Playwright sync/async, network interception
    storage/     # StorageService, AsyncStorageService, SQLAlchemy models
  scraper/scrapy_project/  # BooksSpider e QuotesSpider via Scrapy
  worker/app/
    main.py      # App Celery + Beat schedule
    jobs/        # scrape_books e scrape_quotes tasks
    signals.py   # Prometheus HTTP server, logging, webhook alerts
  alembic/       # Migrations do banco de dados
  prometheus.yml # Configuracao de scrape
  grafana/       # Datasource Prometheus provisionado automaticamente
```

Decisoes de design e debitos tecnicos: ver `CLAUDE.md`.
