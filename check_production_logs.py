#!/usr/bin/env python3
"""
Script para consultar logs e estatísticas do ambiente de produção.

Uso:
    python check_production_logs.py
"""

import requests
import json
from typing import Optional


PRODUCTION_URL = "https://busca-eventos-rio-production.up.railway.app"


def get_stats():
    """Obtém estatísticas dos eventos em produção."""
    print("📊 Obtendo estatísticas de produção...\n")

    try:
        response = requests.get(f"{PRODUCTION_URL}/api/stats", timeout=10)
        response.raise_for_status()

        data = response.json()

        print(f"✅ Total de eventos: {data['total_eventos']}")
        print(f"\n📈 Por Categoria:")
        for cat, count in sorted(data['por_categoria'].items(), key=lambda x: x[1], reverse=True):
            print(f"   • {cat}: {count} eventos")

        print(f"\n🏛️  Por Venue (top 10):")
        top_venues = sorted(data['por_venue'].items(), key=lambda x: x[1], reverse=True)[:10]
        for venue, count in top_venues:
            print(f"   • {venue}: {count} eventos")

        # Análise de meta mínima
        print(f"\n⚠️  Análise de Meta Mínima:")

        jazz_count = data['por_categoria'].get('Jazz', 0)
        musica_classica_count = data['por_categoria'].get('Música Clássica', 0)

        print(f"   • Jazz: {jazz_count}/4 eventos (meta: 4) {'✅' if jazz_count >= 4 else '❌'}")
        print(f"   • Música Clássica: {musica_classica_count}/2 eventos (meta: 2) {'✅' if musica_classica_count >= 2 else '❌'}")

        return data

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print("❌ Acesso negado (403). A API pode requerer autenticação.")
            print("💡 Alternativa: Acesse o Railway dashboard e veja os logs por lá:")
            print("   https://railway.app/project/<seu-projeto>/deployments")
        else:
            print(f"❌ Erro HTTP {e.response.status_code}: {e}")
    except Exception as e:
        print(f"❌ Erro ao consultar API: {e}")
        return None


def get_logs(lines: int = 100, search: Optional[str] = None, level: Optional[str] = None):
    """Obtém logs de produção."""
    print(f"\n📋 Obtendo últimas {lines} linhas de log...\n")

    params = {"lines": lines, "reverse": True}
    if search:
        params["search"] = search
    if level:
        params["level"] = level

    try:
        response = requests.get(
            f"{PRODUCTION_URL}/api/logs",
            params=params,
            timeout=15
        )
        response.raise_for_status()

        data = response.json()
        logs = data.get("logs", [])

        print(f"✅ {data['returned_lines']} linhas retornadas (de {data['total_lines']} totais)")
        print(f"   Tamanho do arquivo: {data['file_size_mb']}MB\n")

        # Mostrar logs
        for log in logs[:50]:  # Primeiras 50 linhas
            level_emoji = {
                "INFO": "ℹ️",
                "ERROR": "❌",
                "WARNING": "⚠️",
                "DEBUG": "🐛"
            }.get(log["level"], "📝")

            print(f"{level_emoji} [{log['timestamp']}] {log['level']}: {log['message'][:120]}")

        if len(logs) > 50:
            print(f"\n... ({len(logs) - 50} linhas omitidas)\n")

        return logs

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print("❌ Acesso negado (403). A API pode requerer autenticação.")
        else:
            print(f"❌ Erro HTTP {e.response.status_code}: {e}")
    except Exception as e:
        print(f"❌ Erro ao consultar logs: {e}")
        return None


def analyze_search_results(logs: list):
    """Analisa logs para identificar resultados de busca por categoria/venue."""
    print("\n🔍 Analisando resultados de busca nos logs...\n")

    search_patterns = [
        "eventos validados",
        "eventos parsed",
        "eventos encontrados",
        "Busca concluída",
        "eventos verificados"
    ]

    relevant_logs = []
    for log in logs:
        msg = log.get("message", "")
        if any(pattern in msg.lower() for pattern in search_patterns):
            relevant_logs.append(log)

    if relevant_logs:
        print("📊 Linhas relevantes sobre busca:")
        for log in relevant_logs[:20]:
            print(f"   • [{log['timestamp']}] {log['message'][:100]}")
    else:
        print("⚠️  Nenhuma linha relevante encontrada sobre resultados de busca")

    return relevant_logs


def check_judge_results():
    """Verifica resultados do julgamento de qualidade."""
    print("\n⚖️  Verificando julgamento de qualidade...\n")

    try:
        response = requests.get(f"{PRODUCTION_URL}/api/judge/results", timeout=10)
        response.raise_for_status()

        data = response.json()
        events = data.get("events", [])
        stats = data.get("stats", {})

        print(f"✅ {stats['total']} eventos julgados")
        print(f"   Nota média: {stats['average_score']}/10")
        print(f"   Nota mínima: {stats['min_score']}/10")
        print(f"   Nota máxima: {stats['max_score']}/10")

        # Top 5 piores eventos
        sorted_events = sorted(events, key=lambda e: e.get('quality_score', 0))
        print(f"\n⚠️  Top 5 eventos com menor qualidade:")
        for i, event in enumerate(sorted_events[:5], 1):
            score = event.get('quality_score', 0)
            categoria = event.get('categoria', 'N/A')
            venue = event.get('venue', 'N/A')
            print(f"   {i}. {event.get('titulo', 'Sem título')} ({score}/10)")
            print(f"      Categoria: {categoria} | Venue: {venue}")
            print(f"      Notas: {event.get('quality_notes', 'N/A')[:80]}...")

        return data

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print("⚠️  Nenhum julgamento disponível ainda")
        elif e.response.status_code == 403:
            print("❌ Acesso negado (403)")
        else:
            print(f"❌ Erro HTTP {e.response.status_code}")
    except Exception as e:
        print(f"❌ Erro: {e}")
        return None


def main():
    print("=" * 80)
    print("🔍 ANÁLISE DE LOGS DE PRODUÇÃO - Busca Eventos Rio")
    print("=" * 80)
    print(f"\n🌐 Ambiente: {PRODUCTION_URL}\n")

    # 1. Estatísticas gerais
    stats = get_stats()

    # 2. Logs recentes (focando em eventos)
    logs = get_logs(lines=200, search="eventos")

    # 3. Analisar resultados de busca
    if logs:
        analyze_search_results(logs)

    # 4. Verificar julgamento de qualidade
    check_judge_results()

    print("\n" + "=" * 80)
    print("✅ Análise concluída!")
    print("=" * 80)
    print("\n💡 Dicas:")
    print("   - Se receber 403, configure autenticação ou use Railway CLI")
    print("   - Consulte ANALISE_PROMPTS_PRODUCAO.md para análise detalhada dos prompts")
    print("   - Para logs completos: railway logs (requer Railway CLI)")
    print("\n")


if __name__ == "__main__":
    main()
