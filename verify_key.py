#!/usr/bin/env python3
"""Verifica se a chave está sendo carregada corretamente."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
env_path = BASE_DIR / ".env"

print("=" * 80)
print("🔍 VERIFICAÇÃO DA CHAVE")
print("=" * 80)

# Carregar .env
load_dotenv(dotenv_path=env_path, override=True)

# Pegar a chave
key_from_env = os.getenv("OPENROUTER_API_KEY")

print(f"\n📁 Arquivo .env: {env_path}")
print(f"📄 Existe: {env_path.exists()}")

if key_from_env:
    print(f"\n✅ Chave carregada do .env:")
    print(f"   Tamanho: {len(key_from_env)} caracteres")
    print(f"   Primeiro caractere: '{key_from_env[0]}'")
    print(f"   Primeiros 20: {key_from_env[:20]}")
    print(f"   Últimos 10: {key_from_env[-10:]}")
    print(f"\n   Chave completa: {key_from_env}")

    # Verificar espaços ou caracteres invisíveis
    if key_from_env != key_from_env.strip():
        print(f"\n⚠️  AVISO: Chave contém espaços no início ou fim!")

    # Verificar quebras de linha
    if '\n' in key_from_env or '\r' in key_from_env:
        print(f"\n⚠️  AVISO: Chave contém quebras de linha!")
else:
    print("\n❌ Chave NÃO encontrada no .env")

# Agora testar o que o config.py carrega
print("\n" + "-" * 80)
print("📦 Testando import do config.py:")
print("-" * 80)

from config import OPENROUTER_API_KEY

print(f"\n✅ Chave do config.py:")
print(f"   Tamanho: {len(OPENROUTER_API_KEY)} caracteres")
print(f"   Chave completa: {OPENROUTER_API_KEY}")

if key_from_env == OPENROUTER_API_KEY:
    print("\n✅ Chaves são IDÊNTICAS (config.py == .env)")
else:
    print("\n❌ Chaves são DIFERENTES!")
    print(f"   .env:      {key_from_env}")
    print(f"   config.py: {OPENROUTER_API_KEY}")

print("\n" + "=" * 80)
