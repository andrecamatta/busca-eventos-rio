#!/usr/bin/env python3
"""
Sistema Multi-Agente de Busca de Eventos no Rio de Janeiro

Utiliza Agno + OpenRouter para buscar, verificar e formatar eventos culturais.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Desabilitar telemetria da biblioteca Agno (reduz 1000+ chamadas HTTP desnecessárias)
os.environ['AGNO_TELEMETRY'] = 'false'

from agents.enrichment_agent import EnrichmentAgent
from agents.format_agent import FormatAgent
from agents.retry_agent import RetryAgent
from agents.search_agent import SearchAgent
from agents.title_enhancement_agent import enhance_event_titles
from agents.verify_agent import VerifyAgent
from config import (
    ENRICHMENT_ENABLED,
    EVENT_CLASSIFIER_ENABLED,
    MIN_EVENTS_THRESHOLD,
    OPENROUTER_API_KEY,
    SEARCH_CONFIG,
    TITLE_ENHANCEMENT_ENABLED,
)
from utils.continuous_event_handler import consolidate_continuous_events
from utils.deduplicator import deduplicate_events
from utils.event_classifier import classify_events
from utils.event_consolidator import EventConsolidator
from utils.event_merger import EventMerger
from utils.file_manager import EventFileManager

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("busca_eventos.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


class EventSearchOrchestrator:
    """Orquestrador do sistema multi-agente de busca de eventos."""

    def __init__(self):
        self.search_agent = SearchAgent()
        self.verify_agent = VerifyAgent()
        self.retry_agent = RetryAgent()
        self.enrichment_agent = EnrichmentAgent()
        self.format_agent = FormatAgent()
        self.merger = EventMerger()
        self.file_manager = EventFileManager()

    async def run(self) -> str:
        """Executa pipeline completo de busca de eventos."""
        logger.info("=" * 80)
        logger.info("Iniciando Sistema de Busca de Eventos")
        logger.info(f"Período: {SEARCH_CONFIG['start_date'].strftime('%d/%m/%Y')} a "
                   f"{SEARCH_CONFIG['end_date'].strftime('%d/%m/%Y')}")
        logger.info("=" * 80)

        try:
            # Fase 1: Busca (Search Agent com Perplexity Sonar Pro)
            logger.info("\n[FASE 1/3] 🔍 Buscando eventos com Perplexity Sonar Pro...")
            raw_events = await self.search_agent.search_all_sources()

            # Perplexity já retorna estruturado
            logger.info("\n[FASE 1.5/3] 🧠 Extraindo dados estruturados...")
            structured_events = self.search_agent.process_with_llm(raw_events)

            if not structured_events or structured_events == "{}":
                logger.warning("Nenhum evento encontrado nas fontes de dados")
                return "Nenhum evento encontrado para o período especificado."

            logger.info(f"✓ Eventos encontrados pelo Perplexity")

            # Salvar eventos brutos
            self.file_manager.save_json(raw_events, "raw_events.json")
            self.file_manager.save_json(structured_events, "structured_events.json")

            # Fase 2: Verificação (Verify Agent)
            logger.info("\n[FASE 2/4] ✅ Verificando e validando eventos...")
            verified_events = await self.verify_agent.verify_events(structured_events)

            # Estatísticas de verificação
            stats = self.verify_agent.get_verification_stats(verified_events)
            logger.info(f"✓ Eventos verificados: {stats['total_verified']}")
            logger.info(f"✗ Eventos rejeitados: {stats['total_rejected']}")
            logger.info(f"⚠️  Avisos: {stats['total_warnings']}")
            logger.info(f"🔄 Duplicatas removidas: {stats['duplicates_removed']}")

            # Salvar eventos verificados (versão inicial)
            self.file_manager.save_json(verified_events, "verified_events_initial.json")

            # Fase 3: Enriquecimento ANTES de retry (enriquecer apenas eventos já validados)
            if ENRICHMENT_ENABLED and len(verified_events.get("verified_events", [])) > 0:
                logger.info("\n[FASE 3/5] 🧠 Enriquecendo eventos iniciais com contexto adicional...")
                enrichment_result = await self.enrichment_agent.enrich_events(
                    verified_events.get("verified_events", [])
                )

                # Atualizar eventos com versões enriquecidas
                verified_events["verified_events"] = enrichment_result["enriched_events"]

                # Estatísticas de enriquecimento
                stats_enrich = enrichment_result["enrichment_stats"]
                logger.info(f"✓ Eventos enriquecidos: {stats_enrich['enriched']}/{stats_enrich['total']}")
                logger.info(f"🔍 Buscas utilizadas: {stats_enrich['searches_used']}/{stats_enrich.get('max_searches', 10)}")

                # Salvar eventos enriquecidos
                self.file_manager.save_json(verified_events, "enriched_events_initial.json")
            else:
                logger.info("\n[FASE 3/5] ⏭️  Enriquecimento desabilitado ou sem eventos, pulando...")

            # Fase 3.1: Title Enhancement (enriquecer títulos genéricos)
            if TITLE_ENHANCEMENT_ENABLED and len(verified_events.get("verified_events", [])) > 0:
                logger.info("\n[FASE 3.1/5] ✨ Enriquecendo títulos genéricos...")
                verified_events["verified_events"] = await enhance_event_titles(
                    verified_events.get("verified_events", [])
                )
                logger.info(f"✓ Títulos processados")
            else:
                logger.info("\n[FASE 3.1/5] ⏭️  Title Enhancement desabilitado, pulando...")

            # Fase 3.5: Retry Agent (se necessário)
            logger.info(f"\n[FASE 3.5/5] 🔄 Verificando threshold mínimo ({MIN_EVENTS_THRESHOLD} eventos)...")
            needs_retry, analysis = self.retry_agent.needs_retry(verified_events)

            if needs_retry:
                logger.info(f"⚠️  Apenas {stats['total_verified']} eventos encontrados. "
                           f"Iniciando busca complementar...")

                # Tentar recuperar eventos rejeitados
                recoverable = analysis.get("recoverable_events", [])
                if recoverable:
                    logger.info(f"🔧 Analisando {len(recoverable)} eventos recuperáveis...")
                    recovered = self.retry_agent.analyze_recoverable(recoverable)
                    if recovered:
                        # Adicionar eventos recuperados aos verificados
                        verified_events["verified_events"].extend(recovered)
                        logger.info(f"✓ Recuperados {len(recovered)} eventos")

                # Buscar eventos complementares
                complementary_data = await self.retry_agent.search_complementary(analysis)
                complementary_events = complementary_data.get("eventos_complementares", [])

                if complementary_events:
                    logger.info(f"🔍 Encontrados {len(complementary_events)} eventos complementares")

                    # Criar estrutura compatível para verificação
                    complementary_structured = {
                        "eventos_gerais": {"eventos": complementary_events},
                        "eventos_locais_especiais": {}
                    }

                    # Verificar eventos complementares
                    logger.info("✅ Verificando eventos complementares...")
                    verified_complementary = await self.verify_agent.verify_events(
                        json.dumps(complementary_structured, ensure_ascii=False)
                    )

                    # Merge com eventos existentes (removendo duplicatas)
                    logger.info("🔀 Fazendo merge de eventos (removendo duplicatas)...")
                    verified_events = self.merger.merge_events(verified_events, verified_complementary)

                    # Estatísticas finais
                    final_count = len(verified_events["verified_events"])
                    logger.info(f"✓ Total final de eventos: {final_count}")
                else:
                    logger.warning("Nenhum evento complementar encontrado")
            else:
                logger.info(f"✓ Threshold atingido ({stats['total_verified']} eventos)")

            # Deduplicação final (remover eventos duplicados por titulo + data + horario)
            logger.info("\n[FASE 3.7/5] 🗑️  Removendo eventos duplicados...")
            verified_events["verified_events"] = deduplicate_events(
                verified_events.get("verified_events", [])
            )
            final_count = len(verified_events["verified_events"])
            logger.info(f"✓ Total após deduplicação: {final_count} eventos únicos")

            # Classificação automática de categorias (usando Gemini Flash)
            if EVENT_CLASSIFIER_ENABLED:
                logger.info("\n[FASE 3.8/5] 🏷️  Classificando eventos em categorias...")
                verified_events["verified_events"] = await classify_events(
                    verified_events.get("verified_events", [])
                )
                logger.info(f"✓ Eventos classificados em categorias")
            else:
                logger.info("\n[FASE 3.8/5] ⏭️  Classificação de categorias desabilitada (SearchAgent já categoriza), pulando...")

            # Consolidação de eventos recorrentes (mesmo evento em múltiplas datas)
            logger.info("\n[FASE 3.9/5] 🔁 Consolidando eventos recorrentes...")
            before_recurring = len(verified_events.get("verified_events", []))
            consolidator = EventConsolidator()
            verified_events["verified_events"] = consolidator.consolidate_recurring_events(
                verified_events.get("verified_events", [])
            )
            after_recurring = len(verified_events.get("verified_events", []))
            if before_recurring != after_recurring:
                logger.info(f"✓ Eventos recorrentes consolidados: {before_recurring} -> {after_recurring} eventos")
            else:
                logger.info(f"✓ Nenhum evento recorrente detectado")

            # Consolidação de eventos contínuos (exposições, mostras, temporadas)
            logger.info("\n[FASE 3.10/5] 📅 Consolidando eventos contínuos (exposições/mostras)...")
            before_consolidation = len(verified_events.get("verified_events", []))
            verified_events["verified_events"] = consolidate_continuous_events(
                verified_events.get("verified_events", [])
            )
            after_consolidation = len(verified_events.get("verified_events", []))
            if before_consolidation != after_consolidation:
                logger.info(f"✓ Consolidação aplicada: {before_consolidation} -> {after_consolidation} eventos")
            else:
                logger.info(f"✓ Nenhum evento contínuo detectado para consolidar")

            # Salvar eventos verificados finais
            self.file_manager.save_json(verified_events, "verified_events.json")

            if len(verified_events.get("verified_events", [])) == 0:
                logger.warning("Nenhum evento passou na verificação")
                return "Nenhum evento válido encontrado após verificação."

            # Fase 4: Formatação (Format Agent com consolidação inline)
            logger.info("\n[FASE 4/4] 📱 Formatando para WhatsApp...")
            whatsapp_message = self.format_agent.format_for_whatsapp(verified_events)

            # Salvar mensagem final
            self.file_manager.save_text(whatsapp_message, "eventos_whatsapp.txt")

            logger.info("\n" + "=" * 80)
            logger.info("✓ BUSCA CONCLUÍDA COM SUCESSO!")
            logger.info("=" * 80)
            logger.info(f"\nArquivos salvos:")
            logger.info("  - raw_events.json (eventos brutos)")
            logger.info("  - structured_events.json (eventos estruturados)")
            logger.info("  - verified_events_initial.json (eventos verificados inicialmente)")
            if ENRICHMENT_ENABLED:
                logger.info("  - enriched_events_initial.json (eventos iniciais enriquecidos)")
            logger.info("  - verified_events.json (eventos verificados finais após retry)")
            logger.info("  - eventos_whatsapp.txt (mensagem final com consolidação)")
            logger.info("  - busca_eventos.log (logs)")

            return whatsapp_message

        except Exception as e:
            logger.error(f"Erro durante execução: {e}", exc_info=True)
            raise


async def main():
    """Função principal."""
    # Verificar API key
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY não configurada!")
        logger.error("Configure a variável de ambiente ou crie arquivo .env")
        sys.exit(1)

    # Criar orquestrador e executar
    orchestrator = EventSearchOrchestrator()
    whatsapp_message = await orchestrator.run()

    # Exibir mensagem final
    print("\n" + "=" * 80)
    print("MENSAGEM PARA WHATSAPP (Ctrl+C para copiar)")
    print("=" * 80)
    print(whatsapp_message)
    print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nExecução interrompida pelo usuário")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)
