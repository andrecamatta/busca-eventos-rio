"""Agente de verificação e validação de eventos."""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

import httpx
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import (
    HTTP_TIMEOUT,
    MAX_RETRIES,
    MODELS,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    SEARCH_CONFIG,
)

logger = logging.getLogger(__name__)


class VerifyAgent:
    """Agente responsável por verificar e validar informações de eventos."""

    def __init__(self):
        self.agent = Agent(
            name="Event Verification Agent",
            model=OpenAIChat(
                id=MODELS["verify"],  # Claude Sonnet para verificação rigorosa
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
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

        # Padrões de URLs genéricas
        generic_patterns = [
            r'/eventos/[^/]+\?',  # /eventos/categoria?params
            r'/eventos\?',         # /eventos?params
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

        # Verificar se URL é muito curta (provavelmente genérica)
        # Ex: ingresso.com/eventos vs ingresso.com/evento/nome-evento-123456
        path = url.split('?')[0]  # Remover query params
        path_parts = [p for p in path.split('/') if p and p not in ['http:', 'https:', '']]

        # URL específica geralmente tem pelo menos 3 partes: dominio/tipo/identificador
        if len(path_parts) < 3:
            # Exceções: alguns domínios têm estrutura diferente
            if not any(domain in url.lower() for domain in ['bluenote', 'casadeshow', 'teatro']):
                return True

        return False

    async def verify_events(self, events_json: str) -> dict[str, Any]:
        """Verifica e valida eventos extraídos pelo agente de busca."""
        logger.info("Iniciando verificação de eventos...")

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
        logger.info("Iniciando validação individual rigorosa...")
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
        self, client: httpx.AsyncClient, link: str, attempt_num: int = 1
    ) -> dict:
        """Valida um único link com retry automático para erros temporários."""
        logger.info(f"Validando link (tentativa {attempt_num}): {link}")
        response = await client.head(link, timeout=10)
        return {
            "valid": 200 <= response.status_code < 400,
            "status_code": response.status_code,
        }

    async def _intelligent_link_search(self, event: dict) -> str | None:
        """Usa Perplexity para buscar o link correto de um evento."""
        titulo = event.get("titulo", "") or event.get("nome", "")
        data = event.get("data", "")
        horario = event.get("horario", "")
        local = event.get("local", "")
        categoria = event.get("categoria", "")
        preco = event.get("preco", "")
        descricao = event.get("descricao_enriquecida") or event.get("descricao", "")
        fontes = event.get("fontes", [])

        logger.info(f"Buscando link correto para: {titulo}")

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

        prompt = f"""Encontre o link de compra/informações OFICIAL para este evento no Rio de Janeiro:

Título: {titulo}
Data: {data}{horario_info}
Local: {local}{categoria_info}{preco_info}
Descrição: {descricao[:200]}{fonte_info}

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
                logger.info(f"✓ Link encontrado: {new_link}")
                return new_link
            else:
                logger.warning(f"✗ Nenhum link válido encontrado para: {titulo}")
                return None

        except Exception as e:
            logger.error(f"Erro na busca inteligente de link: {e}")
            return None

    async def _validate_links(self, events: dict | list) -> dict | list:
        """Valida se os links de eventos são acessíveis com retry e busca inteligente."""
        logger.info("Validando links de eventos com retry automático...")

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

        # Estatísticas de validação
        stats = {
            "total_links": 0,
            "validated_first_try": 0,
            "validated_after_retry": 0,
            "failed_all_retries": 0,
            "intelligent_searches": 0,
            "links_fixed": 0,
            "no_retry_needed": 0,  # HTTP 404, 403, etc
            "generic_links_detected": 0,  # Links genéricos detectados
        }

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            for event in event_list:
                link = event.get("link") or event.get("link_ingresso") or event.get("ticket_link")

                if not link:
                    event["link_valid"] = None
                    continue

                # Detectar placeholder "INCOMPLETO" e ir direto para busca inteligente
                if link in ["INCOMPLETO", "incompleto", "/INCOMPLETO", "NONE", "none"]:
                    logger.info(f"→ Link placeholder detectado ({link}), iniciando busca inteligente: {event.get('titulo')}")
                    stats["total_links"] += 1
                    stats["intelligent_searches"] += 1

                    new_link = await self._intelligent_link_search(event)

                    if new_link and new_link not in ["INCOMPLETO", "NONE", "none"]:
                        event["link_original"] = link
                        event["link"] = new_link
                        event["link_updated_by_ai"] = True

                        # Validar novo link (1 tentativa)
                        try:
                            result = await self._validate_single_link(client, new_link, attempt_num=1)
                            event["link_valid"] = result["valid"]
                            event["link_status_code"] = result["status_code"]
                            stats["links_fixed"] += 1
                            logger.info(f"✓ Link corrigido com sucesso: {new_link}")
                        except Exception as e:
                            event["link_valid"] = False
                            event["link_error"] = f"Novo link falhou: {type(e).__name__}"
                            logger.warning(f"✗ Novo link também falhou: {new_link}")
                    else:
                        event["link_valid"] = False
                        event["link_error"] = "Placeholder sem link válido encontrado"
                        event["requires_manual_link_check"] = True
                        logger.warning(f"⚠ Nenhum link encontrado para: {event.get('titulo')}")

                    continue

                # Detectar link genérico (página de busca/categoria) e ir para busca inteligente
                if self._is_generic_link(link):
                    logger.info(f"🚫 Link genérico detectado, iniciando busca inteligente: {link[:80]}...")
                    stats["total_links"] += 1
                    stats["generic_links_detected"] += 1
                    stats["intelligent_searches"] += 1

                    new_link = await self._intelligent_link_search(event)

                    if new_link and not self._is_generic_link(new_link):
                        event["link_original"] = link
                        event["link"] = new_link
                        event["link_updated_by_ai"] = True
                        event["link_was_generic"] = True

                        # Validar novo link (1 tentativa)
                        try:
                            result = await self._validate_single_link(client, new_link, attempt_num=1)
                            event["link_valid"] = result["valid"]
                            event["link_status_code"] = result["status_code"]
                            stats["links_fixed"] += 1
                            logger.info(f"✓ Link genérico substituído por link específico: {new_link}")
                        except Exception as e:
                            event["link_valid"] = False
                            event["link_error"] = f"Novo link falhou: {type(e).__name__}"
                            logger.warning(f"✗ Novo link também falhou: {new_link}")
                    else:
                        # Nenhum link específico encontrado, manter genérico mas marcar
                        event["link_valid"] = False
                        event["link_is_generic"] = True
                        event["link_error"] = "Link genérico - página de busca/categoria"
                        event["requires_manual_link_check"] = True
                        logger.warning(f"⚠ Nenhum link específico encontrado para: {event.get('titulo')}")

                    continue

                stats["total_links"] += 1
                original_link = link

                try:
                    # Tentar validar com retry automático
                    result = await self._validate_single_link(client, link, attempt_num=1)
                    event["link_valid"] = result["valid"]
                    event["link_status_code"] = result["status_code"]
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
                            new_link = await self._intelligent_link_search(event)

                            if new_link and new_link != original_link:
                                event["link_original"] = original_link
                                event["link"] = new_link
                                event["link_updated_by_ai"] = True

                                # Validar novo link (1 tentativa apenas)
                                try:
                                    result = await self._validate_single_link(client, new_link, attempt_num=1)
                                    event["link_valid"] = result["valid"]
                                    event["link_status_code"] = result["status_code"]
                                    stats["links_fixed"] += 1
                                    logger.info(f"✓ Link corrigido com sucesso: {new_link}")
                                except Exception:
                                    event["link_valid"] = False
                                    logger.warning(f"✗ Novo link também falhou: {new_link}")

                            continue

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

                    new_link = await self._intelligent_link_search(event)

                    if new_link and new_link != original_link:
                        event["link_original"] = original_link
                        event["link"] = new_link
                        event["link_updated_by_ai"] = True

                        # Validar novo link (1 tentativa apenas)
                        try:
                            result = await self._validate_single_link(client, new_link, attempt_num=1)
                            event["link_valid"] = result["valid"]
                            event["link_status_code"] = result["status_code"]
                            stats["links_fixed"] += 1
                            logger.info(f"✓ Link corrigido com sucesso: {new_link}")
                        except Exception as e2:
                            event["link_valid"] = False
                            event["link_error"] = f"Novo link falhou: {type(e2).__name__}"
                            logger.warning(f"✗ Novo link também falhou: {new_link}")
                    else:
                        # Marcar para revisão manual
                        event["requires_manual_link_check"] = True
                        logger.warning(f"⚠ Evento requer revisão manual de link: {event.get('titulo')}")

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
