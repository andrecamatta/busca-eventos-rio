"""Classificador automático de eventos em categorias usando LLM."""

import asyncio
import json
import logging
import re
from typing import Any

from utils.agent_factory import AgentFactory
from utils.json_helpers import safe_json_parse

logger = logging.getLogger(__name__)

# Categorias válidas (extraídas de config.EVENT_CATEGORIES)
VALID_CATEGORIES = [
    "Jazz",
    "Música Clássica",
    "Teatro",
    "Comédia",
    "Cinema",
    "Feira Gastronômica",
    "Feira de Artesanato",
    "Outdoor/Parques",
    "Cursos de Café"
]

CLASSIFICATION_PROMPT = """Você é um classificador de eventos culturais. Classifique cada evento abaixo em UMA das 9 categorias válidas:

CATEGORIAS VÁLIDAS:
1. Jazz - Shows de jazz, bossa nova, jam sessions de jazz, música instrumental
2. Música Clássica - Concertos, orquestras, música erudita, ópera, coral, recitais
3. Teatro - Peças dramáticas, performances teatrais (EXCETO comédia)
4. Comédia - Stand-up, peças de comédia, shows de humor
5. Cinema - Sessões de cinema, mostras de filmes, festivais de cinema
6. Feira Gastronômica - Feiras de comida, food festivals (fim de semana)
7. Feira de Artesanato - Feiras de arte, artesanato, design (fim de semana)
8. Outdoor/Parques - Eventos ao ar livre em parques (fim de semana, culturais)
9. Cursos de Café - Workshops, cursos e degustações de café

REGRAS:
- Use EXATAMENTE o nome da categoria acima (ex: "Jazz", não "jazz" ou "Shows de Jazz")
- Se o evento se encaixa em múltiplas categorias, escolha a MAIS ESPECÍFICA
- Se NÃO se encaixa em nenhuma, use "Geral"
- Considere: título, descrição E local/venue do evento
- PRIORIZE jazz autêntico sobre tributos quando houver dúvida

EVENTOS PARA CLASSIFICAR:
{eventos_json}

RETORNE UM JSON com esta estrutura EXATA:
{{
  "classifications": [
    {{"id": 0, "categoria": "Jazz"}},
    {{"id": 1, "categoria": "Música Clássica"}},
    ...
  ]
}}

IMPORTANTE: IDs devem corresponder à ordem dos eventos na lista de entrada.
"""


async def classify_events(events: list[dict[str, Any]], batch_size: int = 25) -> list[dict[str, Any]]:
    """Reclassifica todos os eventos em uma das 9 categorias válidas.

    Args:
        events: Lista de eventos a classificar
        batch_size: Quantos eventos processar por chamada LLM (default: 25)

    Returns:
        Lista de eventos com campo 'categoria' atualizado
    """
    if not events:
        return []

    # Criar agente de classificação (usa gemini-2.5-flash)
    classifier = AgentFactory.create_agent(
        name="Event Classifier",
        model_type="light",  # gemini-2.5-flash (rápido e barato)
        description="Classificador rápido de eventos em categorias",
        instructions=["Classificar eventos culturais nas 9 categorias válidas"],
        markdown=True,
    )

    # Dividir eventos em batches
    batches = [events[i:i + batch_size] for i in range(0, len(events), batch_size)]

    logger.info(f"🏷️  Classificando {len(events)} eventos em {len(batches)} batches de {batch_size}...")

    # Processar batches em paralelo
    classified_batches = await asyncio.gather(
        *[_classify_batch(classifier, batch, i) for i, batch in enumerate(batches)]
    )

    # Flatten results
    classified_events = []
    for batch_result in classified_batches:
        classified_events.extend(batch_result)

    # Estatísticas de distribuição
    category_counts = {}
    for event in classified_events:
        cat = event.get("categoria", "Geral")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    logger.info("📊 Distribuição de categorias após classificação:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        logger.info(f"   - {cat}: {count} eventos")

    return classified_events


async def _classify_batch(
    classifier: Any,
    batch: list[dict[str, Any]],
    batch_num: int
) -> list[dict[str, Any]]:
    """Classifica um batch de eventos usando LLM.

    Args:
        classifier: Agente de classificação (Gemini Flash)
        batch: Lista de eventos a classificar neste batch
        batch_num: Número do batch (para logging)

    Returns:
        Lista de eventos com categorias atualizadas
    """
    # Preparar dados mínimos para LLM (reduzir tokens)
    eventos_minimos = []
    for i, event in enumerate(batch):
        eventos_minimos.append({
            "id": i,
            "titulo": event.get("titulo", ""),
            "descricao": (event.get("descricao", "") or "")[:300],  # Limitar descrição
            "local": event.get("local", ""),
        })

    # Montar prompt
    prompt = CLASSIFICATION_PROMPT.format(
        eventos_json=json.dumps(eventos_minimos, ensure_ascii=False, indent=2)
    )

    try:
        # Chamar LLM (síncrono, pois agent.run não é async)
        response = classifier.run(prompt)

        # Parse resposta
        result_json = _extract_json(response.content)
        classifications = result_json.get("classifications", [])

        # Aplicar classificações aos eventos originais
        changes_count = 0
        for i, event in enumerate(batch):
            classification = next((c for c in classifications if c.get("id") == i), None)
            if classification:
                new_category = classification.get("categoria", "Geral")

                # Validar categoria
                if new_category not in VALID_CATEGORIES and new_category != "Geral":
                    logger.warning(
                        f"⚠️  Categoria inválida '{new_category}' para evento "
                        f"'{event.get('titulo', '')}', usando 'Geral'"
                    )
                    new_category = "Geral"

                # Verificar se houve mudança
                old_category = event.get("categoria", "Geral")
                if old_category != new_category:
                    changes_count += 1
                    logger.debug(
                        f"   '{event.get('titulo', '')[:50]}': {old_category} → {new_category}"
                    )

                event["categoria"] = new_category
            else:
                # Fallback se LLM não retornou classificação para este evento
                if "categoria" not in event:
                    event["categoria"] = "Geral"

        logger.info(
            f"✓ Batch {batch_num + 1}/{batch_num + 1} classificado "
            f"({len(batch)} eventos, {changes_count} reclassificações)"
        )
        return batch

    except Exception as e:
        logger.error(f"❌ Erro ao classificar batch {batch_num + 1}: {e}")
        # Fallback: manter categorias existentes ou usar "Geral"
        for event in batch:
            if "categoria" not in event or not event["categoria"]:
                event["categoria"] = "Geral"
        return batch


def _extract_json(text: str) -> dict:
    """Extrai JSON de resposta do LLM (remove markdown code blocks).

    Args:
        text: Resposta do LLM (pode conter markdown)

    Returns:
        Dict parseado do JSON

    Raises:
        json.JSONDecodeError: Se não conseguir parsear JSON
    """
    # Usar json_helpers que já implementa essa lógica
    return safe_json_parse(text, default={})
