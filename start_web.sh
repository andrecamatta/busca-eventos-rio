#!/bin/bash
# Script para iniciar a aplicação web localmente

echo "🚀 Iniciando Eventos Culturais Rio..."

# Sincronizar dependências
echo "📦 Sincronizando dependências..."
uv sync

# Iniciar servidor
echo "🌐 Iniciando servidor web em http://localhost:8000"
uv run uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload
