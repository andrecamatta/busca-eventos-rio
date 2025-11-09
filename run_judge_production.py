#!/usr/bin/env python3
"""Executa julgamento de qualidade nos eventos reais do output/latest."""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from agents.judge_agent import QualityJudgeAgent
from utils.file_manager import EventFileManager

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Executa julgamento completo dos eventos reais."""
    print("\n" + "=" * 80)
    print("🚀 JULGAMENTO DE QUALIDADE - EVENTOS REAIS (OTIMIZADO)")
    print("=" * 80)

    # Carregar eventos diretamente do arquivo
    verified_file = Path("output/latest/verified_events.json")

    if not verified_file.exists():
        print(f"\n❌ ERRO: Arquivo {verified_file} não encontrado")
        print("Execute 'python main.py' primeiro para gerar eventos.")
        return

    try:
        with open(verified_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Extrair eventos do dicionário (se necessário)
        if isinstance(data, dict) and 'verified_events' in data:
            events = data['verified_events']
        elif isinstance(data, list):
            events = data
        else:
            print(f"\n❌ ERRO: Formato de dados inválido no JSON")
            return

    except Exception as e:
        print(f"\n❌ ERRO ao carregar eventos: {e}")
        return

    if not events:
        print("\n⚠️ Nenhum evento encontrado em output/latest/verified_events.json")
        return

    print(f"\n📊 {len(events)} eventos carregados de output/latest/verified_events.json")
    print(f"⚡ Implementação OTIMIZADA: batching verdadeiro + paralelização")
    print(f"📦 Batches de 5 eventos por chamada GPT-5")
    print(f"🔀 Até 3 batches processados em paralelo")

    expected_batches = (len(events) + 4) // 5
    expected_rounds = (expected_batches + 2) // 3

    print(f"\n📈 Estatísticas esperadas:")
    print(f"   Total de batches: {expected_batches}")
    print(f"   Rounds paralelos: {expected_rounds}")
    print(f"   Chamadas GPT-5: {expected_batches} (vs {len(events)} na versão antiga)")
    print(f"   Ganho: ~{len(events) / expected_batches:.1f}x mais rápido")
    print("\n" + "=" * 80)

    # Callback de progresso
    completed_batches = [0]  # Use list to allow modification in nested function

    def progress_callback(batch_num, total_batches):
        completed_batches[0] = batch_num
        percent = (batch_num / total_batches) * 100
        print(f"\n⏳ Progresso: {batch_num}/{total_batches} batches ({percent:.1f}%)")

    # Executar julgamento
    judge = QualityJudgeAgent()

    start_time = datetime.now()
    print(f"\n🎬 Iniciando julgamento às {start_time.strftime('%H:%M:%S')}...\n")

    judged_events = await judge.judge_all_events(
        events,
        progress_callback=progress_callback,
        max_parallel_batches=3
    )

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # Estatísticas
    print("\n" + "=" * 80)
    print("📊 ESTATÍSTICAS FINAIS")
    print("=" * 80)

    avg_score = sum(e.get('quality_score', 0) for e in judged_events) / len(judged_events)
    high_quality = sum(1 for e in judged_events if e.get('quality_score', 0) >= 8)
    medium_quality = sum(1 for e in judged_events if 5 <= e.get('quality_score', 0) < 8)
    low_quality = sum(1 for e in judged_events if e.get('quality_score', 0) < 5)

    print(f"\n⏱️  Tempo total: {duration:.1f}s ({duration/60:.1f} minutos)")
    print(f"📈 Eventos julgados: {len(judged_events)}")
    print(f"⚡ Tempo médio por evento: {duration / len(judged_events):.1f}s")

    print(f"\n🎯 Nota média geral: {avg_score:.2f}/10")
    print(f"   ⭐ Alta qualidade (≥8):    {high_quality} eventos ({high_quality/len(judged_events)*100:.1f}%)")
    print(f"   ✓  Média qualidade (5-7.9): {medium_quality} eventos ({medium_quality/len(judged_events)*100:.1f}%)")
    print(f"   ⚠️  Baixa qualidade (<5):    {low_quality} eventos ({low_quality/len(judged_events)*100:.1f}%)")

    # Top 5 e Bottom 5
    sorted_events = sorted(judged_events, key=lambda e: e.get('quality_score', 0), reverse=True)

    print("\n" + "=" * 80)
    print("🏆 TOP 5 EVENTOS (Maior Qualidade)")
    print("=" * 80)
    for i, event in enumerate(sorted_events[:5], 1):
        score = event.get('quality_score', 0)
        print(f"\n{i}. {event.get('titulo', 'Sem título')} ({score:.1f}/10)")
        print(f"   📍 {event.get('local', 'Local não especificado')}")
        print(f"   💬 {event.get('quality_notes', 'Sem observações')[:100]}")

    print("\n" + "=" * 80)
    print("⚠️  BOTTOM 5 EVENTOS (Menor Qualidade)")
    print("=" * 80)
    for i, event in enumerate(sorted_events[-5:][::-1], 1):
        score = event.get('quality_score', 0)
        print(f"\n{i}. {event.get('titulo', 'Sem título')} ({score:.1f}/10)")
        print(f"   📍 {event.get('local', 'Local não especificado')}")
        print(f"   💬 {event.get('quality_notes', 'Sem observações')[:100]}")

    # Salvar resultados
    output_file = Path("output/latest/judged_events.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "metadata": {
                "total_events": len(judged_events),
                "judged_at": datetime.now().isoformat(),
                "duration_seconds": duration,
                "average_score": avg_score,
                "high_quality_count": high_quality,
                "medium_quality_count": medium_quality,
                "low_quality_count": low_quality
            },
            "events": judged_events
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"✅ JULGAMENTO CONCLUÍDO COM SUCESSO!")
    print("=" * 80)
    print(f"\n💾 Resultados salvos em: {output_file}")
    print(f"🌐 Acesse http://localhost:8000 para visualizar no calendário")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Julgamento cancelado pelo usuário")
    except Exception as e:
        print(f"\n\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
