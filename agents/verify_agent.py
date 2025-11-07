"""Agente de verificação e validação de eventos."""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import (
    HTTP_TIMEOUT,
    MAX_RETRIES,
    SEARCH_CONFIG,
)
from utils.agent_factory import AgentFactory

logger = logging.getLogger(__name__)

# Prefixo para logs deste agente
LOG_PREFIX = "[VerifyAgent] ✔️"

# Sites SPAs que sempre retornam 200 OK (requerem validação de conteúdo)
SPA_DOMAINS = [
    'eleventickets.com',
    'eventbrite.com.br',
    'eventbrite.com',
]

# Padrões de URL válidos por domínio
URL_PATTERNS = {
    'eleventickets.com': r'!/apresentacao/[a-f0-9]{40}$',  # Hash SHA1 de 40 chars hex (fragment sem #)
}


class VerifyAgent:
    """Agente responsável por verificar e validar informações de eventos."""

    def __init__(self):
        self.log_prefix = "[VerifyAgent] ✔️"

        self.agent = AgentFactory.create_agent(
            name="Event Verification Agent",
            model_type="important",  # GPT-5 - tarefa crítica (verificação rigorosa)
            description="Agente especializado em verificar e validar informações de eventos",
            instructions=[
                "Verificar se as datas dos eventos estão no período correto "
                f"({SEARCH_CONFIG['start_date'].strftime('%d/%m/%Y')} a {SEARCH_CONFIG['end_date'].strftime('%d/%m/%Y')})",
                "Validar se os links de compra são válidos e acessíveis",
                "Identificar e remover eventos duplicados",
                "Confirmar se eventos de comédia não são infantis",
                "Verificar consistência de informações (data/hora/local/preço)",
                "Enriquecer descrições quando necessário",
                "Validar se eventos ao ar livre são realmente em fim de semana",
                "Marcar eventos com baixa confiabilidade para revisão",
            ],
            markdown=True,
        )

    def _is_generic_link(self, url: str) -> bool:
        """Detecta se um link é genérico (página de busca/categoria/listagem).

        Args:
            url: URL a verificar

        Returns:
            True se o link for genérico (não específico de um evento)
        """
        if not url or not isinstance(url, str):
            return False

        # EXCEÇÕES: URLs conhecidas e confiáveis (não marcar como genérico)
        # Estes venues têm apenas página de listagem ou links específicos confiáveis
        trusted_listing_pages = [
            'bluenoterio.com.br/shows',
            'eventim.com.br/artist/blue-note-rio',  # Aceita tanto /artist/ quanto /artist/blue-note-rio/event-name-id/
        ]

        for trusted in trusted_listing_pages:
            if trusted in url.lower():
                return False  # Não é genérico, é confiável

        # Padrões de URLs genéricas
        generic_patterns = [
            r'/eventos/[^/]+\?',  # /eventos/categoria?params
            r'/eventos\?',         # /eventos?params
            r'/eventos/?$',        # /eventos ou /eventos/ no final
            r'/shows/?$',          # /shows ou /shows/ no final (Blue Note, etc)
            r'/agenda/?$',         # /agenda ou /agenda/ no final
            r'/programacao/?$',    # /programacao ou /programacao/ no final
            r'/calendar/?$',       # /calendar ou /calendar/ no final
            r'/schedule/?$',       # /schedule ou /schedule/ no final
            r'/busca\?',          # /busca?query=
            r'/search\?',         # /search?q=
            r'[?&]city=',         # query param de cidade
            r'[?&]partnership=',  # query param de partnership
            r'/d/brazil--',       # eventbrite listings
            r'/eventos/rio-de-janeiro',  # páginas de listagem por cidade
            r'/events/rio-de-janeiro',   # páginas de listagem por cidade
        ]

        for pattern in generic_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True

        # Verificar se URL é homepage (muito curta)
        # Ex: salaceliciameireles.com.br/ ou casadochoro.com.br/
        path = url.split('?')[0]  # Remover query params
        path_parts = [p for p in path.split('/') if p and p not in ['http:', 'https:', '']]

        # URL com apenas domínio (homepage) é genérica
        if len(path_parts) == 1:
            return True

        # URL com domínio + apenas 1 segmento genérico também é genérica
        # Ex: bluenoterio.com.br/shows (2 partes, mas shows é genérico)
        if len(path_parts) == 2:
            generic_segments = ['shows', 'eventos', 'events', 'agenda', 'programacao', 'calendar', 'schedule']
            last_segment = path_parts[-1].lower().rstrip('/')
            if last_segment in generic_segments:
                return True

        return False

    def _matches_url_pattern(self, url: str) -> bool:
        """Valida se URL corresponde ao padrão esperado para o domínio.

        Args:
            url: URL a validar

        Returns:
            True se URL corresponde ao padrão do domínio, False caso contrário
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Verificar se domínio tem padrão definido
            for pattern_domain, pattern in URL_PATTERNS.items():
                if pattern_domain in domain:
                    # Validar contra o padrão
                    full_path = parsed.path + parsed.fragment  # ElevenTickets usa fragment (#/...)
                    if re.search(pattern, full_path):
                        return True
                    else:
                        logger.warning(f"URL não corresponde ao padrão esperado para {pattern_domain}: {url}")
                        return False

            # Domínio sem padrão definido = aceitar
            return True

        except Exception as e:
            logger.error(f"Erro ao validar padrão de URL: {e}")
            return True  # Em caso de erro, não bloquear

    async def _validate_link_content(self, link: str, event: dict) -> dict:
        """Valida conteúdo de link SPA verificando se informações do evento correspondem.

        Args:
            link: URL a validar
            event: Evento com informações esperadas

        Returns:
            dict com: valid (bool), reason (str), details (dict)
        """
        try:
            # Fetch HTML da página
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(link)

                if response.status_code != 200:
                    return {
                        "valid": False,
                        "reason": f"HTTP {response.status_code}",
                        "details": {}
                    }

                # Parse HTML
                soup = BeautifulSoup(response.text, 'html.parser')

                # Extrair texto visível da página
                page_text = soup.get_text(separator=' ', strip=True).lower()

                # Informações do evento para validar
                titulo = (event.get("titulo") or event.get("nome", "")).lower()
                local = (event.get("local", "")).lower()

                # Validações de conteúdo
                issues = []
                matches = []

                # Verificar título (pelo menos 60% das palavras)
                titulo_words = [w for w in titulo.split() if len(w) > 3]  # palavras > 3 chars
                if titulo_words:
                    titulo_matches = sum(1 for word in titulo_words if word in page_text)
                    titulo_match_ratio = titulo_matches / len(titulo_words)

                    if titulo_match_ratio >= 0.6:
                        matches.append(f"Título encontrado ({titulo_match_ratio:.0%})")
                    else:
                        issues.append(f"Título não encontrado ({titulo_match_ratio:.0%} match)")

                # Verificar local (palavras principais)
                local_words = [w for w in local.split() if len(w) > 4]  # palavras > 4 chars
                if local_words:
                    local_matches = sum(1 for word in local_words if word in page_text)
                    local_match_ratio = local_matches / len(local_words) if local_words else 0

                    if local_match_ratio >= 0.5:
                        matches.append(f"Local encontrado ({local_match_ratio:.0%})")
                    else:
                        issues.append(f"Local não encontrado ({local_match_ratio:.0%} match)")

                # Verificar se página tem indicadores de venda (botões de compra)
                buy_indicators = ['comprar', 'ingresso', 'ticket', 'buy', 'cart', 'carrinho']
                has_buy_button = any(indicator in page_text for indicator in buy_indicators)

                if has_buy_button:
                    matches.append("Botão de compra encontrado")
                else:
                    issues.append("Nenhum botão de compra encontrado")

                # Decisão final
                valid = len(matches) >= 2 and len(issues) <= 1

                return {
                    "valid": valid,
                    "reason": "Conteúdo validado" if valid else f"Validação falhou: {', '.join(issues)}",
                    "details": {
                        "matches": matches,
                        "issues": issues,
                        "titulo_match": titulo_match_ratio if titulo_words else None,
                        "local_match": local_match_ratio if local_words else None,
                    }
                }

        except Exception as e:
            logger.error(f"Erro ao validar conteúdo do link: {e}")
            return {
                "valid": True,  # Em caso de erro, não bloquear (pode ser problema temporário)
                "reason": f"Erro na validação: {str(e)}",
                "details": {}
            }

    async def verify_events(self, events_json: str) -> dict[str, Any]:
        """Verifica e valida eventos extraídos pelo agente de busca."""
        logger.info(f"{self.log_prefix} Iniciando verificação de eventos...")

        try:
            events_data = json.loads(events_json) if isinstance(events_json, str) else events_json
        except json.JSONDecodeError:
            logger.error("Erro ao decodificar JSON de eventos")
            return {"verified_events": [], "rejected_events": [], "warnings": ["JSON inválido"]}

        # Validar links em paralelo (validação básica)
        events_with_link_validation = await self._validate_links(events_data)

        # Processar com LLM para verificação inteligente (primeira camada)
        verified_data = self._verify_with_llm(events_with_link_validation)

        # NOVA CAMADA: Validação individual rigorosa com ValidationAgent
        logger.info(f"{self.log_prefix} Iniciando validação individual rigorosa...")
        from agents.validation_agent import ValidationAgent

        validation_agent = ValidationAgent()
        individual_validation = await validation_agent.validate_events_batch(
            verified_data.get("verified_events", [])
        )

        # Combinar resultados
        final_verified = individual_validation["validated_events"]
        final_rejected = (
            verified_data.get("rejected_events", [])
            + individual_validation["rejected_events"]
        )
        final_warnings = (
            verified_data.get("warnings", [])
            + individual_validation["validation_warnings"]
        )

        logger.info(
            f"Verificação concluída. Eventos finais aprovados: {len(final_verified)} "
            f"(rejeitados na validação individual: {len(individual_validation['rejected_events'])})"
        )

        return {
            "verified_events": final_verified,
            "rejected_events": final_rejected,
            "warnings": final_warnings,
            "duplicates_removed": verified_data.get("duplicates_removed", []),
        }

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadTimeout,
        )),
        reraise=True,
    )
    async def _validate_single_link(
        self, client: httpx.AsyncClient, link: str, event: dict = None, attempt_num: int = 1
    ) -> dict:
        """Valida um único link com retry automático para erros temporários.

        Args:
            client: Cliente HTTP assíncrono
            link: URL a validar
            event: Evento (opcional, necessário para validação de conteúdo SPA)
            attempt_num: Número da tentativa

        Returns:
            dict com: valid (bool), status_code (int), spa_validation (dict, opcional)
        """
        logger.info(f"Validando link (tentativa {attempt_num}): {link}")
        response = await client.head(link, timeout=HTTP_TIMEOUT)

        status_valid = 200 <= response.status_code < 400

        if not status_valid:
            return {
                "valid": False,
                "status_code": response.status_code,
            }

        # Se HTTP 200, verificar se é SPA que precisa validação adicional
        parsed = urlparse(link)
        domain = parsed.netloc.lower()
        is_spa = any(spa_domain in domain for spa_domain in SPA_DOMAINS)

        if is_spa:
            logger.info(f"🔍 Link SPA detectado ({domain}), aplicando validação adicional...")

            # 1. Validar padrão de URL
            pattern_valid = self._matches_url_pattern(link)

            if not pattern_valid:
                logger.warning(f"❌ Link SPA falhou validação de padrão: {link}")

                # 2. Tentar validação de conteúdo se padrão falhar E temos dados do evento
                if event:
                    logger.info("→ Tentando validação de conteúdo...")
                    content_validation = await self._validate_link_content(link, event)

                    if content_validation["valid"]:
                        logger.info(f"✅ Link SPA aprovado por validação de conteúdo: {content_validation['reason']}")
                        return {
                            "valid": True,
                            "status_code": response.status_code,
                            "spa_validation": {
                                "type": "content",
                                "result": content_validation
                            }
                        }
                    else:
                        logger.warning(f"❌ Link SPA rejeitado: {content_validation['reason']}")
                        return {
                            "valid": False,
                            "status_code": response.status_code,
                            "spa_validation": {
                                "type": "content",
                                "result": content_validation
                            }
                        }
                else:
                    # Sem dados do evento, não podemos validar conteúdo
                    logger.warning("❌ Link SPA falhou validação de padrão e sem dados para validar conteúdo")
                    return {
                        "valid": False,
                        "status_code": response.status_code,
                        "spa_validation": {
                            "type": "pattern",
                            "reason": "URL não corresponde ao padrão esperado"
                        }
                    }
            else:
                logger.info("✅ Link SPA aprovado por padrão de URL")
                return {
                    "valid": True,
                    "status_code": response.status_code,
                    "spa_validation": {
                        "type": "pattern",
                        "reason": "URL corresponde ao padrão esperado"
                    }
                }

        # Link não-SPA, validação HTTP é suficiente
        return {
            "valid": status_valid,
            "status_code": response.status_code,
        }

    async def _intelligent_link_search(self, event: dict, attempt: int = 1) -> dict[str, Any]:
        """Usa Perplexity para buscar o link correto de um evento e valida o conteúdo.

        Returns:
            dict com: link (str), quality_score (int), validation (dict) ou None se não encontrar
        """
        from config import LINK_MAX_INTELLIGENT_SEARCHES, LINK_QUALITY_THRESHOLD

        if attempt > LINK_MAX_INTELLIGENT_SEARCHES:
            logger.warning(f"{self.log_prefix} Limite de {LINK_MAX_INTELLIGENT_SEARCHES} tentativas atingido para: {event.get('titulo')}")
            return None

        titulo = event.get("titulo", "") or event.get("nome", "")
        data = event.get("data", "")
        horario = event.get("horario", "")
        local = event.get("local", "")
        categoria = event.get("categoria", "")
        preco = event.get("preco", "")
        descricao = event.get("descricao_enriquecida") or event.get("descricao", "")
        fontes = event.get("fontes", [])

        logger.info(f"{self.log_prefix} Buscando link correto (tentativa {attempt}/{LINK_MAX_INTELLIGENT_SEARCHES}): {titulo}")

        # Criar agente de busca com Perplexity
        search_agent = Agent(
            name="Link Search Agent",
            model=OpenAIChat(
                id=MODELS["search"],  # perplexity/sonar-pro
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
            description="Agente especializado em encontrar links oficiais de eventos",
            instructions=[
                "Buscar apenas links OFICIAIS de venda/informações",
                "Priorizar Sympla, Eventbrite, Ticketmaster, site do venue",
                "NÃO retornar links genéricos de homepage",
                "Retornar APENAS o URL ou 'NONE' se não encontrar",
            ],
        )

        # Construir prompt com todas as informações disponíveis
        fonte_info = f"\nFontes mencionadas: {', '.join(fontes[:3])}" if fontes else ""
        horario_info = f"\nHorário: {horario}" if horario else ""
        categoria_info = f"\nCategoria: {categoria}" if categoria else ""
        preco_info = f"\nPreço: {preco}" if preco else ""

        # Se é retry, adicionar contexto do problema anterior
        retry_context = ""
        if attempt > 1:
            retry_context = "\n\n⚠️ TENTATIVA ANTERIOR RETORNOU LINK DE BAIXA QUALIDADE. Por favor, busque um link MAIS ESPECÍFICO que contenha:\n- Título EXATO do evento\n- Data específica\n- Nomes dos artistas/músicos (se houver)\n- Botão de compra de ingresso"

        prompt = f"""Encontre o link de compra/informações OFICIAL para este evento no Rio de Janeiro:

Título: {titulo}
Data: {data}{horario_info}
Local: {local}{categoria_info}{preco_info}
Descrição: {descricao[:200]}{fonte_info}{retry_context}

IMPORTANTE:
- Busque o link ESPECÍFICO deste evento, não a página principal do local
- Priorize plataformas de venda: Sympla, Eventbrite, Ticketmaster
- Se não encontrar em plataformas, busque no site oficial do venue
- Valide que a data e título correspondem ao evento solicitado

Busque em:
- Sympla (sympla.com.br) - busque pelo título exato
- Eventbrite (eventbrite.com.br) - busque pelo título exato
- Ticketmaster Brasil
- Site oficial do venue/local (ex: bluenoterio.com.br, casadochoro.com.br)
- Instagram oficial do evento/local (apenas se tiver link de venda)

Retorne APENAS o URL completo e válido (começando com http:// ou https://), ou "NONE" se não encontrar nada confiável.
NÃO retorne:
- Links genéricos de homepage
- Agregadores de eventos
- Links quebrados
- Páginas de busca"""

        try:
            response = search_agent.run(prompt)
            new_link = response.content.strip()

            # Validar resposta
            if new_link and new_link != "NONE" and new_link.startswith("http"):
                logger.info(f"{self.log_prefix} Link encontrado: {new_link}")

                # Verificar se link é genérico (página de listagem)
                if self._is_generic_link(new_link):
                    logger.warning(f"{self.log_prefix} ❌ Link genérico detectado: {new_link}")

                    # Retry se ainda tiver tentativas
                    if attempt < LINK_MAX_INTELLIGENT_SEARCHES:
                        logger.info(f"{self.log_prefix} Tentando busca novamente solicitando link ESPECÍFICO...")
                        return await self._intelligent_link_search(event, attempt + 1)
                    else:
                        logger.warning(f"{self.log_prefix} Todas tentativas esgotadas. Link genérico rejeitado.")
                        return None

                # NOVO: Validar qualidade do link encontrado
                try:
                    from agents.validation_agent import ValidationAgent

                    validation_agent = ValidationAgent()
                    link_info = await validation_agent._fetch_link_info(new_link, event)

                    quality_validation = link_info.get("quality_validation")

                    if quality_validation:
                        score = quality_validation["score"]
                        is_quality = quality_validation["is_quality"]

                        if is_quality:
                            logger.info(f"{self.log_prefix} ✅ Link aprovado (score: {score}/100)")
                            return {
                                "link": new_link,
                                "quality_score": score,
                                "validation": quality_validation,
                                "structured_data": link_info.get("structured_data", {}),
                            }
                        else:
                            logger.warning(
                                f"{self.log_prefix} ❌ Link rejeitado (score: {score}/{LINK_QUALITY_THRESHOLD})"
                            )
                            logger.warning(f"{self.log_prefix} Issues: {', '.join(quality_validation['issues'])}")

                            # Retry se ainda tiver tentativas
                            if attempt < LINK_MAX_INTELLIGENT_SEARCHES:
                                logger.info(f"{self.log_prefix} Tentando busca novamente com critérios mais rigorosos...")
                                return await self._intelligent_link_search(event, attempt + 1)
                            else:
                                logger.warning(f"{self.log_prefix} Todas tentativas esgotadas. Retornando link mesmo com baixa qualidade.")
                                return {
                                    "link": new_link,
                                    "quality_score": score,
                                    "validation": quality_validation,
                                    "low_quality": True,
                                }
                    else:
                        # Sem validação de qualidade (erro), aceitar link
                        logger.warning(f"{self.log_prefix} Validação de qualidade falhou, aceitando link")
                        return {"link": new_link, "quality_score": None, "validation": None}

                except Exception as e:
                    logger.error(f"{self.log_prefix} Erro ao validar qualidade do link: {e}")
                    # Em caso de erro, retornar link sem validação
                    return {"link": new_link, "quality_score": None, "validation": None}

            else:
                logger.warning(f"{self.log_prefix} ✗ Nenhum link válido encontrado para: {titulo}")
                return None

        except Exception as e:
            logger.error(f"{self.log_prefix} Erro na busca inteligente de link: {e}")
            return None

    async def _validate_single_event_link(
        self, event: dict, client: httpx.AsyncClient
    ) -> dict:
        """Valida o link de um único evento com retry e busca inteligente.

        Args:
            event: Evento a validar
            client: Cliente HTTP assíncrono compartilhado

        Returns:
            Dicionário com estatísticas da validação deste evento
        """
        stats = {
            "total_links": 0,
            "validated_first_try": 0,
            "failed_all_retries": 0,
            "intelligent_searches": 0,
            "links_fixed": 0,
            "no_retry_needed": 0,
            "generic_links_detected": 0,
        }

        link = event.get("link") or event.get("link_ingresso") or event.get("ticket_link")

        if not link:
            logger.info(f"→ Evento sem link, iniciando busca inteligente: {event.get('titulo')}")
            stats["total_links"] += 1
            stats["intelligent_searches"] += 1

            link_result = await self._intelligent_link_search(event)

            if link_result and link_result.get("link"):
                new_link = link_result["link"]
                event["link"] = new_link
                event["link_updated_by_ai"] = True
                event["link_added_by_ai"] = True  # Novo campo para indicar que foi adicionado (não apenas corrigido)
                event["link_quality_score"] = link_result.get("quality_score")
                event["link_quality_validation"] = link_result.get("validation")

                # Armazenar dados estruturados extraídos do link
                if link_result.get("structured_data"):
                    event["link_structured_data"] = link_result["structured_data"]

                # Link já foi validado no _intelligent_link_search
                event["link_valid"] = True
                event["link_status_code"] = 200
                stats["links_fixed"] += 1
                logger.info(f"✓ Link adicionado com sucesso: {new_link}")
            else:
                event["link_valid"] = None
                event["link_error"] = "Nenhum link encontrado via busca inteligente"
                event["requires_manual_link_check"] = True
                logger.warning(f"⚠ Nenhum link encontrado para: {event.get('titulo')}")

            return stats

        # Detectar placeholder "INCOMPLETO" e ir direto para busca inteligente
        if link in ["INCOMPLETO", "incompleto", "/INCOMPLETO", "NONE", "none"]:
            logger.info(f"→ Link placeholder detectado ({link}), iniciando busca inteligente: {event.get('titulo')}")
            stats["total_links"] += 1
            stats["intelligent_searches"] += 1

            link_result = await self._intelligent_link_search(event)

            if link_result and link_result.get("link"):
                new_link = link_result["link"]
                event["link_original"] = link
                event["link"] = new_link
                event["link_updated_by_ai"] = True
                event["link_quality_score"] = link_result.get("quality_score")
                event["link_quality_validation"] = link_result.get("validation")

                # Armazenar dados estruturados extraídos do link
                if link_result.get("structured_data"):
                    event["link_structured_data"] = link_result["structured_data"]

                # Link já foi validado no _intelligent_link_search
                event["link_valid"] = True
                event["link_status_code"] = 200
                stats["links_fixed"] += 1
                logger.info(f"✓ Link corrigido com sucesso: {new_link}")
            else:
                event["link_valid"] = False
                event["link_error"] = "Placeholder sem link válido encontrado"
                event["requires_manual_link_check"] = True
                logger.warning(f"⚠ Nenhum link encontrado para: {event.get('titulo')}")

            return stats

        # Detectar link genérico (página de busca/categoria) e ir para busca inteligente
        if self._is_generic_link(link):
            logger.info(f"🚫 Link genérico detectado, iniciando busca inteligente: {link[:80]}...")
            stats["total_links"] += 1
            stats["generic_links_detected"] += 1
            stats["intelligent_searches"] += 1

            link_result = await self._intelligent_link_search(event)

            if link_result and link_result.get("link"):
                new_link = link_result["link"]
                event["link_original"] = link
                event["link"] = new_link
                event["link_updated_by_ai"] = True
                event["link_was_generic"] = True
                event["link_quality_score"] = link_result.get("quality_score")
                event["link_quality_validation"] = link_result.get("validation")

                # Armazenar dados estruturados extraídos do link
                if link_result.get("structured_data"):
                    event["link_structured_data"] = link_result["structured_data"]

                # Link já foi validado no _intelligent_link_search
                event["link_valid"] = True
                event["link_status_code"] = 200
                stats["links_fixed"] += 1
                logger.info(f"✓ Link genérico substituído por link específico: {new_link}")
            else:
                # Nenhum link específico encontrado, manter genérico mas marcar
                event["link_valid"] = False
                event["link_is_generic"] = True
                event["link_error"] = "Link genérico - página de busca/categoria"
                event["requires_manual_link_check"] = True
                logger.warning(f"⚠ Nenhum link específico encontrado para: {event.get('titulo')}")

            return stats

        stats["total_links"] += 1
        original_link = link

        # EXCEÇÃO 1: Links do Eventim não respondem bem a HEAD requests
        if 'eventim.com.br/artist/blue-note-rio/' in link.lower():
            event["link_valid"] = True
            event["link_status_code"] = 200
            event["validation_skipped"] = "Eventim links are trusted (HEAD requests not supported)"
            stats["validated_first_try"] += 1
            logger.info(f"✓ Link Eventim válido (sem validação HTTP): {link}")
            return stats

        # EXCEÇÃO 2: Links oficiais da Sala Cecília Meireles (.gov.br)
        if 'salaceciliameireles.rj.gov.br/programacao/' in link.lower():
            event["link_valid"] = True
            event["link_status_code"] = 200
            event["validation_skipped"] = "Official Sala Cecília Meireles links are trusted"
            stats["validated_first_try"] += 1
            logger.info(f"✓ Link oficial Sala Cecília válido (sem validação HTTP): {link}")
            return stats

        try:
            # Tentar validar com retry automático (passando evento para validação SPA)
            result = await self._validate_single_link(client, link, event=event, attempt_num=1)
            event["link_valid"] = result["valid"]
            event["link_status_code"] = result["status_code"]

            # Adicionar informações de validação SPA se presente
            if "spa_validation" in result:
                event["spa_validation"] = result["spa_validation"]

            stats["validated_first_try"] += 1
            logger.info(f"✓ Link válido: {link} (status: {result['status_code']})")

        except Exception as e:
            # Verificar se é erro que não deve ter retry (404, 403, etc)
            if isinstance(e, httpx.HTTPStatusError):
                if e.response.status_code in [404, 403, 401, 410]:
                    # Erros permanentes - não fazer retry
                    event["link_valid"] = False
                    event["link_status_code"] = e.response.status_code
                    event["link_error"] = f"HTTP {e.response.status_code}"
                    stats["no_retry_needed"] += 1
                    logger.warning(f"✗ Link com erro permanente: {link} ({e.response.status_code})")

                    # Ir direto para busca inteligente
                    stats["intelligent_searches"] += 1
                    link_result = await self._intelligent_link_search(event)

                    if link_result and link_result.get("link") and link_result["link"] != original_link:
                        new_link = link_result["link"]
                        event["link_original"] = original_link
                        event["link"] = new_link
                        event["link_updated_by_ai"] = True
                        event["link_quality_score"] = link_result.get("quality_score")
                        event["link_quality_validation"] = link_result.get("validation")

                        # Armazenar dados estruturados extraídos do link
                        if link_result.get("structured_data"):
                            event["link_structured_data"] = link_result["structured_data"]

                        # Link já foi validado no _intelligent_link_search
                        event["link_valid"] = True
                        event["link_status_code"] = 200
                        stats["links_fixed"] += 1
                        logger.info(f"✓ Link corrigido com sucesso: {new_link}")

                    return stats

            # Todas as tentativas de retry falharam (timeout, connection error, etc)
            logger.warning(f"✗ Todas as {MAX_RETRIES} tentativas falharam para: {link}")
            logger.warning(f"   Erro: {type(e).__name__}: {e}")

            event["link_valid"] = False
            event["link_error"] = f"{type(e).__name__}: {str(e)}"
            event["link_validation_failed"] = True
            stats["failed_all_retries"] += 1

            # Tentar busca inteligente como último recurso
            logger.info(f"→ Tentando busca inteligente para: {event.get('titulo')}")
            stats["intelligent_searches"] += 1

            link_result = await self._intelligent_link_search(event)

            if link_result and link_result.get("link") and link_result["link"] != original_link:
                new_link = link_result["link"]
                event["link_original"] = original_link
                event["link"] = new_link
                event["link_updated_by_ai"] = True
                event["link_quality_score"] = link_result.get("quality_score")
                event["link_quality_validation"] = link_result.get("validation")

                # Armazenar dados estruturados extraídos do link
                if link_result.get("structured_data"):
                    event["link_structured_data"] = link_result["structured_data"]

                # Link já foi validado no _intelligent_link_search
                event["link_valid"] = True
                event["link_status_code"] = 200
                stats["links_fixed"] += 1
                logger.info(f"✓ Link corrigido com sucesso: {new_link}")
            else:
                # Marcar para revisão manual
                event["requires_manual_link_check"] = True
                logger.warning(f"⚠ Evento requer revisão manual de link: {event.get('titulo')}")

        return stats

    async def _validate_links(self, events: dict | list) -> dict | list:
        """Valida se os links de eventos são acessíveis com retry e busca inteligente (paralelizado)."""
        logger.info(f"{self.log_prefix} Validando links de eventos em paralelo com retry automático...")

        # Extrair eventos da estrutura complexa do structured_events.json
        event_list = []
        if isinstance(events, dict):
            # Estrutura: {"eventos_gerais": {"eventos": [...]}, "eventos_locais_especiais": {...}}
            if "eventos_gerais" in events:
                event_list.extend(events["eventos_gerais"].get("eventos", []))

            if "eventos_locais_especiais" in events:
                for local_name, local_events in events["eventos_locais_especiais"].items():
                    if isinstance(local_events, list):
                        # Filtra eventos reais (apenas dicts, ignora __checagem e outros tipos)
                        event_list.extend([e for e in local_events if isinstance(e, dict) and "__checagem" not in e])

            # Fallback para estrutura simples
            if not event_list:
                event_list = events.get("events", [])
        else:
            event_list = events

        # Estatísticas agregadas
        stats = {
            "total_links": 0,
            "validated_first_try": 0,
            "validated_after_retry": 0,
            "failed_all_retries": 0,
            "intelligent_searches": 0,
            "links_fixed": 0,
            "no_retry_needed": 0,
            "generic_links_detected": 0,
        }

        # Validar todos os links em paralelo
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            # Criar tasks para validar todos os eventos em paralelo
            validation_tasks = [
                self._validate_single_event_link(event, client)
                for event in event_list
            ]

            # Executar todas as validações em paralelo
            logger.info(f"Iniciando validação paralela de {len(event_list)} links...")
            validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)

            # Agregar estatísticas
            for result in validation_results:
                if isinstance(result, dict):
                    for key in stats:
                        stats[key] += result.get(key, 0)

        # Log de estatísticas
        logger.info(f"\n{'='*60}")
        logger.info("📊 Estatísticas de Validação de Links:")
        logger.info(f"  Total de links verificados: {stats['total_links']}")
        logger.info(f"  ✓ Validados na 1ª tentativa: {stats['validated_first_try']}")
        logger.info(f"  ✗ Falharam após todos os retries: {stats['failed_all_retries']}")
        logger.info(f"  ✗ Erros permanentes (404, 403, etc): {stats['no_retry_needed']}")
        logger.info(f"  🚫 Links genéricos detectados: {stats['generic_links_detected']}")
        logger.info(f"  🔍 Buscas inteligentes realizadas: {stats['intelligent_searches']}")
        logger.info(f"  ✓ Links corrigidos via IA: {stats['links_fixed']}")
        logger.info(f"{'='*60}\n")

        return events

    def _verify_with_llm(self, events: dict | list) -> dict[str, Any]:
        """Usa LLM para verificação inteligente de eventos."""
        logger.info("Verificando eventos com LLM...")

        # Calcular datas e dias da semana para passar ao LLM
        start_date = SEARCH_CONFIG['start_date']
        end_date = SEARCH_CONFIG['end_date']

        # Gerar calendário de sábados e domingos no período
        weekends = []
        current = start_date
        while current <= end_date:
            weekday_num = current.weekday()  # 5=sábado, 6=domingo
            if weekday_num in [5, 6]:
                weekday_name = "sábado" if weekday_num == 5 else "domingo"
                weekends.append(f"{current.strftime('%d/%m/%Y')} ({weekday_name})")
            current += timedelta(days=1)

        weekends_text = "\n".join(weekends)

        prompt = f"""
Você é um agente de verificação rigoroso. Analise os eventos abaixo e classifique cada um como:
- APROVADO: evento válido e confiável
- REJEITADO: evento que não atende critérios ou informações inconsistentes

EVENTOS PARA VERIFICAR:
{json.dumps(events, indent=2, ensure_ascii=False)}

PERÍODO VÁLIDO: {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}

SÁBADOS E DOMINGOS NO PERÍODO (para validação de eventos ao ar livre):
{weekends_text}

CRITÉRIOS DE APROVAÇÃO:

1. DATA VÁLIDA:
   - Deve estar entre {start_date.strftime('%d/%m/%Y')} e {end_date.strftime('%d/%m/%Y')}

2. TEATRO COMÉDIA / STAND-UP:
   - APROVAR: comédia adulta, stand-up, humor para adultos, "indicado para maiores de 14/16/18"
   - REJEITAR: apenas se EXPLICITAMENTE infantil ("teatro infantil", "para crianças", "kids", "família")
   - DICA: Se diz "todas as idades mas voltado ao público adulto" → APROVAR (não é infantil)

3. EVENTOS AO AR LIVRE:
   - APROVAR: apenas se data for sábado OU domingo (use lista acima)
   - REJEITAR: se for segunda, terça, quarta, quinta ou sexta-feira

4. LINKS:
   - Links genéricos (ex: sympla.com.br, ticketmaster.com.br) → NÃO rejeitar automaticamente
   - Se link é de plataforma confiável (Sympla, Eventbrite, Ticketmaster) e outras infos estão completas → APROVAR com aviso
   - Apenas rejeitar se link for suspeito ou evento não tiver NENHUMA info de compra

5. INFORMAÇÕES MÍNIMAS:
   - Obrigatório: título, data, local
   - Preço e horário podem ser "Consultar" se outras infos estiverem completas

CRITÉRIOS DE REJEIÇÃO:

- Eventos com data fora do período válido
- Teatro EXPLICITAMENTE infantil na categoria comédia
- Eventos ao ar livre em dias de SEMANA (segunda a sexta)
- Informações extremamente incompletas (falta título OU data OU local)
- Duplicatas exatas (mesmo título, mesma data, mesmo local)

CRITÉRIOS DE DUPLICATAS:
- Mesmo evento: mesmo título (ou muito similar >90%), mesma data, mesmo local
- EXCEÇÃO: Sessões diferentes do MESMO evento em datas diferentes NÃO são duplicatas (ex: "Show X" dia 12 e "Show X" dia 13)

TAREFA:
Retorne JSON estruturado:
{{
    "verified_events": [eventos aprovados com descrição enriquecida],
    "rejected_events": [eventos rejeitados com motivo claro],
    "warnings": [avisos gerais sobre validações],
    "duplicates_removed": [lista de duplicatas removidas]
}}

IMPORTANTE:
- Para cada evento aprovado, ENRIQUEÇA a descrição se ela estiver muito curta
- Para eventos rejeitados, explique CLARAMENTE o motivo
- Seja mais PERMISSIVO com links genéricos de plataformas confiáveis
- Valide dias da semana usando a lista de sábados/domingos fornecida acima
"""

        try:
            response = self.agent.run(prompt)
            content = response.content

            # Tentar extrair JSON da resposta
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            verified_data = json.loads(content)
            return verified_data

        except Exception as e:
            logger.error(f"Erro ao verificar com LLM: {e}")
            return {
                "verified_events": [],
                "rejected_events": [],
                "warnings": [f"Erro na verificação: {str(e)}"],
            }

    def get_verification_stats(self, verified_data: dict[str, Any]) -> dict[str, int]:
        """Retorna estatísticas da verificação."""
        return {
            "total_verified": len(verified_data.get("verified_events", [])),
            "total_rejected": len(verified_data.get("rejected_events", [])),
            "total_warnings": len(verified_data.get("warnings", [])),
            "duplicates_removed": len(verified_data.get("duplicates_removed", [])),
        }
