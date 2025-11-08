#!/usr/bin/env python3
"""
Teste do filtro temporal na API da web app.
"""
from datetime import datetime, timedelta
import json

# Criar dados de teste com eventos de hoje em diferentes horários
now = datetime.now()
today_str = now.strftime("%d/%m/%Y")
tomorrow_str = (now + timedelta(days=1)).strftime("%d/%m/%Y")

# Horários para teste
hora_passada = (now - timedelta(hours=2)).strftime("%H:%M")
hora_proxima = (now + timedelta(hours=1)).strftime("%H:%M")  # < 3h - deve ser filtrado
hora_valida = (now + timedelta(hours=4)).strftime("%H:%M")  # > 3h - deve aparecer

test_events = {
    "verified_events": [
        {
            "titulo": "Evento PASSADO (deve ser filtrado)",
            "data": today_str,
            "horario": hora_passada,
            "categoria": "Teatro",
            "local": "Teatro Municipal",
            "link_ingresso": "https://example.com/1"
        },
        {
            "titulo": "Evento MUITO PRÓXIMO (deve ser filtrado)",
            "data": today_str,
            "horario": hora_proxima,
            "categoria": "Jazz",
            "local": "Blue Note",
            "link_ingresso": "https://example.com/2"
        },
        {
            "titulo": "Evento VÁLIDO +4h (deve aparecer)",
            "data": today_str,
            "horario": hora_valida,
            "categoria": "Música Clássica",
            "local": "Sala Cecília Meireles",
            "link_ingresso": "https://example.com/3"
        },
        {
            "titulo": "Evento AMANHÃ (deve aparecer)",
            "data": tomorrow_str,
            "horario": "14:00",
            "categoria": "Teatro",
            "local": "Teatro Riachuelo",
            "link_ingresso": "https://example.com/4"
        },
    ]
}

# Salvar arquivo de teste
import os
os.makedirs("output/test_temporal", exist_ok=True)

with open("output/test_temporal/verified_events.json", "w", encoding="utf-8") as f:
    json.dump(test_events, f, ensure_ascii=False, indent=2)

# Criar symlink para latest
if os.path.exists("output/latest"):
    os.remove("output/latest")
os.symlink("test_temporal", "output/latest")

print("=" * 80)
print("DADOS DE TESTE CRIADOS")
print("=" * 80)
print(f"\nHorário atual: {now.strftime('%H:%M')}")
print(f"Data hoje: {today_str}")
print()
print("Eventos criados:")
print(f"  1. Evento PASSADO ({hora_passada}) - DEVE SER FILTRADO")
print(f"  2. Evento MUITO PRÓXIMO ({hora_proxima}) - DEVE SER FILTRADO")
print(f"  3. Evento VÁLIDO ({hora_valida}) - DEVE APARECER")
print(f"  4. Evento AMANHÃ (14:00) - DEVE APARECER")
print()
print("=" * 80)
print("Teste:")
print("1. Inicie a web app: uv run uvicorn web.app:app --reload")
print("2. Acesse: http://localhost:8000/api/events")
print("3. Deve mostrar APENAS 2 eventos (válido +4h e amanhã)")
print("=" * 80)
