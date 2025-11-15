"""Utilitários para normalização e acesso a campos de eventos."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventNormalizer:
    """Classe utilitária para normalizar acesso a campos de eventos."""

    # Mapeamento de campo canônico -> aliases possíveis
    FIELD_ALIASES = {
        'titulo': ['titulo', 'nome', 'title', 'event_name'],
        'link': ['link_ingresso', 'link_referencia', 'link', 'ticket_link', 'url'],
        'horario': ['horario', 'time', 'hora'],
        'preco': ['preco', 'price', 'valor', 'ticket_price'],
        'local': ['local', 'venue', 'lugar'],
        'data': ['data', 'date', 'dia'],
        'categoria': ['categoria', 'category', 'tipo'],
        'descricao': ['descricao', 'description', 'resumo', 'desc'],
        'fonte': ['fonte', 'source', 'origem'],
    }

    @staticmethod
    def get_field(event: dict, field_name: str, default: Any = "") -> Any:
        """Obtém campo de evento com suporte a aliases.

        Args:
            event: Dicionário do evento
            field_name: Nome do campo (usa nome canônico)
            default: Valor padrão se campo não encontrado

        Returns:
            Valor do campo ou default

        Example:
            >>> event = {"nome": "Show de Jazz", "ticket_link": "http://..."}
            >>> EventNormalizer.get_field(event, 'titulo')
            'Show de Jazz'
            >>> EventNormalizer.get_field(event, 'link')
            'http://...'
        """
        # Tentar aliases do campo
        aliases = EventNormalizer.FIELD_ALIASES.get(field_name, [field_name])

        for alias in aliases:
            value = event.get(alias)
            if value is not None and value != "":
                return value

        return default

    @staticmethod
    def normalize_event(event: dict) -> dict:
        """Normaliza todos os campos de um evento para nomes canônicos.

        Args:
            event: Evento com campos possivelmente variados

        Returns:
            Novo evento com campos normalizados

        Example:
            >>> event = {"nome": "Show", "ticket_link": "http://..."}
            >>> normalized = EventNormalizer.normalize_event(event)
            >>> normalized
            {'titulo': 'Show', 'link': 'http://...', ...}
        """
        normalized = {}

        # Para cada campo canônico, buscar valor com aliases
        for canonical, aliases in EventNormalizer.FIELD_ALIASES.items():
            for alias in aliases:
                if alias in event:
                    normalized[canonical] = event[alias]
                    break

        # Adicionar campos que não têm aliases (manter como estão)
        for key, value in event.items():
            if key not in normalized and not any(key in aliases for aliases in EventNormalizer.FIELD_ALIASES.values()):
                normalized[key] = value

        return normalized

    @staticmethod
    def has_field(event: dict, field_name: str) -> bool:
        """Verifica se evento tem campo (considerando aliases).

        Args:
            event: Dicionário do evento
            field_name: Nome do campo

        Returns:
            True se campo existe e não é vazio
        """
        value = EventNormalizer.get_field(event, field_name, default=None)
        return value is not None and value != ""

    @staticmethod
    def get_required_fields(event: dict, fields: list[str]) -> dict[str, Any]:
        """Obtém múltiplos campos obrigatórios.

        Args:
            event: Dicionário do evento
            fields: Lista de campos a extrair

        Returns:
            Dict com campos encontrados

        Raises:
            ValueError: Se algum campo obrigatório está ausente
        """
        result = {}
        missing = []

        for field in fields:
            value = EventNormalizer.get_field(event, field, default=None)
            if value is None or value == "":
                missing.append(field)
            else:
                result[field] = value

        if missing:
            raise ValueError(f"Campos obrigatórios ausentes: {', '.join(missing)}")

        return result

    @staticmethod
    def get_link(event: dict) -> str | None:
        """Obtém link do evento (helper específico).

        Args:
            event: Dicionário do evento

        Returns:
            Link do evento ou None
        """
        return EventNormalizer.get_field(event, 'link', default=None)

    @staticmethod
    def get_title(event: dict) -> str:
        """Obtém título do evento (helper específico).

        Args:
            event: Dicionário do evento

        Returns:
            Título do evento ou string vazia
        """
        return EventNormalizer.get_field(event, 'titulo', default="")

    @staticmethod
    def get_venue(event: dict) -> str:
        """Obtém local do evento (helper específico).

        Args:
            event: Dicionário do evento

        Returns:
            Local do evento ou string vazia
        """
        return EventNormalizer.get_field(event, 'local', default="")

    @staticmethod
    def get_date(event: dict) -> str:
        """Obtém data do evento (helper específico).

        Args:
            event: Dicionário do evento

        Returns:
            Data do evento ou string vazia
        """
        return EventNormalizer.get_field(event, 'data', default="")

    @staticmethod
    def get_category(event: dict) -> str:
        """Obtém categoria do evento (helper específico).

        Args:
            event: Dicionário do evento

        Returns:
            Categoria do evento ou string vazia
        """
        return EventNormalizer.get_field(event, 'categoria', default="")

    @staticmethod
    def set_field(event: dict, field_name: str, value: Any) -> None:
        """Define valor de campo (in-place) usando nome canônico.

        Args:
            event: Dicionário do evento (modificado in-place)
            field_name: Nome do campo canônico
            value: Valor a definir
        """
        event[field_name] = value

    @staticmethod
    def merge_events(base_event: dict, update_event: dict, overwrite: bool = False) -> dict:
        """Mescla dois eventos, preenchendo campos ausentes.

        Args:
            base_event: Evento base
            update_event: Evento com atualizações
            overwrite: Se True, sobrescreve campos existentes

        Returns:
            Novo evento mesclado
        """
        merged = base_event.copy()

        for canonical in EventNormalizer.FIELD_ALIASES.keys():
            base_value = EventNormalizer.get_field(base_event, canonical, default=None)
            update_value = EventNormalizer.get_field(update_event, canonical, default=None)

            # Se base não tem valor, usar update
            if base_value is None or base_value == "":
                if update_value is not None and update_value != "":
                    merged[canonical] = update_value

            # Se overwrite=True e update tem valor, sobrescrever
            elif overwrite and update_value is not None and update_value != "":
                merged[canonical] = update_value

        return merged
