"""Agente de enriquecimento inteligente de descrições de eventos."""

import json
import logging
import re
from typing import Any

from agno.agent import Agent
from agno.models.openai import OpenAIChat

from config import (
    ENRICHMENT_BATCH_SIZE,
    ENRICHMENT_ENABLED,
    ENRICHMENT_GENERIC_TERMS,
    ENRICHMENT_MAX_SEARCHES,
    ENRICHMENT_MIN_DESC_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MODELS,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
)

logger = logging.getLogger(__name__)


class EnrichmentAgent:
    """Agente especializado em enriquecer descrições genéricas de eventos."""

    def __init__(self):
        # Agent para busca web com Perplexity
        self.search_agent = Agent(
            name="Event Search Agent",
            model=OpenAIChat(
                id=MODELS["search"],  # perplexity/sonar-pro
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
            description="Agente especializado em buscar contexto adicional de eventos",
            instructions=[
                "Buscar informações específicas sobre artistas, venues e eventos",
                "Focar em fatos verificáveis e fontes confiáveis",
                "Retornar resumo conciso e relevante",
            ],
            markdown=True,
        )

        # Agent para processar e enriquecer com Gemini
        self.processing_agent = Agent(
            name="Event Enrichment Processor",
            model=OpenAIChat(
                id=MODELS["format"],  # google/gemini-2.5-flash
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
            description="Agente especializado em enriquecer descrições de eventos",
            instructions=[
                "Combinar informações existentes com contexto adicional",
                "Manter tom profissional e atrativo",
                "Evitar especulação ou informações não verificadas",
                "Ser conciso e objetivo",
            ],
            markdown=True,
        )

        self.searches_count = 0

    async def enrich_events(self, events: list[dict]) -> dict[str, Any]:
        """Enriquece descrições de eventos que precisam de mais contexto."""

        if not ENRICHMENT_ENABLED:
            logger.info("Enriquecimento desabilitado, pulando...")
            return {
                "enriched_events": events,
                "enrichment_stats": {
                    "total": len(events),
                    "enriched": 0,
                    "searches_used": 0,
                },
            }

        logger.info(f"Analisando {len(events)} eventos para enriquecimento...")

        enriched_events = []
        enrichment_stats = {
            "total": len(events),
            "enriched": 0,
            "searches_used": 0,
            "reasons": [],
        }

        for i, event in enumerate(events):
            if self.searches_count >= ENRICHMENT_MAX_SEARCHES:
                logger.warning(
                    f"Limite de {ENRICHMENT_MAX_SEARCHES} buscas atingido, "
                    f"eventos restantes não serão enriquecidos"
                )
                enriched_events.extend(events[i:])
                break

            needs_enrichment, reason = self._needs_enrichment(event)

            if needs_enrichment:
                logger.info(
                    f"Enriquecendo evento {i+1}/{len(events)}: "
                    f"{event.get('titulo', 'Sem título')} ({reason})"
                )

                enriched_event = await self._enrich_single_event(event, reason)
                enriched_events.append(enriched_event)
                enrichment_stats["enriched"] += 1
                enrichment_stats["reasons"].append(reason)
            else:
                logger.debug(
                    f"Evento {i+1}/{len(events)} não precisa de enriquecimento: "
                    f"{event.get('titulo', 'Sem título')}"
                )
                enriched_events.append(event)

        enrichment_stats["searches_used"] = self.searches_count

        logger.info(
            f"Enriquecimento concluído: {enrichment_stats['enriched']}/{enrichment_stats['total']} "
            f"eventos enriquecidos ({self.searches_count} buscas utilizadas)"
        )

        return {
            "enriched_events": enriched_events,
            "enrichment_stats": enrichment_stats,
        }

    def _needs_enrichment(self, event: dict) -> tuple[bool, str]:
        """Verifica se evento precisa de enriquecimento e retorna o motivo."""
        desc = event.get("descricao_enriquecida") or event.get("descricao", "")
        desc_words = len(desc.split())

        # Critério 1: Descrição muito curta
        if desc_words < ENRICHMENT_MIN_DESC_LENGTH:
            return True, f"descrição curta ({desc_words} palavras)"

        # Critério 2: Contém termos genéricos
        desc_lower = desc.lower()
        for term in ENRICHMENT_GENERIC_TERMS:
            if term in desc_lower:
                return True, f"termo genérico: '{term}'"

        # Critério 3: Link quebrado/ausente (se tiver essa info)
        if event.get("link_valid") is False:
            return True, "link quebrado/inválido"

        # Evento OK, não precisa enriquecimento
        return False, ""

    async def _enrich_single_event(self, event: dict, reason: str) -> dict:
        """Enriquece um único evento com busca e processamento LLM."""

        # 1. Construir query de busca inteligente
        search_query = self._build_search_query(event, reason)

        # 2. Buscar contexto com Perplexity
        search_results = await self._search_context(search_query)
        self.searches_count += 1

        # 3. Processar e enriquecer descrição com Gemini
        enriched_desc = await self._process_enrichment(event, search_results, reason)

        # 4. Atualizar evento
        event["descricao_original"] = event.get("descricao_enriquecida") or event.get("descricao", "")
        event["descricao"] = enriched_desc
        event["enriched"] = True
        event["enrichment_reason"] = reason

        return event

    def _build_search_query(self, event: dict, reason: str) -> str:
        """Constrói query otimizada para Perplexity baseada no motivo."""
        titulo = event.get("titulo", "")
        local = event.get("local", "")
        categoria = event.get("categoria", "")

        # Estratégias de busca baseadas no motivo
        if "descrição curta" in reason:
            # Buscar biografia/contexto completo
            return f"{titulo} {local} Rio de Janeiro biografia contexto detalhes público programação"

        elif "termo genérico" in reason:
            # Focar em quem são os artistas/participantes
            if "músicos" in reason or "artistas" in reason:
                return f"{titulo} {local} artistas participantes músicos elenco biografia"
            elif "consultar" in reason:
                return f"{titulo} {local} preço ingresso valores ticket faixa de preço"
            else:
                return f"{titulo} {local} detalhes programação informações completas"

        elif "link quebrado" in reason:
            # Tentar confirmar se evento existe
            return f"{titulo} {local} {event.get('data', '')} Rio de Janeiro confirmação agenda oficial"

        else:
            # Query genérica
            return f"{titulo} {local} Rio de Janeiro detalhes informações completas"

    async def _search_context(self, query: str) -> str:
        """Busca contexto adicional com Perplexity Sonar Pro."""

        prompt = f"""Busque informações específicas sobre este evento no Rio de Janeiro:

{query}

Retorne um resumo conciso (máximo 300 palavras) contendo:
- Nome completo de artistas/participantes (se houver)
- Estilo/gênero artístico
- Contexto histórico/cultural relevante
- Público-alvo
- Informações práticas (duração, classificação, etc)

Foque apenas em FATOS VERIFICÁVEIS de fontes confiáveis. Se não encontrar informações, diga explicitamente."""

        try:
            response = self.search_agent.run(prompt)
            return response.content
        except Exception as e:
            logger.error(f"Erro na busca de contexto: {e}")
            return f"Não foi possível obter contexto adicional: {str(e)}"

    async def _process_enrichment(
        self, event: dict, search_results: str, reason: str
    ) -> str:
        """Processa resultados da busca e cria descrição enriquecida."""

        original_desc = event.get("descricao_enriquecida") or event.get("descricao", "")
        titulo = event.get("titulo", "")

        prompt = f"""Você é um especialista em eventos culturais do Rio de Janeiro.

EVENTO:
Título: {titulo}
Descrição Atual: {original_desc}
Motivo do Enriquecimento: {reason}

CONTEXTO ADICIONAL ENCONTRADO:
{search_results}

TAREFA:
Crie uma descrição enriquecida e atrativa que:
1. Mantém informações corretas da descrição original
2. Adiciona contexto relevante do material encontrado
3. É objetiva e profissional (sem exageros)
4. Tem no máximo {MAX_DESCRIPTION_LENGTH} palavras
5. Foca em informações úteis para quem vai decidir se compra ingresso

IMPORTANTE:
- NÃO invente informações
- Se o contexto adicional não trouxe nada útil, apenas melhore a redação da descrição original
- Mantenha fatos como: data, horário, local, preço (não altere)
- Evite frases genéricas como "não perca", "imperdível", etc

Retorne APENAS a nova descrição, sem explicações adicionais."""

        try:
            response = self.processing_agent.run(prompt)
            content = response.content.strip()

            # Remover possíveis markdown artifacts
            content = content.replace("**", "").replace("*", "")

            # Limitar tamanho
            words = content.split()
            if len(words) > MAX_DESCRIPTION_LENGTH:
                content = " ".join(words[:MAX_DESCRIPTION_LENGTH]) + "..."

            return content

        except Exception as e:
            logger.error(f"Erro no processamento do enriquecimento: {e}")
            # Fallback: retornar descrição original
            return original_desc
