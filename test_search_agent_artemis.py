"""Teste: Simular busca do SearchAgent para Artemis usando prompt real."""

import asyncio
import sys
import yaml
from datetime import datetime, timedelta
from pathlib import Path

# Fix encoding para Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')


async def test_search_agent_artemis():
    """Testa busca Artemis exatamente como SearchAgent faria."""

    print("=" * 80)
    print("TESTE: SearchAgent - Busca Artemis (Simulação Real)")
    print("=" * 80)

    # Configurar datas dinâmicas (igual ao SearchAgent)
    start_date = datetime.now()
    end_date = start_date + timedelta(days=30)

    start_date_str = start_date.strftime("%d/%m/%Y")
    end_date_str = end_date.strftime("%d/%m/%Y")
    month_year_str = start_date.strftime("%B %Y")
    month_str = start_date.strftime("%B").lower()

    print(f"\n📅 Período: {start_date_str} a {end_date_str}")
    print(f"📆 Mês: {month_year_str}\n")

    # Carregar prompt real do search_prompts.yaml
    prompts_file = Path(__file__).parent / "prompts" / "search_prompts.yaml"

    with open(prompts_file, 'r', encoding='utf-8') as f:
        prompts_data = yaml.safe_load(f)

    # Artemis está em 'venues', não em 'categorias'
    artemis_config = prompts_data.get('venues', {}).get('artemis')

    if not artemis_config:
        # Tentar em categorias também
        artemis_config = prompts_data.get('categorias', {}).get('artemis')

    if not artemis_config:
        print("❌ ERRO: Configuração 'artemis' não encontrada em search_prompts.yaml")
        print(f"   Seções disponíveis: {list(prompts_data.keys())}")
        return

    print("📋 CONFIGURAÇÃO CARREGADA DO search_prompts.yaml:")
    print(f"   Nome: {artemis_config.get('nome')}")
    print(f"   Tipo: {artemis_config.get('tipo_busca')}")
    print(f"   Endereço: {artemis_config.get('endereco')}")
    print()

    # Interpolar variáveis no prompt (igual ao SearchAgent)
    instrucoes = artemis_config.get('instrucoes_especiais', '')
    instrucoes = instrucoes.format(
        start_date_str=start_date_str,
        end_date_str=end_date_str,
        month_year_str=month_year_str,
        month_str=month_str
    )

    # Montar prompt completo (simulando SearchAgent)
    prompt = f"""
BUSCA FOCADA: {artemis_config.get('nome')}

PERÍODO: {start_date_str} a {end_date_str}

DESCRIÇÃO: {artemis_config.get('descricao')}

{instrucoes}

INFORMAÇÕES OBRIGATÓRIAS PARA CADA EVENTO:
- titulo: Nome completo do evento
- data: formato DD/MM/YYYY
- horario: formato HH:MM
- local: Nome do venue + endereço completo
- preco: valor ou 'Consultar'
- link_ingresso: URL de compra/info (ou null se não encontrado)
- descricao: resumo do evento (opcional)

FORMATO DE RETORNO (JSON):
{{
  "eventos": [
    {{
      "titulo": "...",
      "data": "DD/MM/YYYY",
      "horario": "HH:MM",
      "local": "...",
      "preco": "...",
      "link_ingresso": "...",
      "descricao": "..."
    }}
  ],
  "total_encontrado": N,
  "fontes_consultadas": ["URLs"],
  "observacoes": "comentários"
}}

RETORNAR APENAS JSON VÁLIDO.
"""

    print("=" * 80)
    print("PROMPT GERADO (Como SearchAgent faria):")
    print("=" * 80)
    print(prompt)
    print("=" * 80)
    print()

    # Executar busca via Perplexity (igual ao SearchAgent)
    from agents.base_agent import BaseAgent

    agent = BaseAgent(
        agent_name="SearchAgent_Artemis_Test",
        log_emoji="🔍",
        model_type="search",  # Perplexity Sonar Pro
        description="Teste SearchAgent - Artemis",
        instructions=["Executar busca focada para Artemis Torrefação"],
        markdown=True
    )

    print("🔍 Executando busca via Perplexity (modelo: search)...")
    print("-" * 80)

    try:
        response = agent.agent.run(prompt)
        result = response.content

        print("\n" + "=" * 80)
        print("RESULTADO DA BUSCA:")
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
            fontes = data.get("fontes_consultadas", [])
            observacoes = data.get("observacoes", "")

            print(f"\n📊 ANÁLISE DO RESULTADO:")
            print(f"   Total encontrado: {total}")
            print(f"   Eventos retornados: {len(eventos)}")
            print(f"   Fontes consultadas: {len(fontes)}")
            print()

            if eventos:
                print("✅ EVENTOS ENCONTRADOS:")
                for i, evento in enumerate(eventos, 1):
                    print(f"\n   {i}. {evento.get('titulo', 'N/A')}")
                    print(f"      📅 Data: {evento.get('data', 'N/A')}")
                    print(f"      ⏰ Horário: {evento.get('horario', 'N/A')}")
                    print(f"      📍 Local: {evento.get('local', 'N/A')}")
                    print(f"      💰 Preço: {evento.get('preco', 'N/A')}")
                    print(f"      🎫 Link: {evento.get('link_ingresso', 'N/A')}")
                    if evento.get('descricao'):
                        print(f"      📝 Descrição: {evento.get('descricao')[:100]}...")

                print()
                print("=" * 80)
                print(f"✅ SUCESSO: {len(eventos)} evento(s) encontrado(s) para Artemis")
                print("=" * 80)
            else:
                print("❌ NENHUM EVENTO ENCONTRADO")
                print()
                print("💬 Observações do Perplexity:")
                print(f"   {observacoes}")
                print()
                print("=" * 80)
                print("❌ FALHA: Artemis continua sem eventos no período")
                print("=" * 80)

            if fontes:
                print(f"\n🔗 FONTES CONSULTADAS ({len(fontes)}):")
                for fonte in fontes:
                    print(f"   - {fonte}")

            # Análise adicional
            print(f"\n📝 CONCLUSÃO:")
            if total > 0:
                print(f"   ✅ O prompt melhorado FUNCIONOU!")
                print(f"   ✅ SearchAgent deveria encontrar {total} evento(s)")
                print(f"   ✅ Artemis será coberto nas próximas execuções")
            else:
                print(f"   ⚠️  Nenhum evento no período {start_date_str} a {end_date_str}")
                print(f"   💡 Possíveis razões:")
                print(f"      - Artemis não tem eventos agendados neste período")
                print(f"      - Eventos só aparecem mais próximo da data")
                print(f"      - Necessário verificar Instagram/site diretamente")

        except json.JSONDecodeError as e:
            print(f"\n❌ ERRO ao parsear JSON: {e}")
            print(f"   Resposta não está em formato JSON válido")

    except Exception as e:
        print(f"\n❌ ERRO na busca: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("TESTE CONCLUÍDO")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_search_agent_artemis())
