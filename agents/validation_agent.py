"""Agente de validação individual inteligente de eventos com LLM."""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup

from agents.base_agent import BaseAgent
from config import (
    HTTP_TIMEOUT,
    LinkStatus,
    MIN_HOURS_ADVANCE,
    SEARCH_CONFIG,
    VALIDATION_STRICTNESS,
    VENUE_ADDRESSES,
)
from utils.date_validator import DateValidator
from utils.http_client import HttpClientWrapper
from utils.link_validator import LinkValidator

logger = logging.getLogger(__name__)


class ValidationAgent(BaseAgent):
    """Agente especializado em validação individual inteligente com LLM."""

    def __init__(self, http_client=None):
        """Inicializa ValidationAgent.

        Args:
            http_client: HttpClientWrapper opcional para dependency injection (útil para testes)
        """
        super().__init__(
            agent_name="ValidationAgent",
            log_emoji="⚖️",
            model_type="important",  # Gemini Flash 1.5 - validação de eventos
            description="Agente especializado em validação inteligente de eventos usando LLM",
            instructions=[
                "Validar eventos de forma inteligente e flexível",
                "Usar bom senso para aceitar eventos legítimos",
                "Rejeitar apenas eventos claramente falsos ou absurdos",
                "Considerar contexto e plausibilidade geral",
            ],
            markdown=True,
            http_client=http_client,
        )

    def _validate_geographic_location(self, event: dict) -> tuple[bool, str]:
        """Valida se evento está dentro do Rio de Janeiro (não em outras cidades).

        Args:
            event: Dicionário do evento com campo 'local'

        Returns:
            tuple: (is_valid, reason) - True se válido, False com motivo se inválido
        """
        local = event.get("local", "").lower()

        # Municípios FORA do Rio que devem ser rejeitados
        MUNICIPIOS_FORA_RIO = [
            "saquarema", "cabo frio", "búzios", "buzios", "arraial do cabo",
            "maricá", "marica", "itaboraí", "itaborai", "nova iguaçu", "nova iguacu",
            "belford roxo", "são joão de meriti", "sao joao de meriti",
            "mesquita", "nilópolis", "nilopolis", "queimados", "japeri",
            "paracambi", "seropédica", "seropedica", "itaguaí", "itaguai",
            "mangaratiba", "angra dos reis", "paraty", "petrópolis", "petropolis",
            "teresópolis", "teresopolis", "nova friburgo", "magé", "mage"
        ]

        # Rejeitar se menciona município fora do Rio
        for municipio in MUNICIPIOS_FORA_RIO:
            if municipio in local:
                return False, f"Evento fora do Rio de Janeiro (localizado em {municipio.title()})"

        # Aceitar explicitamente Rio de Janeiro e Niterói (região metropolitana aceitável)
        MUNICIPIOS_ACEITAVEIS = ["rio de janeiro", "niterói", "niteroi"]
        if any(cidade in local for cidade in MUNICIPIOS_ACEITAVEIS):
            return True, ""

        # Bairros conhecidos do Rio (aceitar se menciona qualquer um)
        BAIRROS_RIO = [
            "copacabana", "ipanema", "leblon", "centro", "lapa", "botafogo",
            "flamengo", "tijuca", "barra", "recreio", "jacarepaguá", "jacarepagua",
            "santa teresa", "urca", "lagoa", "gávea", "gavea", "jardim botânico",
            "jardim botanico", "humaitá", "humaita", "laranjeiras", "catete",
            "glória", "gloria", "cinelândia", "cinelandia", "são cristóvão",
            "sao cristovao", "maracanã", "maracana", "vila isabel", "grajaú",
            "grajau", "méier", "meier", "ramos", "olaria", "penha", "bonsucesso",
            "ilha do governador", "campo grande", "bangu", "realengo", "madureira"
        ]

        if any(bairro in local for bairro in BAIRROS_RIO):
            return True, ""

        # Se não tem município nem bairro, aceitar (modo permissivo para venues sem endereço completo)
        # Ex: "Blue Note Rio" sem endereço completo
        return True, ""

    def _initialize_dependencies(self, http_client=None, **kwargs):
        """Inicializa HTTP client, date validator e link validator.

        Args:
            http_client: HttpClientWrapper opcional para dependency injection (útil para testes)
            **kwargs: Argumentos adicionais
        """
        self.http_client = http_client or HttpClientWrapper()
        self.date_validator = DateValidator()
        self.link_validator = LinkValidator()

    def _load_validation_config(self) -> dict[str, Any]:
        """Carrega configurações de validação do YAML."""
        from utils.config_loader import ConfigLoader
        return ConfigLoader.load_validation_config()

    def _format_updated_info(self, validation_config: dict) -> str:
        """Formata informações atualizadas de eventos recorrentes."""
        from utils.config_loader import ConfigLoader
        return ConfigLoader.format_updated_info(validation_config)

    def _get_category_rules(self, validation_config: dict, categoria: str) -> dict[str, Any]:
        """Obtém regras de validação para uma categoria específica."""
        rules = validation_config.get('validation_rules', {})

        # Normalizar nome da categoria (remover /Parques, espaços, etc)
        categoria_key = categoria.lower().split('/')[0].strip().replace(' ', '_')

        return rules.get(categoria_key, {
            'require_link': True,
            'allow_weekdays': True,
            'allow_generic_links': False,
            'description': ''
        })

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
            # Teatros oficiais
            'teatro municipal', 'theatro municipal',
            'cidade das artes',
            'theatro net', 'teatro net rio',

            # Salas de concerto
            'sala cecília meireles', 'cecilia meireles',

            # Casas de show especializadas
            'blue note', 'bluenote',
            'casa do choro', 'casa de choro',

            # Centros culturais públicos/institucionais
            'ccbb', 'centro cultural banco do brasil',
            'ccjf', 'centro cultural justiça federal',
            'oi futuro', 'centro cultural oi futuro',
            'parque lage', 'escola de artes visuais parque lage',
            'ims', 'instituto moreira salles',
            'mam', 'museu de arte moderna',

            # SESCs (programação curada)
            'sesc', 'sesc copacabana', 'sesc flamengo', 'sesc tijuca', 'sesc engenho',

            # Cinemas de referência
            'espaço itaú', 'itau de cinema',
            'estação net', 'estacao net',
            'kinoplex',
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
            # FILTRO GEOGRÁFICO: Rejeitar eventos fora do Rio de Janeiro
            is_valid_location, geo_reason = self._validate_geographic_location(event)
            if not is_valid_location:
                rejected_events.append({
                    **event,
                    "motivo_rejeicao": geo_reason,
                    "confidence": 100,  # Alta confiança na rejeição geográfica
                })
                logger.warning(
                    f"✗ Rejeitado (geo): {event.get('titulo', 'Sem título')} - {geo_reason}"
                )
                continue  # Pular para próximo evento

            # Validação normal
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

        # Logar estatísticas de validação de datas
        self.date_validator.log_validation_stats()

        return {
            "validated_events": validated_events,
            "rejected_events": rejected_events,
            "validation_warnings": validation_warnings,
        }

    async def validate_event_individually(self, event: dict) -> dict[str, Any]:
        """Valida um único evento usando LLM para decisão inteligente."""

        # Coletar evidências sobre o evento
        evidences = {}

        # 1. Validar data (obrigatório) - usando DateValidator
        date_check = self.date_validator.check_event_date(event)
        evidences["date"] = date_check
        if not date_check["valid"]:
            return {
                "approved": False,
                "reason": date_check["reason"],
                "confidence": 0,
            }

        # 2. Buscar informações do link (se tiver)
        from utils.event_normalizer import EventNormalizer
        link = EventNormalizer.get_link(event) or ""
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
                    "status": LinkStatus.NOT_FOUND,
                    "status_code": 404,
                    "reason": "Link retorna 404 (não encontrado)",
                }
            elif status_code == 403:
                return {
                    "status": LinkStatus.FORBIDDEN,
                    "status_code": 403,
                    "reason": "Link bloqueado (403 Forbidden)",
                }
            elif result["error"] == "Timeout":
                return {
                    "status": LinkStatus.TIMEOUT,
                    "reason": "Timeout ao acessar link",
                }
            elif status_code:
                return {
                    "status": LinkStatus.ERROR,
                    "status_code": status_code,
                    "reason": f"Link retorna status {status_code}",
                }
            else:
                return {
                    "status": LinkStatus.ERROR,
                    "reason": f"Erro ao acessar link: {result['error']}",
                }

        # Sucesso - processar conteúdo
        page_text = result["text"]
        soup = result["soup"]

        # Extrair datas do conteúdo - usando DateValidator
        extracted_date = self.date_validator.extract_dates_from_html(page_text)

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
            "status": LinkStatus.ACCESSIBLE,
            "status_code": 200,
            "content_preview": page_text,
            "extracted_date": extracted_date,
            "structured_data": structured_data,
            "quality_validation": quality_validation,
        }


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
        return self.link_validator.is_artist_or_venue_site(url, event_title)

    def _validate_link_quality(self, extracted_data: dict, event: dict) -> dict[str, Any]:
        """Valida qualidade do link baseado nos dados extraídos.

        Returns:
            dict com: score (0-100), is_quality, issues (lista de problemas)
        """
        from config import LINK_QUALITY_THRESHOLD, ACCEPT_GENERIC_EVENTS

        return self.link_validator.validate_link_quality(
            extracted_data=extracted_data,
            event=event,
            quality_threshold=LINK_QUALITY_THRESHOLD,
            accept_generic_events=ACCEPT_GENERIC_EVENTS,
        )

    async def _analyze_with_llm(self, event: dict, evidences: dict) -> dict[str, Any]:
        """Usa LLM (Gemini Flash) para análise final inteligente do evento."""

        # Carregar configurações de validação do YAML
        validation_config = self._load_validation_config()
        updated_info_text = self._format_updated_info(validation_config)

        # Obter regras específicas da categoria do evento
        categoria = event.get('categoria', '')
        category_rules = self._get_category_rules(validation_config, categoria)

        # Preparar lista de venues preferidos com endereços
        venues_preferidos = "\n".join([
            f"{venue.replace('_', ' ').title()}: {addrs[0]}"
            for venue, addrs in VENUE_ADDRESSES.items()
        ])

        # Formatar regras da categoria
        category_rules_text = f"""
REGRAS PARA CATEGORIA '{categoria}':
- Requer link: {'Sim' if category_rules.get('require_link', True) else 'Não (eventos sem link são aceitáveis)'}
- Dias permitidos: {'Qualquer dia' if category_rules.get('allow_weekdays', True) else 'Apenas sábados e domingos'}
- Links genéricos: {'Aceitáveis' if category_rules.get('allow_generic_links', False) else 'Não aceitáveis'}
- Nota: {category_rules.get('description', 'N/A')}
"""

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

⚠️ INFORMAÇÕES ATUALIZADAS SOBRE EVENTOS RECORRENTES (2025):
{updated_info_text}

{category_rules_text}

INSTRUÇÕES - LEIA ATENTAMENTE:
1. **VALIDAÇÃO DE DATA (PRIORIDADE MÁXIMA)**:
   - Se o link está acessível E você identifica data DIFERENTE da informada no evento, REJEITE o evento
   - Datas devem ser EXATAMENTE iguais (formato DD/MM/YYYY)
   - Se a data foi corrigida automaticamente, ACEITE a correção e valide outros aspectos
   - Se data não puder ser confirmada no link, adicione warning: "Data não confirmada na fonte"

2. Se o evento menciona um venue da lista acima, compare o endereço fornecido com o endereço correto

3. **VALIDAÇÃO DE LINKS** (considere regras da categoria acima):
   - Se categoria NÃO requer link: eventos sem link são ACEITÁVEIS (ex: outdoor gratuito)
   - Links 404/403 de plataformas confiáveis (Sympla, Eventbrite) podem ser tolerados APENAS se:
     * Não houver outra forma de validação
     * O evento for de venue conhecido e confiável
   - Links genéricos: consultar regras da categoria acima

4. Eventos em venues não listados são aceitáveis se parecerem legítimos

**CRITÉRIOS DE REJEIÇÃO AUTOMÁTICA:**
- Data divergente entre evento e link oficial (NUNCA aprove "apesar da divergência")
- Endereço completamente diferente de venue conhecido
- Informações contraditórias no conteúdo do link
- ⚠️ EXCETO: Para eventos outdoor sem link (consultar regras de categoria acima)

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

            # Usar LLMResponseParser para validação consistente
            from utils.llm_response_parser import LLMResponseParser
            decision = LLMResponseParser.parse_validation_response(
                response.content,
                default_approved=False,
                default_confidence=50
            )

            # Campo quality_score é opcional, mas vamos garantir
            if "quality_score" not in decision:
                decision["quality_score"] = 0
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

