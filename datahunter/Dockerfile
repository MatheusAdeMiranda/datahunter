# =============================================================================
# Stage 1 — builder
# Instala todas as dependencias Python no .venv.
# Essa layer so eh refeita quando pyproject.toml ou uv.lock mudam.
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# uv: gerenciador de pacotes — copiado do container oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# UV_COMPILE_BYTECODE: pre-compila .pyc em tempo de build → startup mais rapido
# UV_LINK_MODE=copy: copia arquivos em vez de hard-links (necessario em containers)
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copia so o manifesto de dependencias para maximizar cache de layer:
# mudancas no codigo-fonte nao invalidam a instalacao de deps
COPY pyproject.toml uv.lock ./

# Instala dependencias de producao (sem dev: pytest, ruff, mypy)
# --no-install-project: instala apenas as deps declaradas, nao o pacote local ainda
RUN uv sync --frozen --no-install-project --no-dev

# Copia o codigo-fonte e instala o pacote local
COPY . .
RUN uv sync --frozen --no-dev

# =============================================================================
# Stage 2 — runtime
# Imagem final enxuta: sem uv, sem caches de pip, sem ferramentas de dev.
# So o Python, o .venv com as deps instaladas, e o codigo da aplicacao.
# =============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Variaveis de ambiente para Python e venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copia o .venv pre-instalado do builder (ja tem os .pyc compilados)
COPY --from=builder /app/.venv /app/.venv

# Copia o codigo da aplicacao
COPY --from=builder /app /app
