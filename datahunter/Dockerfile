FROM python:3.12-slim

WORKDIR /app

# instala uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# copia manifesto de dependencias primeiro (cache layer)
COPY pyproject.toml uv.lock ./

# instala dependencias (sem o pacote local ainda)
RUN uv sync --frozen --no-install-project

# copia o restante do codigo
COPY . .

# instala o pacote local
RUN uv sync --frozen
