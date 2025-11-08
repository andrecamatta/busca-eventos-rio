"""Agente de validação individual inteligente de eventos com LLM."""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup

from config import (
    HTTP_TIMEOUT,
    MIN_HOURS_ADVANCE,
    SEARCH_CONFIG,
    VALIDATION_STRICTNESS,
    VENUE_ADDRESSES,
)
from utils.agent_factory import AgentFactory
from utils.http_client import HttpClientWrapper

logger = logging.getLogger(__name__)

# Prefixo para logs deste agente
LOG_PREFIX = "[ValidationAgent] ⚖️"


class ValidationAgent:
    """Agente especializado em validação individual inteligente com LLM."""

    def __init__(self):
        self.log_prefix = "[ValidationAgent] ⚖️"
        self.http_client = HttpClientWrapper()

        self.agent = AgentFactory.create_agent(
            name="Event Validation Agent",
            model_type="important",  # Gemini Flash 1.5 - validação de eventos
            description="Agente especializado em validação inteligente de eventos usando LLM",
            instructions=[
                "Validar eventos de forma inteligente e flexível",
                "Usar bom senso para aceitar eventos legítimos",
                "Rejeitar apenas eventos claramente falsos ou absurdos",
                "Considerar contexto e plausibilidade geral",
            ],
            markdown=True,
        )

    def _needs_individual_validation(self, event: dict) -> bool:
        """Determina se um evento precisa de validação individual via LLM.

        Eventos com informações completas e link válido podem pular validação (otimização).
        Eventos de venues conhecidos/confiáveis também são auto-aprovados (economia de API).
        """
        # Sempre validar se não tiver campos essenciais
        has_complete_fields = all([
            event.get('titulo'),
            event.get('data'),
            event.get('horario'),
            event.get('local'),
        ])

        if not has_complete_fields:
            return True  # Precisa validar

        # OTIMIZAÇÃO: Auto-aprovar eventos de venues conhecidos e confiáveis
        # Estes venues têm programação curada e eventos sempre válidos
        local = event.get('local', '').lower()

        TRUSTED_VENUES = [
            'teatro municipal', 'theatro municipal',
            'sala cecília meireles', 'cecilia meireles',
            'blue note', 'bluenote',
            'casa do choro',
            'ccbb', 'centro cultural banco do brasil',
            'oi futuro', 'centro cultural oi futuro',
            'cidade das artes',
        ]

        is_trusted_venue = any(venue in local for venue in TRUSTED_VENUES)

        # Auto-aprovar venues confiáveis com campos completos SE link for válido ou não existir
        if is_trusted_venue and has_complete_fields:
            link = event.get('link_ingresso')
            link_valid = event.get('link_valid')

            # Se não tem link, pode auto-aprovar (evento presencial sem venda online)
            if not link:
                return False  # Pode pular validação LLM (venue confiável sem link)

            # Se tem link, só auto-aprovar se link for válido
            if link_valid is True:
                return False  # Pode pular validação LLM (venue confiável com link válido)

            # Se tem link mas é inválido (False ou None), PRECISA validar
            # Links quebrados em venues confiáveis precisam ser verificados
            logger.warning(f"⚠️ Venue confiável '{local}' com link inválido - validação necessária")
            return True  # Precisa validar (link potencialmente quebrado)

        # Se tiver link válido (explicitamente marcado como True) E campos completos, pode pular
        has_valid_link = event.get('link_ingresso') and event.get('link_valid') is True

        if has_valid_link and has_complete_fields:
            return False  # Pode pular validação

        # Se não tiver link OU link não foi validado (None ou False), precisa validar
        return True

    async def validate_events_batch(self, events: list[dict]) -> dict[str, Any]:
        """Valida um lote de eventos individualmente (com validação condicional)."""
        logger.info(f"{self.log_prefix} Validando {len(events)} eventos (modo: {VALIDATION_STRICTNESS})...")

        validated_events = []
        rejected_events = []
        validation_warnings = []

        # Separar eventos que precisam de validação vs auto-aprovados
        events_to_validate = []
        auto_approved_events = []

        for event in events:
            if self._needs_individual_validation(event):
                events_to_validate.append(event)
            else:
                auto_approved_events.append(event)
                # Determinar razão da auto-aprovação para log
                local = event.get('local', '').lower()
                is_trusted = any(v in local for v in [
                    'teatro municipal', 'sala cecília', 'blue note', 'casa do choro',
                    'ccbb', 'oi futuro', 'cidade das artes'
                ])
                reason = "venue confiável" if is_trusted else "link válido"
                logger.info(
                    f"✓ Auto-aprovado ({reason}): "
                    f"{event.get('titulo', 'Sem título')} @ {event.get('local', 'N/A')}"
                )

        logger.info(
            f"{self.log_prefix} Validação condicional: {len(auto_approved_events)} auto-aprovados, "
            f"{len(events_to_validate)} precisam validação LLM"
        )

        # Auto-aprovar eventos com informações completas
        validated_events.extend(auto_approved_events)

        # Criar tasks apenas para eventos que precisam de validação
        if events_to_validate:
            logger.info(f"{self.log_prefix} Iniciando validação LLM de {len(events_to_validate)} eventos...")
            validation_tasks = [
                self.validate_event_individually(event)
                for event in events_to_validate
            ]

            # Executar todas as validações em paralelo
            validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)
        else:
            validation_results = []
            logger.info(f"{self.log_prefix} Nenhum evento precisa de validação LLM (todos auto-aprovados)")

        # Processar resultados (apenas dos eventos que foram validados)
        for i, (event, result) in enumerate(zip(events_to_validate, validation_results)):
            event_title = event.get('titulo', 'Sem título')

            # Tratar exceções que possam ter ocorrido
            if isinstance(result, Exception):
                logger.error(
                    f"Erro ao validar evento {i+1}/{len(events)} ({event_title}): {result}"
                )
                rejected_events.append({
                    **event,
                    "motivo_rejeicao": f"Erro na validação: {str(result)}",
                    "confidence": 0,
                })
                continue

            # Processar resultado normal
            if result["approved"]:
                validated_events.append(event)
                if result.get("warnings"):
                    validation_warnings.extend(result["warnings"])
                logger.info(f"✓ Evento {i+1}/{len(events)} aprovado: {event_title}")
            else:
                rejected_events.append({
                    **event,
                    "motivo_rejeicao": result["reason"],
                    "confidence": result.get("confidence", 0),
                })
                logger.warning(
                    f"✗ Evento {i+1}/{len(events)} rejeitado: {event_title} - "
                    f"Motivo: {result['reason']}"
                )

        logger.info(
            f"Validação concluída: {len(validated_events)} aprovados, "
            f"{len(rejected_events)} rejeitados"
        )

        return {
            "validated_events": validated_events,
            "rejected_events": rejected_events,
            "validation_warnings": validation_warnings,
        }

    async def validate_event_individually(self, event: dict) -> dict[str, Any]:
        """Valida um único evento usando LLM para decisão inteligente."""

        # Coletar evidências sobre o evento
        evidences = {}

        # 1. Validar data (obrigatório)
        date_check = self._check_date(event)
        evidences["date"] = date_check
        if not date_check["valid"]:
            return {
                "approved": False,
                "reason": date_check["reason"],
                "confidence": 0,
            }

        # 2. Buscar informações do link (se tiver)
        link = event.get("link_ingresso") or event.get("link", "")
        if link:
            link_info = await self._fetch_link_info(link, event)  # Passar evento para validação de qualidade
            evidences["link"] = link_info

            # VALIDAÇÃO AUTOMÁTICA DE DATA: Comparar data do evento com data extraída do link
            if link_info.get("extracted_date", {}).get("found"):
                extracted_dates = link_info["extracted_date"]["dates"]
                event_date = event.get("data", "").split()[0]  # Remove horário se presente

                if event_date and event_date not in extracted_dates:
                    # Para festivais multi-dia, verificar se data está dentro do range
                    is_multi_day_event = len(extracted_dates) > 1

                    if is_multi_day_event:
                        try:
                            # Converter datas para objetos datetime
                            event_date_obj = datetime.strptime(event_date, "%d/%m/%Y")
                            dates_objs = [datetime.strptime(d, "%d/%m/%Y") for d in extracted_dates]

                            # Verificar se a data do evento está dentro do range
                            min_date = min(dates_objs)
                            max_date = max(dates_objs)

                            if min_date <= event_date_obj <= max_date:
                                logger.info(
                                    f"✓ Festival multi-dia detectado: data {event_date} está dentro do range "
                                    f"({min_date.strftime('%d/%m/%Y')} a {max_date.strftime('%d/%m/%Y')})"
                                )
                                evidences["date"]["is_within_festival_range"] = True
                                evidences["date"]["festival_start"] = min_date.strftime("%d/%m/%Y")
                                evidences["date"]["festival_end"] = max_date.strftime("%d/%m/%Y")
                                # Data está OK, continuar validação
                            else:
                                raise ValueError("Data fora do range do festival")

                        except (ValueError, TypeError):
                            # Se não conseguir parsear ou data estiver fora do range
                            logger.warning(
                                f"⚠️  DATA DIVERGENTE: Evento informa '{event_date}', "
                                f"mas festival vai de {min(extracted_dates)} a {max(extracted_dates)}"
                            )

                            if VALIDATION_STRICTNESS == "strict":
                                return {
                                    "approved": False,
                                    "reason": f"Data {event_date} fora do range do festival ({min(extracted_dates)} a {max(extracted_dates)}). Rejeitado em modo strict.",
                                    "confidence": 0,
                                    "date_mismatch": True,
                                }
                    else:
                        # Evento de um único dia com data divergente
                        logger.warning(
                            f"⚠️  DATA DIVERGENTE: Evento informa '{event_date}', "
                            f"mas link contém {extracted_dates}"
                        )

                        # Modo STRICT: Rejeitar imediatamente
                        if VALIDATION_STRICTNESS == "strict":
                            return {
                                "approved": False,
                                "reason": f"Data divergente: evento informa {event_date}, mas link oficial contém {extracted_dates[0]}. Rejeitado em modo strict.",
                                "confidence": 0,
                                "date_mismatch": True,
                            }

                        # Modo PERMISSIVE: Corrigir data automaticamente
                        else:
                            logger.info(
                                f"✓ Corrigindo data automaticamente: {event_date} → {extracted_dates[0]}"
                            )
                            event["data_original"] = event_date
                            event["data"] = extracted_dates[0]
                            event["data_corrigida_automaticamente"] = True
                            evidences["date"]["corrected"] = True
                            evidences["date"]["original_date"] = event_date
                            evidences["date"]["corrected_date"] = extracted_dates[0]
        else:
            evidences["link"] = {"status": "no_link", "reason": "Link não fornecido"}

        # 3. Usar LLM para decisão final inteligente
        llm_decision = await self._analyze_with_llm(event, evidences)

        return llm_decision

    async def _fetch_link_info(self, link: str, event: dict = None) -> dict[str, Any]:
        """Busca informações do link (status HTTP + conteúdo estruturado).

        Args:
            link: URL para validar
            event: Dados do evento (opcional, para validação de qualidade)
        """
        # Usar HttpClientWrapper para fetch + parsing
        result = await self.http_client.fetch_and_parse(
            link,
            extract_text=True,
            text_max_length=3000,
            clean_html=True
        )

        # Se não teve sucesso, retornar erro apropriado
        if not result["success"]:
            status_code = result["status_code"]

            if status_code == 404:
                return {
                    "status": "not_found",
                    "status_code": 404,
                    "reason": "Link retorna 404 (não encontrado)",
                }
            elif status_code == 403:
                return {
                    "status": "forbidden",
                    "status_code": 403,
                    "reason": "Link bloqueado (403 Forbidden)",
                }
            elif result["error"] == "Timeout":
                return {
                    "status": "timeout",
                    "reason": "Timeout ao acessar link",
                }
            elif status_code:
                return {
                    "status": "error",
                    "status_code": status_code,
                    "reason": f"Link retorna status {status_code}",
                }
            else:
                return {
                    "status": "error",
                    "reason": f"Erro ao acessar link: {result['error']}",
                }

        # Sucesso - processar conteúdo
        page_text = result["text"]
        soup = result["soup"]

        # Extrair datas do conteúdo
        extracted_date = self._extract_date_from_content(page_text)

        # Extrair dados estruturados
        structured_data = {}
        if soup:
            try:
                structured_data = self._extract_structured_data(soup, page_text)
                # Adicionar data extraída aos dados estruturados
                structured_data["extracted_date"] = extracted_date
            except Exception as e:
                logger.warning(f"{self.log_prefix} Erro ao extrair dados estruturados: {e}")

        # Validar qualidade do link
        quality_validation = None
        if event and structured_data:
            try:
                # Combinar dados estruturados com extração de data
                validation_data = {**structured_data, "extracted_date": extracted_date}
                quality_validation = self._validate_link_quality(validation_data, event)

                logger.info(
                    f"{self.log_prefix} Link quality score: {quality_validation['score']}/100 "
                    f"({'✅ APROVADO' if quality_validation['is_quality'] else '❌ REJEITADO'})"
                )

                if quality_validation['issues']:
                    logger.debug(f"{self.log_prefix} Issues: {', '.join(quality_validation['issues'])}")

            except Exception as e:
                logger.warning(f"{self.log_prefix} Erro ao validar qualidade do link: {e}")

        return {
            "status": "accessible",
            "status_code": 200,
            "content_preview": page_text,
            "extracted_date": extracted_date,
            "structured_data": structured_data,
            "quality_validation": quality_validation,
        }

    def _extract_date_from_content(self, content: str) -> dict[str, Any]:
        """Extrai datas estruturadas do conteúdo HTML."""
        # Padrões de data comuns em Sympla, Eventbrite, etc
        date_patterns = [
            r'(\d{2})/(\d{2})/(\d{4})',  # DD/MM/YYYY
            r'(\d{4})-(\d{2})-(\d{2})',  # YYYY-MM-DD (ISO)
            r'(\d{2})\s+de\s+(\w+)\s+de\s+(\d{4})',  # 15 de novembro de 2025
        ]

        month_map = {
            'janeiro': '01', 'fevereiro': '02', 'março': '03', 'abril': '04',
            'maio': '05', 'junho': '06', 'julho': '07', 'agosto': '08',
            'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12'
        }

        found_dates = []
        content_lower = content.lower()

        for pattern in date_patterns:
            matches = re.findall(pattern, content_lower)
            for match in matches:
                try:
                    if len(match) == 3:
                        if match[1].isalpha():  # Mês por extenso
                            day, month_name, year = match
                            month = month_map.get(month_name, None)
                            if month:
                                date_str = f"{day.zfill(2)}/{month}/{year}"
                                date_obj = datetime.strptime(date_str, "%d/%m/%Y")
                                found_dates.append(date_obj.strftime("%d/%m/%Y"))
                        elif '-' in f"{match[0]}-{match[1]}-{match[2]}":  # ISO format
                            year, month, day = match
                            date_str = f"{day.zfill(2)}/{month.zfill(2)}/{year}"
                            date_obj = datetime.strptime(date_str, "%d/%m/%Y")
                            found_dates.append(date_obj.strftime("%d/%m/%Y"))
                        else:  # DD/MM/YYYY
                            day, month, year = match
                            date_str = f"{day.zfill(2)}/{month.zfill(2)}/{year}"
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
                "primary_date": unique_dates[0]
            }
        else:
            return {"found": False, "dates": []}

    def _extract_structured_data(self, soup: BeautifulSoup, page_text: str) -> dict[str, Any]:
        """Extrai dados estruturados da página do evento.

        Returns:
            dict com: title, artists, time, price, purchase_link, description
        """
        data = {
            "title": None,
            "artists": [],
            "time": None,
            "price": None,
            "purchase_links": [],
            "description": None,
        }

        # Extrair título da página
        # Prioridade: og:title, meta twitter:title, h1, title tag
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            data["title"] = og_title["content"].strip()
        else:
            twitter_title = soup.find("meta", attrs={"name": "twitter:title"})
            if twitter_title and twitter_title.get("content"):
                data["title"] = twitter_title["content"].strip()
            else:
                h1 = soup.find("h1")
                if h1:
                    data["title"] = h1.get_text().strip()
                else:
                    title_tag = soup.find("title")
                    if title_tag:
                        data["title"] = title_tag.get_text().strip()

        # Extrair artistas/músicos
        # Padrões comuns: "com Fulano", "participação de", "apresenta", nomes próprios
        artist_patterns = [
            r'(?:com|Com|featuring|Featuring|ft\.|Ft\.)\s+([A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ\s]+(?:[A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ]+)*)',
            r'(?:participação de|Participação de|apresenta|Apresenta)\s+([A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ\s]+(?:[A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ]+)*)',
            r'(?:solista|Solista|maestro|Maestro)\s*:\s*([A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ\s]+(?:[A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ]+)*)',
        ]

        for pattern in artist_patterns:
            matches = re.findall(pattern, page_text)
            for match in matches:
                artist_name = match.strip()
                # Filtrar nomes muito curtos ou genéricos
                if len(artist_name) > 4 and artist_name.lower() not in ["consultar", "confirmar", "definir"]:
                    if artist_name not in data["artists"]:
                        data["artists"].append(artist_name)

        # Extrair horário
        # Padrões: "19h", "19h00", "19:00", "às 19h"
        time_patterns = [
            r'(\d{1,2})[h:](\d{2})',  # 19h00 ou 19:00
            r'(\d{1,2})h',  # 19h
            r'às\s+(\d{1,2})[h:](\d{2})?',  # às 19h ou às 19h00
        ]

        for pattern in time_patterns:
            match = re.search(pattern, page_text)
            if match:
                groups = match.groups()
                hour = groups[0]
                minute = groups[1] if len(groups) > 1 and groups[1] else "00"
                data["time"] = f"{hour.zfill(2)}:{minute.zfill(2) if minute else '00'}"
                break

        # Extrair preço
        # Padrões: "R$ 50", "R$50,00", "a partir de R$ 30"
        price_patterns = [
            r'R\$\s*(\d+(?:,\d{2})?)',
            r'(\d+)\s*reais',
            r'a partir de\s+R\$\s*(\d+)',
        ]

        for pattern in price_patterns:
            match = re.search(pattern, page_text)
            if match:
                price_value = match.group(1).replace(",", ".")
                data["price"] = f"R$ {price_value}"
                break

        # Extrair links de compra
        # Procurar por links com palavras-chave de compra
        purchase_keywords = ["ingresso", "comprar", "ticket", "compra", "venda", "reserva", "sympla", "eventbrite"]
        links = soup.find_all("a", href=True)

        for link in links:
            href = link.get("href", "")
            link_text = link.get_text().lower()

            # Verificar se é link de compra
            is_purchase_link = any(keyword in link_text for keyword in purchase_keywords)
            is_purchase_link = is_purchase_link or any(keyword in href.lower() for keyword in ["sympla.com", "eventbrite.com", "ticket"])

            if is_purchase_link and href.startswith("http"):
                if href not in data["purchase_links"]:
                    data["purchase_links"].append(href)

        # Extrair descrição
        # Prioridade: og:description, meta description, primeiro parágrafo
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            data["description"] = og_desc["content"].strip()
        else:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                data["description"] = meta_desc["content"].strip()
            else:
                # Procurar primeiro parágrafo significativo
                paragraphs = soup.find_all("p")
                for p in paragraphs:
                    text = p.get_text().strip()
                    if len(text) > 50:  # Parágrafo com conteúdo significativo
                        data["description"] = text
                        break

        return data

    def _is_artist_or_venue_site(self, url: str, event_title: str) -> bool:
        """Detecta se URL é site institucional de artista/venue (não venda).

        Args:
            url: URL a verificar
            event_title: Título do evento

        Returns:
            True se for site genérico que deve ser rejeitado
        """
        from urllib.parse import urlparse

        # Extrair domínio
        domain = urlparse(url).netloc.lower()

        # Lista de plataformas conhecidas (estas NÃO são sites de artistas)
        known_platforms = [
            'sympla', 'eventbrite', 'ticketmaster', 'ingresso', 'ticket',
            'bluenoterio', 'eleventickets', 'ingressodigital',
            'gov.br', # Sites governamentais geralmente têm páginas de eventos
        ]

        # Se é plataforma conhecida, não é site de artista
        if any(platform in domain for platform in known_platforms):
            return False

        # Heurística: domínio contém nome do evento = provável site do artista
        # Remover palavras comuns/stop words para comparação
        stop_words = {'e', 'de', 'da', 'do', 'para', 'com', 'ao', 'a', 'o', 'no', 'na'}

        event_words = set(w.lower() for w in event_title.split() if len(w) > 3 and w.lower() not in stop_words)
        domain_cleaned = domain.replace('.com', '').replace('.br', '').replace('.', ' ').replace('-', ' ')
        domain_words = set(w for w in domain_cleaned.split() if len(w) > 3 and w not in stop_words)

        # Se domínio tem >40% das palavras do título = provável site do artista
        if event_words and domain_words:
            common = event_words & domain_words
            match_ratio = len(common) / len(event_words)

            if match_ratio > 0.4:
                logger.info(f"🚫 Site de artista detectado: {domain} (match: {match_ratio:.0%} com '{event_title}')")
                return True

        return False

    def _validate_link_quality(self, extracted_data: dict, event: dict) -> dict[str, Any]:
        """Valida qualidade do link baseado nos dados extraídos.

        Returns:
            dict com: score (0-100), is_quality, issues (lista de problemas)
        """
        from config import LINK_QUALITY_THRESHOLD, ACCEPT_GENERIC_EVENTS

        score = 0
        issues = []

        # PENALIDADE CRÍTICA: Site de artista/venue (-50 pontos)
        url = extracted_data.get("url", "")
        event_title = event.get("titulo", "")
        if url and self._is_artist_or_venue_site(url, event_title):
            score -= 50
            issues.append("⚠️ Link é site institucional do artista/venue (não é plataforma de venda)")

        # Peso: Título específico (30 pontos)
        if extracted_data.get("title"):
            title = extracted_data["title"].lower()
            event_title = event.get("titulo", "").lower()

            # Verificar se título da página corresponde ao evento
            # Tolerância: pelo menos 50% de palavras em comum
            title_words = set(title.split())
            event_words = set(event_title.split())

            if title_words and event_words:
                common_words = title_words & event_words
                similarity = len(common_words) / max(len(event_words), 1)

                if similarity > 0.5:
                    score += 30
                elif similarity > 0.3:
                    score += 15
                    issues.append("Título da página não corresponde bem ao evento")
                else:
                    issues.append("Título da página muito diferente do evento")
            else:
                score += 10  # Pelo menos tem um título
        else:
            issues.append("Página sem título identificável")

        # Peso: Artistas específicos (25 pontos)
        if extracted_data.get("artists") and len(extracted_data["artists"]) > 0:
            score += 25
        else:
            # Verificar se é tipo de evento que aceita genérico
            event_title_lower = event.get("titulo", "").lower()
            is_acceptable_generic = any(
                generic_type in event_title_lower
                for generic_type in ACCEPT_GENERIC_EVENTS
            )

            if is_acceptable_generic:
                score += 20  # Aumentado de 15 para 20 - eventos genéricos aceitáveis têm menos penalidade
                issues.append("Evento sem artistas específicos (aceitável para este tipo)")
            else:
                score += 10  # Novo: dar crédito parcial mesmo sem artistas (reduz rigor)
                issues.append("Artistas não identificados (crédito parcial concedido)")

        # Peso: Data encontrada (10 pontos, reduzido de 15)
        if extracted_data.get("extracted_date", {}).get("found"):
            score += 10
        else:
            issues.append("Data não encontrada na página")

        # Peso: Horário específico (5 pontos, reduzido de 10)
        if extracted_data.get("time"):
            score += 5
        else:
            issues.append("Horário não encontrado")

        # Peso: Preço ou indicação de valor (5 pontos, reduzido de 10)
        if extracted_data.get("price"):
            score += 5
        elif "consultar" in event.get("preco", "").lower():
            score += 3  # Aceita "consultar" com penalidade (reduzido de 5 para 3)

        # Peso: Link de compra funcional (10 pontos)
        if extracted_data.get("purchase_links") and len(extracted_data["purchase_links"]) > 0:
            score += 10
        else:
            issues.append("Link de compra de ingresso não encontrado na página")

        # Bônus: Descrição detalhada (5 pontos adicionais)
        if extracted_data.get("description") and len(extracted_data.get("description", "")) > 100:
            score += 5

        # Penalidade: Link é homepage genérica (-20 pontos)
        if extracted_data.get("is_generic_page"):
            score -= 20
            issues.append("Link é página genérica (homepage/listagem)")

        # Garantir score entre 0-100
        score = max(0, min(100, score))

        return {
            "score": score,
            "is_quality": score >= LINK_QUALITY_THRESHOLD,
            "issues": issues,
            "threshold": LINK_QUALITY_THRESHOLD,
        }

    async def _analyze_with_llm(self, event: dict, evidences: dict) -> dict[str, Any]:
        """Usa LLM (Gemini Flash) para análise final inteligente do evento."""

        # Preparar lista de venues preferidos com endereços
        venues_preferidos = "\n".join([
            f"{venue.replace('_', ' ').title()}: {addrs[0]}"
            for venue, addrs in VENUE_ADDRESSES.items()
        ])

        prompt = f"""Você é um validador inteligente de eventos culturais no Rio de Janeiro.

EVENTO A VALIDAR:
Título: {event.get('titulo', 'N/A')}
Data: {event.get('data', 'N/A')}
Horário: {event.get('horario') or event.get('time', 'N/A')}
Local: {event.get('local', 'N/A')}
Preço: {event.get('preco') or event.get('price', 'N/A')}
Link: {event.get('link_ingresso') or event.get('link', 'N/A')}
Descrição: {event.get('descricao', 'N/A')[:300]}

EVIDÊNCIAS:
Data: {evidences['date']['reason']}
{f"Data extraída do link: {evidences['link'].get('extracted_date', {}).get('dates', [])} (primária: {evidences['link'].get('extracted_date', {}).get('primary_date', 'N/A')})" if evidences['link'].get('extracted_date', {}).get('found') else ""}
{f"Data corrigida: {evidences['date'].get('original_date')} → {evidences['date'].get('corrected_date')}" if evidences['date'].get('corrected') else ""}
Link: {evidences['link'].get('status', 'N/A')} - {evidences['link'].get('reason', '')}

{f"CONTEÚDO DO LINK:\\n{evidences['link'].get('content_preview', '')[:1000]}" if evidences['link'].get('content_preview') else ""}

VENUES PREFERIDOS (endereços corretos conhecidos):
{venues_preferidos}

INSTRUÇÕES - LEIA ATENTAMENTE:
1. **VALIDAÇÃO DE DATA (PRIORIDADE MÁXIMA)**:
   - Se o link está acessível E você identifica data DIFERENTE da informada no evento, REJEITE o evento
   - Datas devem ser EXATAMENTE iguais (formato DD/MM/YYYY)
   - Se a data foi corrigida automaticamente, ACEITE a correção e valide outros aspectos
   - Se data não puder ser confirmada no link, adicione warning: "Data não confirmada na fonte"

2. Se o evento menciona um venue da lista acima, compare o endereço fornecido com o endereço correto

3. Links 404/403 de plataformas confiáveis (Sympla, Eventbrite) podem ser tolerados APENAS se:
   - Não houver outra forma de validação
   - O evento for de venue conhecido e confiável

4. Eventos em venues não listados são aceitáveis se parecerem legítimos

**CRITÉRIOS DE REJEIÇÃO AUTOMÁTICA:**
- Data divergente entre evento e link oficial (NUNCA aprove "apesar da divergência")
- Endereço completamente diferente de venue conhecido
- Informações contraditórias no conteúdo do link

Retorne JSON:
{{
    "approved": true/false,
    "confidence": 0-100,
    "reason": "explicação concisa (NUNCA aprove eventos com 'data divergente' ou 'apesar da diferença')",
    "warnings": ["avisos específicos sobre divergências"],
    "date_mismatch": true/false
}}
"""

        try:
            response = self.agent.run(prompt)
            content = response.content

            # Extrair JSON da resposta
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # Fallback: tentar encontrar JSON com regex
            if not content or content[0] not in ['{', '[']:
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0)

            decision = json.loads(content)

            # Garantir campos obrigatórios
            if "approved" not in decision:
                decision["approved"] = False
            if "confidence" not in decision:
                decision["confidence"] = 50
            if "reason" not in decision:
                decision["reason"] = "Decisão do LLM"
            if "warnings" not in decision:
                decision["warnings"] = []

            logger.info(
                f"LLM decisão: {'APROVADO' if decision['approved'] else 'REJEITADO'} "
                f"(confiança: {decision['confidence']}%) - {decision['reason']}"
            )

            # VERIFICAÇÃO PÓS-LLM: Detectar aprovações suspeitas com divergências
            if decision['approved']:
                reason_lower = decision['reason'].lower()

                # Usar patterns contextuais sobre divergências de DATA especificamente
                # Isso evita falsos positivos com palavras genéricas como "apesar" ou "embora"
                suspicious_patterns = [
                    r'\bdata\s+divergente\b',
                    r'\bdivergência\s+de\s+data\b',
                    r'\bdata.*\bdifere\b',
                    r'\bdata.*\bnão\s+corresponde\b',
                    r'\bdiscrepância.*\bdata\b',
                    r'evento\s+informa.*mas\s+link',
                    r'link\s+mostra\s+\d{2}/\d{2}/\d{4}',
                ]

                if any(re.search(pattern, reason_lower) for pattern in suspicious_patterns):
                    logger.warning(
                        f"⚠️  LLM aprovou evento mas detectou divergência na razão: {decision['reason']}"
                    )
                    decision['approved'] = False
                    decision['reason'] = (
                        f"Rejeitado por divergência detectada pelo LLM: {decision['reason']} "
                        f"(Este evento foi inicialmente aprovado mas contém palavras suspeitas que indicam problemas)"
                    )
                    decision['confidence'] = 0
                    decision['date_mismatch'] = True

            return decision

        except Exception as e:
            logger.error(f"Erro na análise com LLM: {e}")
            # Em caso de erro, ser conservador mas não bloquear tudo
            if VALIDATION_STRICTNESS == "permissive":
                return {
                    "approved": True,
                    "confidence": 30,
                    "reason": f"Erro na análise LLM, aprovado por padrão (modo permissivo): {str(e)}",
                    "warnings": [f"Erro na validação LLM: {str(e)}"],
                }
            else:
                return {
                    "approved": False,
                    "confidence": 0,
                    "reason": f"Erro na análise LLM: {str(e)}",
                }

    def _check_date(self, event: dict) -> dict[str, Any]:
        """Valida formato e período da data."""
        date_str = event.get("data", "")

        if not date_str:
            return {"valid": False, "reason": "Data não fornecida"}

        # Validação RIGOROSA: Rejeitar datas descritivas
        # Detectar palavras que indicam data inválida
        invalid_indicators = ["última", "primeira", "edição", "temporada", "confirmar", "a definir", "tbd", "novembro de"]
        if any(indicator in date_str.lower() for indicator in invalid_indicators):
            return {"valid": False, "reason": f"Data descritiva não aceita (deve ser DD/MM/YYYY): {date_str}"}

        # Validar formato DD/MM/YYYY (estrito - não aceitar texto extra)
        try:
            # Extrair apenas a parte da data (primeira palavra se houver espaços)
            date_part = date_str.split()[0] if ' ' in date_str else date_str

            # Validar formato exato DD/MM/YYYY
            if not date_part or len(date_part) != 10 or date_part.count('/') != 2:
                return {"valid": False, "reason": f"Formato de data inválido (esperado DD/MM/YYYY): {date_str}"}

            event_date = datetime.strptime(date_part, "%d/%m/%Y")
        except (ValueError, IndexError):
            return {"valid": False, "reason": f"Formato de data inválido (esperado DD/MM/YYYY): {date_str}"}

        # Verificar se está no período válido
        # Normalizar para comparar apenas datas (sem horário)
        start_date = SEARCH_CONFIG["start_date"].date()
        end_date = SEARCH_CONFIG["end_date"].date()
        event_date_only = event_date.date()

        if not (start_date <= event_date_only <= end_date):
            return {
                "valid": False,
                "reason": f"Data fora do período válido ({start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')})",
            }

        # VALIDAÇÃO RIGOROSA: Horário
        horario_str = event.get("horario", "")

        if not horario_str:
            return {"valid": False, "reason": "Horário não fornecido"}

        # Rejeitar placeholders de horário
        invalid_time_indicators = ["xx:xx", "x:x", "tbd", "confirmar", "a definir"]
        if any(indicator in horario_str.lower() for indicator in invalid_time_indicators):
            return {"valid": False, "reason": f"Horário placeholder não aceito (deve ser HH:MM): {horario_str}"}

        # Validar formato HH:MM estrito
        if ":" not in horario_str:
            return {"valid": False, "reason": f"Formato de horário inválido (esperado HH:MM): {horario_str}"}

        try:
            hora_partes = horario_str.strip().split(":")
            if len(hora_partes) != 2:
                return {"valid": False, "reason": f"Formato de horário inválido (esperado HH:MM): {horario_str}"}

            hora = int(hora_partes[0])
            minuto = int(hora_partes[1])

            # Validar ranges válidos
            if not (0 <= hora <= 23):
                return {"valid": False, "reason": f"Hora inválida (deve ser 00-23): {horario_str}"}
            if not (0 <= minuto <= 59):
                return {"valid": False, "reason": f"Minuto inválido (deve ser 00-59): {horario_str}"}

        except (ValueError, IndexError):
            return {"valid": False, "reason": f"Formato de horário inválido (esperado HH:MM): {horario_str}"}

        # VALIDAÇÃO GEOGRÁFICA: Apenas eventos no Rio de Janeiro
        local_str = event.get("local", "")

        if not local_str:
            return {"valid": False, "reason": "Local não fornecido"}

        local_lower = local_str.lower()

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
            if city in local_lower:
                return {"valid": False, "reason": f"Evento fora do Rio de Janeiro (cidade: {city})"}

        # VALIDAÇÃO TEMPORAL: Eventos de hoje só aparecem se faltam pelo menos MIN_HOURS_ADVANCE horas
        now = datetime.now()
        if event_date_only == now.date():
            # Evento é hoje - validar horário
            horario_str = event.get("horario", "00:00")
            try:
                # Parse horário (formato HH:MM)
                hora_partes = horario_str.split(":")
                if len(hora_partes) >= 2:
                    hora = int(hora_partes[0])
                    minuto = int(hora_partes[1])
                    event_datetime = datetime.combine(event_date_only, datetime.min.time()).replace(hour=hora, minute=minuto)

                    # Verificar se faltam pelo menos MIN_HOURS_ADVANCE horas
                    hora_minima = now + timedelta(hours=MIN_HOURS_ADVANCE)
                    if event_datetime < hora_minima:
                        return {
                            "valid": False,
                            "reason": f"Evento hoje às {horario_str} já passou ou está muito próximo (menos de {MIN_HOURS_ADVANCE}h)",
                        }
            except (ValueError, IndexError):
                # Se não conseguir parsear horário, aceitar por segurança (modo permissivo)
                logger.warning(f"Não foi possível parsear horário '{horario_str}' para validação temporal")

        return {"valid": True, "reason": "Data válida", "date": event_date.strftime('%d/%m/%Y')}
