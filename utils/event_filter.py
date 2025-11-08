"""
Sistema de filtragem de eventos com Strategy Pattern.

Centraliza lógica de filtragem duplicada entre agentes, permitindo
composição de filtros reutilizáveis e testáveis.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.text_helpers import normalize_string

logger = logging.getLogger(__name__)


class EventFilter(ABC):
    """
    Interface abstrata para filtros de eventos.

    Cada filtro implementa uma regra específica de validação.
    """

    @abstractmethod
    def should_include(self, event: Dict[str, Any]) -> bool:
        """
        Determina se evento deve ser incluído.

        Args:
            event: Dicionário com dados do evento

        Returns:
            True se evento passa no filtro, False caso contrário
        """
        pass

    @abstractmethod
    def get_rejection_reason(self, event: Dict[str, Any]) -> str:
        """
        Retorna razão de rejeição para logging/debugging.

        Args:
            event: Dicionário com dados do evento

        Returns:
            String descrevendo por que evento foi rejeitado
        """
        pass


class DateRangeFilter(EventFilter):
    """Filtra eventos fora do range de datas válido."""

    def __init__(self, start_date: datetime, end_date: datetime):
        """
        Args:
            start_date: Data de início do período válido
            end_date: Data de fim do período válido
        """
        self.start_date = start_date.date() if hasattr(start_date, 'date') else start_date
        self.end_date = end_date.date() if hasattr(end_date, 'date') else end_date

    def should_include(self, event: Dict[str, Any]) -> bool:
        """Verifica se data do evento está no range."""
        date_str = event.get("data", "")
        if not date_str:
            return False  # Sem data = rejeitar

        try:
            # Parsear data (assume formato DD/MM/YYYY)
            event_date = datetime.strptime(date_str.split()[0], "%d/%m/%Y").date()
            return self.start_date <= event_date <= self.end_date
        except (ValueError, IndexError):
            return False  # Data inválida = rejeitar

    def get_rejection_reason(self, event: Dict[str, Any]) -> str:
        """Retorna razão de rejeição."""
        date_str = event.get("data", "N/A")
        return f"Data fora do range válido ({self.start_date} a {self.end_date}): {date_str}"


class WeekendFilter(EventFilter):
    """Filtra eventos que não ocorrem em fins de semana."""

    def __init__(self, allow_weekdays: bool = False):
        """
        Args:
            allow_weekdays: Se True, permite eventos em dias de semana também
        """
        self.allow_weekdays = allow_weekdays

    def should_include(self, event: Dict[str, Any]) -> bool:
        """Verifica se evento é em fim de semana."""
        if self.allow_weekdays:
            return True  # Aceita qualquer dia

        date_str = event.get("data", "")
        if not date_str:
            return False

        try:
            event_date = datetime.strptime(date_str.split()[0], "%d/%m/%Y")
            # 5=Saturday, 6=Sunday
            is_weekend = event_date.weekday() in [5, 6]
            return is_weekend
        except (ValueError, IndexError):
            return False

    def get_rejection_reason(self, event: Dict[str, Any]) -> str:
        """Retorna razão de rejeição."""
        date_str = event.get("data", "N/A")
        return f"Evento não é em fim de semana: {date_str}"


class ExcludedWordsFilter(EventFilter):
    """Filtra eventos que contêm palavras excluídas no título ou descrição."""

    def __init__(self, excluded_words: List[str], case_sensitive: bool = False):
        """
        Args:
            excluded_words: Lista de palavras a excluir
            case_sensitive: Se True, comparação é case-sensitive
        """
        self.excluded_words = excluded_words
        self.case_sensitive = case_sensitive

        # Normalizar palavras se não for case-sensitive
        if not case_sensitive:
            self.excluded_words = [w.lower() for w in excluded_words]

    def should_include(self, event: Dict[str, Any]) -> bool:
        """Verifica se evento contém palavras excluídas."""
        titulo = event.get("titulo", "")
        descricao = event.get("descricao", "")

        # Combinar título e descrição
        combined_text = f"{titulo} {descricao}"

        if not self.case_sensitive:
            combined_text = combined_text.lower()

        # Verificar se alguma palavra excluída está presente
        for word in self.excluded_words:
            if word in combined_text:
                return False

        return True

    def get_rejection_reason(self, event: Dict[str, Any]) -> str:
        """Retorna razão de rejeição."""
        titulo = event.get("titulo", "")
        descricao = event.get("descricao", "")
        combined_text = f"{titulo} {descricao}"

        if not self.case_sensitive:
            combined_text = combined_text.lower()

        # Encontrar qual palavra causou rejeição
        for word in self.excluded_words:
            if word in combined_text:
                return f"Contém palavra excluída: '{word}'"

        return "Contém palavra excluída"


class MandatoryFieldsFilter(EventFilter):
    """Filtra eventos sem campos obrigatórios."""

    def __init__(self, required_fields: List[str]):
        """
        Args:
            required_fields: Lista de campos obrigatórios
        """
        self.required_fields = required_fields

    def should_include(self, event: Dict[str, Any]) -> bool:
        """Verifica se evento tem todos os campos obrigatórios."""
        for field in self.required_fields:
            if not event.get(field):
                return False
        return True

    def get_rejection_reason(self, event: Dict[str, Any]) -> str:
        """Retorna razão de rejeição."""
        missing = [f for f in self.required_fields if not event.get(f)]
        if missing:
            return f"Campos obrigatórios ausentes: {', '.join(missing)}"
        return "Campos obrigatórios ausentes"


class DuplicateFilter(EventFilter):
    """Filtra eventos duplicados baseado em chave de identidade."""

    def __init__(self):
        """Inicializa filtro com set vazio de eventos vistos."""
        self.seen_keys = set()

    def _get_event_key(self, event: Dict[str, Any]) -> str:
        """Gera chave única para evento."""
        from utils.event_identity import EventIdentity
        return EventIdentity.get_dedup_key(event)

    def should_include(self, event: Dict[str, Any]) -> bool:
        """Verifica se evento é duplicata."""
        key = self._get_event_key(event)

        # Converter tupla para string hashable
        key_str = str(key)

        if key_str in self.seen_keys:
            return False  # Duplicata

        self.seen_keys.add(key_str)
        return True

    def get_rejection_reason(self, event: Dict[str, Any]) -> str:
        """Retorna razão de rejeição."""
        titulo = event.get("titulo", "N/A")
        data = event.get("data", "N/A")
        return f"Evento duplicado: {titulo} em {data}"

    def reset(self):
        """Limpa set de eventos vistos."""
        self.seen_keys.clear()


class EventFilterPipeline:
    """
    Pipeline de filtros composável para eventos.

    Permite aplicar múltiplos filtros em sequência e coletar estatísticas.

    Example:
        >>> pipeline = EventFilterPipeline()
        >>> pipeline.add_filter(DateRangeFilter(start, end))
        >>> pipeline.add_filter(WeekendFilter())
        >>> pipeline.add_filter(ExcludedWordsFilter(["infantil", "criança"]))
        >>> filtered = pipeline.filter_events(events)
        >>> stats = pipeline.get_stats()
    """

    def __init__(self):
        """Inicializa pipeline vazio."""
        self.filters: List[EventFilter] = []
        self.rejected_events: List[Dict[str, Any]] = []
        self.rejection_reasons: Dict[str, List[str]] = {}

    def add_filter(self, filter_instance: EventFilter) -> "EventFilterPipeline":
        """
        Adiciona filtro ao pipeline.

        Args:
            filter_instance: Instância de EventFilter

        Returns:
            Self para method chaining
        """
        self.filters.append(filter_instance)
        return self

    def filter_events(
        self,
        events: List[Dict[str, Any]],
        log_rejections: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Aplica todos os filtros aos eventos.

        Args:
            events: Lista de eventos a filtrar
            log_rejections: Se True, loga eventos rejeitados

        Returns:
            Lista de eventos que passaram todos os filtros
        """
        # Resetar estatísticas
        self.rejected_events = []
        self.rejection_reasons = {}

        filtered = []

        for event in events:
            passed_all = True
            rejection_reason = None

            # Aplicar cada filtro
            for filter_instance in self.filters:
                if not filter_instance.should_include(event):
                    passed_all = False
                    rejection_reason = filter_instance.get_rejection_reason(event)

                    # Coletar estatísticas
                    filter_name = filter_instance.__class__.__name__
                    if filter_name not in self.rejection_reasons:
                        self.rejection_reasons[filter_name] = []
                    self.rejection_reasons[filter_name].append(rejection_reason)

                    break  # Parar no primeiro filtro que rejeitar

            if passed_all:
                filtered.append(event)
            else:
                self.rejected_events.append({
                    **event,
                    "rejection_reason": rejection_reason
                })

                if log_rejections:
                    titulo = event.get("titulo", "Sem título")
                    logger.debug(f"❌ Evento rejeitado: {titulo} - {rejection_reason}")

        return filtered

    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas de filtragem.

        Returns:
            Dict com total rejeitado, por filtro, etc.
        """
        stats = {
            "total_rejected": len(self.rejected_events),
            "by_filter": {}
        }

        for filter_name, reasons in self.rejection_reasons.items():
            stats["by_filter"][filter_name] = len(reasons)

        return stats

    def clear_filters(self):
        """Remove todos os filtros do pipeline."""
        self.filters = []

    def get_rejected_events(self) -> List[Dict[str, Any]]:
        """Retorna lista de eventos rejeitados com razões."""
        return self.rejected_events
