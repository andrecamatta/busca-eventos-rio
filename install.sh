#!/bin/bash
# Script de instalação rápida para Busca Eventos Rio

set -e

echo "🎭 Instalando Busca Eventos Rio..."
echo ""

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 não encontrado. Instale Python 3.11+ primeiro."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python $PYTHON_VERSION encontrado"

# Verificar/Instalar uv
if ! command -v uv &> /dev/null; then
    echo "📦 Instalando uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

echo "✓ uv instalado"

# Instalar dependências
echo "📦 Instalando dependências..."
uv pip install -r <(grep -E "^[a-zA-Z]" pyproject.toml | sed 's/,$//')

# Criar .env se não existir
if [ ! -f .env ]; then
    echo "📝 Criando arquivo .env..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANTE: Edite o arquivo .env e adicione sua OPENROUTER_API_KEY"
    echo "   Obtenha sua chave em: https://openrouter.ai/keys"
fi

# Criar diretório output
mkdir -p output

echo ""
echo "✅ Instalação concluída!"
echo ""
echo "Próximos passos:"
echo "1. Edite .env e adicione sua OPENROUTER_API_KEY"
echo "2. Execute: python main.py"
echo ""
