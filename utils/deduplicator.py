"""Utilitário para deduplicação de eventos."""

import logging
from typing import Any
from utils.text_helpers import normalize_string
from utils.event_identity import EventIdentity

logger = logging.getLogger(__name__)


def deduplicate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove eventos duplicados baseado em (titulo, data, horario).

    Args:
        events: Lista de eventos a deduplic ar

    Returns:
        Lista de eventos únicos (mantém o primeiro encontrado)
    """
    if not events:
        return []

    seen = set()
    unique_events = []
    duplicates_removed = 0

    for event in events:
        # Usar EventIdentity para gerar chave de deduplicação
        dedup_key = EventIdentity.get_dedup_key(event)

        if dedup_key in seen:
            duplicates_removed += 1
            data = event.get("data", "")
            horario = event.get("horario", "")
            logger.info(
                f"   🗑️  Duplicata removida: '{event.get('titulo')}' "
                f"({data} {horario})"
            )
            continue

        seen.add(dedup_key)
        unique_events.append(event)

    if duplicates_removed > 0:
        logger.info(
            f"✓ Deduplicação: {duplicates_removed} eventos duplicados removidos, "
            f"{len(unique_events)} únicos mantidos"
        )

    return unique_events
