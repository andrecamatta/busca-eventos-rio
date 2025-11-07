# ==============================================================================
# STAGE 1: Builder - Instala dependências com uv
# ==============================================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS builder

WORKDIR /app

# Copiar apenas arquivos de dependências primeiro (cache layer)
COPY pyproject.toml uv.lock ./

# Criar virtual environment e instalar dependências
# uv cria automaticamente em .venv
RUN uv sync --no-dev

# Copiar código da aplicação
COPY . .

# ==============================================================================
# STAGE 2: Runtime - Imagem final mínima com Playwright
# ==============================================================================
FROM python:3.12-slim-bookworm

# Instalar dependências do sistema necessárias para Playwright
RUN apt-get update && apt-get install -y \
    # Playwright browser dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libxshmfence1 \
    # Para subprocess e git (se necessário)
    git \
    && rm -rf /var/lib/apt/lists/*

# Configurar virtual environment no PATH (uv cria em .venv por padrão)
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# Copiar virtual environment e código do builder
COPY --from=builder /app /app

# Instalar browsers do Playwright (chromium suficiente para maioria dos casos)
RUN /app/.venv/bin/playwright install chromium --with-deps

# Criar diretórios necessários
RUN mkdir -p /app/output/latest

# Railway define PORT dinamicamente, mas definimos default para testes locais
ENV PORT=8000

# Health check para Railway
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:$PORT/health')" || exit 1

# Expor porta (informativo, Railway usa $PORT)
EXPOSE $PORT

# Comando final: uvicorn com timeout adequado para Railway
CMD uvicorn web.app:app --host 0.0.0.0 --port $PORT --timeout-keep-alive 65
