#!/usr/bin/env python3
"""
Analisa eventos de produção para identificar problemas de classificação.
"""

import requests
import json
from collections import defaultdict

PRODUCTION_URL = "https://busca-eventos-rio-production.up.railway.app"


def analyze_events():
    """Analisa eventos detalhados de produção."""
    print("=" * 80)
    print("🔍 ANÁLISE DETALHADA DE EVENTOS DE PRODUÇÃO")
    print("=" * 80)

    try:
        # Obter todos os eventos
        response = requests.get(f"{PRODUCTION_URL}/api/events", timeout=10)
        response.raise_for_status()

        events = response.json()

        print(f"\n✅ {len(events)} eventos carregados\n")

        # Agrupar por categoria
        by_category = defaultdict(list)
        for event in events:
            cat = event.get("extendedProps", {}).get("categoria", "Desconhecida")
            by_category[cat].append(event)

        # Mostrar distribuição
        print("📊 DISTRIBUIÇÃO POR CATEGORIA:")
        for cat in sorted(by_category.keys(), key=lambda x: len(by_category[x]), reverse=True):
            count = len(by_category[cat])
            print(f"   • {cat}: {count} eventos")

        # Analisar eventos "Geral"
        print("\n" + "=" * 80)
        print("🔍 ANÁLISE DE EVENTOS CLASSIFICADOS COMO 'GERAL'")
        print("=" * 80)

        geral_events = by_category.get("Geral", [])

        if not geral_events:
            print("\n✅ Nenhum evento classificado como 'Geral'")
        else:
            print(f"\n⚠️  {len(geral_events)} eventos em 'Geral' - detalhes:\n")

            for i, event in enumerate(geral_events, 1):
                props = event.get("extendedProps", {})
                print(f"{i}. {event.get('title', 'Sem título')}")
                print(f"   📍 Local: {props.get('local', 'N/A')[:80]}")
                print(f"   📅 Data: {event.get('start', 'N/A')[:10]}")

                desc = props.get('descricao', '')
                if desc:
                    print(f"   📝 Descrição: {desc[:100]}...")

                venue = props.get('venue', '')
                if venue:
                    print(f"   🏛️  Venue: {venue}")

                print()

        # Analisar venues
        print("=" * 80)
        print("🏛️  ANÁLISE DE VENUES")
        print("=" * 80)

        by_venue = defaultdict(list)
        no_venue = []

        for event in events:
            venue = event.get("extendedProps", {}).get("venue", "")
            if venue:
                by_venue[venue].append(event)
            else:
                no_venue.append(event)

        print(f"\n✅ Eventos COM venue: {len(events) - len(no_venue)}")
        print(f"⚠️  Eventos SEM venue: {len(no_venue)}")

        if by_venue:
            print(f"\n📊 Top 10 Venues:")
            top_venues = sorted(by_venue.items(), key=lambda x: len(x[1]), reverse=True)[:10]
            for venue, venue_events in top_venues:
                print(f"   • {venue}: {len(venue_events)} eventos")

        if no_venue:
            print(f"\n⚠️  Eventos sem venue (primeiros 10):")
            for event in no_venue[:10]:
                props = event.get("extendedProps", {})
                print(f"   • {event.get('title', 'Sem título')}")
                print(f"     Local: {props.get('local', 'N/A')[:60]}")

        # Analisar categorias ausentes
        print("\n" + "=" * 80)
        print("❌ CATEGORIAS ESPERADAS MAS AUSENTES")
        print("=" * 80)

        expected = [
            "Jazz", "Música Clássica", "Teatro", "Comédia",
            "Cinema", "Feira Gastronômica", "Feira de Artesanato",
            "Outdoor/Parques", "Cursos de Café"
        ]

        missing = [cat for cat in expected if cat not in by_category or len(by_category[cat]) == 0]

        if missing:
            print("\nCategorias com 0 eventos:")
            for cat in missing:
                print(f"   ❌ {cat}")

                # Sugestões baseadas na categoria
                if cat == "Comédia":
                    print("      💡 Possível causa: Filtros LGBTQIA+ muito restritivos")
                elif cat == "Outdoor/Parques":
                    print("      💡 Possível causa: Filtros de exclusão (samba/pagode) muito agressivos")
                elif cat == "Cursos de Café":
                    print("      💡 Possível causa: Artemis sem eventos agendados no período")
                elif cat == "Feira Gastronômica":
                    print("      💡 Possível causa: Poucos eventos no período ou busca ineficaz")
        else:
            print("\n✅ Todas as categorias esperadas têm eventos!")

        # Resumo
        print("\n" + "=" * 80)
        print("📊 RESUMO DA ANÁLISE")
        print("=" * 80)

        print(f"\n✅ Total de eventos: {len(events)}")
        print(f"📂 Categorias únicas: {len(by_category)}")
        print(f"🏛️  Venues únicos: {len(by_venue)}")
        print(f"⚠️  Eventos 'Geral': {len(geral_events)} ({len(geral_events)/len(events)*100:.1f}%)")
        print(f"⚠️  Eventos sem venue: {len(no_venue)} ({len(no_venue)/len(events)*100:.1f}%)")
        print(f"❌ Categorias ausentes: {len(missing)}")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    analyze_events()
