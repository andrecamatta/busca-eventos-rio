"""Agente de validação individual inteligente de eventos com LLM."""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any

import httpx
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from bs4 import BeautifulSoup

from config import (
    HTTP_TIMEOUT,
    MODELS,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    SEARCH_CONFIG,
    VALIDATION_STRICTNESS,
    VENUE_ADDRESSES,
)

logger = logging.getLogger(__name__)


class ValidationAgent:
    """Agente especializado em validação individual inteligente com LLM."""

    def __init__(self):
        self.agent = Agent(
            name="Event Validation Agent",
            model=OpenAIChat(
                id=MODELS["format"],  # Gemini Flash - rápido e econômico
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
            description="Agente especializado em validação inteligente de eventos usando LLM",
            instructions=[
                "Validar eventos de forma inteligente e flexível",
                "Usar bom senso para aceitar eventos legítimos",
                "Rejeitar apenas eventos claramente falsos ou absurdos",
                "Considerar contexto e plausibilidade geral",
            ],
            markdown=True,
        )

    async def validate_events_batch(self, events: list[dict]) -> dict[str, Any]:
        """Valida um lote de eventos individualmente."""
        logger.info(f"Validando {len(events)} eventos (modo: {VALIDATION_STRICTNESS})...")

        validated_events = []
        rejected_events = []
        validation_warnings = []

        # Criar tasks para validar todos os eventos em paralelo
        logger.info(f"Iniciando validação paralela de {len(events)} eventos...")
        validation_tasks = [
            self.validate_event_individually(event)
            for event in events
        ]

        # Executar todas as validações em paralelo
        validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)

        # Processar resultados
        for i, (event, result) in enumerate(zip(events, validation_results)):
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
            link_info = await self._fetch_link_info(link)
            evidences["link"] = link_info

            # VALIDAÇÃO AUTOMÁTICA DE DATA: Comparar data do evento com data extraída do link
            if link_info.get("extracted_date", {}).get("found"):
                extracted_dates = link_info["extracted_date"]["dates"]
                event_date = event.get("data", "").split()[0]  # Remove horário se presente

                if event_date and event_date not in extracted_dates:
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

    async def _fetch_link_info(self, link: str) -> dict[str, Any]:
        """Busca informações do link (status HTTP + conteúdo)."""
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(link, timeout=15)

                if response.status_code == 200:
                    # Extrair texto relevante da página
                    try:
                        soup = BeautifulSoup(response.text, "html.parser")
                        # Remover scripts e styles
                        for script in soup(["script", "style"]):
                            script.decompose()
                        page_text = soup.get_text()
                        # Limpar e pegar primeiros 3000 caracteres
                        page_text = " ".join(page_text.split())[:3000]
                    except Exception as e:
                        logger.warning(f"Erro ao extrair texto da página: {e}")
                        page_text = ""

                    # Extrair datas do conteúdo
                    extracted_date = self._extract_date_from_content(page_text)

                    return {
                        "status": "accessible",
                        "status_code": 200,
                        "content_preview": page_text,
                        "extracted_date": extracted_date,
                    }
                elif response.status_code == 404:
                    return {
                        "status": "not_found",
                        "status_code": 404,
                        "reason": "Link retorna 404 (não encontrado)",
                    }
                elif response.status_code == 403:
                    return {
                        "status": "forbidden",
                        "status_code": 403,
                        "reason": "Link bloqueado (403 Forbidden)",
                    }
                else:
                    return {
                        "status": "error",
                        "status_code": response.status_code,
                        "reason": f"Link retorna status {response.status_code}",
                    }

        except httpx.TimeoutException:
            return {
                "status": "timeout",
                "reason": "Timeout ao acessar link",
            }
        except Exception as e:
            return {
                "status": "error",
                "reason": f"Erro ao acessar link: {str(e)}",
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

        # Validar formato DD/MM/YYYY
        try:
            event_date = datetime.strptime(date_str.split()[0], "%d/%m/%Y")
        except (ValueError, IndexError):
            return {"valid": False, "reason": f"Formato de data inválido: {date_str}"}

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

        return {"valid": True, "reason": "Data válida", "date": event_date.strftime('%d/%m/%Y')}
