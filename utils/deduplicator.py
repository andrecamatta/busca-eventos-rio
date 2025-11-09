"""Utilitário para deduplicação de eventos."""

import logging
from typing import Any
from utils.text_helpers import normalize_string
from utils.event_identity import EventIdentity

logger = logging.getLogger(__name__)


def deduplicate_events(events: list[dict[str, Any]], use_similarity: bool = True, threshold: float = 0.92) -> list[dict[str, Any]]:
    """Remove eventos duplicados baseado em (titulo, data, horario) com detecção semântica.

    Args:
        events: Lista de eventos a deduplicar
        use_similarity: Se True, usa detecção semântica para duplicatas (padrão: True)
        threshold: Threshold de similaridade de título para consideração de duplicata (padrão: 0.92)

    Returns:
        Lista de eventos únicos (mantém o primeiro encontrado)
    """
    if not events:
        return []

    # PASSO 1: Deduplicação exata (chave baseada em título+data+horário)
    seen_exact = set()
    unique_events = []
    duplicates_exact = 0

    for event in events:
        # Usar EventIdentity para gerar chave de deduplicação exata
        dedup_key = EventIdentity.get_dedup_key(event)

        if dedup_key in seen_exact:
            duplicates_exact += 1
            data = event.get("data", "")
            horario = event.get("horario", "")
            logger.info(
                f"   🗑️  Duplicata exata removida: '{event.get('titulo')}' "
                f"({data} {horario})"
            )
            continue

        seen_exact.add(dedup_key)
        unique_events.append(event)

    # PASSO 2: Deduplicação semântica (detectar títulos similares na mesma data/hora)
    duplicates_semantic = 0

    if use_similarity and len(unique_events) > 1:
        final_events = []
        seen_indices = set()

        for i, event1 in enumerate(unique_events):
            if i in seen_indices:
                continue

            # Verificar se existe evento similar posterior
            is_duplicate = False
            for j in range(i + 1, len(unique_events)):
                if j in seen_indices:
                    continue

                event2 = unique_events[j]

                # Usar nova função de similaridade
                if EventIdentity.events_are_similar(event1, event2, threshold=threshold):
                    duplicates_semantic += 1
                    seen_indices.add(j)

                    similarity = EventIdentity.calculate_title_similarity(
                        event1.get("titulo", ""),
                        event2.get("titulo", "")
                    )

                    logger.info(
                        f"   🔄 Duplicata semântica removida ({similarity:.1%} similar): "
                        f"'{event2.get('titulo')}' → '{event1.get('titulo')}' "
                        f"({event1.get('data')} {event1.get('horario')})"
                    )

            # Manter o primeiro evento encontrado
            if not is_duplicate:
                final_events.append(event1)

        unique_events = final_events

    # Log final
    total_removed = duplicates_exact + duplicates_semantic
    if total_removed > 0:
        logger.info(
            f"✓ Deduplicação: {total_removed} eventos duplicados removidos "
            f"(exatas: {duplicates_exact}, semânticas: {duplicates_semantic}), "
            f"{len(unique_events)} únicos mantidos"
        )

    return unique_events
