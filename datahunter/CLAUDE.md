# CLAUDE.md

## Objetivo
Sistema de web scraping profissional para coleta e monitoramento de dados da web.

## Stack
- Python 3.12
- uv — gerenciamento de pacotes
- httpx — cliente HTTP sync/async
- BeautifulSoup4 + lxml — parsing HTML
- Playwright — sites dinamicos
- Scrapy — scraping em escala
- SQLAlchemy 2.0 — ORM
- Alembic — migrations
- Celery + Redis — filas de jobs
- Docker Compose — orquestracao local

## Arquitetura
- scraper: coleta e parse de dados
- worker: executa jobs de scraping em fila
- postgres: persiste resultados
- redis: broker de filas e rate limiting
- flower: monitoramento de workers

## Portas previstas
- scraper api: 8000
- postgres: 5432
- redis: 6379
- flower: 5555
- prometheus: 9090
- grafana: 3000

## Fluxo Git
- branch por feature: feat/nome-da-feature
- commits pequenos no imperativo em ingles
- formato: tipo(escopo): descricao curta
  - feat, fix, refactor, test, chore, docs
- PR obrigatoria antes de mergear na main
- squash merge na main
- CI deve estar verde antes de mergear

## Politica de Acesso
- respeitar robots.txt sempre
- rate limit: no maximo 2 requests por segundo por dominio
- identificar o bot no User-Agent
- nao coletar dado pessoal sem necessidade

## Modulos existentes (Semana 1 em andamento)

`scraper/app/core/` — todos com 100% de cobertura e mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `utils.py` | 2 | `_DEFAULT_HEADERS` (MappingProxyType), closures, generators |
| `exceptions.py` | 3 | `ScrapingError`, `NetworkError`, `ParseError`, `StorageError` |
| `entities.py` | 3 | `ScrapingJob` (frozen dataclass), `ScrapedItem`, `ScrapingResult` |
| `pipeline.py` | 4 | `PageIterator`, pipeline gerador, `itertools`, `functools.lru_cache` |
| `decorators.py` | 5 | `@retry`, `@rate_limit` (sliding-window), `@log_execution` |

## Decisoes
- httpx no lugar de requests: suporte nativo a async
- Playwright no lugar de Selenium: API moderna e async
- uv no lugar de pip: reproducibilidade e velocidade
- `UP047` ignorado no ruff (`ignore = ["UP047"]` em pyproject.toml): target-version e py312 mas o floor e 3.11; PEP 695 (type parameters) nao pode ser usado em codigo que precisa rodar no 3.11

## Decisoes Abertas
- banco local: SQLite para dev, PostgreSQL para prod (decidir no Dia 11)
- framework de API para gerenciar jobs: a definir na Semana 4

## Dividas Tecnicas
(registrar aqui conforme aparecerem)

## Proximo passo — Dia 6: Context Managers e Tipagem Estatica

Entregas esperadas:
- `scraper/app/core/contexts.py`: `managed_session()` (contextlib.contextmanager) e `BrowserContext` (classe com __enter__/__exit__)
- `scraper/tests/test_contexts.py`
- mypy --strict sem erros em todos os modulos da semana
