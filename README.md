# datahunter

Sistema profissional de web scraping — construido ao longo de 30 dias de mentoria.

## Requisitos

- Python 3.12+
- uv
- Docker e Docker Compose

## Instalacao

```bash
uv sync
```

## Rodar testes

```bash
uv run pytest
```

## Lint e formatacao

```bash
uv run ruff check .
uv run ruff format .
```

## Type check

```bash
uv run mypy scraper/ --strict
```

## Subir o stack completo

```bash
cp .env.example .env
docker compose up --build -d
```

## Arquitetura

Ver `CLAUDE.md`.
