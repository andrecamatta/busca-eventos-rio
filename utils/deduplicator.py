"""Utilitário para deduplicação de eventos."""

import logging
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)


def normalize_string(text: str) -> str:
    """Normaliza string para comparação (remove acentos, normaliza pontuação, lowercase, espaços extras)."""
    if not text:
        return ""

    # Normalizar pontuação: substituir travessões e variantes por hífen simples
    # U+2013 EN DASH (–), U+2014 EM DASH (—), U+2015 HORIZONTAL BAR (―)
    text = text.replace('–', '-').replace('—', '-').replace('―', '-')

    # Remover outros caracteres de pontuação problemáticos
    text = text.replace('|', '-').replace('/', '-')

    # Remover acentos (NFD decomposition + remoção de caracteres de combinação)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')

    # Lowercase e remover espaços extras
    text = text.lower().strip()
    text = ' '.join(text.split())

    return text


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
        # Criar chave única baseada em titulo normalizado + data + horario
        titulo_norm = normalize_string(event.get("titulo", ""))
        data = event.get("data", "")
        horario = event.get("horario", "")

        # Chave de deduplicação
        dedup_key = (titulo_norm, data, horario)

        if dedup_key in seen:
            duplicates_removed += 1
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
