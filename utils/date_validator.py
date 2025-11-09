"""Validador rigoroso de datas para eventos culturais.

Este módulo centraliza toda a lógica de validação de datas, incluindo:
- Validação de formato (DD/MM/YYYY)
- Validação de período (dentro da janela de busca)
- Validação de horário (HH:MM)
- Validação geográfica (apenas Rio de Janeiro)
- Validação temporal (eventos não podem estar muito próximos)
- Extração de datas de conteúdo HTML
- Comparação entre data do evento e data extraída de links
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from config import MIN_HOURS_ADVANCE, SEARCH_CONFIG

logger = logging.getLogger(__name__)


class DateValidator:
    """Validador centralizado para datas de eventos."""

    def __init__(self):
        """Inicializa o validador de datas."""
        self.log_prefix = "[DateValidator] 📅"
        self.validation_stats = {
            "total_validations": 0,
            "approved": 0,
            "rejected_format": 0,
            "rejected_period": 0,
            "rejected_time": 0,
            "rejected_geography": 0,
            "rejected_temporal": 0,
        }

    def check_event_date(self, event: dict) -> dict[str, Any]:
        """Valida data e horário de um evento (método principal).

        Args:
            event: Dicionário com dados do evento (data, horario, local)

        Returns:
            dict com: valid (bool), reason (str), date (str, opcional)
        """
        self.validation_stats["total_validations"] += 1

        # 1. Validar formato da data
        date_format_check = self.validate_date_format(event.get("data", ""))
        if not date_format_check["valid"]:
            self.validation_stats["rejected_format"] += 1
            return date_format_check

        event_date = date_format_check["parsed_date"]

        # 2. Validar período (dentro da janela de busca)
        period_check = self.validate_date_period(event_date)
        if not period_check["valid"]:
            self.validation_stats["rejected_period"] += 1
            return period_check

        # 3. Validar horário
        time_check = self.validate_time_format(event.get("horario", ""))
        if not time_check["valid"]:
            self.validation_stats["rejected_time"] += 1
            return time_check

        # 4. Validar geografia (apenas Rio de Janeiro)
        geo_check = self.validate_geographic_location(event.get("local", ""))
        if not geo_check["valid"]:
            self.validation_stats["rejected_geography"] += 1
            return geo_check

        # 5. Validar proximidade temporal (eventos hoje devem ter antecedência mínima)
        temporal_check = self.validate_temporal_proximity(event_date, event.get("horario", ""))
        if not temporal_check["valid"]:
            self.validation_stats["rejected_temporal"] += 1
            return temporal_check

        # Todas validações passaram
        self.validation_stats["approved"] += 1
        return {
            "valid": True,
            "reason": "Data válida",
            "date": event_date.strftime("%d/%m/%Y"),
        }

    def validate_date_format(self, date_str: str) -> dict[str, Any]:
        """Valida formato da data (DD/MM/YYYY) de forma rigorosa.

        Args:
            date_str: String com a data a validar

        Returns:
            dict com: valid (bool), reason (str), parsed_date (datetime, opcional)
        """
        if not date_str:
            return {"valid": False, "reason": "Data não fornecida"}

        # Rejeitar datas descritivas
        invalid_indicators = [
            "última", "primeira", "edição", "temporada",
            "confirmar", "a definir", "tbd", "novembro de",
            "dezembro de", "janeiro de", "fevereiro de"
        ]
        date_str_lower = date_str.lower()

        for indicator in invalid_indicators:
            if indicator in date_str_lower:
                return {
                    "valid": False,
                    "reason": f"Data descritiva não aceita (deve ser DD/MM/YYYY): {date_str}",
                }

        # Extrair apenas a parte da data (primeira palavra se houver espaços)
        date_part = date_str.split()[0] if " " in date_str else date_str

        # Validar formato exato DD/MM/YYYY
        if not date_part or len(date_part) != 10 or date_part.count("/") != 2:
            return {
                "valid": False,
                "reason": f"Formato de data inválido (esperado DD/MM/YYYY): {date_str}",
            }

        # Validar se é uma data válida (detecta impossíveis como 32/13/2025)
        try:
            day, month, year = date_part.split("/")
            day_int = int(day)
            month_int = int(month)
            year_int = int(year)

            # Validação preventiva antes de strptime
            if not (1 <= day_int <= 31):
                return {
                    "valid": False,
                    "reason": f"Dia inválido (deve ser 01-31): {day} em {date_str}",
                }

            if not (1 <= month_int <= 12):
                return {
                    "valid": False,
                    "reason": f"Mês inválido (deve ser 01-12): {month} em {date_str}",
                }

            if not (2020 <= year_int <= 2030):
                return {
                    "valid": False,
                    "reason": f"Ano fora do range esperado (2020-2030): {year} em {date_str}",
                }

            # Fazer parsing completo
            parsed_date = datetime.strptime(date_part, "%d/%m/%Y")

        except (ValueError, IndexError) as e:
            return {
                "valid": False,
                "reason": f"Data inválida ou impossível: {date_str} (erro: {e})",
            }

        return {"valid": True, "reason": "Formato válido", "parsed_date": parsed_date}

    def validate_date_period(self, event_date: datetime) -> dict[str, Any]:
        """Valida se a data está dentro do período de busca configurado.

        Args:
            event_date: Data do evento (datetime)

        Returns:
            dict com: valid (bool), reason (str)
        """
        start_date = SEARCH_CONFIG["start_date"].date()
        end_date = SEARCH_CONFIG["end_date"].date()
        event_date_only = event_date.date()

        if not (start_date <= event_date_only <= end_date):
            return {
                "valid": False,
                "reason": (
                    f"Data fora do período válido "
                    f"({start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')})"
                ),
            }

        return {"valid": True, "reason": "Data dentro do período"}

    def validate_time_format(self, time_str: str) -> dict[str, Any]:
        """Valida formato do horário (HH:MM) de forma rigorosa.

        Args:
            time_str: String com o horário a validar

        Returns:
            dict com: valid (bool), reason (str), parsed_hour (int), parsed_minute (int)
        """
        if not time_str:
            return {"valid": False, "reason": "Horário não fornecido"}

        # Rejeitar placeholders de horário
        invalid_time_indicators = ["xx:xx", "x:x", "tbd", "confirmar", "a definir"]
        time_str_lower = time_str.lower()

        for indicator in invalid_time_indicators:
            if indicator in time_str_lower:
                return {
                    "valid": False,
                    "reason": f"Horário placeholder não aceito (deve ser HH:MM): {time_str}",
                }

        # Validar formato HH:MM estrito
        if ":" not in time_str:
            return {
                "valid": False,
                "reason": f"Formato de horário inválido (esperado HH:MM): {time_str}",
            }

        try:
            hora_partes = time_str.strip().split(":")
            if len(hora_partes) != 2:
                return {
                    "valid": False,
                    "reason": f"Formato de horário inválido (esperado HH:MM): {time_str}",
                }

            hora = int(hora_partes[0])
            minuto = int(hora_partes[1])

            # Validar ranges válidos
            if not (0 <= hora <= 23):
                return {
                    "valid": False,
                    "reason": f"Hora inválida (deve ser 00-23): {time_str}",
                }

            if not (0 <= minuto <= 59):
                return {
                    "valid": False,
                    "reason": f"Minuto inválido (deve ser 00-59): {time_str}",
                }

        except (ValueError, IndexError):
            return {
                "valid": False,
                "reason": f"Formato de horário inválido (esperado HH:MM): {time_str}",
            }

        return {
            "valid": True,
            "reason": "Horário válido",
            "parsed_hour": hora,
            "parsed_minute": minuto,
        }

    def validate_geographic_location(self, location_str: str) -> dict[str, Any]:
        """Valida se o evento é no Rio de Janeiro (rejeita outras cidades).

        Args:
            location_str: String com o local do evento

        Returns:
            dict com: valid (bool), reason (str)
        """
        if not location_str:
            return {"valid": False, "reason": "Local não fornecido"}

        location_lower = location_str.lower()

        # Lista de cidades FORA do Rio de Janeiro que devem ser rejeitadas
        invalid_cities = [
            "paraty", "parati",  # Paraty/Parati
            "niterói", "niteroi",  # Niterói
            "são gonçalo", "sao goncalo",  # São Gonçalo
            "duque de caxias",  # Duque de Caxias
            "nova iguaçu", "nova iguacu",  # Nova Iguaçu
            "são paulo", "sao paulo", "sp",  # São Paulo
            "belo horizonte",  # BH
            "brasília", "brasilia",  # Brasília
        ]

        # Verificar se o local contém alguma cidade inválida
        for city in invalid_cities:
            if city in location_lower:
                return {
                    "valid": False,
                    "reason": f"Evento fora do Rio de Janeiro (cidade: {city})",
                }

        return {"valid": True, "reason": "Localização válida"}

    def validate_temporal_proximity(
        self, event_date: datetime, time_str: str
    ) -> dict[str, Any]:
        """Valida se eventos de hoje têm antecedência mínima (MIN_HOURS_ADVANCE).

        Args:
            event_date: Data do evento (datetime)
            time_str: Horário do evento (HH:MM)

        Returns:
            dict com: valid (bool), reason (str)
        """
        now = datetime.now()
        event_date_only = event_date.date()

        # Só validar se for evento de hoje
        if event_date_only != now.date():
            return {"valid": True, "reason": "Evento futuro (não é hoje)"}

        try:
            # Parse horário (formato HH:MM)
            hora_partes = time_str.split(":")
            if len(hora_partes) >= 2:
                hora = int(hora_partes[0])
                minuto = int(hora_partes[1])
                event_datetime = datetime.combine(event_date_only, datetime.min.time()).replace(
                    hour=hora, minute=minuto
                )

                # Verificar se faltam pelo menos MIN_HOURS_ADVANCE horas
                hora_minima = now + timedelta(hours=MIN_HOURS_ADVANCE)
                if event_datetime < hora_minima:
                    return {
                        "valid": False,
                        "reason": (
                            f"Evento hoje às {time_str} já passou ou está muito próximo "
                            f"(menos de {MIN_HOURS_ADVANCE}h)"
                        ),
                    }

        except (ValueError, IndexError):
            # Se não conseguir parsear horário, aceitar por segurança (modo permissivo)
            logger.warning(
                f"{self.log_prefix} Não foi possível parsear horário '{time_str}' "
                f"para validação temporal"
            )

        return {"valid": True, "reason": "Proximidade temporal válida"}

    def extract_dates_from_html(self, content: str) -> dict[str, Any]:
        """Extrai datas estruturadas de conteúdo HTML.

        Suporta múltiplos formatos:
        - DD/MM/YYYY (brasileiro)
        - YYYY-MM-DD (ISO)
        - DD de MMMM de YYYY (textual português)
        - DD.MM.YYYY (pontos)
        - YYYY/MM/DD (barras invertidas)
        - DD MMMM YYYY (textual inglês)

        Args:
            content: Texto HTML ou texto puro

        Returns:
            dict com: found (bool), dates (list), primary_date (str, opcional)
        """
        # Mapa de meses em português
        month_map_pt = {
            "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03",
            "abril": "04", "maio": "05", "junho": "06",
            "julho": "07", "agosto": "08", "setembro": "09",
            "outubro": "10", "novembro": "11", "dezembro": "12",
        }

        # Mapa de meses em inglês
        month_map_en = {
            "january": "01", "february": "02", "march": "03",
            "april": "04", "may": "05", "june": "06",
            "july": "07", "august": "08", "september": "09",
            "october": "10", "november": "11", "december": "12",
        }

        # Padrões de data (ordem de prioridade)
        date_patterns = [
            # DD/MM/YYYY (brasileiro)
            (r"(\d{2})/(\d{2})/(\d{4})", "dmy_slash"),
            # YYYY-MM-DD (ISO)
            (r"(\d{4})-(\d{2})-(\d{2})", "ymd_dash"),
            # DD de MMMM de YYYY (textual português)
            (r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", "dmy_text_pt"),
            # DD.MM.YYYY (pontos)
            (r"(\d{2})\.(\d{2})\.(\d{4})", "dmy_dot"),
            # YYYY/MM/DD (barras invertidas)
            (r"(\d{4})/(\d{2})/(\d{2})", "ymd_slash"),
            # DD MMMM YYYY (textual inglês - sem "de")
            (r"(\d{1,2})\s+(\w+)\s+(\d{4})", "dmy_text_en"),
        ]

        found_dates = []
        content_lower = content.lower()

        for pattern, pattern_type in date_patterns:
            matches = re.findall(pattern, content_lower)
            for match in matches:
                try:
                    if pattern_type == "dmy_slash":
                        # DD/MM/YYYY
                        day, month, year = match
                        date_str = f"{day.zfill(2)}/{month.zfill(2)}/{year}"
                        date_obj = datetime.strptime(date_str, "%d/%m/%Y")
                        found_dates.append(date_obj.strftime("%d/%m/%Y"))

                    elif pattern_type == "ymd_dash":
                        # YYYY-MM-DD (ISO)
                        year, month, day = match
                        date_str = f"{day.zfill(2)}/{month.zfill(2)}/{year}"
                        date_obj = datetime.strptime(date_str, "%d/%m/%Y")
                        found_dates.append(date_obj.strftime("%d/%m/%Y"))

                    elif pattern_type == "dmy_text_pt":
                        # DD de MMMM de YYYY (português)
                        day, month_name, year = match
                        month = month_map_pt.get(month_name.lower())
                        if month:
                            date_str = f"{day.zfill(2)}/{month}/{year}"
                            date_obj = datetime.strptime(date_str, "%d/%m/%Y")
                            found_dates.append(date_obj.strftime("%d/%m/%Y"))

                    elif pattern_type == "dmy_dot":
                        # DD.MM.YYYY
                        day, month, year = match
                        date_str = f"{day.zfill(2)}/{month.zfill(2)}/{year}"
                        date_obj = datetime.strptime(date_str, "%d/%m/%Y")
                        found_dates.append(date_obj.strftime("%d/%m/%Y"))

                    elif pattern_type == "ymd_slash":
                        # YYYY/MM/DD
                        year, month, day = match
                        date_str = f"{day.zfill(2)}/{month.zfill(2)}/{year}"
                        date_obj = datetime.strptime(date_str, "%d/%m/%Y")
                        found_dates.append(date_obj.strftime("%d/%m/%Y"))

                    elif pattern_type == "dmy_text_en":
                        # DD MMMM YYYY (inglês)
                        day, month_name, year = match
                        month = month_map_en.get(month_name.lower())
                        if month:
                            date_str = f"{day.zfill(2)}/{month}/{year}"
                            date_obj = datetime.strptime(date_str, "%d/%m/%Y")
                            found_dates.append(date_obj.strftime("%d/%m/%Y"))

                except (ValueError, AttributeError):
                    continue

        # Remove duplicatas preservando ordem
        unique_dates = []
        for date in found_dates:
            if date not in unique_dates:
                unique_dates.append(date)

        if unique_dates:
            return {
                "found": True,
                "dates": unique_dates,
                "primary_date": unique_dates[0],
            }
        else:
            return {"found": False, "dates": []}

    def compare_event_date_with_link(
        self,
        event_date_str: str,
        extracted_dates: list[str],
        strict_mode: bool = False,
    ) -> dict[str, Any]:
        """Compara data do evento com datas extraídas do link.

        Suporta eventos single-day e multi-day (festivais).

        Args:
            event_date_str: Data do evento (DD/MM/YYYY)
            extracted_dates: Lista de datas extraídas do link (DD/MM/YYYY)
            strict_mode: Se True, rejeita divergências. Se False, corrige automaticamente.

        Returns:
            dict com: match (bool), is_multi_day (bool), reason (str),
                     corrected_date (str, opcional)
        """
        if not extracted_dates:
            return {
                "match": None,  # Sem informação para comparar
                "reason": "Nenhuma data encontrada no link para comparar",
            }

        # Extrair apenas a parte da data (remover horário se presente)
        event_date = event_date_str.split()[0] if " " in event_date_str else event_date_str

        # Verificar se é exatamente igual (caso simples)
        if event_date in extracted_dates:
            return {
                "match": True,
                "is_multi_day": len(extracted_dates) > 1,
                "reason": "Data do evento corresponde ao link",
            }

        # Evento multi-dia (festival): verificar se data está dentro do range
        is_multi_day = len(extracted_dates) > 1

        if is_multi_day:
            try:
                # Converter para datetime
                event_date_obj = datetime.strptime(event_date, "%d/%m/%Y")
                dates_objs = [datetime.strptime(d, "%d/%m/%Y") for d in extracted_dates]

                min_date = min(dates_objs)
                max_date = max(dates_objs)

                # Verificar se está dentro do range
                if min_date <= event_date_obj <= max_date:
                    return {
                        "match": True,
                        "is_multi_day": True,
                        "reason": (
                            f"Data do evento ({event_date}) está dentro do range do festival "
                            f"({min_date.strftime('%d/%m/%Y')} a {max_date.strftime('%d/%m/%Y')})"
                        ),
                        "festival_start": min_date.strftime("%d/%m/%Y"),
                        "festival_end": max_date.strftime("%d/%m/%Y"),
                    }

            except (ValueError, TypeError):
                pass

        # Data divergente
        if strict_mode:
            return {
                "match": False,
                "is_multi_day": is_multi_day,
                "reason": (
                    f"Data divergente: evento informa {event_date}, "
                    f"mas link contém {extracted_dates[0]}. Rejeitado em modo strict."
                ),
            }
        else:
            # Modo permissivo: sugerir correção
            return {
                "match": False,
                "is_multi_day": is_multi_day,
                "reason": (
                    f"Data divergente: evento informa {event_date}, "
                    f"mas link contém {extracted_dates[0]}. Sugerindo correção automática."
                ),
                "corrected_date": extracted_dates[0],
            }

    def get_validation_stats(self) -> dict[str, Any]:
        """Retorna estatísticas de validação acumuladas.

        Returns:
            dict com estatísticas detalhadas de todas validações realizadas
        """
        total = self.validation_stats["total_validations"]
        if total == 0:
            return {**self.validation_stats, "approval_rate": 0.0}

        approval_rate = (self.validation_stats["approved"] / total) * 100

        return {
            **self.validation_stats,
            "approval_rate": round(approval_rate, 2),
        }

    def log_validation_stats(self):
        """Loga estatísticas de validação de forma estruturada."""
        stats = self.get_validation_stats()

        logger.info(f"{self.log_prefix} ===== ESTATÍSTICAS DE VALIDAÇÃO =====")
        logger.info(f"{self.log_prefix} Total de validações: {stats['total_validations']}")
        logger.info(f"{self.log_prefix} Aprovados: {stats['approved']} ({stats['approval_rate']}%)")
        logger.info(f"{self.log_prefix} Rejeitados por:")
        logger.info(f"{self.log_prefix}   - Formato: {stats['rejected_format']}")
        logger.info(f"{self.log_prefix}   - Período: {stats['rejected_period']}")
        logger.info(f"{self.log_prefix}   - Horário: {stats['rejected_time']}")
        logger.info(f"{self.log_prefix}   - Geografia: {stats['rejected_geography']}")
        logger.info(f"{self.log_prefix}   - Proximidade temporal: {stats['rejected_temporal']}")
        logger.info(f"{self.log_prefix} ====================================")
