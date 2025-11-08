"""
Utilitários centralizados para identidade e comparação de eventos.
Define diferentes estratégias para determinar se eventos são duplicados/iguais.
"""

from typing import Tuple
from utils.text_helpers import normalize_string


class EventIdentity:
    """
    Classe centralizada para determinar identidade de eventos.
    Fornece diferentes estratégias de identificação dependendo do contexto.
    """

    @staticmethod
    def get_dedup_key(event: dict) -> Tuple[str, str, str]:
        """
        Gera chave para deduplicação precisa de eventos.
        Usado quando queremos identificar eventos exatamente iguais.

        Baseado em: título normalizado + data + horário

        Args:
            event: Dicionário do evento

        Returns:
            Tupla (título_normalizado, data, horário)

        Examples:
            >>> event = {"titulo": "Show de Jazz", "data": "15/11/2025", "horario": "20:00"}
            >>> EventIdentity.get_dedup_key(event)
            ('show de jazz', '15/11/2025', '20:00')
        """
        titulo_norm = normalize_string(event.get("titulo", ""))
        data = event.get("data", "")
        horario = event.get("horario", "")

        return (titulo_norm, data, horario)

    @staticmethod
    def get_merge_key(event: dict) -> str:
        """
        Gera chave para merge de eventos de diferentes fontes.
        Usado para identificar o mesmo evento vindo de fontes diferentes.

        Baseado em: título + data + local (todos normalizados)

        Args:
            event: Dicionário do evento

        Returns:
            String no formato "titulo|data|local"

        Examples:
            >>> event = {"titulo": "Show de Jazz", "data": "15/11/2025", "local": "Blue Note"}
            >>> EventIdentity.get_merge_key(event)
            'show de jazz|15/11/2025|blue note'
        """
        # Suporta tanto 'titulo' quanto 'titulo_evento'
        titulo = event.get("titulo") or event.get("titulo_evento", "")
        data = event.get("data", "")
        local = event.get("local", "")

        # Normalizar para comparação
        titulo_norm = titulo.lower().strip()
        local_norm = local.lower().strip()

        return f"{titulo_norm}|{data}|{local_norm}"

    @staticmethod
    def get_filter_key(event: dict, title_key: str = "titulo") -> str:
        """
        Gera chave para filtro básico de eventos duplicados.
        Usado para remoção rápida de duplicatas óbvias.

        Baseado em: título + data (normalizados)

        Args:
            event: Dicionário do evento
            title_key: Nome da chave que contém o título (padrão: "titulo")

        Returns:
            String no formato "titulo|data"

        Examples:
            >>> event = {"titulo": "Show de Jazz", "data": "15/11/2025"}
            >>> EventIdentity.get_filter_key(event)
            'show de jazz|15/11/2025'
        """
        # Suporta diferentes chaves de título
        if title_key in event:
            titulo = event[title_key]
        else:
            titulo = event.get("titulo") or event.get("titulo_evento", "")

        data = event.get("data", "").strip()

        # Normalizar título
        titulo_norm = titulo.lower().strip()

        return f"{titulo_norm}|{data}"

    @staticmethod
    def events_are_duplicates(event1: dict, event2: dict, strategy: str = "dedup") -> bool:
        """
        Verifica se dois eventos são duplicados usando uma estratégia específica.

        Args:
            event1: Primeiro evento
            event2: Segundo evento
            strategy: Estratégia a usar ("dedup", "merge", ou "filter")

        Returns:
            True se eventos são considerados duplicados, False caso contrário

        Examples:
            >>> e1 = {"titulo": "Show", "data": "15/11/2025", "horario": "20:00"}
            >>> e2 = {"titulo": "SHOW", "data": "15/11/2025", "horario": "20:00"}
            >>> EventIdentity.events_are_duplicates(e1, e2, "dedup")
            True
        """
        if strategy == "dedup":
            return EventIdentity.get_dedup_key(event1) == EventIdentity.get_dedup_key(event2)
        elif strategy == "merge":
            return EventIdentity.get_merge_key(event1) == EventIdentity.get_merge_key(event2)
        elif strategy == "filter":
            return EventIdentity.get_filter_key(event1) == EventIdentity.get_filter_key(event2)
        else:
            raise ValueError(f"Estratégia desconhecida: {strategy}")

    @staticmethod
    def get_event_signature(event: dict) -> str:
        """
        Gera assinatura única do evento para logging e debugging.
        Formato legível para humanos.

        Args:
            event: Dicionário do evento

        Returns:
            String descritiva do evento

        Examples:
            >>> event = {"titulo": "Show", "data": "15/11/2025", "local": "Teatro"}
            >>> EventIdentity.get_event_signature(event)
            "Show (15/11/2025 @ Teatro)"
        """
        titulo = event.get("titulo", "Sem título")
        data = event.get("data", "")
        local = event.get("local", "")
        horario = event.get("horario", "")

        parts = [titulo]
        if data:
            date_part = data
            if horario:
                date_part += f" às {horario}"
            parts.append(date_part)
        if local:
            parts.append(f"@ {local}")

        return " - ".join(parts) if len(parts) > 1 else parts[0]
