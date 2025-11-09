"""Teste diagnóstico: Por que Perplexity não encontrou eventos Artemis?"""

import asyncio
import logging
from datetime import datetime, timedelta
from agents.base_agent import BaseAgent

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_artemis_search():
    """Testa busca específica de eventos Artemis via Perplexity."""

    print("=" * 80)
    print("TESTE DIAGNÓSTICO: Busca Artemis via Perplexity")
    print("=" * 80)

    # Configurar datas dinâmicas
    start_date = datetime.now()
    end_date = start_date + timedelta(days=30)

    start_date_str = start_date.strftime("%d/%m/%Y")
    end_date_str = end_date.strftime("%d/%m/%Y")
    month_year_str = start_date.strftime("%B %Y")
    month_str = start_date.strftime("%B").lower()

    print(f"\nPeríodo de busca: {start_date_str} a {end_date_str}")
    print(f"Mês: {month_year_str}\n")

    # Criar agente Perplexity
    agent = BaseAgent(
        agent_name="PerplexityTest",
        log_emoji="🔍",
        model_type="search",  # Perplexity Sonar Pro
        description="Teste de busca Artemis",
        instructions=["Buscar eventos específicos do venue Artemis no Rio de Janeiro"],
        markdown=True
    )

    # Prompt de teste
    prompt = f"""
🎯 BUSCA ULTRA-ESPECÍFICA: ARTEMIS RIO DE JANEIRO

PERÍODO: {start_date_str} a {end_date_str}

OBJETIVO: Encontrar eventos confirmados no venue ARTEMIS no Rio de Janeiro.

INFORMAÇÕES DO VENUE:
- Nome: Artemis
- Local: Rio de Janeiro (verificar endereço exato)
- Tipo: Casa de shows, eventos culturais

ESTRATÉGIAS DE BUSCA:
1. 🔍 Sympla: site:sympla.com.br/produtor/artemis
2. 🔍 Site oficial: procurar "Artemis Rio de Janeiro eventos {month_str}"
3. 🔍 Redes sociais: Instagram @artemisrio
4. 🔍 Fever: site:fever.com.br artemis rio
5. 🔍 Agendas culturais: "Artemis eventos {month_year_str}"

INFORMAÇÕES OBRIGATÓRIAS PARA CADA EVENTO:
- titulo: Nome do evento
- data: DD/MM/YYYY
- horario: HH:MM
- local: "Artemis + endereço completo"
- preco: valor ou "Consultar"
- link_ingresso: URL de compra/informações
- descricao: resumo do evento

FORMATO DE RETORNO (JSON):
{{
  "eventos": [
    {{
      "titulo": "...",
      "data": "DD/MM/YYYY",
      "horario": "HH:MM",
      "local": "Artemis - [endereço]",
      "preco": "...",
      "link_ingresso": "...",
      "descricao": "..."
    }}
  ],
  "total_encontrado": N,
  "fontes_consultadas": ["lista de URLs"],
  "observacoes": "comentários sobre a busca (se não encontrou nada, explicar por quê)"
}}

IMPORTANTE:
- Se NÃO encontrar eventos, explicar POR QUÊ nas observações
- Verificar se venue existe, se está aberto, se tem agenda pública
- Retornar JSON válido mesmo se não encontrar eventos (eventos: [])
"""

    print("Executando busca via Perplexity...")
    print("-" * 80)

    try:
        response = agent.agent.run(
            prompt,
            response_format={"type": "json_object"}
        )

        result = response.content

        print("\n" + "=" * 80)
        print("RESULTADO DA BUSCA:")
        print("=" * 80)
        print(result)
        print("=" * 80)

        # Análise do resultado
        import json
        try:
            data = json.loads(result)
            total = data.get("total_encontrado", 0)
            eventos = data.get("eventos", [])
            observacoes = data.get("observacoes", "")

            print(f"\n📊 ANÁLISE:")
            print(f"   Total encontrado: {total}")
            print(f"   Eventos retornados: {len(eventos)}")

            if eventos:
                print(f"\n✅ EVENTOS ENCONTRADOS:")
                for i, evento in enumerate(eventos, 1):
                    print(f"\n   {i}. {evento.get('titulo', 'Sem título')}")
                    print(f"      Data: {evento.get('data', 'N/A')}")
                    print(f"      Horário: {evento.get('horario', 'N/A')}")
                    print(f"      Link: {evento.get('link_ingresso', 'N/A')}")
            else:
                print(f"\n❌ NENHUM EVENTO ENCONTRADO")
                print(f"\n💡 Observações do Perplexity:")
                print(f"   {observacoes}")

        except json.JSONDecodeError as e:
            print(f"\n⚠️  ERRO ao parsear JSON: {e}")
            print(f"   Resposta não está em formato JSON válido")

    except Exception as e:
        print(f"\n❌ ERRO na busca: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("TESTE CONCLUÍDO")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_artemis_search())
