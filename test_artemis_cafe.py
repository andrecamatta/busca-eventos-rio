"""Teste: Buscar Artemis Torrefação (cursos de café)"""

import asyncio
import sys
from datetime import datetime, timedelta
from agents.base_agent import BaseAgent

# Fix encoding para Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')


async def test_artemis_cafe():
    """Testa busca para Artemis Torrefação - cursos de café."""

    print("=" * 80)
    print("TESTE: Artemis Torrefação - Cursos de Café")
    print("=" * 80)

    # Datas dinâmicas
    start_date = datetime.now()
    end_date = start_date + timedelta(days=30)

    start_date_str = start_date.strftime("%d/%m/%Y")
    end_date_str = end_date.strftime("%d/%m/%Y")
    month_year_str = start_date.strftime("%B %Y")

    print(f"\nPeríodo: {start_date_str} a {end_date_str}\n")

    # Criar agente
    agent = BaseAgent(
        agent_name="PerplexityTest",
        log_emoji="☕",
        model_type="search",
        description="Teste Artemis Torrefação",
        instructions=["Buscar cursos de café na Artemis Torrefação"],
        markdown=True
    )

    # Prompt GENÉRICO para não restringir
    prompt = f"""
🔍 BUSCA GENÉRICA: ARTEMIS NO RIO DE JANEIRO

PERÍODO: {start_date_str} a {end_date_str}

OBJETIVO: Encontrar QUALQUER tipo de evento, curso, workshop ou atividade relacionada a "Artemis" no Rio de Janeiro.

TIPOS DE EVENTOS A BUSCAR:
- Cursos de café (barista, degustação, torra)
- Workshops gastronômicos
- Eventos culturais
- Shows
- Aulas
- Palestras
- Qualquer atividade agendada

ESTRATÉGIAS DE BUSCA:
1. "Artemis Rio de Janeiro {month_year_str}"
2. "Artemis Torrefação cursos"
3. "Artemis café Rio"
4. site:sympla.com.br artemis rio
5. site:eventbrite.com.br artemis rio
6. "cursos barista Artemis"
7. "workshop café Artemis"

INFORMAÇÕES OBRIGATÓRIAS:
- titulo: Nome do evento/curso
- data: DD/MM/YYYY
- horario: HH:MM
- local: Nome completo + endereço
- preco: valor
- link_ingresso: URL
- descricao: descrição do evento

FORMATO JSON:
{{
  "eventos": [...],
  "total_encontrado": N,
  "fontes_consultadas": ["URLs"],
  "observacoes": "comentários"
}}

IMPORTANTE: Buscar QUALQUER coisa relacionada a Artemis no Rio, não apenas shows.
"""

    print("Executando busca via Perplexity...")
    print("-" * 80)

    try:
        response = agent.agent.run(prompt)
        result = response.content

        print("\n" + "=" * 80)
        print("RESULTADO:")
        print("=" * 80)
        print(result)
        print("=" * 80)

        # Parse JSON
        import json
        from utils.json_helpers import clean_json_response

        try:
            cleaned = clean_json_response(result)
            data = json.loads(cleaned)

            total = data.get("total_encontrado", 0)
            eventos = data.get("eventos", [])
            observacoes = data.get("observacoes", "")

            print(f"\n📊 RESULTADO:")
            print(f"   Total: {total}")
            print(f"   Eventos: {len(eventos)}")

            if eventos:
                print(f"\n✅ EVENTOS ENCONTRADOS:")
                for i, evento in enumerate(eventos, 1):
                    print(f"\n   {i}. {evento.get('titulo', 'N/A')}")
                    print(f"      Tipo: {evento.get('tipo', 'N/A')}")
                    print(f"      Data: {evento.get('data', 'N/A')}")
                    print(f"      Local: {evento.get('local', 'N/A')}")
                    print(f"      Link: {evento.get('link_ingresso', 'N/A')}")
            else:
                print(f"\n❌ NENHUM EVENTO ENCONTRADO")
                print(f"\n💬 Observações:")
                print(f"   {observacoes}")

        except json.JSONDecodeError as e:
            print(f"\n⚠️  Erro ao parsear JSON: {e}")

    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("TESTE CONCLUÍDO")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_artemis_cafe())
