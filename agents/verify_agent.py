"""Agente de verificação e validação de eventos."""

import asyncio
import difflib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from config import (
    HTTP_TIMEOUT,
    LINK_VALIDATION_MAX_CONCURRENT,
    MAX_RETRIES,
    SEARCH_CONFIG,
)
from utils.agent_factory import AgentFactory
from utils.http_client import HttpClientWrapper

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
        self.http_client = HttpClientWrapper()

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

    def _find_consensus(self, links: list[str], event: dict) -> dict[str, Any] | None:
        """Encontra consenso entre múltiplos links retornados por diferentes buscas.

        Args:
            links: Lista de links encontrados (pode conter duplicatas e None)
            event: Dados do evento (para logging)

        Returns:
            dict com link consensual e metadados, ou None se não houver consenso
        """
        from collections import Counter
        from config import LINK_CONSENSUS_THRESHOLD, LINK_CONSENSUS_USE_GPT5_TIEBREAKER

        titulo = event.get("titulo", "")

        # Filtrar links válidos (remover None, vazios, "NONE")
        valid_links = [
            link.strip()
            for link in links
            if link and isinstance(link, str) and link.strip() and link.strip().upper() != "NONE"
        ]

        if not valid_links:
            logger.warning(f"{self.log_prefix} Nenhum link válido para consenso: {titulo}")
            return None

        # Normalizar URLs (remover trailing slashes, query params opcionais)
        def normalize_url(url: str) -> str:
            """Normaliza URL para comparação (mantém path e domínio)."""
            # Remove trailing slash
            normalized = url.rstrip('/')
            # Remove fragmentos (#)
            normalized = normalized.split('#')[0]
            return normalized

        normalized_links = [normalize_url(link) for link in valid_links]

        # Contar ocorrências
        link_counts = Counter(normalized_links)
        total_searches = len(links)  # Total de buscas (incluindo falhas)
        threshold = LINK_CONSENSUS_THRESHOLD

        logger.info(f"{self.log_prefix} Consenso de links para '{titulo}':")
        logger.info(f"{self.log_prefix}   Total de buscas: {total_searches}")
        logger.info(f"{self.log_prefix}   Links válidos: {len(valid_links)}")
        logger.info(f"{self.log_prefix}   Links únicos: {len(link_counts)}")

        # Encontrar link com maior frequência
        most_common_link, count = link_counts.most_common(1)[0]
        consensus_ratio = count / total_searches

        logger.info(f"{self.log_prefix}   Link mais comum: {most_common_link}")
        logger.info(f"{self.log_prefix}   Aparições: {count}/{total_searches} ({consensus_ratio:.1%})")

        # Verificar se atingiu threshold
        if consensus_ratio >= threshold:
            logger.info(f"{self.log_prefix} ✅ CONSENSO ATINGIDO ({consensus_ratio:.1%} >= {threshold:.1%})")
            return {
                "link": most_common_link,
                "consensus_ratio": consensus_ratio,
                "votes": count,
                "total_votes": total_searches,
                "method": "majority_vote",
            }

        # EMPATE ou consenso insuficiente
        logger.warning(f"{self.log_prefix} ⚠️ CONSENSO INSUFICIENTE ({consensus_ratio:.1%} < {threshold:.1%})")

        # Se habilitado, usar GPT-5 Mini como tiebreaker
        if LINK_CONSENSUS_USE_GPT5_TIEBREAKER and len(link_counts) > 1:
            logger.info(f"{self.log_prefix} Usando GPT-5 Mini como desempate...")
            tiebreaker_link = self._tiebreaker_with_gpt5(list(link_counts.keys()), event)
            if tiebreaker_link:
                logger.info(f"{self.log_prefix} ✅ DESEMPATE GPT-5: {tiebreaker_link}")
                return {
                    "link": tiebreaker_link,
                    "consensus_ratio": 0.0,  # Não teve consenso por voto
                    "votes": 0,
                    "total_votes": total_searches,
                    "method": "gpt5_tiebreaker",
                    "tiebreaker_candidates": list(link_counts.keys()),
                }

        # Sem consenso e sem desempate
        logger.warning(f"{self.log_prefix} ❌ Falha no consenso para: {titulo}")
        return None

    def _tiebreaker_with_gpt5(self, candidate_links: list[str], event: dict) -> str | None:
        """Usa GPT-5 Mini com web search para escolher o melhor link em caso de empate.

        Args:
            candidate_links: Links candidatos (2 ou mais)
            event: Dados do evento

        Returns:
            URL escolhido pelo GPT-5 Mini, ou None se falhar
        """
        from phidata.agent import Agent
        from phidata.models.openai import OpenAIChat
        from config import MODELS, OPENROUTER_API_KEY, OPENROUTER_BASE_URL

        titulo = event.get("titulo", "")
        data = event.get("data", "")
        local = event.get("local", "")

        logger.info(f"{self.log_prefix} GPT-5 Mini: escolhendo entre {len(candidate_links)} links candidatos")

        # Criar agente GPT-5 Mini com web search
        tiebreaker_agent = Agent(
            name="Link Tiebreaker Agent",
            model=OpenAIChat(
                id=MODELS["link_consensus"],  # openai/gpt-5-mini:online
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
            description="Agente especializado em escolher o melhor link entre candidatos",
            instructions=[
                "Usar web search para verificar qual link é mais confiável",
                "Priorizar links de plataformas oficiais (Sympla, Eventbrite, etc)",
                "Verificar se o link realmente corresponde ao evento específico",
                "Retornar APENAS o URL escolhido (nada mais)",
            ],
        )

        # Formatar links candidatos
        links_formatted = "\n".join([f"  {i+1}. {link}" for i, link in enumerate(candidate_links)])

        prompt = f"""Escolha o MELHOR link para este evento entre os candidatos abaixo.

EVENTO:
- Título: {titulo}
- Data: {data}
- Local: {local}

LINKS CANDIDATOS (escolha apenas 1):
{links_formatted}

CRITÉRIOS DE ESCOLHA:
1. Link de plataforma oficial de venda (Sympla, Eventbrite, etc) > site do venue > outros
2. Link que realmente corresponde ao evento específico (não genérico)
3. Link ativo e acessível (verificar com web search se possível)

RETORNE APENAS:
- O URL completo do link escolhido (copie exatamente como está acima)
- NÃO adicione explicações ou justificativas"""

        try:
            response = tiebreaker_agent.run(prompt)
            chosen_link = response.content.strip()

            # Validar que é um dos candidatos
            normalized_chosen = chosen_link.rstrip('/').split('#')[0]
            for candidate in candidate_links:
                normalized_candidate = candidate.rstrip('/').split('#')[0]
                if normalized_chosen == normalized_candidate:
                    logger.info(f"{self.log_prefix} GPT-5 Mini escolheu: {candidate}")
                    return candidate

            logger.warning(f"{self.log_prefix} GPT-5 Mini retornou link inválido: {chosen_link}")
            return None

        except Exception as e:
            logger.error(f"{self.log_prefix} Erro no tiebreaker GPT-5: {e}")
            return None

    async def _search_with_variants(self, event: dict, variant_suffix: str = "") -> str | None:
        """Executa busca com Perplexity com pequenas variações para diversificar resultados.

        Args:
            event: Dados do evento
            variant_suffix: Sufixo para adicionar variação na busca (ex: "sympla", "eventbrite")

        Returns:
            URL encontrado ou None
        """
        from phidata.agent import Agent
        from phidata.models.openai import OpenAIChat
        from config import MODELS, OPENROUTER_API_KEY, OPENROUTER_BASE_URL

        titulo = event.get("titulo", "") or event.get("nome", "")
        data = event.get("data", "")
        local = event.get("local", "")

        # Criar agente de busca com Perplexity
        search_agent = Agent(
            name="Link Search Agent",
            model=OpenAIChat(
                id=MODELS["search"],  # perplexity/sonar
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

        # Adicionar variação à busca se especificada
        platform_hint = f"\nPRIORIDADE: Buscar preferencialmente em {variant_suffix}" if variant_suffix else ""

        prompt = f"""Encontre o link OFICIAL de compra/venda de ingresso para este evento:

EVENTO:
- Título: {titulo}
- Data: {data}
- Local: {local}{platform_hint}

⚠️ REGRAS:
1. NÃO retorne homepages ou páginas de listagem
2. Link DEVE ser específico do evento (com ID/slug único)
3. Retorne APENAS o URL completo ou "NONE"

RETORNE APENAS:
- O URL completo (https://...) OU
- A palavra "NONE" (se não encontrar)"""

        try:
            response = search_agent.run(prompt)
            link = response.content.strip()

            if link and link != "NONE" and link.startswith("http"):
                logger.info(f"{self.log_prefix} Busca{f' ({variant_suffix})' if variant_suffix else ''}: {link}")
                return link
            else:
                logger.warning(f"{self.log_prefix} Busca{f' ({variant_suffix})' if variant_suffix else ''}: NONE")
                return None

        except Exception as e:
            logger.error(f"{self.log_prefix} Erro na busca com variante: {e}")
            return None

    async def _intelligent_link_search_with_consensus(self, event: dict, attempt: int = 1) -> dict[str, Any]:
        """Versão com consenso multi-modelo do _intelligent_link_search().

        Executa múltiplas buscas independentes e usa consenso para reduzir alucinações.

        Returns:
            dict com: link (str), quality_score (int), validation (dict), consensus_info (dict)
        """
        from config import (
            LINK_CONSENSUS_ENABLED,
            LINK_CONSENSUS_SEARCHES,
            LINK_MAX_INTELLIGENT_SEARCHES,
            LINK_QUALITY_THRESHOLD,
        )

        titulo = event.get("titulo", "") or event.get("nome", "")

        # Se consenso desabilitado, usar método tradicional
        if not LINK_CONSENSUS_ENABLED:
            return await self._intelligent_link_search(event, attempt)

        if attempt > LINK_MAX_INTELLIGENT_SEARCHES:
            logger.warning(f"{self.log_prefix} Limite de {LINK_MAX_INTELLIGENT_SEARCHES} tentativas atingido: {titulo}")
            return None

        logger.info(f"{self.log_prefix} Busca com consenso (tentativa {attempt}/{LINK_MAX_INTELLIGENT_SEARCHES}): {titulo}")

        # Executar múltiplas buscas independentes em paralelo
        search_tasks = []

        # Primeira busca sem variação
        search_tasks.append(self._search_with_variants(event, ""))

        # Demais buscas com hints de plataforma (para diversificar)
        platform_variants = ["sympla", "eventbrite", "site oficial"]
        for i in range(1, LINK_CONSENSUS_SEARCHES):
            variant = platform_variants[i % len(platform_variants)]
            search_tasks.append(self._search_with_variants(event, variant))

        # Executar todas em paralelo
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Converter exceções em None
        links = [result if not isinstance(result, Exception) else None for result in search_results]

        logger.info(f"{self.log_prefix} Resultados de {LINK_CONSENSUS_SEARCHES} buscas: {links}")

        # Encontrar consenso
        consensus_result = self._find_consensus(links, event)

        if not consensus_result:
            logger.warning(f"{self.log_prefix} Nenhum consenso encontrado para: {titulo}")

            # Retry se ainda tiver tentativas
            if attempt < LINK_MAX_INTELLIGENT_SEARCHES:
                logger.info(f"{self.log_prefix} Tentando novamente com novos critérios...")
                return await self._intelligent_link_search_with_consensus(event, attempt + 1)
            else:
                return None

        # Validar qualidade do link consensual
        consensus_link = consensus_result["link"]

        # Verificar se link é genérico
        if self._is_generic_link(consensus_link):
            logger.warning(f"{self.log_prefix} ❌ Link consensual é genérico: {consensus_link}")
            if attempt < LINK_MAX_INTELLIGENT_SEARCHES:
                return await self._intelligent_link_search_with_consensus(event, attempt + 1)
            else:
                return None

        # Validar qualidade
        try:
            from agents.validation_agent import ValidationAgent

            validation_agent = ValidationAgent()
            link_info = await validation_agent._fetch_link_info(consensus_link, event)

            quality_validation = link_info.get("quality_validation")

            if quality_validation:
                score = quality_validation["score"]
                is_quality = quality_validation["is_quality"]

                if is_quality:
                    logger.info(f"{self.log_prefix} ✅ Link consensual aprovado (score: {score}/100)")
                    return {
                        "link": consensus_link,
                        "quality_score": score,
                        "validation": quality_validation,
                        "consensus_info": consensus_result,
                        "structured_data": link_info.get("structured_data", {}),
                    }
                else:
                    logger.warning(f"{self.log_prefix} ❌ Link consensual rejeitado (score: {score}/{LINK_QUALITY_THRESHOLD})")
                    if attempt < LINK_MAX_INTELLIGENT_SEARCHES:
                        return await self._intelligent_link_search_with_consensus(event, attempt + 1)
                    else:
                        # Última tentativa - retornar mesmo com baixa qualidade
                        return {
                            "link": consensus_link,
                            "quality_score": score,
                            "validation": quality_validation,
                            "consensus_info": consensus_result,
                            "low_quality": True,
                        }
            else:
                # Sem validação, aceitar link consensual
                logger.warning(f"{self.log_prefix} Validação falhou, aceitando link consensual")
                return {
                    "link": consensus_link,
                    "quality_score": None,
                    "validation": None,
                    "consensus_info": consensus_result,
                }

        except Exception as e:
            logger.error(f"{self.log_prefix} Erro ao validar link consensual: {e}")
            return {
                "link": consensus_link,
                "quality_score": None,
                "validation": None,
                "consensus_info": consensus_result,
            }

    def _classify_link_type(self, url: str, event: dict) -> str:
        """Classifica o tipo de link do evento.

        Args:
            url: URL do link
            event: Dados do evento (para contexto)

        Returns:
            "purchase" (plataforma de venda), "info" (site informativo), ou "venue" (página do local)
        """
        if not url:
            return "info"  # Default para links ausentes

        url_lower = url.lower()

        # 1. PLATAFORMAS DE VENDA (maior prioridade)
        purchase_platforms = [
            'sympla.com',
            'eventbrite.com',
            'ticketmaster.com',
            'ingresso.com',
            'ingressodigital.com',
            'tickets.com',
            'eventim.com.br/artist',  # Eventim com artista específico
            'eleventickets.com',
        ]

        for platform in purchase_platforms:
            if platform in url_lower:
                return "purchase"

        # 2. VENUES COM PÁGINAS ESPECÍFICAS DE EVENTOS
        venue_event_patterns = [
            ('bluenoterio.com.br/shows/', 5),  # Blue Note com slug do show
            ('salaceliciameireles.rj.gov.br/programacao/', 5),  # Sala Cecília com evento específico
        ]

        for pattern, min_length in venue_event_patterns:
            if pattern in url_lower:
                # Verificar se tem slug/ID significativo no final
                slug = url.split('/')[-1].rstrip('/')
                if len(slug) > min_length:
                    return "purchase"  # Página específica de evento

        # 3. VERIFICAR SE É LINK GENÉRICO (listagem/homepage)
        if self._is_generic_link(url):
            return "venue"  # Links genéricos geralmente são páginas do venue

        # 4. VERIFICAR SE É SITE DE ARTISTA (informativo)
        # NOTA: _is_artist_or_venue_site precisa do título do evento
        titulo = event.get("titulo", "")
        if titulo:
            try:
                if hasattr(self, '_validation_agent') and self._validation_agent:
                    if self._validation_agent._is_artist_or_venue_site(url, titulo):
                        return "info"
            except:
                pass  # Se falhar, continuar com outras verificações

        # 5. DOMÍNIOS .GOV.BR = venue
        if '.gov.br' in url_lower:
            return "venue"

        # 6. FALLBACK: Link externo genérico = info
        return "info"

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
            # Fetch + parse usando HttpClientWrapper
            result = await self.http_client.fetch_and_parse(
                link,
                extract_text=True,
                text_max_length=5000,  # Mais texto para validação de conteúdo
                clean_html=True
            )

            if not result["success"]:
                status_code = result["status_code"]
                return {
                    "valid": False,
                    "reason": f"HTTP {status_code}" if status_code else result["error"],
                    "details": {}
                }

            # Extrair texto visível da página
            page_text = result["text"].lower()

            # QUICK WIN #1: Validar conteúdo mínimo (detectar soft 404s)
            if not page_text or len(page_text.strip()) < 50:
                return {
                    "valid": False,
                    "reason": "Página vazia ou conteúdo muito curto (possível 404 disfarçado)",
                    "details": {"page_length": len(page_text.strip()) if page_text else 0}
                }

            # Informações do evento para validar
            titulo = (event.get("titulo") or event.get("nome", "")).lower()
            local = (event.get("local", "")).lower()

            # Validações de conteúdo
            issues = []
            matches = []

            # Verificar título (pelo menos 70% das palavras) - threshold aumentado para reduzir falsos positivos
            titulo_words = [w for w in titulo.split() if len(w) > 3]  # palavras > 3 chars
            titulo_match_ratio = 0
            if titulo_words:
                titulo_matches = sum(1 for word in titulo_words if word in page_text)
                titulo_match_ratio = titulo_matches / len(titulo_words)

                if titulo_match_ratio >= 0.7:  # Aumentado de 0.5 para 0.7 (reduzir falsos positivos)
                    matches.append(f"Título encontrado ({titulo_match_ratio:.0%})")
                else:
                    issues.append(f"Título não encontrado ({titulo_match_ratio:.0%} match)")

            # Verificar local (palavras principais) - QUICK WIN #2: threshold reduzido de 50% para 40%
            local_words = [w for w in local.split() if len(w) > 4]  # palavras > 4 chars
            local_match_ratio = 0
            if local_words:
                local_matches = sum(1 for word in local_words if word in page_text)
                local_match_ratio = local_matches / len(local_words) if local_words else 0

                if local_match_ratio >= 0.4:  # Reduzido de 0.5 para 0.4 (menos falsos negativos)
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
            retry_context = f"""

⚠️ TENTATIVA {attempt}/{LINK_MAX_INTELLIGENT_SEARCHES} - TENTATIVA ANTERIOR FALHOU

PROBLEMAS DETECTADOS:
- Link retornado foi genérico/homepage ou não foi encontrado
- Tente buscar em OUTRAS plataformas além da anterior
- Verifique redes sociais do venue (Instagram/Facebook) por links nos posts
- Se realmente não existir link online, retorne "NONE"
"""

        prompt = f"""Encontre o link OFICIAL de compra/venda de ingresso para este evento:

EVENTO:
- Título: {titulo}
- Data: {data}{horario_info}
- Local: {local}{categoria_info}{preco_info}
- Descrição: {descricao[:200]}{fonte_info}{retry_context}

⚠️ REGRAS CRÍTICAS (leia com atenção):

1. NÃO RETORNE sites de ARTISTAS ou VENUES (páginas institucionais):
   ❌ ERRADO: raphaelghanem.com.br (site do artista)
   ❌ ERRADO: casadochoro.com.br (homepage do venue)
   ❌ ERRADO: sympla.com.br (homepage do Sympla)
   ❌ ERRADO: salaceliciameireles.rj.gov.br/programacao (listagem geral)

   ✅ CORRETO: sympla.com.br/evento/raphael-ghanem-18112025/12345
   ✅ CORRETO: eventbrite.com.br/e/quarteto-de-cordas-tickets-67890
   ✅ CORRETO: bluenoterio.com.br/shows/nome-show__abc123/

2. O link DEVE conter identificador ÚNICO do evento:
   - ID numérico: /evento/nome/123456
   - Slug com data: /evento-18-11-2025
   - Hash alfanumérico: /show/nome__abc123de/
   - Parâmetro: ?event_id=789

3. PLATAFORMAS PRIORITÁRIAS (nesta ordem):
   a) Sympla: sympla.com.br/evento/[nome-evento]/[ID-numerico]
   b) Eventbrite: eventbrite.com.br/e/[nome-evento]-tickets-[ID]
   c) Ticketmaster: ticketmaster.com.br/event/[ID]
   d) Ingresso.com: ingresso.com/evento/[nome-evento]/[ID]
   e) Site do venue com página específica (ex: bluenoterio.com.br/shows/[evento]/)

4. SE NÃO ENCONTRAR link específico em NENHUMA plataforma:
   - Retorne "NONE"
   - NÃO invente links genéricos

EXEMPLOS DE LINKS VÁLIDOS (RETORNE ASSIM):
✅ https://www.sympla.com.br/evento/raphael-ghanem-stand-up/2345678
✅ https://www.eventbrite.com.br/e/quarteto-de-cordas-da-osb-tickets-987654321
✅ https://bluenoterio.com.br/shows/irma-you-and-my-guitar__22hz624n/
✅ https://sis.ingressodigital.com/lojanew/detalhes_evento.asp?eve_cod=15246

EXEMPLOS DE LINKS INVÁLIDOS (NÃO RETORNE):
❌ https://raphaelghanem.com.br (site oficial do artista)
❌ https://www.sympla.com.br (homepage do Sympla)
❌ https://www.sympla.com.br/eventos/rio-de-janeiro (listagem por cidade)
❌ https://casadochoro.com.br/programacao (calendário do venue)
❌ https://salaceliciameireles.rj.gov.br/programacao (agenda geral)

RETORNE APENAS:
- O URL completo (https://...) OU
- A palavra "NONE" (se não encontrar link específico de venda)"""

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

    async def _validate_single_event_link(self, event: dict) -> dict:
        """Valida o link de um único evento com retry e busca inteligente.

        Args:
            event: Evento a validar

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

            link_result = await self._intelligent_link_search_with_consensus(event)

            if link_result and link_result.get("link"):
                new_link = link_result["link"]
                event["link_ingresso"] = new_link
                event["link_type"] = self._classify_link_type(new_link, event)
                event["link_updated_by_ai"] = True
                event["link_added_by_ai"] = True  # Novo campo para indicar que foi adicionado (não apenas corrigido)
                event["link_quality_score"] = link_result.get("quality_score")
                event["link_quality_validation"] = link_result.get("validation")

                # Armazenar informações de consenso (se disponível)
                if link_result.get("consensus_info"):
                    event["link_consensus_info"] = link_result["consensus_info"]

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

            link_result = await self._intelligent_link_search_with_consensus(event)

            if link_result and link_result.get("link"):
                new_link = link_result["link"]
                event["link_original"] = link
                event["link_ingresso"] = new_link
                event["link_type"] = self._classify_link_type(new_link, event)
                event["link_updated_by_ai"] = True
                event["link_quality_score"] = link_result.get("quality_score")
                event["link_quality_validation"] = link_result.get("validation")

                # Armazenar informações de consenso (se disponível)
                if link_result.get("consensus_info"):
                    event["link_consensus_info"] = link_result["consensus_info"]

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

            link_result = await self._intelligent_link_search_with_consensus(event)

            if link_result and link_result.get("link"):
                new_link = link_result["link"]
                event["link_original"] = link
                event["link_ingresso"] = new_link
                event["link_type"] = self._classify_link_type(new_link, event)
                event["link_updated_by_ai"] = True
                event["link_was_generic"] = True
                event["link_quality_score"] = link_result.get("quality_score")
                event["link_quality_validation"] = link_result.get("validation")

                # Armazenar informações de consenso (se disponível)
                if link_result.get("consensus_info"):
                    event["link_consensus_info"] = link_result["consensus_info"]

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

        # EXCEÇÃO 3: Links oficiais do Teatro Municipal (.gov.br) - SSL issues
        if 'theatromunicipal.rj.gov.br' in link.lower():
            event["link_valid"] = True
            event["link_status_code"] = 200
            event["validation_skipped"] = "Official Teatro Municipal links are trusted (SSL issues)"
            stats["validated_first_try"] += 1
            logger.info(f"✓ Link oficial Teatro Municipal válido (sem validação HTTP): {link}")
            return stats

        # Validar link via HTTP request
        http_client = HttpClientWrapper()
        link_status = await http_client.check_link_status(link)

        # Link acessível (200 OK) - validar conteúdo antes de aceitar
        if link_status["accessible"]:
            # NOVA VALIDAÇÃO: Verificar se conteúdo corresponde ao evento
            logger.info(f"→ Link HTTP 200 OK, validando conteúdo: {link[:80]}...")
            content_validation = await self._validate_link_content(link, event)

            if content_validation["valid"]:
                # Conteúdo válido - aceitar link
                event["link_valid"] = True
                event["link_status_code"] = link_status["status_code"]
                event["link_content_validated"] = True
                event["link_validation_details"] = content_validation["details"]
                stats["validated_first_try"] += 1
                logger.info(f"✓ Link válido (HTTP 200 + conteúdo OK): {link}")
                return stats
            else:
                # Conteúdo inválido - link está acessível mas aponta para evento errado
                reason = content_validation["reason"]
                logger.warning(f"⚠️ Link HTTP 200 mas conteúdo inválido ({reason}): {link} - Tentando busca inteligente...")

                # Marcar como erro de conteúdo e tentar busca inteligente
                event["link_original"] = link
                event["link_content_error"] = reason
                event["link_validation_details"] = content_validation["details"]

                stats["total_links"] += 1
                stats["link_errors"] = stats.get("link_errors", 0) + 1
                stats["intelligent_searches"] += 1

                # Tentar encontrar link correto
                link_result = await self._intelligent_link_search_with_consensus(event)

                if link_result and link_result.get("link"):
                    new_link = link_result["link"]
                    event["link_ingresso"] = new_link
                    event["link_type"] = self._classify_link_type(new_link, event)
                    event["link_updated_by_ai"] = True
                    event["link_recovered_from_content_error"] = True
                    event["link_quality_score"] = link_result.get("quality_score")
                    event["link_quality_validation"] = link_result.get("validation")

                    # Armazenar informações de consenso (se disponível)
                    if link_result.get("consensus_info"):
                        event["link_consensus_info"] = link_result["consensus_info"]

                    # Armazenar dados estruturados extraídos do link
                    if link_result.get("structured_data"):
                        event["link_structured_data"] = link_result["structured_data"]

                    # Link já foi validado no _intelligent_link_search
                    event["link_valid"] = True
                    event["link_status_code"] = 200
                    stats["links_fixed"] += 1
                    stats["links_recovered"] = stats.get("links_recovered", 0) + 1
                    logger.info(f"✓ Link recuperado após erro de conteúdo: {new_link}")
                else:
                    # Nenhum link alternativo encontrado - manter link original mas marcar como suspeito
                    event["link_valid"] = False
                    event["link_status_code"] = link_status["status_code"]
                    event["link_error"] = f"Conteúdo inválido: {reason}"
                    event["requires_manual_link_check"] = True
                    stats["links_failed_permanently"] = stats.get("links_failed_permanently", 0) + 1
                    logger.error(f"❌ Link com conteúdo inválido ({reason}): {link} - Nenhum link alternativo encontrado")

                return stats

        # Link com erro (404, 403, timeout) - tentar busca inteligente
        status_code = link_status.get("status_code")
        reason = link_status.get("reason", "Unknown error")

        logger.warning(f"⚠️ Link com erro ({reason}): {link} - Tentando busca inteligente...")
        stats["total_links"] += 1
        stats["link_errors"] = stats.get("link_errors", 0) + 1
        stats["intelligent_searches"] += 1

        # Tentar encontrar link alternativo
        link_result = await self._intelligent_link_search_with_consensus(event)

        if link_result and link_result.get("link"):
            new_link = link_result["link"]
            event["link_original"] = link
            event["link_ingresso"] = new_link
            event["link_type"] = self._classify_link_type(new_link, event)
            event["link_updated_by_ai"] = True
            event["link_recovered_from_error"] = True
            event["link_original_error"] = f"{status_code} - {reason}" if status_code else reason
            event["link_quality_score"] = link_result.get("quality_score")
            event["link_quality_validation"] = link_result.get("validation")

            # Armazenar informações de consenso (se disponível)
            if link_result.get("consensus_info"):
                event["link_consensus_info"] = link_result["consensus_info"]

            # Armazenar dados estruturados extraídos do link
            if link_result.get("structured_data"):
                event["link_structured_data"] = link_result["structured_data"]

            # Link já foi validado no _intelligent_link_search
            event["link_valid"] = True
            event["link_status_code"] = 200
            stats["links_fixed"] += 1
            stats["links_recovered"] = stats.get("links_recovered", 0) + 1
            logger.info(f"✓ Link recuperado com sucesso: {new_link} (original tinha erro: {reason})")
        else:
            # Nenhum link alternativo encontrado
            event["link_valid"] = False
            event["link_status_code"] = status_code
            event["link_error"] = f"{status_code} - {reason}" if status_code else reason
            event["requires_manual_link_check"] = True
            stats["links_failed_permanently"] = stats.get("links_failed_permanently", 0) + 1
            logger.error(f"❌ Link permanentemente inválido ({reason}): {link} - Nenhum link alternativo encontrado")

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

        # Validar todos os links em paralelo com rate limiting
        # Criar semáforo para limitar concorrência
        semaphore = asyncio.Semaphore(LINK_VALIDATION_MAX_CONCURRENT)

        async def validate_with_semaphore(event):
            """Wrapper para validação com semáforo."""
            async with semaphore:
                return await self._validate_single_event_link(event)

        # Criar tasks para validar todos os eventos em paralelo
        validation_tasks = [
            validate_with_semaphore(event)
            for event in event_list
        ]

        # Executar todas as validações em paralelo (respeitando semáforo)
        logger.info(f"Iniciando validação paralela de {len(event_list)} links (máx {LINK_VALIDATION_MAX_CONCURRENT} concorrentes)...")
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

2. TEATRO COMÉDIA / STAND-UP - VALIDAÇÃO RIGOROSA:
   - APROVAR: comédia adulta, stand-up, humor para adultos, "indicado para maiores de 14/16/18"
   - REJEITAR SEMPRE se contém QUALQUER termo:

     INFANTIL/FAMILIAR:
     * "infantil", "criança(s)", "kids", "criancas"
     * "infanto-juvenil", "infanto juvenil"
     * "família", "familia", "family", "para toda família"
     * "sessão infantil", "sessao infantil", "sessão dupla", "sessao dupla"
     * "indicado para crianças", "filme infantil", "filmes infantis", "cinema infantil"

     LGBTQIAPN+:
     * "lgbt", "lgbtq", "lgbtqia", "lgbtqiapn"
     * "pride", "parada gay", "parada lgbtq"
     * "diversidade sexual", "queer", "drag queen", "drag king"

   - Se menciona "todas as idades" SEM clareza de ser adulto → REJEITAR (preferir segurança)

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
