#!/usr/bin/env python3
"""Testa nova chave do OpenRouter."""
import httpx
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL

print("=" * 80)
print("🔑 TESTE DA NOVA CHAVE OPENROUTER")
print("=" * 80)

print(f"\nChave: {OPENROUTER_API_KEY[:20]}...{OPENROUTER_API_KEY[-10:]}")
print(f"Tamanho: {len(OPENROUTER_API_KEY)} caracteres")

url = f"{OPENROUTER_BASE_URL}/chat/completions"
headers = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://busca-eventos-rio.com",
    "X-Title": "Busca Eventos Rio"
}

# Tentar modelo gratuito primeiro
payload = {
    "model": "meta-llama/llama-3.2-3b-instruct:free",
    "messages": [
        {"role": "user", "content": "Responda apenas: OK"}
    ],
    "max_tokens": 10
}

print(f"\n🧪 Testando modelo gratuito: {payload['model']}")

try:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, json=payload, headers=headers)

        print(f"\n📊 Status Code: {response.status_code}")

        if response.status_code == 200:
            print("✅ SUCESSO! Chave funcionando!")
            data = response.json()
            if 'choices' in data:
                content = data['choices'][0]['message']['content']
                print(f"Resposta do modelo: {content}")
        else:
            print(f"❌ Erro: {response.status_code}")
            print(f"Body: {response.text}")

except Exception as e:
    print(f"❌ Exceção: {e}")

print("\n" + "=" * 80)
