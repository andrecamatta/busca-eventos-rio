"""
Utilitários centralizados para manipulação de datas e horários.
Elimina duplicação de lógica em múltiplos arquivos.
"""

from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DateParser:
    """Classe centralizada para parsing e manipulação de datas."""

    MONTHS = {
        'jan': '01', 'fev': '02', 'mar': '03', 'abr': '04',
        'mai': '05', 'jun': '06', 'jul': '07', 'ago': '08',
        'set': '09', 'out': '10', 'nov': '11', 'dez': '12'
    }

    @staticmethod
    def parse_month(month_str: str) -> str:
        """
        Converte mês abreviado para número.

        Args:
            month_str: Mês abreviado (ex: 'jan', 'fev')

        Returns:
            Mês como string numérica (ex: '01', '02')
        """
        return DateParser.MONTHS.get(month_str.lower()[:3], '01')

    @staticmethod
    def normalize_time(time_str: str) -> str:
        """
        Converte formato de hora para padrão HH:MM.

        Args:
            time_str: Hora em formatos como '20H00', '20h00', '20:00'

        Returns:
            Hora normalizada no formato 'HH:MM'
        """
        if not time_str:
            return "20:00"

        # Substituir H ou h por :
        normalized = time_str.upper().replace('H', ':').replace('h', ':')

        # Garantir formato HH:MM
        parts = normalized.split(':')
        if len(parts) == 2:
            hour = parts[0].zfill(2)
            minute = parts[1][:2].zfill(2)
            return f"{hour}:{minute}"

        return "20:00"  # Fallback

    @staticmethod
    def determine_year(month: str, day: str) -> str:
        """
        Determina o ano do evento baseado no mês/dia.
        Se a data já passou este ano, assume próximo ano.

        Args:
            month: Mês como string numérica (ex: '01', '12')
            day: Dia como string numérica (ex: '01', '31')

        Returns:
            Ano como string (ex: '2025')
        """
        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.month

        event_month = int(month)
        event_day = int(day)

        # Se o mês já passou este ano, usar próximo ano
        if event_month < current_month:
            return str(current_year + 1)
        elif event_month == current_month and event_day < current_date.day:
            return str(current_year + 1)
        else:
            return str(current_year)

    @staticmethod
    def parse_date(date_str: str, formats: Optional[list[str]] = None) -> Optional[datetime]:
        """
        Parse data em múltiplos formatos possíveis.

        Args:
            date_str: String com data
            formats: Lista de formatos para tentar (padrão: formatos comuns brasileiros)

        Returns:
            datetime object ou None se não conseguir fazer parse
        """
        if not date_str:
            return None

        if formats is None:
            formats = [
                "%d/%m/%Y",
                "%d-%m-%Y",
                "%Y-%m-%d",
                "%d/%m/%y",
                "%d de %B de %Y",
                "%d de %b de %Y"
            ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        logger.warning(f"Não foi possível fazer parse da data: {date_str}")
        return None

    @staticmethod
    def is_weekend(date_str: str, date_format: str = "%d/%m/%Y") -> bool:
        """
        Verifica se uma data é fim de semana (sábado ou domingo).

        Args:
            date_str: Data como string
            date_format: Formato da data (padrão: DD/MM/YYYY)

        Returns:
            True se é fim de semana, False caso contrário
        """
        if not date_str:
            return False

        try:
            data = datetime.strptime(date_str, date_format)
            # weekday(): 0=segunda, 1=terça, ..., 5=sábado, 6=domingo
            return data.weekday() in [5, 6]
        except ValueError:
            logger.warning(f"Data inválida: {date_str}")
            return False

    @staticmethod
    def format_date(date: datetime, output_format: str = "%d/%m/%Y") -> str:
        """
        Formata um objeto datetime para string.

        Args:
            date: Objeto datetime
            output_format: Formato de saída desejado

        Returns:
            Data formatada como string
        """
        return date.strftime(output_format)
