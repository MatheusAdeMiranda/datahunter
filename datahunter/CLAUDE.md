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
| `contexts.py` | 6 | `Resource` (Protocol), `managed_session()` (@contextmanager), `BrowserContext` (__enter__/__exit__), `open_resources()` (ExitStack) |
| `http_client.py` | 8 | `HTTPClient` (httpx.Client wrapper), retry em 429/5xx, timeout configuravel, `NetworkError` em falhas de conexao |

`scraper/app/parsers/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `html_parser.py` | 9–10 | `parse_catalog_page()` (CSS via BS4+lxml), `extract_available_titles_xpath()` (XPath com lxml.etree), `extract_next_page_url()` (paginacao), `BookData` TypedDict, `ParseError` defensivo |

`scraper/app/spiders/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `books_spider.py` | 10–11 | `BooksSpider` (paginacao completa, deduplicacao por `set[str]`, JSON e/ou DB), `_save_json()`, entrypoint `__main__` |

`scraper/app/storage/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `models.py` | 11 | `Base` (DeclarativeBase), `ScrapedBook` (PK=title, Mapped/mapped_column) |
| `service.py` | 11 | `StorageService` — `save_items()` upsert via `session.merge()`, `count()`, `init_db()` |

`alembic/` — migrations com Alembic:

| Arquivo | Dia | O que tem |
|---|---|---|
| `versions/0001_create_scraped_books.py` | 11 | cria tabela `scraped_books` com PK em `title` |

## Decisoes
- httpx no lugar de requests: suporte nativo a async
- Playwright no lugar de Selenium: API moderna e async
- uv no lugar de pip: reproducibilidade e velocidade
- `UP047` ignorado no ruff (`ignore = ["UP047"]` em pyproject.toml): target-version e py312 mas o floor e 3.11; PEP 695 (type parameters) nao pode ser usado em codigo que precisa rodar no 3.11
- `ParseError` em pagina nao interrompe paginacao: erro e logado e a spider segue para o proximo link
- `NetworkError` interrompe a paginacao: erro de rede provavelmente afeta as paginas seguintes tambem
- `cast(dict[str, str], book)` no lugar de `dict(book)`: TypedDict tem `__getitem__` com retorno `object` no mypy strict; cast e seguro porque TypedDict e um dict em runtime
- banco: SQLite para dev, PostgreSQL para prod (Dia 25, Docker Compose)
- `title` como PK de `ScrapedBook`: identificador natural no books.toscrape.com; permite `session.merge()` sem coluna auxiliar de unicidade
- `session.merge()` para upsert: funciona em SQLite e PostgreSQL sem codigo dialect-specific; custo e um SELECT extra por item, aceitavel no volume atual
- `StorageService` injetado no spider via parametro opcional: testes do Dia 10 nao quebram (passam `storage=None`)
- `StorageService` importado via `TYPE_CHECKING` no spider: evita importacao circular em runtime caso o modulo de storage importe algo do spider no futuro

## Decisoes Abertas
- framework de API para gerenciar jobs: a definir na Semana 4
- upsert dialect-specific (`INSERT ... ON CONFLICT DO UPDATE`) para PostgreSQL: avaliar no Dia 19+ (async)

## Dividas Tecnicas
(registrar aqui conforme aparecerem)

## Proximo passo — Dia 12: Robustez (Retry, Rate Limiting e Tratamento de Erro)

Entregas esperadas:
- backoff exponencial no `@retry`
- rate limiter por dominio no `HTTPClient`
- spider nao para em erro de item isolado
- verificacao de `robots.txt` antes de scraper
- testes com SQLite em memoria
- salva resultado em JSON
- testes com mock HTTP (respx) e fixtures HTML locais
