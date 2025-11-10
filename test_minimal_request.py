#!/usr/bin/env python3
"""Testa com headers mínimos."""
import httpx
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL

print("=" * 80)
print("🔑 TESTE COM HEADERS MÍNIMOS")
print("=" * 80)

url = f"{OPENROUTER_BASE_URL}/chat/completions"

# Apenas headers obrigatórios
headers = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "model": "meta-llama/llama-3.2-3b-instruct:free",
    "messages": [
        {"role": "user", "content": "Say OK"}
    ]
}

print(f"\n🧪 Testando sem headers opcionais...")

try:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, json=payload, headers=headers)

        print(f"\n📊 Status Code: {response.status_code}")

        if response.status_code == 200:
            print("✅ SUCESSO!")
            data = response.json()
            print(f"Resposta: {data}")
        else:
            print(f"❌ Erro: {response.status_code}")
            print(f"Body: {response.text}")

except Exception as e:
    print(f"❌ Exceção: {e}")

print("\n" + "=" * 80)
