"""Consolidador de eventos recorrentes.

Identifica eventos que se repetem em múltiplas datas e os consolida
em uma única entrada com lista de próximas ocorrências.
"""

import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any


class EventConsolidator:
    """Consolida eventos recorrentes em uma única entrada."""

    # Thresholds de similaridade
    TITLE_SIMILARITY_THRESHOLD = 0.90  # 90% de similaridade no título
    TIME_TOLERANCE_MINUTES = 60  # Tolerância de 1h para horários

    def __init__(self):
        """Inicializa consolidador."""
        pass

    def consolidate_recurring_events(self, events: list[dict]) -> list[dict]:
        """Consolida eventos recorrentes.

        Args:
            events: Lista de eventos a consolidar

        Returns:
            Lista de eventos consolidados
        """
        if not events:
            return []

        # Agrupar eventos por similaridade
        groups = self._group_similar_events(events)

        # Consolidar grupos com múltiplas ocorrências
        consolidated = []
        for group in groups:
            if len(group) > 1:
                # Múltiplas ocorrências: consolidar
                consolidated_event = self._merge_group(group)
                consolidated.append(consolidated_event)
            else:
                # Evento único: manter como está
                consolidated.append(group[0])

        # Ordenar por data
        consolidated.sort(key=lambda e: self._parse_date(e.get("data", "")))

        return consolidated

    def _group_similar_events(self, events: list[dict]) -> list[list[dict]]:
        """Agrupa eventos similares.

        Args:
            events: Lista de eventos

        Returns:
            Lista de grupos de eventos similares
        """
        groups = []
        remaining = events.copy()

        while remaining:
            # Pegar primeiro evento não agrupado
            base_event = remaining.pop(0)
            group = [base_event]

            # Encontrar eventos similares
            to_remove = []
            for event in remaining:
                if self._are_similar(base_event, event):
                    group.append(event)
                    to_remove.append(event)

            # Remover eventos agrupados
            for event in to_remove:
                remaining.remove(event)

            groups.append(group)

        return groups

    def _are_similar(self, event1: dict, event2: dict) -> bool:
        """Verifica se dois eventos são similares (recorrentes).

        Args:
            event1: Primeiro evento
            event2: Segundo evento

        Returns:
            True se eventos são similares
        """
        # Extrair campos
        title1 = self._extract_base_title(event1.get("titulo", ""))
        title2 = self._extract_base_title(event2.get("titulo", ""))

        local1 = self._normalize_location(event1.get("local", ""))
        local2 = self._normalize_location(event2.get("local", ""))

        time1 = event1.get("horario", "")
        time2 = event2.get("horario", "")

        # Verificar similaridade
        title_similar = self._calculate_similarity(title1, title2) >= self.TITLE_SIMILARITY_THRESHOLD
        local_same = local1 == local2
        time_similar = self._is_similar_time(time1, time2)

        return title_similar and local_same and time_similar

    def _extract_base_title(self, title: str) -> str:
        """Remove datas do título para extração do título base.

        Args:
            title: Título completo

        Returns:
            Título base sem datas
        """
        # Remover padrões de data (DD/MM/YYYY, DD/MM/YY, etc.)
        cleaned = re.sub(r"\s*—\s*\d{2}/\d{2}/\d{2,4}", "", title)
        cleaned = re.sub(r"\s*-\s*\d{2}/\d{2}/\d{2,4}", "", cleaned)

        # Remover dias da semana
        weekdays = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
        for day in weekdays:
            cleaned = re.sub(rf"\s*\(?{day}[^)]*\)?", "", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    def _normalize_location(self, location: str) -> str:
        """Normaliza nome do local para comparação.

        Args:
            location: Local do evento

        Returns:
            Local normalizado
        """
        # Lowercase e remover acentos
        normalized = location.lower().strip()

        # Remover pontuação extra
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"[,.]$", "", normalized)

        return normalized

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calcula similaridade entre duas strings.

        Args:
            str1: Primeira string
            str2: Segunda string

        Returns:
            Similaridade (0-1)
        """
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def _is_similar_time(self, time1: str, time2: str) -> bool:
        """Verifica se dois horários são similares.

        Args:
            time1: Primeiro horário (HH:MM)
            time2: Segundo horário (HH:MM)

        Returns:
            True se horários são similares
        """
        if not time1 or not time2:
            return False

        try:
            # Extrair horas e minutos
            h1, m1 = map(int, time1.split(":"))
            h2, m2 = map(int, time2.split(":"))

            # Calcular diferença em minutos
            diff_minutes = abs((h1 * 60 + m1) - (h2 * 60 + m2))

            return diff_minutes <= self.TIME_TOLERANCE_MINUTES

        except (ValueError, AttributeError):
            # Formato inválido: considerar diferentes
            return False

    def _merge_group(self, group: list[dict]) -> dict:
        """Merge grupo de eventos recorrentes em um único evento consolidado.

        Args:
            group: Grupo de eventos similares

        Returns:
            Evento consolidado
        """
        # Ordenar por data
        sorted_group = sorted(group, key=lambda e: self._parse_date(e.get("data", "")))

        # Usar primeiro evento como base
        base_event = sorted_group[0].copy()

        # Extrair título base (sem data)
        base_event["titulo"] = self._extract_base_title(base_event["titulo"])

        # Coletar todas as datas e horários
        proximas_datas = []
        for event in sorted_group:
            data = event.get("data", "")
            horario = event.get("horario", "")
            proximas_datas.append({"data": data, "horario": horario})

        # Adicionar informações de recorrência
        base_event["eh_recorrente"] = True
        base_event["total_ocorrencias"] = len(group)
        base_event["proximas_datas"] = proximas_datas

        # Ajustar horário para range se houver variação
        horarios = list({e.get("horario") for e in sorted_group if e.get("horario")})
        if len(horarios) > 1:
            horarios.sort()
            base_event["horario"] = f"{horarios[0]}-{horarios[-1]}"

        # Manter descrição do primeiro evento (geralmente a mais completa)
        # ou consolidar se houver descrições diferentes

        return base_event

    def _parse_date(self, date_str: str) -> datetime:
        """Parse data no formato DD/MM/YYYY.

        Args:
            date_str: Data como string

        Returns:
            Data como datetime (ou datetime.min se inválido)
        """
        try:
            # Remove horário se presente
            date_only = date_str.split()[0] if " " in date_str else date_str
            return datetime.strptime(date_only, "%d/%m/%Y")
        except (ValueError, AttributeError):
            return datetime.min
