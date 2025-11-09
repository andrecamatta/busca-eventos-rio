"""
Validação rigorosa de datas extraídas comparando com conteúdo do link.
Previne erros críticos de data que penalizam score de qualidade em até 9 pontos.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from bs4 import BeautifulSoup

from utils.date_helpers import DateParser

logger = logging.getLogger(__name__)


class DateValidator:
    """Validador rigoroso de datas extraídas vs conteúdo real do link."""

    # Padrões regex para extrair datas de HTML
    DATE_PATTERNS = [
        # ISO 8601: 2025-11-15, 2025/11/15
        r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b',

        # BR: 15/11/2025, 15-11-2025
        r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b',

        # Texto: "15 de novembro de 2025", "15 nov 2025"
        r'\b(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\b',
        r'\b(\d{1,2})\s+(\w{3,})\s+(\d{4})\b',

        # Schema.org datetime attributes: 2025-11-15T20:00:00
        r'\b(\d{4})-(\d{2})-(\d{2})T\d{2}:\d{2}:\d{2}',
    ]

    # Mapeamento de meses em português
    MONTH_NAMES = {
        'janeiro': '01', 'jan': '01',
        'fevereiro': '02', 'fev': '02',
        'março': '03', 'mar': '03',
        'abril': '04', 'abr': '04',
        'maio': '05', 'mai': '05',
        'junho': '06', 'jun': '06',
        'julho': '07', 'jul': '07',
        'agosto': '08', 'ago': '08',
        'setembro': '09', 'set': '09',
        'outubro': '10', 'out': '10',
        'novembro': '11', 'nov': '11',
        'dezembro': '12', 'dez': '12',
    }

    @staticmethod
    def extract_dates_from_html(html: str) -> List[datetime]:
        """
        Extrai todas as datas encontradas no HTML.

        Prioridade:
        1. Atributos datetime de <time> tags
        2. JSON-LD schema.org startDate/endDate
        3. Data-* attributes
        4. Texto parseado com regex

        Args:
            html: Conteúdo HTML da página

        Returns:
            Lista de objetos datetime encontrados (sem duplicatas)
        """
        if not html:
            return []

        dates = []
        soup = BeautifulSoup(html, 'html.parser')

        # 1. Prioridade: <time datetime="..."> (mais confiável)
        time_tags = soup.find_all('time', attrs={'datetime': True})
        for tag in time_tags:
            dt_str = tag.get('datetime', '')
            parsed = DateValidator._parse_iso_datetime(dt_str)
            if parsed:
                dates.append(parsed)

        # 2. JSON-LD schema.org
        script_tags = soup.find_all('script', type='application/ld+json')
        for script in script_tags:
            try:
                import json
                data = json.loads(script.string)

                # Pode ser dict ou list de dicts
                if isinstance(data, dict):
                    data = [data]

                for item in data:
                    if item.get('@type') == 'Event':
                        start_date = item.get('startDate')
                        if start_date:
                            parsed = DateValidator._parse_iso_datetime(start_date)
                            if parsed:
                                dates.append(parsed)

                        end_date = item.get('endDate')
                        if end_date:
                            parsed = DateValidator._parse_iso_datetime(end_date)
                            if parsed:
                                dates.append(parsed)
            except Exception as e:
                logger.debug(f"Erro ao parsear JSON-LD: {e}")

        # 3. Meta tags
        meta_tags = soup.find_all('meta', attrs={'content': True})
        for tag in meta_tags:
            property_name = tag.get('property', '') + tag.get('name', '')
            if 'date' in property_name.lower():
                content = tag.get('content', '')
                parsed = DateValidator._parse_iso_datetime(content)
                if parsed:
                    dates.append(parsed)

        # 4. Texto do HTML com regex
        text = soup.get_text()
        dates.extend(DateValidator._extract_dates_from_text(text))

        # Remover duplicatas e ordenar
        unique_dates = list(set(dates))
        unique_dates.sort()

        logger.debug(f"📅 Extraídas {len(unique_dates)} datas únicas do HTML")
        return unique_dates

    @staticmethod
    def _parse_iso_datetime(dt_str: str) -> Optional[datetime]:
        """Parse de datetime ISO 8601."""
        if not dt_str:
            return None

        # Remover timezone para simplificar
        dt_str = re.sub(r'[+-]\d{2}:\d{2}$', '', dt_str)
        dt_str = dt_str.replace('Z', '')

        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(dt_str[:len(fmt)], fmt)
            except ValueError:
                continue

        return None

    @staticmethod
    def _extract_dates_from_text(text: str) -> List[datetime]:
        """Extrai datas do texto usando regex."""
        dates = []

        for pattern in DateValidator.DATE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)

            for match in matches:
                groups = match.groups()
                parsed = DateValidator._parse_regex_match(groups, pattern)
                if parsed:
                    dates.append(parsed)

        return dates

    @staticmethod
    def _parse_regex_match(groups: tuple, pattern: str) -> Optional[datetime]:
        """Parse de grupos capturados pelo regex."""
        try:
            # ISO: (year, month, day)
            if 'YYYY' in pattern or groups[0].isdigit() and len(groups[0]) == 4:
                if len(groups) >= 3:
                    year = int(groups[0])
                    month = int(groups[1])
                    day = int(groups[2])
                    return datetime(year, month, day)

            # BR: (day, month, year)
            elif len(groups) >= 3 and groups[2].isdigit() and len(groups[2]) == 4:
                day = int(groups[0])

                # Mês pode ser número ou nome
                if groups[1].isdigit():
                    month = int(groups[1])
                else:
                    month_name = groups[1].lower()[:3]
                    month = int(DateValidator.MONTH_NAMES.get(month_name, '01'))

                year = int(groups[2])
                return datetime(year, month, day)

        except (ValueError, IndexError):
            pass

        return None

    @staticmethod
    def validate_event_date(
        event_date_str: str,
        link_html: str,
        tolerance_days: int = 7
    ) -> dict:
        """
        Valida data do evento comparando com datas encontradas no link.

        Args:
            event_date_str: Data extraída do evento (formato DD/MM/YYYY)
            link_html: HTML do link do evento
            tolerance_days: Tolerância em dias (padrão: 7 dias)

        Returns:
            Dict com resultado da validação:
            {
                'valid': bool,
                'confidence': float (0-1),
                'severity': str ('ok', 'leve', 'medio', 'grave', 'critico'),
                'message': str,
                'link_dates': List[str],  # Datas encontradas no link
                'date_diff_days': int,  # Diferença em dias (se encontrou data próxima)
            }
        """
        result = {
            'valid': False,
            'confidence': 0.0,
            'severity': 'critico',
            'message': '',
            'link_dates': [],
            'date_diff_days': None,
        }

        # Parse da data do evento
        event_date = DateParser.parse_date(event_date_str)
        if not event_date:
            result['message'] = f"Data do evento inválida: {event_date_str}"
            return result

        # Extrair datas do HTML
        link_dates = DateValidator.extract_dates_from_html(link_html)
        result['link_dates'] = [d.strftime("%d/%m/%Y") for d in link_dates]

        if not link_dates:
            # Sem datas no link - não podemos validar, mas não é crítico
            result['valid'] = True  # Considerar válido por falta de evidência contrária
            result['confidence'] = 0.5
            result['severity'] = 'ok'
            result['message'] = "Link sem datas estruturadas - impossível validar"
            logger.warning(f"⚠️ Link sem datas para validar: {event_date_str}")
            return result

        # Verificar se data do evento está próxima de alguma data do link
        min_diff_days = None
        for link_date in link_dates:
            diff_days = abs((event_date - link_date).days)

            if min_diff_days is None or diff_days < min_diff_days:
                min_diff_days = diff_days

        result['date_diff_days'] = min_diff_days

        # Classificar severidade baseado na diferença
        if min_diff_days == 0:
            result['valid'] = True
            result['confidence'] = 1.0
            result['severity'] = 'ok'
            result['message'] = "Data exata encontrada no link"

        elif min_diff_days <= tolerance_days:
            result['valid'] = True
            result['confidence'] = 0.9
            result['severity'] = 'ok'
            result['message'] = f"Data próxima no link (±{min_diff_days} dias)"

        elif min_diff_days <= 14:
            # Evento multi-sessão ou range flexível
            result['valid'] = True
            result['confidence'] = 0.7
            result['severity'] = 'leve'
            result['message'] = f"Data com diferença leve ({min_diff_days} dias) - possível multi-sessão"

        elif min_diff_days <= 30:
            # Pode ser erro de interpretação de mês
            result['valid'] = False
            result['confidence'] = 0.3
            result['severity'] = 'medio'
            result['message'] = f"Data diverge em {min_diff_days} dias - verificar"

        elif min_diff_days <= 180:
            # Erro grave - meses errados
            result['valid'] = False
            result['confidence'] = 0.1
            result['severity'] = 'grave'
            result['message'] = f"Data diverge em {min_diff_days} dias - erro provável"

        else:
            # Erro crítico - anos errados ou evento muito antigo
            result['valid'] = False
            result['confidence'] = 0.0
            result['severity'] = 'critico'
            result['message'] = f"Data diverge em {min_diff_days} dias - erro crítico"

        # Log
        if not result['valid']:
            logger.warning(
                f"❌ Data inválida: {event_date_str} vs link ({min_diff_days} dias) "
                f"- {result['severity'].upper()}"
            )
        else:
            logger.debug(
                f"✅ Data validada: {event_date_str} ({result['severity']})"
            )

        return result

    @staticmethod
    def should_reject_event(validation_result: dict) -> bool:
        """
        Determina se evento deve ser rejeitado baseado na validação.

        Rejeitar apenas erros graves/críticos (>30 dias de diferença).
        Erros leves/médios são aceitos mas marcados para review.

        Args:
            validation_result: Resultado de validate_event_date()

        Returns:
            True se evento deve ser rejeitado, False caso contrário
        """
        severity = validation_result.get('severity', 'critico')
        return severity in ['grave', 'critico']
