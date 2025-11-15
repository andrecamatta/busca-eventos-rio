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
# STAGE 2: Runtime - Imagem final mínima
# ==============================================================================
FROM python:3.12-slim-bookworm

# Configurar virtual environment no PATH (uv cria em .venv por padrão)
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# Copiar virtual environment e código do builder
COPY --from=builder /app /app

# Criar diretório base de output (latest será symlink criado por EventFileManager)
RUN mkdir -p /app/output

# Railway define PORT dinamicamente, mas definimos default para testes locais
ENV PORT=8000

# Health check para Railway
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:$PORT/health')" || exit 1

# Expor porta (informativo, Railway usa $PORT)
EXPOSE $PORT

# Comando final: uvicorn com timeout adequado para Railway
# Usar sh -c para garantir expansão correta de $PORT
CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 65"]
