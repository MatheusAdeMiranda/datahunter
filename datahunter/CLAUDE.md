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
| `decorators.py` | 5–12 | `@retry` (com `backoff_base` para backoff exponencial), `@rate_limit` (sliding-window), `@log_execution` |
| `contexts.py` | 6 | `Resource` (Protocol), `managed_session()` (@contextmanager), `BrowserContext` (__enter__/__exit__), `open_resources()` (ExitStack) |
| `http_client.py` | 8–12 | `HTTPClient` (httpx.Client wrapper), retry em 429/5xx, timeout configuravel, `NetworkError` em falhas de conexao, backoff exponencial (`backoff_base`), rate limit por dominio (`requests_per_second`) |

`scraper/app/core/robots.py` — com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `robots.py` | 12 | `RobotsChecker` — fetch + parse de `robots.txt` por dominio, cache, `is_allowed()`, falha silenciosa (permite tudo) em erro de rede ou non-200 |

`scraper/app/parsers/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `html_parser.py` | 9–10 | `parse_catalog_page()` (CSS via BS4+lxml), `extract_available_titles_xpath()` (XPath com lxml.etree), `extract_next_page_url()` (paginacao), `BookData` TypedDict, `ParseError` defensivo |

`scraper/app/spiders/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `books_spider.py` | 10–12 | `BooksSpider` (paginacao completa, deduplicacao por `set[str]`, JSON e/ou DB), `_save_json()`, `robots_checker` opcional, isolamento de erro por livro, entrypoint `__main__` |

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

- `backoff_base * 2^(attempt-1)` no `@retry` e no `HTTPClient`: padrao exponencial classico; testavel via `patch("time.sleep")` sem sleep real
- `requests_per_second: float | None = None` no HTTPClient: `None` desabilita o rate limit (testes existentes nao quebram); spider e `__main__` passam `2.0` conforme politica
- `RobotsChecker` em `core/` e nao em `spiders/`: pode ser reutilizado por qualquer spider ou cliente HTTP futuro
- `parser.parse([])` sempre chamado no `_fetch_parser`: garante que `last_checked` seja definido mesmo em erro/non-200; `can_fetch` retorna `True` sem regras de Disallow
- `next_url = extract_next_page_url(html, current_url)` extraido ANTES do bloco `try/except ParseError`: preserva a capacidade de seguir para a proxima pagina mesmo quando o parse da atual falha

## Decisoes Abertas
- framework de API para gerenciar jobs: a definir na Semana 4
- upsert dialect-specific (`INSERT ... ON CONFLICT DO UPDATE`) para PostgreSQL: avaliar no Dia 19+ (async)

## Dividas Tecnicas

- `_wait_for_rate_limit` no `HTTPClient` impoe intervalo minimo entre requests por dominio (nao janela deslizante como o decorator `@rate_limit`): comportamento correto para scraper, mas a diferenca de semantica nao esta documentada no codigo — avaliar unificacao ou comentario no Dia 18+ (async)
- `StorageService.save_items` envolve qualquer excecao como `StorageError`: um `KeyError` por chave ausente no `item.data` geraria mensagem confusa; adicionar validacao de campos antes da sessao de banco no Dia 19+ (storage async)

## Cobertura de testes

- **100%** em todos os modulos de `scraper/` (520 statements, 0 missed)
- Entrypoints `if __name__ == "__main__"` marcados com `# pragma: no cover` (nao sao unidades testavel)
- Casos de HTML invalido organizados como tabelas `@pytest.mark.parametrize` em `test_html_parser.py`: facil adicionar nova linha quando o site mudar
- Nenhum teste faz requisicao real de rede: tudo mockado com `respx` ou fixtures HTML locais em `scraper/tests/fixtures/`

## Decisao — Dia 13

- `try/except Exception` em volta de `ScrapedItem(...)` removido do spider: frozen dataclass com inputs validos nao pode lancar excecao; o bloco era codigo morto que reduzia legibilidade e criava gap de cobertura artificialmente irresolvivel

## Decisoes — Dia 14

- `BOT_USER_AGENT = "datahunter/0.1"` em `utils.py`: string completa usada no header HTTP (padrao `Nome/Versao`)
- `ROBOTS_USER_AGENT = BOT_USER_AGENT.split("/")[0]` = `"datahunter"`: agente usado no `RobotsChecker`. Python 3.11+ `urllib.robotparser` faz strip da versao na query (`can_fetch`) mas NAO na regra do robots.txt — entao `User-agent: datahunter` no robots.txt bate com `can_fetch("datahunter", url)` mas NAO com `can_fetch("datahunter/0.1", url)`. O agente de checagem deve ser o nome sem versao para que sites que bloqueiem `datahunter` nos logs sejam respeitados
- Revisao senior da Semana 2: sem bugs criticos reais alem do user-agent. Padroes como `raise AssertionError("unreachable")`, `assert last_exc is not None` e `cast(dict[str,str], book)` sao corretos e documentados; nao foram alterados

## Estrategias para sites dinamicos (Dia 15)

### Estrategia 1 — API interna (sem browser)

Inspecionar aba Network → Fetch/XHR antes de qualquer codigo. Muitos sites que "renderizam com JS" buscam dados de um endpoint JSON proprio. Se encontrar, consumir direto com `httpx`.

Exemplo: `quotes.toscrape.com/js/` → `GET /api/quotes?page=N` retorna JSON paginado com campo `has_next`. Nenhum Playwright necessario.

### Estrategia 2 — Renderizacao headless (Playwright)

Quando nao ha endpoint JSON detectavel (dados embutidos no JS, WebSocket, canvas), usar Playwright para renderizar o browser e extrair do DOM. Custo: ~10x mais lento, binario de browser necessario, maior superficie de deteccao. Ver Dia 16.

### Quando usar cada uma

| Sinal | Estrategia |
|---|---|
| Network tab mostra chamadas XHR/Fetch com JSON | API interna (httpx) |
| Resposta HTML chega vazia, dados aparecem so apos render | Playwright |
| Site carrega dados via WebSocket | Playwright + interceptacao |
| Endpoint exige auth ou CSRF token complexo | Avaliar caso a caso |

## Modulos existentes (atualizado Dia 15)

`scraper/app/spiders/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `books_spider.py` | 10–12 | `BooksSpider` (HTML + paginacao via "next" link, BS4, SQLite/Postgres) |
| `quotes_spider.py` | 15 | `QuotesSpider` (JSON API, paginacao via `has_next`, sem browser) |

`scraper/tests/fixtures/` — fixtures de teste:

| Arquivo | Usado por |
|---|---|
| `books_catalog.html`, `books_page1.html`, `books_page2.html` | `test_html_parser.py`, `test_books_spider.py` |
| `quotes_page1.json`, `quotes_page2.json` | `test_quotes_spider.py` |

## Decisoes — Dia 15

- `StorageService` nao persiste quotes: o modelo `ScrapedBook` tem campos especificos de livro (`title`, `price`, `availability`, `rating`); quotes tem campos diferentes (`text`, `author`, `tags`). Para persistir quotes, criar `ScrapedQuote` (modelo separado) — avaliar no Dia 19+ quando armazenamento async for introduzido
- `_extract_quote` e `_parse_response` exportadas (sem underscore duplo): permitem teste unitario direto sem instanciar o spider
- Tags sao joinadas como CSV string (`"tag1, tag2"`) para caber no schema generico `dict[str, str]` do `ScrapedItem.data` sem alterar a entidade

## Modulos existentes (atualizado Dia 16)

`scraper/app/browsers/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `playwright_client.py` | 16 | `PlaywrightClient` — context manager headless Chromium, `add_route()` para interceptacao de requests, `fetch_html()`, `iter_pages()` com paginacao por clique |
| `quotes_pw_spider.py` | 16 | `QuotesPWSpider` — scraping via DOM renderizado (Strategy 2), BS4 parsing, isolamento de erro por quote, JSON output |

`scraper/tests/fixtures/` — fixtures de teste atualizadas:

| Arquivo | Usado por |
|---|---|
| `quotes_pw_page1.html`, `quotes_pw_page2.html`, `quotes_pw_malformed.html` | `test_playwright_client.py` |

## Decisoes — Dia 16

- `PlaywrightClient.add_route(pattern, handler)` registra interceptadores aplicados a toda nova page criada pelo cliente: testes passam HTML estatico via `page.route()` sem servidor externo nem rede real
- `concurrency = ["thread", "greenlet"]` no `[tool.coverage.run]` do pyproject.toml: Playwright sync API usa greenlets internamente para sincronizar o event loop asyncio com o thread principal — sem essa configuracao, `coverage.py` nao rastreia linhas executadas atraves de `greenlet.switch()` e reporta 59% mesmo com todos os testes passando
- `iter_pages` faz `break` apos o `yield` da ultima pagina permitida (`page_num == max_pages`) ANTES de tentar clicar no proximo botao: evita navegar para uma URL que pode nao existir no ambiente de teste e causar timeout no `wait_for_selector`
- `QuotesPWSpider` usa BS4 + lxml para parsing do HTML renderizado: mesma stack do `BooksSpider`, sem dependencia extra; o Playwright so e responsavel por renderizar o JS e entregar o HTML final
- `_extract_quotes` isolado de `_extract_one` para permitir teste unitario de `_extract_one` sem browser (tag BS4 construida diretamente em Python); `_extract_quotes` e testada via spider integration test com fixture HTML
- `quotes.toscrape.com/js/` e o mesmo site do Dia 15 — intencional para contrastar: Dia 15 usou a API JSON interna (Strategy 1, sem browser), Dia 16 usa o DOM renderizado (Strategy 2, com Playwright); mesmo dado, custo diferente

## Modulos existentes (atualizado Dia 17)

`scraper/app/browsers/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `playwright_client.py` | 16 | `PlaywrightClient` — context manager headless Chromium, `add_route()` para interceptacao de requests, `fetch_html()`, `iter_pages()` com paginacao por clique |
| `quotes_pw_spider.py` | 16 | `QuotesPWSpider` — scraping via DOM renderizado (Strategy 2), BS4 parsing, isolamento de erro por quote, JSON output |
| `quotes_intercept_spider.py` | 17 | `QuotesInterceptSpider` — captura respostas XHR com `page.expect_response()` (Strategy 3), `page.evaluate()` para ler estado JS, zero HTML parsing |

`scraper/tests/fixtures/` — fixtures de teste atualizadas:

| Arquivo | Usado por |
|---|---|
| `quotes_intercept.html` | `test_quotes_intercept_spider.py` — mini-SPA com `fetch('/api/quotes?page=N')` no DOMContentLoaded e botao Next |

## Decisoes — Dia 17

- `page.expect_response(predicate)` em vez de `page.on("response", handler)`: o context manager garante que o listener e registrado ANTES da acao que dispara o XHR, eliminando o race condition onde a resposta poderia chegar antes do listener; `page.on` e adequado para captura continua de multiplas respostas sem saber quando chegam
- `_is_api_response(response: PlaywrightResponse) -> bool` como funcao nomeada em vez de lambda: mypy --strict exige anotacao explicita de tipo no parametro; funcao nomeada e mais legivel e testavel que lambda anonimo
- `self.page_title = str(page.evaluate("() => document.title"))`: `page.evaluate()` retorna `Any`; o `str()` converte explicitamente para satisfazer mypy --strict sem precisar de `cast`; demonstra acesso a estado JS em runtime invisivel via CSS/XPath
- `cast(dict[str, Any], resp_info.value.json())`: `Response.json()` retorna `Any`; `cast` e necessario para mypy atribuir o tipo correto a `api_data` sem introducir checagem de runtime desnecessaria
- `QuotesInterceptSpider` nao faz HTML parsing: a resposta XHR ja e JSON estruturado; nao ha BS4, lxml nem seletores — se o site mudar o HTML renderizado, o spider nao quebra
- Branch defensivo `next_btn.count() == 0` cobre inconsistencia DOM/API: `has_next=True` na resposta JSON mas botao nao presente no DOM (race condition ou bug do site); testado com fixture HTML sem botao Next mas que ainda dispara o XHR inicial
- Mesmo site `quotes.toscrape.com/js/` usado nos tres dias para comparacao direta das tres estrategias: Strategy 1 (httpx, sem browser) e 10x mais rapida; Strategy 3 (interceptacao) e equivalente em velocidade a Strategy 2 (DOM) mas mais robusta a mudancas de layout

## Modulos existentes (atualizado Dia 18)

`scraper/app/core/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `async_http_client.py` | 18 | `AsyncHTTPClient` — equivalente async do `HTTPClient`: `httpx.AsyncClient`, `asyncio.Semaphore` para concorrencia, `asyncio.sleep` para backoff, `_wait_for_rate_limit` async |

`scraper/app/benchmarks/` — scripts de medicao (omitidos do coverage):

| Arquivo | Dia | O que tem |
|---|---|---|
| `sync_vs_async.py` | 18 | benchmark sequencial vs concorrente: 20 requests x 50ms latencia simulada → ~16x de speedup |

## Decisoes — Dia 18

- `AsyncHTTPClient` adicionado ao lado do `HTTPClient` sincronizado (nao substitui): o sincrono ainda e valido para scripts simples e testes sem event loop; o async e a escolha para spiders em escala
- `asyncio.Semaphore` injetado via construtor (`semaphore: asyncio.Semaphore | None = None`): quem chama controla o nivel de concorrencia; sem semaphore, todas as coroutines correm livres — correto para benchmark, perigoso para producao
- `contextlib.AbstractAsyncContextManager[Any]` como tipo da variavel `lock`: unifica `asyncio.Semaphore` e `contextlib.nullcontext()` sem duplicar o corpo do loop de retry; mypy --strict aceita porque `Any` e compativel com o tipo retornado por `__aenter__` em ambos
- `asyncio.sleep` no lugar de `time.sleep` para backoff: `time.sleep` bloqueia a thread inteira e paralisa o event loop; `asyncio.sleep` suspende so a coroutine e cede o loop para outras tasks
- Rate limit nao e concurrency-safe no `AsyncHTTPClient`: a janela deslizante pode ser violada entre o check e o update (`_last_request_time`) quando multiplas coroutines compartilham o mesmo cliente, pois ha um `await` no meio. Fix: `asyncio.Lock` por dominio — avaliar no Dia 19+ (ver Dividas Tecnicas)
- `*/benchmarks/*` adicionado ao `omit` do coverage: scripts de medicao nao sao codigo de biblioteca e nao precisam ser cobertos por testes automatizados
- Benchmark usa `time.sleep` / `asyncio.sleep` como simulacao de latencia de rede: nao faz requisicoes reais, mas demonstra com clareza o ganho de concorrencia (~16x com 20 requests e 50ms de latencia)

## Dividas Tecnicas (atualizado Dia 18)

- `_wait_for_rate_limit` no `HTTPClient` impoe intervalo minimo entre requests por dominio (nao janela deslizante como o decorator `@rate_limit`): comportamento correto para scraper, mas a diferenca de semantica nao esta documentada no codigo — avaliar unificacao ou comentario no Dia 19+
- `_wait_for_rate_limit` no `AsyncHTTPClient` nao e concurrency-safe: race condition entre check e update de `_last_request_time` em um `await` point — adicionar `asyncio.Lock` por dominio no Dia 19+
- `StorageService.save_items` envolve qualquer excecao como `StorageError`: um `KeyError` por chave ausente no `item.data` geraria mensagem confusa; adicionar validacao de campos antes da sessao de banco no Dia 19+

## Modulos existentes (atualizado Dia 19)

`scraper/app/storage/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `models.py` | 11 | `Base`, `ScrapedBook` |
| `service.py` | 11 | `StorageService` — sync, SQLite/PostgreSQL |
| `async_service.py` | 19 | `AsyncStorageService` — `AsyncSession`, `await session.merge()`, `aiosqlite` para dev |

`scraper/app/spiders/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `books_spider.py` | 10–12 | `BooksSpider` — sync |
| `quotes_spider.py` | 15 | `QuotesSpider` — JSON API |
| `async_books_spider.py` | 19 | `AsyncBooksSpider` — producer-consumer com `asyncio.Queue`, `AsyncHTTPClient`, `AsyncStorageService` opcional |

## Decisoes — Dia 19

- `AsyncStorageService` usa `AsyncSession` com `await session.merge()` e `await session.commit()`: mesmo semantica de upsert do `StorageService` sincrono, mas nao bloqueia o event loop
- `aiosqlite` como driver async para SQLite (dev): URL `sqlite+aiosqlite:///:memory:` nos testes, `sqlite+aiosqlite:///arquivo.db` em dev; producao usara `asyncpg` (Dia 25)
- `await conn.run_sync(Base.metadata.create_all)` em `init_db()`: a criacao de schema e sincrona na SQLAlchemy — `run_sync` executa o callable bloqueante em um executor thread sem paralisar o event loop
- Producer-consumer com `asyncio.Queue`: pagination e inerentemente serial (URL de cada pagina vem da anterior), mas o consumer pode processar/persistir a pagina N enquanto o producer esta aguardando o HTTP da pagina N+1 — a queue e o ponto de desacoplamento
- Sentinel `None` para sinalizar fim da fila: padrao classico e legivel; alternativas (Event, CancelledError) sao mais complexas sem beneficio aqui
- `asyncio.gather(producer(), consumer())` em vez de tarefas separadas: se o producer lancar excecao, o consumer e cancelado automaticamente (comportamento correto); nao e necessario `return_exceptions=True`
- `AsyncStorageService` importado via `TYPE_CHECKING` na spider: mesma decisao do `StorageService` na `BooksSpider` — evita importacao circular em runtime

## Dividas Tecnicas (atualizado Dia 19)

- `_wait_for_rate_limit` no `HTTPClient` impoe intervalo minimo entre requests por dominio (nao janela deslizante): avaliar unificacao no Dia 20+
- `_wait_for_rate_limit` no `AsyncHTTPClient` nao e concurrency-safe: race condition entre check e update de `_last_request_time` — adicionar `asyncio.Lock` por dominio
- `StorageService.save_items` envolve qualquer excecao como `StorageError`: validacao de campos antes da sessao seria mais precisa — avaliar no Dia 20+
- `_save_json` duplicada em `books_spider.py` e `async_books_spider.py`: extrair para `scraper/app/core/utils.py` ou modulo proprio no Dia 21+

## Modulos existentes (atualizado Dia 20)

`scraper/app/browsers/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `playwright_client.py` | 16 | `PlaywrightClient` — sync, headless Chromium, `add_route()`, `fetch_html()`, `iter_pages()` |
| `quotes_pw_spider.py` | 16 | `QuotesPWSpider` — DOM renderizado, BS4, JSON output |
| `quotes_intercept_spider.py` | 17 | `QuotesInterceptSpider` — interceptacao XHR via `page.expect_response()`, zero HTML parsing |
| `async_playwright_client.py` | 20 | `AsyncPlaywrightClient` — async context manager, `BrowserContext` isolado por fetch, `asyncio.Semaphore` para cap de concorrencia, `add_route()` para interceptacao em testes |
| `async_quotes_pw_spider.py` | 20 | `AsyncQuotesPWSpider` — recebe lista de URLs, scraping paralelo com `asyncio.gather`, `Semaphore(max_concurrent)`, JSON output |

`scraper/app/benchmarks/` — scripts de medicao (omitidos do coverage):

| Arquivo | Dia | O que tem |
|---|---|---|
| `sync_vs_async.py` | 18 | benchmark sequencial vs concorrente: 20 requests x 50ms → ~16x speedup |
| `parallel_browsers.py` | 20 | benchmark max_concurrent=1..6 com `asyncio.sleep(200ms)` simulando render JS: speedup quase linear com o numero de contexts paralelos |

## Decisoes — Dia 20

- `AsyncPlaywrightClient` separa o `BrowserContext` (e o `Page`) por chamada de `fetch_html()`: cada request abr e fecha seu proprio contexto — sem vazamento de cookies, sessao ou localStorage entre fetches paralelos
- `asyncio.Semaphore` aceito opcionalmente em `fetch_html(url, semaphore=...)`: quem chama controla o cap de concorrencia, como no `AsyncHTTPClient` do Dia 18; sem semaphore, todos os contexts abrem simultaneamente
- `contextlib.AbstractAsyncContextManager[Any]` reutilizado como tipo de `lock`: mesma decisao do Dia 18 — unifica `asyncio.Semaphore` e `contextlib.nullcontext()` sem duplicar o bloco `async with`
- `AsyncQuotesPWSpider` cria o `Semaphore` internamente com `max_concurrent` e o passa para `fetch_html()`: encapsula a politica de concorrencia na spider sem expor o semaphore para quem instancia
- `asyncio.gather(*[scrape_one(url) for url in urls])`: todas as coroutines sao agendadas de uma vez; o semaphore e que garante que no maximo `max_concurrent` browsers estejam abertos simultaneamente
- `page.route()` registrado por contexto (dentro de `fetch_html`) e por page (dentro de `new_page()`): os dois metodos precisam aplicar as rotas porque sao independentes; testes dos dois caminhos cobrem ambas as listas de rotas
- Benchmark `parallel_browsers.py` usa `asyncio.sleep(0.2)` para simular render JS: resultado: `max_concurrent=1: 1.25s`, `max_concurrent=2: 0.62s`, `max_concurrent=3: 0.42s`, `max_concurrent=6: 0.20s` — speedup quase linear confirma que o semaphore nao introduz overhead significativo

## Dividas Tecnicas (atualizado Dia 20)

- `_wait_for_rate_limit` no `HTTPClient` impoe intervalo minimo entre requests por dominio (nao janela deslizante): avaliar unificacao no Dia 21+
- `_wait_for_rate_limit` no `AsyncHTTPClient` nao e concurrency-safe: race condition entre check e update de `_last_request_time` — adicionar `asyncio.Lock` por dominio
- `StorageService.save_items` envolve qualquer excecao como `StorageError`: validacao de campos antes da sessao seria mais precisa — avaliar no Dia 21+
- `_save_json` duplicada em `books_spider.py`, `async_books_spider.py` e `async_quotes_pw_spider.py`: extrair para `scraper/app/core/utils.py` ou modulo proprio no Dia 21+

## Decisoes — Dia 21

- `--cov-fail-under=90` adicionado ao job `test` no CI: um PR que derruba a cobertura abaixo de 90% falha automaticamente — e a protecao concreta da main; threshold foi 90 (nao 100) para dar margem a entrypoints e codigo de inicializacao do worker que nao sao testáveis como unidade sem overhead desproporcional
- `--cov-report=xml` adicionado junto: gera `coverage.xml` para integracao futura com Codecov ou badge no README (Dia 28+)
- lint e typecheck rodam so em Python 3.12: ruff e agnóstico de versao; mypy usa `python_version = "3.12"` no pyproject.toml — apenas o job `test` precisa da matrix 3.11/3.12 para garantir compatibilidade de runtime
- squash merge na main (confirma e documenta decisao existente): um commit por PR no historico da main; commits intermediarios ficam na branch e no squash message — `git log --oneline` na main conta a historia do produto, nao os passos de desenvolvimento; rebase merge manteria todos os commits mas polui o historico; merge commit cria um commit extra vazio de merge
- `git bisect`: ferramenta para encontrar qual commit introduziu um bug em O(log n) passos — `git bisect start`, `git bisect bad HEAD`, `git bisect good <hash-bom>` e o Git faz checkout automatico para o commit do meio; util quando um teste falha na main mas nao se sabe em qual dos N commits o problema entrou; nao requer configuracao de arquivo

## Dividas Tecnicas (atualizado Dia 21)

- `_wait_for_rate_limit` no `HTTPClient` impoe intervalo minimo entre requests por dominio (nao janela deslizante): avaliar unificacao no Dia 22+
- `_wait_for_rate_limit` no `AsyncHTTPClient` nao e concurrency-safe: race condition entre check e update de `_last_request_time` — adicionar `asyncio.Lock` por dominio
- `StorageService.save_items` envolve qualquer excecao como `StorageError`: validacao de campos antes da sessao seria mais precisa — avaliar no Dia 22+
- `_save_json` duplicada em `books_spider.py`, `async_books_spider.py` e `async_quotes_pw_spider.py`: extrair para `scraper/app/core/utils.py` ou modulo proprio no Dia 22+

## Modulos existentes (atualizado Dia 22)

`scraper/scrapy_project/` — projeto Scrapy (nao segue a estrutura `app/`; Scrapy exige layout proprio):

| Arquivo | O que tem |
|---|---|
| `scrapy.cfg` | aponta para `scraper.scrapy_project.settings`; executar `scrapy crawl books` a partir de `datahunter/` |
| `settings.py` | `USER_AGENT=datahunter/0.1`, `ROBOTSTXT_OBEY=True`, `DOWNLOAD_DELAY=0.5`, `AUTOTHROTTLE_ENABLED=True`, `StoragePipeline` ativo |
| `items.py` | `BookItem` — campos: `title`, `price`, `availability`, `rating` |
| `pipelines.py` | `StoragePipeline` — batch upsert via `StorageService` existente; `DropItem` em campo ausente |
| `spiders/books_spider.py` | `BooksScrapySpider` — paginacao via `response.follow`, `_RATING_MAP` (palavra → numero) |

## Decisoes — Dia 22

- Projeto Scrapy em `scraper/scrapy_project/` (nao dentro de `scraper/app/`): Scrapy exige `scrapy.cfg` + modulo de settings apontado por ele; colocar dentro de `app/` quebraria o layout esperado pelo CLI do Scrapy
- `scrapy.cfg` na raiz de `datahunter/`: o Scrapy procura o `scrapy.cfg` subindo a arvore de diretorios; com ele em `datahunter/`, `scrapy crawl books` funciona sem variavel de ambiente `SCRAPY_SETTINGS_MODULE`
- `StoragePipeline` reutiliza `StorageService` do Dia 11 diretamente: sem duplicar logica de upsert; a pipeline recebe `DATABASE_URL` via `spider.settings.get()` — injetavel nos testes com `sqlite:///:memory:`
- `DropItem` em campo ausente na pipeline: item com campo vazio geraria `KeyError` no `StorageService.save_items()`; melhor falhar cedo com mensagem clara
- `close_spider` faz batch upsert (acumula na lista, persiste no fim): evita uma transacao por item durante o crawl; aceitavel porque `StorageService.save_items()` ja usa `session.merge()` em loop dentro de uma unica transacao
- `*/scrapy_project/settings.py` adicionado ao `omit` do coverage: arquivo de configuracao pura — constantes atribuidas ao modulo; sem logica condicional testavel
- `TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"` em settings: Scrapy 2.7+ exige declaracao explicita do reactor; o `AsyncioSelectorReactor` permite coexistir com `asyncio` caso o projeto use os dois no futuro

## Comparativo — spider manual (Dia 10) vs Scrapy (Dia 22)

| Feature | BooksSpider (httpx) | BooksScrapySpider |
|---|---|---|
| Deduplicacao de URL | `set[str]` manual | `DupeFilter` automatico |
| Rate limiting | `_wait_for_rate_limit` manual | `DOWNLOAD_DELAY` + `AUTOTHROTTLE` |
| Retry | `@retry` decorator | `RetryMiddleware` automatico |
| robots.txt | `RobotsChecker` manual | `ROBOTSTXT_OBEY = True` |
| Output multi-formato | `_save_json()` manual | `-o file.json/csv/xml` built-in |
| Stats de crawl | logs manuais | `scrapy stats` automatico |
| Debug interativo | — | `scrapy shell <url>` |
| Integracao asyncio | nativa | via `AsyncioSelectorReactor` (complexo) |
| Controle fino de headers | total | via middleware |

**Quando NAO usar Scrapy:** APIs JSON simples (overhead do framework nao compensa), projetos asyncio-first onde misturar Twisted e asyncio adiciona complexidade, scraping pontual de um ou dois endpoints.

## Dividas Tecnicas (atualizado Dia 22)

- `_wait_for_rate_limit` no `HTTPClient` impoe intervalo minimo entre requests por dominio (nao janela deslizante): avaliar unificacao no Dia 23+
- `_wait_for_rate_limit` no `AsyncHTTPClient` nao e concurrency-safe: race condition entre check e update de `_last_request_time` — adicionar `asyncio.Lock` por dominio
- `StorageService.save_items` envolve qualquer excecao como `StorageError`: validacao de campos antes da sessao seria mais precisa — avaliar no Dia 23+
- `_save_json` duplicada em `books_spider.py`, `async_books_spider.py` e `async_quotes_pw_spider.py`: extrair para `scraper/app/core/utils.py` no Dia 23+

## Modulos existentes (atualizado Dia 23)

`scraper/scrapy_project/middlewares/` — middlewares customizados:

| Arquivo | O que tem |
|---|---|
| `retry.py` | `ExponentialBackoffRetryMiddleware` — substitui `RetryMiddleware` padrao; wait = `backoff_base * 2^attempt`; testavel via `patch("time.sleep")` |
| `user_agent.py` | `RandomUserAgentMiddleware` — substitui `UserAgentMiddleware` padrao; rotaciona `USER_AGENT_LIST` das settings; fallback para `USER_AGENT` |

`scraper/scrapy_project/spiders/` — spiders Scrapy:

| Arquivo | O que tem |
|---|---|
| `books_spider.py` | `BooksScrapySpider` — Dia 22 |
| `quotes_spider.py` | `QuotesScrapySpider` — usa scrapy-playwright (`meta={"playwright": True}`); `_parse_quote(Any)` isolado como static method |

`scraper/scrapy_project/items.py` — `BookItem` + `QuoteItem` (text, author, tags CSV)

## Decisoes — Dia 23

- `ExponentialBackoffRetryMiddleware` usa `time.sleep` (bloqueia reactor do Twisted): para concorrencia 1 por dominio e volume baixo, o custo e aceitavel; a alternativa correta seria `reactor.callLater` + `Deferred` (Twisted-idiomatic) mas adiciona complexidade desproporcional ao projeto atual
- Prioridade 200 para retry e 150 para user-agent: mesmas slots dos middlewares padrao que substituem — `settings.py` desabilita os originais com `None` antes de registrar os nossos
- `_parse_quote(selector: Any)`: parsel (biblioteca interna do Scrapy) e scrapy.Selector sao o mesmo tipo em runtime mas as stubs mypy enxergam caminho de modulo diferente; `Any` evita o falso positivo sem perder seguranca de tipo no resto do metodo
- `QuotesScrapySpider.parse` e async generator (yield dentro de async def): Scrapy aceita porque o `ScrapyPlaywrightDownloadHandler` chama `async for` na coroutine; `start_requests` e sync generator normal (nao async) — retorna `Iterator[Request]`
- `AsyncMock` cobre os branches `if page:` em `parse`: `page.wait_for_selector` e `page.close` sao chamadas reais do Playwright; testar com `AsyncMock` confirma que sao invocadas sem precisar de browser real
- `DOWNLOAD_HANDLERS` com `ScrapyPlaywrightDownloadHandler` em settings: requests sem `meta={"playwright": True}` passam pelo handler mas nao abrem browser — o handler so inicializa o Playwright na primeira request playwright; nao afeta os testes unitarios que usam `HtmlResponse` diretamente

## Modulos existentes (atualizado Dia 24)

`worker/app/` — Celery worker:

| Arquivo | O que tem |
|---|---|
| `config.py` | `WorkerSettings` (pydantic-settings) — le `DATAHUNTER_REDIS_URL` e `DATAHUNTER_SCRAPING_INTERVAL_SECONDS` do ambiente |
| `main.py` | app Celery com broker/backend Redis; Beat schedule para `scrape_books` e `scrape_quotes` a cada hora |
| `jobs/scraping_jobs.py` | `scrape_books` e `scrape_quotes` — tasks com `autoretry_for=(NetworkError, ConnectionError, TimeoutError)`, `retry_backoff=True`, `max_retries=3` |

`docker-compose.yml` — servicos:

| Servico | Porta | O que faz |
|---|---|---|
| `redis` | 6379 | broker de filas e result backend; healthcheck com `redis-cli ping` |
| `worker` | — | Celery worker, `--concurrency=2`, reinicia em falha |
| `beat` | — | Celery Beat com `PersistentScheduler`; dispara as tasks agendadas |
| `flower` | 5555 | UI de monitoramento de tasks em tempo real |

`Dockerfile` — imagem uv-based para worker e flower

## Decisoes — Dia 24

- `autoretry_for=(NetworkError, ConnectionError, TimeoutError)` nas tasks: as tres excecoes cobrem falhas de rede (nossa excecao customizada) e falhas de transporte (stdlib) — sem retentativa em `ParseError` (bug de parsing nao se resolve sozinho)
- `retry_backoff=True` + `retry_backoff_max=300` + `retry_jitter=True`: backoff exponencial com cap de 5 minutos e jitter para evitar thundering herd quando multiplos workers falham ao mesmo tempo
- `task_always_eager=True` nos testes: executa a task sincronamente sem broker real — evita dependencia de Redis nos testes de CI; `task_eager_propagates=True` propaga excecoes em vez de engoli-las
- `celery.exceptions.Retry` em vez de excecao original em modo eager: quando `autoretry_for` dispara em modo eager, Celery levanta `Retry` (nao a excecao original) — o teste correto e verificar que `Retry` foi levantado, confirmando que o mecanismo de reenvio foi acionado
- `WorkerSettings` com `env_prefix = "DATAHUNTER_"`: prefixo evita colisao com variáveis de ambiente de outras ferramentas no mesmo host; `DATAHUNTER_REDIS_URL=redis://redis:6379/0` no compose
- `beat_schedule` no `app.conf` (nao em arquivo separado): simples para o volume atual; `PersistentScheduler` persiste o ultimo horario de execucao em `celerybeat-schedule` — evita execucao dupla ao reiniciar o servico beat
- Beat como servico separado do worker no compose: padrao recomendado pelo Celery; rodar beat e worker no mesmo processo e deprecated desde Celery 4 e proibido em producao (risco de execucao duplicada)
- Dockerfile com `uv sync --frozen` em dois passos (deps primeiro, codigo depois): maximiza o cache da layer do Docker — mudancas no codigo do projeto nao invalidam a layer de instalacao de dependencias

## Dividas Tecnicas (atualizado Dia 24)

- `ExponentialBackoffRetryMiddleware._retry` usa `time.sleep`: bloqueia o reactor em crawls com alta concorrencia; fix correto usa `reactor.callLater` + Deferred — avaliar se escala for necessaria
- `_wait_for_rate_limit` no `HTTPClient` impoe intervalo minimo (nao janela deslizante): avaliar unificacao no Dia 25+
- `_wait_for_rate_limit` no `AsyncHTTPClient` nao e concurrency-safe: race condition — adicionar `asyncio.Lock` por dominio
- `_save_json` duplicada em `books_spider.py`, `async_books_spider.py` e `async_quotes_pw_spider.py`: extrair para `scraper/app/core/utils.py` no Dia 25+
- `worker/app/jobs/scraping_jobs.py` nao persiste resultados no banco: retorna apenas um resumo `dict`; para persistir, injetar `StorageService` ou `AsyncStorageService` na task — avaliar no Dia 25+ junto com PostgreSQL

## Modulos existentes (atualizado Dia 25)

`docker-compose.yml` — stack completo:

| Servico | Porta | O que faz |
|---|---|---|
| `postgres` | 5432 | PostgreSQL 16-alpine; volume `postgres_data`; healthcheck `pg_isready` |
| `redis` | 6379 | broker de filas e result backend; healthcheck `redis-cli ping` |
| `worker` | — | Celery worker, `--concurrency=2`; depende de redis + postgres (ambos healthy) |
| `beat` | — | Celery Beat com `PersistentScheduler`; depende de redis |
| `flower` | 5555 | UI de monitoramento; depende de redis |

`docker-compose.override.yml` — sobreposicoes de dev:
- volume `.:/app` em todos os servicos de build: editar codigo sem rebuild
- Celery em `--pool=solo --concurrency=1 --loglevel=debug`

`Dockerfile` — multi-stage (builder + runtime):
- **builder**: copia `pyproject.toml` + `uv.lock`, instala deps (`--no-dev`) com `UV_COMPILE_BYTECODE=1`; depois copia codigo e instala pacote local
- **runtime**: copia apenas `.venv` + codigo do builder; sem uv, sem pip, sem caches — imagem menor e mais segura

`.env.example` — documenta `POSTGRES_*`, `DATAHUNTER_*`, `LOG_LEVEL`

## Decisoes — Dia 25

- Dockerfile multi-stage: a layer de instalacao de deps (builder) e separada da layer de codigo — uma mudanca de arquivo Python nao invalida o cache de `uv sync`; o runtime so tem o necessario para executar
- `UV_COMPILE_BYTECODE=1` no builder: pre-compila `.pyc` em tempo de build; o runtime nao precisa escrever `.pyc` em disco → `PYTHONDONTWRITEBYTECODE=1` no runtime e consistente com isso
- `UV_LINK_MODE=copy`: hard-links nao funcionam entre layers do Docker (sistemas de arquivo diferentes); `copy` garante que o `.venv` no builder seja auto-contido e copiavel para o runtime
- `target: runtime` no `docker-compose.yml`: instrui o `docker compose build` a parar no stage runtime (nao precisamos do builder em producao)
- `depends_on: condition: service_healthy` para postgres: o worker nao sobe ate o postgres estar pronto para aceitar conexoes — evita o erro `FATAL: the database system is starting up` no primeiro `save_items`
- `pg_isready` como healthcheck do postgres: built-in no proprio container PostgreSQL; mais confiavel que `nc -z` ou `curl` porque testa o protocolo de conexao real
- `docker-compose.override.yml` carregado automaticamente: Docker Compose mescla `docker-compose.yml` + `override` sem flags extras em dev; em producao, usar `docker compose -f docker-compose.yml up` explicitamente
- `_make_storage(database_url)` como funcao auxiliar: isolada e testavel com mock de `create_engine` e `StorageService` sem tocar no banco real; a task chama `_make_storage(db_url or settings.database_url)` — sem duplicacao de logica

## Dividas Tecnicas (atualizado Dia 25)

- `ExponentialBackoffRetryMiddleware._retry` usa `time.sleep`: bloqueia o reactor em crawls com alta concorrencia — avaliar se escala for necessaria
- `_wait_for_rate_limit` no `HTTPClient` impoe intervalo minimo (nao janela deslizante): avaliar unificacao no Dia 26+
- `_wait_for_rate_limit` no `AsyncHTTPClient` nao e concurrency-safe: race condition — adicionar `asyncio.Lock` por dominio
- `_save_json` duplicada em `books_spider.py`, `async_books_spider.py` e `async_quotes_pw_spider.py`: extrair para `scraper/app/core/utils.py` no Dia 26+
- `scrape_quotes` nao persiste: aguardando modelo `ScrapedQuote` (Dia 27+)

## Modulos existentes (atualizado Dia 26)

`scraper/app/core/` — todos com mypy --strict passando:

| Arquivo | Dia | O que tem |
|---|---|---|
| `logging.py` | 26 | `configure_logging()` — structlog JSON via bridge stdlib; `get_logger()` — BoundLogger tipado; `job_context()` — context manager que associa `job_id` a todos os logs do bloco via contextvars |
| `metrics.py` | 26 | `METRICS_REGISTRY` (CollectorRegistry isolado), `pages_scraped_total` (Counter), `scraping_errors_total` (Counter com label `error_type`), `scraping_duration_seconds` (Histogram) |

`worker/app/` — sinais Celery e observabilidade:

| Arquivo | Dia | O que tem |
|---|---|---|
| `signals.py` | 26 | `on_worker_process_init` → `configure_logging()`; `on_worker_ready` → `start_http_server(metrics_port)`; `on_task_failure` → POST webhook se `DATAHUNTER_WEBHOOK_URL` configurada |

Infraestrutura adicionada ao compose:

| Serviço | Porta | O que faz |
|---|---|---|
| `prometheus` | 9090 | Coleta métricas do worker em `worker:8001/metrics` a cada 15s |
| `grafana` | 3000 | Visualização; datasource Prometheus provisionado automaticamente via `grafana/datasources/` |

## Decisoes — Dia 26

- `structlog` com bridge para stdlib (`ProcessorFormatter`): todos os 20+ módulos existentes que usam `logging.getLogger(__name__)` passam a emitir JSON automaticamente — sem tocar em nenhum arquivo de produção existente; o bridge é registrado uma vez no `configure_logging()`
- `configure_logging()` chamada no sinal `worker_process_init` (não no import de `main.py`): `main.py` é importado em testes (`from worker.app.main import app`); se configurasse o logging no nível de import, pytest perderia controle sobre captura de logs e cada test run adicionaria um handler ao root logger
- `on_worker_ready` sobe o servidor de métricas Prometheus: o sinal só dispara quando o worker está pronto para aceitar tasks — garante que o processo está estável antes de abrir a porta HTTP; `worker_process_init` dispara antes (por processo, não por worker)
- `METRICS_REGISTRY` isolado do `REGISTRY` global do prometheus_client: o REGISTRY global acumula métricas permanentemente entre imports; em testes onde o módulo é importado uma única vez (cache Python), o registry global causaria `Duplicated timeseries` se `Counter(...)` fosse chamado mais de uma vez (ex.: múltiplos runs de pytest no mesmo processo)
- `on_task_failure` usa `task_failure` do Celery (não `task_retry`): `task_failure` só dispara quando a task esgota todas as retentativas e falha definitivamente — é o momento certo para alertar; `task_retry` dispararia em cada tentativa intermediária, causando ruído
- `job_id = self.request.id or "eager"`: em modo `task_always_eager=True` (testes), Celery ainda atribui um ID; o fallback `"eager"` é apenas uma garantia defensiva para modo muito bare-bones
- `structlog.contextvars.clear_contextvars()` no `finally` de cada task: garante que o contexto `job_id` não vaze para a próxima task executada no mesmo processo (Celery reutiliza processos)
- Grafana com provisioning via `grafana/datasources/prometheus.yml`: datasource Prometheus configurado automaticamente na primeira subida — zero cliques manuais no UI; `isDefault: true` o torna datasource padrão em novos painéis

## Dividas Tecnicas (atualizado Dia 26)

- `ExponentialBackoffRetryMiddleware._retry` usa `time.sleep`: bloqueia o reactor — avaliar se escala for necessaria
- `_wait_for_rate_limit` no `HTTPClient` impoe intervalo minimo (nao janela deslizante): avaliar unificacao no Dia 27+
- `_wait_for_rate_limit` no `AsyncHTTPClient` nao e concurrency-safe: race condition — adicionar `asyncio.Lock` por dominio
- `_save_json` duplicada em `books_spider.py`, `async_books_spider.py` e `async_quotes_pw_spider.py`: extrair para `scraper/app/core/utils.py` no Dia 27+
- `scrape_quotes` nao persiste: aguardando modelo `ScrapedQuote` (Dia 27+)
- Grafana sem dashboard provisionado: apenas datasource configurado — painéis de `pages_scraped_total`, `scraping_errors_total` e `scraping_duration_seconds` podem ser criados manualmente ou provisionados via `grafana/dashboards/` (Dia 29+)

## Proximo passo — Dia 27
