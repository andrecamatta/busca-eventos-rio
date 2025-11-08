"""Utilitário para detectar e consolidar eventos contínuos (exposições, mostras, temporadas)."""

import logging
import random
from datetime import datetime
from typing import Any

from config import CONTINUOUS_EVENT_KEYWORDS, CONTINUOUS_EVENT_TYPES

logger = logging.getLogger(__name__)


def is_continuous_event(event: dict) -> tuple[bool, str | None]:
    """
    Detecta se um evento é contínuo (exposição, mostra, temporada).

    Args:
        event: Dicionário com dados do evento

    Returns:
        Tuple (is_continuous, tipo_temporada)
        - is_continuous: True se for evento contínuo
        - tipo_temporada: Tipo identificado (Exposição, Mostra, etc.) ou None
    """
    titulo = event.get("titulo", "").lower()
    descricao = (event.get("descricao") or "").lower()

    # Verificar keywords em título e descrição
    texto_completo = f"{titulo} {descricao}"

    for keyword in CONTINUOUS_EVENT_KEYWORDS:
        if keyword.lower() in texto_completo:
            # Identificar tipo específico
            tipo = CONTINUOUS_EVENT_TYPES.get(keyword, "Exposição")
            logger.debug(f"Evento contínuo detectado: '{event.get('titulo')}' (tipo: {tipo})")
            return True, tipo

    return False, None


def consolidate_continuous_events(events: list[dict]) -> list[dict]:
    """
    Consolida eventos contínuos removendo duplicatas e escolhendo uma data aleatória.

    Exposições/mostras com o mesmo título e local aparecem apenas uma vez,
    com uma data aleatória dentro do período de vigência.

    Args:
        events: Lista de eventos

    Returns:
        Lista consolidada (eventos pontuais + 1 entrada por exposição)
    """
    continuous_events = {}  # {(titulo_normalizado, local): [eventos]}
    pontual_events = []

    for event in events:
        is_cont, tipo = is_continuous_event(event)

        if is_cont:
            # Marcar como temporada
            event["is_temporada"] = True
            event["tipo_temporada"] = tipo

            # Agrupar por título + local (normalizado)
            titulo_norm = event.get("titulo", "").lower().strip()
            local_norm = event.get("local", "").lower().strip()
            key = (titulo_norm, local_norm)

            if key not in continuous_events:
                continuous_events[key] = []
            continuous_events[key].append(event)
        else:
            # Evento pontual - manter como está
            pontual_events.append(event)

    # Consolidar eventos contínuos (escolher 1 representante por grupo)
    consolidated_continuous = []
    for (titulo_norm, local_norm), event_group in continuous_events.items():
        if not event_group:
            continue

        # Escolher aleatoriamente um representante do grupo
        representative = random.choice(event_group)

        # Logar consolidação
        if len(event_group) > 1:
            logger.info(
                f"📅 Consolidado evento contínuo: '{representative.get('titulo')}' "
                f"({len(event_group)} datas -> 1 entrada aleatória)"
            )

        consolidated_continuous.append(representative)

    # Retornar eventos pontuais + eventos contínuos consolidados
    result = pontual_events + consolidated_continuous

    logger.info(
        f"📅 Consolidação: {len(events)} eventos -> {len(result)} "
        f"(pontuais: {len(pontual_events)}, contínuos: {len(consolidated_continuous)})"
    )

    return result
