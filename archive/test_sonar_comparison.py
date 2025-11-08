#!/usr/bin/env python3
"""
Teste Comparativo: Perplexity Sonar vs Sonar Pro

Executa buscas paralelas com ambos os modelos e compara resultados.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from config import SEARCH_CONFIG, OPENROUTER_API_KEY, OPENROUTER_BASE_URL

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Criar diretório de resultados
RESULTS_DIR = Path("test_results")
RESULTS_DIR.mkdir(exist_ok=True)


class SonarTester:
    """Testa Sonar vs Sonar Pro em buscas reais."""

    def __init__(self):
        self.start_date = SEARCH_CONFIG['start_date'].strftime('%d/%m/%Y')
        self.end_date = SEARCH_CONFIG['end_date'].strftime('%d/%m/%Y')

    def create_agent(self, model_name: str, test_name: str) -> Agent:
        """Cria agente de busca com modelo específico."""
        return Agent(
            name=f"Test Agent - {test_name}",
            model=OpenAIChat(
                id=model_name,
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
            description=f"Agente de teste usando {model_name}",
            instructions=[
                f"Buscar eventos culturais no Rio de Janeiro entre {self.start_date} e {self.end_date}",
                "Retornar informações completas: título, data, horário, local, link de ingresso",
            ],
            markdown=True,
        )

    def build_test_prompts(self) -> list[dict]:
        """Constrói prompts de teste para categorias representativas."""
        return [
            {
                "name": "Jazz",
                "prompt": f"""Busque shows de JAZZ no Rio de Janeiro entre {self.start_date} e {self.end_date}.

INSTRUÇÕES:
1. Buscar em casas de jazz: Maze Jazz Club, Clube do Jazz, Jazz nos Fundos
2. EXCLUIR: Blue Note Rio (será obtido por outro método)
3. Incluir jazz em hotéis e bares especializados
4. Buscar em portais: TimeOut Rio, Veja Rio, Sympla, Eventbrite

Para cada evento, retorne JSON:
{{
  "titulo": "Nome do show",
  "data": "DD/MM/AAAA",
  "horario": "HH:MM",
  "local": "Nome do venue",
  "preco": "Valor ou 'Entrada franca'",
  "link_ingresso": "URL completa de compra",
  "descricao": "Breve descrição"
}}

Retorne array JSON com todos os eventos encontrados."""
            },
            {
                "name": "Teatro-Comédia",
                "prompt": f"""Busque peças de TEATRO e shows de COMÉDIA/STAND-UP no Rio de Janeiro entre {self.start_date} e {self.end_date}.

FILTROS IMPORTANTES:
- EXCLUIR: eventos infantis, musicais infantis
- INCLUIR: stand-up comedy, comédia adulta, teatro adulto
- Venues: Teatro Rival, Teatro Clara Nunes, Teatro Riachuelo, etc

Para cada evento, retorne JSON:
{{
  "titulo": "Nome da peça/show",
  "data": "DD/MM/AAAA",
  "horario": "HH:MM",
  "local": "Nome do teatro",
  "preco": "Valor ou faixa de preço",
  "link_ingresso": "URL completa de compra",
  "descricao": "Sinopse breve"
}}

Retorne array JSON com todos os eventos encontrados."""
            },
            {
                "name": "Casa-do-Choro",
                "prompt": f"""Busque eventos na CASA DO CHORO (Rio de Janeiro) entre {self.start_date} e {self.end_date}.

INSTRUÇÕES:
1. Buscar especificamente eventos na Casa do Choro
2. Incluir: shows de choro, samba, MPB
3. Verificar site oficial e plataformas de ingressos

Para cada evento, retorne JSON:
{{
  "titulo": "Nome do show/artista",
  "data": "DD/MM/AAAA",
  "horario": "HH:MM",
  "local": "Casa do Choro",
  "preco": "Valor",
  "link_ingresso": "URL de compra",
  "descricao": "Descrição do evento"
}}

Retorne array JSON com todos os eventos encontrados."""
            },
        ]

    async def run_search(self, agent: Agent, prompt_data: dict) -> dict:
        """Executa uma busca e retorna resultado."""
        category = prompt_data["name"]
        prompt = prompt_data["prompt"]

        logger.info(f"🔍 Buscando: {category} com {agent.model}...")

        try:
            response = agent.run(prompt)
            content = response.content.strip()

            # Tentar parsear JSON
            try:
                # Remover markdown code blocks se presente
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                eventos = json.loads(content)

                if not isinstance(eventos, list):
                    eventos = []

                return {
                    "category": category,
                    "model": str(agent.model.id),  # Apenas o ID do modelo
                    "success": True,
                    "events_count": len(eventos),
                    "events": eventos,
                    "raw_response": content[:500],  # Primeiros 500 chars
                }

            except json.JSONDecodeError as e:
                logger.warning(f"⚠️  JSON inválido para {category}: {e}")
                return {
                    "category": category,
                    "model": str(agent.model.id),
                    "success": False,
                    "events_count": 0,
                    "error": f"JSON parsing error: {str(e)}",
                    "raw_response": content[:500],
                }

        except Exception as e:
            logger.error(f"❌ Erro na busca {category}: {e}")
            return {
                "category": category,
                "model": str(agent.model.id),
                "success": False,
                "events_count": 0,
                "error": str(e),
            }

    async def compare_models(self):
        """Executa teste comparativo entre Sonar e Sonar Pro."""
        logger.info("=" * 80)
        logger.info("TESTE COMPARATIVO: Sonar vs Sonar Pro")
        logger.info("=" * 80)

        # Criar agentes
        agent_sonar = self.create_agent("perplexity/sonar", "Sonar")
        agent_sonar_pro = self.create_agent("perplexity/sonar-pro", "Sonar Pro")

        # Prompts de teste
        test_prompts = self.build_test_prompts()

        # Executar buscas em paralelo para cada categoria
        results_sonar = []
        results_sonar_pro = []

        for prompt_data in test_prompts:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Categoria: {prompt_data['name']}")
            logger.info(f"{'=' * 60}")

            # Executar ambas as buscas em paralelo
            result_sonar, result_sonar_pro = await asyncio.gather(
                self.run_search(agent_sonar, prompt_data),
                self.run_search(agent_sonar_pro, prompt_data),
            )

            results_sonar.append(result_sonar)
            results_sonar_pro.append(result_sonar_pro)

            # Log resumido
            logger.info(f"  Sonar:     {result_sonar.get('events_count', 0)} eventos")
            logger.info(f"  Sonar Pro: {result_sonar_pro.get('events_count', 0)} eventos")

        # Salvar resultados
        self.save_results(results_sonar, results_sonar_pro)

        # Gerar relatório
        self.generate_report(results_sonar, results_sonar_pro)

    def save_results(self, results_sonar: list, results_sonar_pro: list):
        """Salva resultados em arquivos JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        sonar_file = RESULTS_DIR / f"sonar_results_{timestamp}.json"
        sonar_pro_file = RESULTS_DIR / f"sonar_pro_results_{timestamp}.json"

        with open(sonar_file, "w", encoding="utf-8") as f:
            json.dump(results_sonar, f, ensure_ascii=False, indent=2)

        with open(sonar_pro_file, "w", encoding="utf-8") as f:
            json.dump(results_sonar_pro, f, ensure_ascii=False, indent=2)

        logger.info(f"\n✓ Resultados salvos:")
        logger.info(f"  - {sonar_file}")
        logger.info(f"  - {sonar_pro_file}")

    def generate_report(self, results_sonar: list, results_sonar_pro: list):
        """Gera relatório comparativo."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = RESULTS_DIR / f"comparison_report_{timestamp}.txt"

        with open(report_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("RELATÓRIO COMPARATIVO: Perplexity Sonar vs Sonar Pro\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Data do teste: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write(f"Período de eventos: {self.start_date} a {self.end_date}\n\n")

            # Resumo por categoria
            f.write("RESUMO POR CATEGORIA\n")
            f.write("-" * 80 + "\n\n")

            total_sonar = 0
            total_sonar_pro = 0

            for sonar, sonar_pro in zip(results_sonar, results_sonar_pro):
                category = sonar["category"]
                count_sonar = sonar.get("events_count", 0)
                count_sonar_pro = sonar_pro.get("events_count", 0)

                total_sonar += count_sonar
                total_sonar_pro += count_sonar_pro

                diff = count_sonar - count_sonar_pro
                diff_pct = ((count_sonar - count_sonar_pro) / count_sonar_pro * 100) if count_sonar_pro > 0 else 0

                f.write(f"📂 {category}\n")
                f.write(f"   Sonar:     {count_sonar:3d} eventos\n")
                f.write(f"   Sonar Pro: {count_sonar_pro:3d} eventos\n")
                f.write(f"   Diferença: {diff:+3d} eventos ({diff_pct:+.1f}%)\n")

                if not sonar.get("success"):
                    f.write(f"   ⚠️  Sonar FALHOU: {sonar.get('error', 'Erro desconhecido')}\n")
                if not sonar_pro.get("success"):
                    f.write(f"   ⚠️  Sonar Pro FALHOU: {sonar_pro.get('error', 'Erro desconhecido')}\n")

                f.write("\n")

            # Totais
            f.write("-" * 80 + "\n")
            f.write("TOTAIS\n")
            f.write("-" * 80 + "\n\n")
            f.write(f"Sonar:     {total_sonar} eventos totais\n")
            f.write(f"Sonar Pro: {total_sonar_pro} eventos totais\n")

            if total_sonar_pro > 0:
                diff_total = total_sonar - total_sonar_pro
                diff_pct_total = (diff_total / total_sonar_pro * 100)
                f.write(f"Diferença: {diff_total:+d} eventos ({diff_pct_total:+.1f}%)\n\n")

            # Análise de custo (estimativa)
            f.write("-" * 80 + "\n")
            f.write("ANÁLISE DE CUSTO (ESTIMATIVA)\n")
            f.write("-" * 80 + "\n\n")

            # Assumindo ~2000 tokens input + 1500 tokens output por busca
            tokens_per_search_input = 2000
            tokens_per_search_output = 1500

            searches_count = len(results_sonar)

            # Custos por 1M tokens
            cost_sonar_input = 0.06  # $0.06/1M tokens
            cost_sonar_output = 0.20  # $0.20/1M tokens
            cost_sonar_pro_input = 0.30  # $0.30/1M tokens
            cost_sonar_pro_output = 1.00  # $1.00/1M tokens

            cost_sonar = (
                (tokens_per_search_input * searches_count * cost_sonar_input / 1_000_000) +
                (tokens_per_search_output * searches_count * cost_sonar_output / 1_000_000)
            )

            cost_sonar_pro = (
                (tokens_per_search_input * searches_count * cost_sonar_pro_input / 1_000_000) +
                (tokens_per_search_output * searches_count * cost_sonar_pro_output / 1_000_000)
            )

            savings = cost_sonar_pro - cost_sonar
            savings_pct = (savings / cost_sonar_pro * 100) if cost_sonar_pro > 0 else 0

            f.write(f"Custo estimado Sonar:     ${cost_sonar:.4f} ({searches_count} buscas)\n")
            f.write(f"Custo estimado Sonar Pro: ${cost_sonar_pro:.4f} ({searches_count} buscas)\n")
            f.write(f"Economia:                 ${savings:.4f} ({savings_pct:.1f}%)\n\n")

            # Recomendação
            f.write("-" * 80 + "\n")
            f.write("RECOMENDAÇÃO\n")
            f.write("-" * 80 + "\n\n")

            if total_sonar_pro == 0:
                f.write("⚠️  Sonar Pro não retornou eventos. Teste inconclusivo.\n")
            elif total_sonar == 0:
                f.write("❌ Sonar não retornou eventos. Manter Sonar Pro.\n")
            elif total_sonar >= total_sonar_pro * 0.85:  # Sonar mantém 85%+ dos resultados
                f.write("✅ RECOMENDADO: Migrar para Sonar\n\n")
                f.write(f"   Sonar mantém {(total_sonar/total_sonar_pro*100):.1f}% dos eventos\n")
                f.write(f"   Economia estimada: {savings_pct:.1f}% (~${savings:.4f} por execução)\n")
                f.write(f"   Qualidade: ACEITÁVEL (perda de {100-(total_sonar/total_sonar_pro*100):.1f}%)\n")
            else:
                f.write("⚠️  AVALIAR COM CAUTELA: Sonar encontrou significativamente menos eventos\n\n")
                f.write(f"   Sonar mantém apenas {(total_sonar/total_sonar_pro*100):.1f}% dos eventos\n")
                f.write(f"   Perda de {100-(total_sonar/total_sonar_pro*100):.1f}% pode ser crítica\n")
                f.write(f"   Considerar modelo híbrido ou manter Sonar Pro\n")

        logger.info(f"\n✓ Relatório salvo: {report_file}")

        # Exibir resumo no console
        print("\n" + "=" * 80)
        print("RESUMO DO TESTE")
        print("=" * 80)
        print(f"Sonar:     {total_sonar} eventos totais")
        print(f"Sonar Pro: {total_sonar_pro} eventos totais")

        if total_sonar_pro > 0:
            print(f"Diferença: {total_sonar - total_sonar_pro:+d} eventos ({(total_sonar - total_sonar_pro) / total_sonar_pro * 100:+.1f}%)")
            print(f"Economia:  ~${savings:.4f} ({savings_pct:.1f}%)")

        print("\n📄 Veja o relatório completo em:")
        print(f"   {report_file}")
        print("=" * 80)


async def main():
    """Executa teste comparativo."""
    # Desabilitar telemetria
    os.environ['AGNO_TELEMETRY'] = 'false'

    tester = SonarTester()
    await tester.compare_models()


if __name__ == "__main__":
    asyncio.run(main())
