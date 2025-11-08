"""Utilitário para merge e deduplicação de eventos."""

import logging
from utils.event_identity import EventIdentity

logger = logging.getLogger(__name__)


class EventMerger:
    """Responsável por merge e deduplicação de conjuntos de eventos."""

    @staticmethod
    def get_event_id(event: dict) -> str:
        """
        Gera ID único para evento baseado em titulo, data e local.

        Args:
            event: Dicionário do evento

        Returns:
            String no formato "titulo|data|local" (normalizado)
        """
        return EventIdentity.get_merge_key(event)

    def merge_events(self, events1: dict, events2: dict) -> dict:
        """
        Faz merge de dois conjuntos de eventos, removendo duplicatas.

        Args:
            events1: Primeiro conjunto (dict com verified_events, rejected_events, etc)
            events2: Segundo conjunto (mesmo formato)

        Returns:
            Dicionário merged com:
            - verified_events: eventos únicos dos dois conjuntos
            - rejected_events: rejected de ambos
            - warnings: warnings de ambos
            - duplicates_removed: duplicatas encontradas
        """
        # Extrair eventos
        verified1 = events1.get("verified_events", [])
        verified2 = events2.get("verified_events", [])

        # Criar conjunto de IDs únicos
        seen = set()
        merged_events = []

        # Adicionar eventos do primeiro conjunto
        for event in verified1:
            event_id = self.get_event_id(event)
            if event_id not in seen:
                seen.add(event_id)
                merged_events.append(event)

        # Adicionar eventos do segundo conjunto (apenas novos)
        duplicates_count = 0
        for event in verified2:
            event_id = self.get_event_id(event)
            if event_id not in seen:
                seen.add(event_id)
                merged_events.append(event)
            else:
                duplicates_count += 1

        if duplicates_count > 0:
            logger.info(f"🔄 Removidas {duplicates_count} duplicatas no merge")

        # Combinar rejected e warnings
        rejected1 = events1.get("rejected_events", [])
        rejected2 = events2.get("rejected_events", [])
        warnings1 = events1.get("warnings", [])
        warnings2 = events2.get("warnings", [])

        return {
            "verified_events": merged_events,
            "rejected_events": rejected1 + rejected2,
            "warnings": warnings1 + warnings2,
            "duplicates_removed": (
                events1.get("duplicates_removed", [])
                + events2.get("duplicates_removed", [])
            ),
        }
