"""Utilitário para contagem e análise de eventos por categoria/venue."""

from typing import Any
import logging
from utils.category_registry import CategoryRegistry

logger = logging.getLogger(__name__)


class EventCounter:
    """Classe utilitária para contar eventos por categoria e venue."""

    # Mapeamentos são gerados dinamicamente do CategoryRegistry
    @classmethod
    def _get_category_map(cls) -> dict[str, str]:
        """Gera mapeamento de category_id -> display_name do CategoryRegistry."""
        category_ids = CategoryRegistry.get_all_category_ids()
        return {
            cat_id: CategoryRegistry.get_category_display_name(cat_id)
            for cat_id in category_ids
        }

    @classmethod
    def _get_reverse_map(cls) -> dict[str, str]:
        """Gera mapeamento reverso display_name -> category_id."""
        return {v: k for k, v in cls._get_category_map().items()}

    @staticmethod
    def count_by_category(events: list[dict]) -> dict[str, int]:
        """Conta eventos agrupados por categoria.

        Args:
            events: Lista de eventos com campo 'categoria'

        Returns:
            Dicionário {categoria: contagem}
        """
        counts: dict[str, int] = {}

        for event in events:
            categoria = event.get("categoria", "Desconhecida")
            counts[categoria] = counts.get(categoria, 0) + 1

        return counts

    @staticmethod
    def count_by_venue(events: list[dict]) -> dict[str, int]:
        """Conta eventos agrupados por local.

        Args:
            events: Lista de eventos com campo 'local'

        Returns:
            Dicionário {local: contagem}
        """
        counts: dict[str, int] = {}

        for event in events:
            local = event.get("local", "Desconhecido")
            counts[local] = counts.get(local, 0) + 1

        return counts

    @classmethod
    def normalize_category_name(cls, config_key: str) -> str:
        """Converte nome de config para nome display.

        Args:
            config_key: Chave de categoria (ex: 'musica_classica')

        Returns:
            Nome display (ex: 'Música Clássica')
        """
        # Try CategoryRegistry first
        if CategoryRegistry.is_valid_category(config_key):
            return CategoryRegistry.get_category_display_name(config_key)
        # Fallback to formatted key
        return config_key.replace("_", " ").title()

    @classmethod
    def get_config_key(cls, display_name: str) -> str:
        """Converte nome display para chave de config.

        Args:
            display_name: Nome display (ex: 'Música Clássica')

        Returns:
            Chave de config (ex: 'musica_classica')
        """
        # Use reverse map from CategoryRegistry
        reverse_map = cls._get_reverse_map()
        return reverse_map.get(display_name, display_name.lower().replace(" ", "_"))

    @staticmethod
    def count_events_by_category_config(
        events: list[dict],
        category_configs: dict[str, Any]
    ) -> dict[str, int]:
        """Conta eventos usando keys de configuração.

        Args:
            events: Lista de eventos com campo 'categoria'
            category_configs: Dicionário de configurações por categoria

        Returns:
            Dicionário {config_key: contagem}
        """
        counts: dict[str, int] = {}

        for config_key in category_configs.keys():
            display_name = EventCounter.normalize_category_name(config_key)

            count = sum(
                1 for event in events
                if event.get("categoria") == display_name
            )

            counts[config_key] = count

        return counts

    @staticmethod
    def filter_by_category(events: list[dict], categoria: str) -> list[dict]:
        """Filtra eventos por categoria.

        Args:
            events: Lista de eventos
            categoria: Nome da categoria (display name ou config key)

        Returns:
            Lista de eventos da categoria especificada
        """
        # Aceitar tanto display name quanto config key
        display_name = EventCounter.normalize_category_name(categoria)

        return [
            event for event in events
            if event.get("categoria") in [categoria, display_name]
        ]

    @staticmethod
    def filter_by_venue(events: list[dict], local: str) -> list[dict]:
        """Filtra eventos por local.

        Args:
            events: Lista de eventos
            local: Nome do local

        Returns:
            Lista de eventos no local especificado
        """
        return [
            event for event in events
            if event.get("local") == local
        ]

    @staticmethod
    def get_categories_summary(events: list[dict]) -> str:
        """Gera resumo de eventos por categoria em formato texto.

        Args:
            events: Lista de eventos

        Returns:
            String com resumo formatado
        """
        counts = EventCounter.count_by_category(events)

        if not counts:
            return "Nenhum evento encontrado"

        lines = ["Eventos por categoria:"]
        for categoria, count in sorted(counts.items()):
            lines.append(f"  • {categoria}: {count}")

        return "\n".join(lines)

    @staticmethod
    def get_venues_summary(events: list[dict]) -> str:
        """Gera resumo de eventos por local em formato texto.

        Args:
            events: Lista de eventos

        Returns:
            String com resumo formatado
        """
        counts = EventCounter.count_by_venue(events)

        if not counts:
            return "Nenhum evento encontrado"

        lines = ["Eventos por local:"]
        # Ordenar por contagem (decrescente) e depois alfabeticamente
        sorted_venues = sorted(counts.items(), key=lambda x: (-x[1], x[0]))

        for local, count in sorted_venues:
            lines.append(f"  • {local}: {count}")

        return "\n".join(lines)
