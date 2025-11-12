"""Agente de busca de eventos."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from agents.base_agent import BaseAgent
from config import SEARCH_CONFIG, MAX_EVENTS_PER_VENUE, ENABLED_CATEGORIES, ENABLED_VENUES
from models.event_models import ResultadoBuscaCategoria
from utils.deduplicator import deduplicate_events
from utils.prompt_templates import PromptBuilder
from utils.prompt_loader import get_prompt_loader
from utils.date_helpers import DateParser

logger = logging.getLogger(__name__)


class SearchAgent(BaseAgent):
    """Agente responsável por buscar eventos em múltiplas fontes."""

    def __init__(self):
        super().__init__(
            agent_name="SearchAgent",
            log_emoji="🔍",
            model_type="search",  # perplexity/sonar-pro
            description="Agente com busca web em tempo real para encontrar eventos culturais no Rio de Janeiro",
            instructions=[
                f"Você tem acesso à busca web em tempo real. Use para encontrar eventos no Rio de Janeiro "
                f"entre {SEARCH_CONFIG['start_date'].strftime('%d/%m/%Y')} "
                f"e {SEARCH_CONFIG['end_date'].strftime('%d/%m/%Y')}",
                "Busque nas seguintes categorias:",
                "1. Shows de jazz no Rio (próximas 3 semanas)",
                "2. Teatro comédia/stand-up no Rio (EXCETO eventos infantis)",
                "3. Eventos na Casa do Choro, Sala Cecília Meireles e Teatro Municipal",
                "4. Eventos ao ar livre em fim de semana no Rio",
                "Para cada evento, extrair: título, data completa, horário, local, valor/preço, link para compra de ingressos",
                "Buscar em sites como: Sympla, Eventbrite, Fever, TimeOut Rio, sites oficiais dos locais",
                "Retorne no formato JSON estruturado",
            ],
            markdown=True,
        )

        # Renomear agent para compatibilidade
        self.search_agent = self.agent

    def _initialize_dependencies(self, **kwargs):
        """Inicializa prompt loader."""
        self.prompt_loader = get_prompt_loader()
        self.log_info(
            f"📋 Prompts carregados: "
            f"{len(self.prompt_loader.get_all_categorias())} categorias, "
            f"{len(self.prompt_loader.get_all_venues())} venues"
        )

    def _limit_events_per_venue(self, eventos_por_venue: dict[str, list[dict]]) -> dict[str, list[dict]]:
        """
        Limita eventos por venue ao máximo definido em MAX_EVENTS_PER_VENUE.

        Critérios de priorização (em ordem):
        1. Eventos com link válido (prioridade alta)
        2. Diversidade de datas (evita concentração no mesmo dia)
        3. Completude da descrição (mais informação = melhor)
        4. Ordem cronológica (mais próximos primeiro)
        """
        limited_events = {}

        for venue_name, eventos in eventos_por_venue.items():
            if len(eventos) <= MAX_EVENTS_PER_VENUE:
                limited_events[venue_name] = eventos
                continue

            # Calcular score para cada evento
            scored_events = []
            for evento in eventos:
                score = 0

                # 1. Link válido = +100 pontos
                if evento.get("link_ingresso") and evento["link_ingresso"].lower() not in ("null", "none", ""):
                    score += 100

                # 2. Descrição completa = +50 pontos (se > 50 palavras)
                descricao = evento.get("descricao", "") or ""
                if len(descricao.split()) > 50:
                    score += 50
                elif len(descricao.split()) > 20:
                    score += 25

                # 3. Data mais próxima = +1 a +30 pontos (inverso da posição)
                try:
                    data_str = evento.get("data", "")
                    if data_str:
                        # Parsear DD/MM/YYYY
                        data_evento = datetime.strptime(data_str, "%d/%m/%Y")
                        # Quanto mais próximo, maior o score (max 30 pontos)
                        days_diff = (data_evento - datetime.now()).days
                        if days_diff >= 0:
                            # Normalizar: 0-21 dias → 30-10 pontos
                            score += max(10, 30 - days_diff)
                except:
                    score += 15  # score neutro se data inválida

                scored_events.append((score, evento))

            # Ordenar por score (maior primeiro)
            scored_events.sort(key=lambda x: x[0], reverse=True)

            # Selecionar top MAX_EVENTS_PER_VENUE
            selected = [evento for _, evento in scored_events[:MAX_EVENTS_PER_VENUE]]
            limited_events[venue_name] = selected

            # Log da redução
            if len(eventos) > MAX_EVENTS_PER_VENUE:
                logger.info(
                    f"📊 Venue '{venue_name}': {len(eventos)} eventos → "
                    f"{len(selected)} selecionados (limite: {MAX_EVENTS_PER_VENUE})"
                )

        return limited_events

    def _normalize_venue_names(self, eventos_por_venue: dict[str, list[dict]]) -> dict[str, list[dict]]:
        """
        Consolida sub-venues em venues principais usando VENUE_ALIASES.

        Exemplo: "CCBB Teatro III" → "CCBB Rio - Centro Cultural Banco do Brasil"
        """
        from config import VENUE_ALIASES

        normalized = {}
        consolidation_log = []

        for venue_name, eventos in eventos_por_venue.items():
            # Obter nome canônico do venue
            canonical_name = VENUE_ALIASES.get(venue_name, venue_name)

            # Log de consolidação se houve mudança
            if canonical_name != venue_name and len(eventos) > 0:
                consolidation_log.append(f"{venue_name} → {canonical_name} ({len(eventos)} eventos)")

            # Merge eventos no venue canônico
            if canonical_name not in normalized:
                normalized[canonical_name] = []
            normalized[canonical_name].extend(eventos)

        # Log consolidações realizadas
        if consolidation_log:
            logger.info(f"🔗 Consolidação de venues:")
            for log_msg in consolidation_log:
                logger.info(f"   - {log_msg}")

        return normalized

    async def _run_micro_search(self, prompt: str, search_name: str) -> str:
        """Executa uma micro-search focada de forma assíncrona."""
        logger.info(f"   🔍 Iniciando busca: {search_name}")

        def sync_search():
            try:
                response = self.search_agent.run(prompt)
                return response.content
            except Exception as e:
                logger.error(f"Erro na busca {search_name}: {e}")
                return "{}"

        result = await asyncio.to_thread(sync_search)

        # Log resposta do Perplexity para diagnóstico (primeiros 500 chars)
        if result and isinstance(result, str) and result.strip():
            preview = result[:500].replace('\n', ' ')
            logger.debug(f"   📄 Resposta Perplexity [{search_name}]: {preview}...")

        logger.info(f"   ✓ Busca concluída: {search_name}")
        return result

    def _deduplicate_events_by_title(self, events: list[dict]) -> list[dict]:
        """
        Deduplica eventos por similaridade de título.

        Remove eventos duplicados baseado em:
        1. Títulos idênticos (case-insensitive)
        2. Títulos muito similares (>85% de similaridade)

        Args:
            events: Lista de eventos para deduplicar

        Returns:
            Lista de eventos únicos, priorizando os mais completos
        """
        from difflib import SequenceMatcher

        if not events:
            return []

        unique_events = []
        seen_titles = []

        # Ordenar por completude (eventos com link e descrição primeiro)
        sorted_events = sorted(
            events,
            key=lambda e: (
                bool(e.get('link_ingresso')),
                bool(e.get('descricao')),
                len(str(e.get('titulo', '')))
            ),
            reverse=True
        )

        for event in sorted_events:
            titulo = str(event.get('titulo', '')).strip().lower()
            if not titulo:
                continue

            # Verificar se é similar a algum título já visto
            is_duplicate = False
            for seen_title in seen_titles:
                similarity = SequenceMatcher(None, titulo, seen_title).ratio()
                if similarity > 0.85:  # 85% de similaridade
                    is_duplicate = True
                    logger.debug(f"      Duplicata detectada: '{titulo}' vs '{seen_title}' ({similarity:.2%})")
                    break

            if not is_duplicate:
                unique_events.append(event)
                seen_titles.append(titulo)

        return unique_events

    async def _run_parallel_micro_search(
        self,
        prompt: str,
        search_name: str,
        n_parallel: int = 3
    ) -> list[dict]:
        """
        Executa múltiplas buscas paralelas e merge os resultados.

        Estratégia: Fazer N consultas simultâneas ao Perplexity para aumentar
        cobertura, já que cada chamada pode retornar eventos diferentes devido
        à variabilidade do modelo.

        Args:
            prompt: Prompt de busca
            search_name: Nome da busca (para logs)
            n_parallel: Número de consultas paralelas (padrão: 3)

        Returns:
            Lista de eventos únicos (deduplificados) de todas as consultas
        """
        import json

        logger.info(f"   🔍⚡ Iniciando {n_parallel} buscas paralelas: {search_name}")

        # Executar N buscas em paralelo
        tasks = [
            self._run_micro_search(prompt, f"{search_name} #{i+1}")
            for i in range(n_parallel)
        ]

        results = await asyncio.gather(*tasks)

        # Parsear e coletar todos os eventos
        all_events = []
        successful_queries = 0

        for i, result_str in enumerate(results, 1):
            try:
                # Limpar JSON de markdown/texto extra
                clean_json = self._clean_json_from_markdown(result_str)
                if not clean_json:
                    logger.warning(f"      Query #{i}: JSON vazio após limpeza")
                    continue

                data = json.loads(clean_json)
                events = data.get('eventos', [])

                if events:
                    all_events.extend(events)
                    successful_queries += 1
                    logger.info(f"      Query #{i}: {len(events)} eventos encontrados")
                else:
                    logger.info(f"      Query #{i}: Nenhum evento encontrado")

            except json.JSONDecodeError as e:
                logger.warning(f"      Query #{i}: Erro ao parsear JSON - {e}")
            except Exception as e:
                logger.error(f"      Query #{i}: Erro inesperado - {e}")

        # Deduplicar eventos
        unique_events = self._deduplicate_events_by_title(all_events)

        logger.info(
            f"   ✓ Busca paralela concluída: {search_name} - "
            f"{len(all_events)} eventos brutos → {len(unique_events)} únicos "
            f"({successful_queries}/{n_parallel} queries OK)"
        )

        return unique_events

    def _clean_json_from_markdown(self, text: str) -> str:
        """Remove markdown code blocks e texto extra do JSON.

        Já existe implementação similar, mas criando versão standalone.
        """
        import re

        if not text or text.strip() == "":
            return ""

        text = text.strip()

        # STEP 1: Extrair JSON de dentro de ```json blocks
        code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        matches = re.findall(code_block_pattern, text)
        if matches:
            text = matches[-1].strip()

        # STEP 2: Remover texto ANTES do primeiro { ou [
        json_start_brace = text.find('{')
        json_start_bracket = text.find('[')
        valid_starts = [pos for pos in [json_start_brace, json_start_bracket] if pos != -1]
        if valid_starts:
            json_start = min(valid_starts)
            text = text[json_start:]

        # STEP 3: Remover texto DEPOIS do último } ou ]
        if text.startswith('{'):
            depth = 0
            for i, char in enumerate(text):
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        text = text[:i+1]
                        break
        elif text.startswith('['):
            depth = 0
            for i, char in enumerate(text):
                if char == '[':
                    depth += 1
                elif char == ']':
                    depth -= 1
                    if depth == 0:
                        text = text[:i+1]
                        break

        return text.strip()

    def _build_focused_prompt(
        self,
        categoria: str,
        tipo_busca: str,  # "categoria" ou "venue"
        descricao: str,
        tipos_evento: list[str],
        palavras_chave: list[str],
        venues_sugeridos: list[str],
        instrucoes_especiais: str = "",
        start_date_str: str = "",
        end_date_str: str = "",
        month_year_str: str = "",
        month_str: str = "",
    ) -> str:
        """Constrói prompt focado para uma única categoria ou venue (DRY)."""

        # Template comum para todos os prompts
        common_header = f"""Execute uma busca FOCADA e DETALHADA exclusivamente para: {categoria}

PERÍODO: {start_date_str} a {end_date_str}

🎯 FOCO EXCLUSIVO: {descricao}

ESTRATÉGIA DE BUSCA:
"""

        # Seção de tipos de evento
        tipos_section = "TIPOS DE EVENTO:\n"
        for tipo in tipos_evento:
            tipos_section += f"- {tipo}\n"

        # Seção de palavras-chave
        keywords_section = "\nPALAVRAS-CHAVE PARA BUSCA:\n"
        for keyword in palavras_chave:
            keywords_section += f'- "{keyword}"\n'

        # Seção de venues
        venues_section = "\nVENUES/LOCAIS PRIORITÁRIOS:\n"
        for venue in venues_sugeridos:
            venues_section += f"- {venue}\n"

        # Fontes (comum para todos)
        sources_section = """
FONTES PARA BUSCAR:
- Sympla (sympla.com.br), Eventbrite (eventbrite.com.br), Fever (fever.com.br)
- Portais culturais: TimeOut Rio, Veja Rio, O Globo Cultura
- Sites oficiais dos venues e suas redes sociais (Instagram/Facebook)
- Bilheterias online oficiais dos locais
"""

        # Campos obrigatórios (comum para todos)
        required_fields = """
INFORMAÇÕES OBRIGATÓRIAS PARA CADA EVENTO:
- Nome completo do evento
- Data exata (formato DD/MM/YYYY)
- ⚠️ Horário de início (HH:MM) - CRÍTICO: SEMPRE inclua o horário preciso
- Nome completo do local/venue + endereço
- Preço (incluir meia-entrada se disponível)
- Link para compra de ingressos (se disponível)
- Descrição detalhada: artistas, duração, público-alvo

ATENÇÃO ESPECIAL AO HORÁRIO:
- O horário é OBRIGATÓRIO (não opcional)
- Formato: "19:00", "20:30", "21:00" (HH:MM)
- Se o site não mostrar horário, busque em Instagram, Facebook, Sympla, Eventbrite
- NUNCA deixe horário em branco
"""

        # Formato de retorno (diferente para categoria vs venue)
        if tipo_busca == "categoria":
            return_format = f"""
FORMATO DE RETORNO:
{{
  "eventos": [
    {{
      "categoria": "{categoria}",
      "titulo": "Nome do evento",
      "data": "DD/MM/YYYY",
      "horario": "HH:MM",
      "local": "Nome completo + Endereço",
      "preco": "Valor completo",
      "link_ingresso": "URL específica ou null",
      "descricao": "Descrição detalhada"
    }}
  ]
}}

IMPORTANTE:
- Busque o MÁXIMO de eventos possível (objetivo: pelo menos 3 eventos)
- INCLUA TODOS os eventos que encontrar com data, horário, local e descrição

⚠️ REGRAS CRÍTICAS PARA LINKS (leia com atenção - links inválidos serão rejeitados):

1. NÃO RETORNE HOMEPAGES/SITES INSTITUCIONAIS:
   ❌ NUNCA retornar sites de ARTISTAS (ex: raphaelghanem.com.br, fabriciolins.com.br)
   ❌ NUNCA retornar homepages de VENUES (ex: casadochoro.com.br, teatroopuscitta.com.br)
   ❌ NUNCA retornar homepages de PLATAFORMAS (ex: sympla.com.br, ingresso.com)
   ❌ NUNCA retornar AGREGADORES genéricos (ex: shazam.com/events, concerts50.com, songkick.com)
   ❌ NUNCA retornar páginas de PROGRAMAÇÃO GERAL (ex: /programacao, /agenda, /calendario)

2. O link DEVE conter IDENTIFICADOR ÚNICO do evento (um destes formatos):
   - ID numérico: /evento/nome-do-evento/123456
   - Slug com data: /evento-nome-18-11-2025
   - Hash alfanumérico: /shows/nome__abc123de/
   - Parâmetro único: ?event_id=789 ou ?eve_cod=15246

3. PLATAFORMAS DE BUSCA (nesta ordem de prioridade):
   🥇 PRIORITÁRIAS (sempre buscar primeiro):
   a) Sympla: sympla.com.br/evento/[nome]/[ID-numerico]
   b) Eventbrite: eventbrite.com.br/e/[nome]-tickets-[ID]
   c) Ticketmaster: ticketmaster.com.br/event/[ID]
   d) Fever: feverup.com/rio-de-janeiro/events/[nome-evento]

   🥈 SECUNDÁRIAS (se prioritárias não tiverem):
   e) Ingresso.com: ingresso.com/evento/[nome]/[ID]
   f) Bileto: bileto.sympla.com.br/event/[ID]

   🥉 VENUES ESPECÍFICOS (apenas com página do evento):
   g) Blue Note: bluenoterio.com.br/shows/[nome-show]__[hash]/
   h) Sites oficiais com link ESPECÍFICO do evento (NÃO homepage)

✅ EXEMPLOS DE LINKS VÁLIDOS:
   ✅ https://www.sympla.com.br/evento/raphael-ghanem-stand-up/2345678
   ✅ https://www.eventbrite.com.br/e/quarteto-de-cordas-da-osb-tickets-987654321
   ✅ https://bluenoterio.com.br/shows/irma-you-and-my-guitar__22hz624n/
   ✅ https://www.ingresso.com/evento/caio-martins-segredo-revelado/15246

❌ EXEMPLOS DE LINKS INVÁLIDOS (NUNCA RETORNAR):
   HOMEPAGES E SITES INSTITUCIONAIS:
   ❌ https://raphaelghanem.com.br (site oficial do artista)
   ❌ https://casadochoro.com.br (homepage do venue)
   ❌ https://teatroopuscitta.com.br (homepage do teatro)
   ❌ https://www.sympla.com.br (homepage da plataforma)

   AGREGADORES GENÉRICOS (não vendem ingressos):
   ❌ https://shazam.com/events/rio-de-janeiro (apenas lista eventos)
   ❌ https://concerts50.com/brazil/rio-de-janeiro (agregador de terceiros)

   PÁGINAS DE CATEGORIA/BUSCA/LISTAGEM:
   ❌ https://www.ingresso.com/espetaculos/categorias/stand-up (categoria genérica)
   ❌ https://www.sympla.com.br/eventos/rio-de-janeiro (listagem por cidade)
   ❌ https://eventbrite.com.br/d/brazil--rio-de-janeiro/events/ (listagem)
   ❌ https://bluenoterio.com.br/shows (listagem de todos os shows - falta ID específico)

   PROGRAMAÇÃO GERAL DE VENUES:
   ❌ https://salaceliciameireles.rj.gov.br/programacao (calendário mensal)
   ❌ https://casadochoro.com.br/programacao (agenda geral)

📋 CHECKLIST ANTES DE RETORNAR UM LINK:
   ✅ O link contém ID/identificador único? (numérico, slug, hash, ou parâmetro)
   ✅ O link é de uma PLATAFORMA de venda (Sympla, Eventbrite, etc) OU página específica do venue?
   ✅ O link aponta para UMA página específica de evento (não listagem/categoria)?
   ✅ O link NÃO é homepage do artista/venue/plataforma?
   ✅ O link NÃO é de agregador genérico (Shazam, Concerts50, etc)?

   SE TODAS AS RESPOSTAS FOREM ✅ → retornar link
   SE QUALQUER RESPOSTA FOR ❌ → retornar null

4. SE NÃO ENCONTRAR link específico:
   - Busque em TODAS as plataformas prioritárias (Sympla, Eventbrite, Ticketmaster, Fever)
   - Busque em plataformas secundárias (Ingresso.com, Bileto)
   - APENAS APÓS TENTAR TODAS AS FONTES: retorne null
   - NÃO retorne links genéricos "por garantia" (null é MELHOR que link inválido)
"""
        else:  # venue
            return_format = f"""
ENCODING E CARACTERES ESPECIAIS:
- Usar UTF-8 encoding para TODOS os campos
- Caracteres acentuados são PERMITIDOS e DEVEM ser escritos normalmente (ex: "Cecília", "música", "sábado")
- NÃO usar escapes unicode (ex: \\u00ed) - escrever os caracteres acentuados diretamente
- A chave do JSON DEVE ser EXATAMENTE: "{categoria}" (preservar acentuação se houver)

FORMATO DE RETORNO (use exatamente estes nomes de campos):
{{
  "{categoria}": [
    {{
      "titulo": "Nome do evento",
      "data": "DD/MM/YYYY",
      "horario": "HH:MM",
      "local": "{categoria} - Endereço completo",
      "preco": "Valor completo",
      "link_ingresso": "URL específica ou null",
      "descricao": "Descrição detalhada"
    }}
  ]
}}

IMPORTANTE - NOMES DE CAMPOS:
- Use "horario" (não "hora")
- Use "preco" (não "preço")
- Use "link_ingresso" (não "link")
- Use "descricao" (não "descrição")

REGRAS CRÍTICAS PARA JSON:
1. Comece DIRETAMENTE com {{ (sem markdown, sem textos, sem cabeçalhos antes)
2. Se usar markdown, use APENAS ```json no início e ``` no final
3. Feche COMPLETAMENTE o JSON antes de qualquer texto explicativo
4. NÃO adicione nada DEPOIS do último }}
5. Caracteres especiais devem ser escritos normalmente (ex: "à", "ã", "ç", "é", "í", "ó", "ô", "õ", "ü")

OBJETIVO:
- Busque o MÁXIMO de eventos possível (objetivo: pelo menos 1 evento)
- INCLUA TODOS os eventos que encontrar com data, horário, local e descrição

⚠️ REGRAS CRÍTICAS PARA LINKS (leia com atenção - links inválidos serão rejeitados):

1. NÃO RETORNE HOMEPAGES/SITES INSTITUCIONAIS:
   ❌ NUNCA retornar sites de ARTISTAS (ex: raphaelghanem.com.br, fabriciolins.com.br)
   ❌ NUNCA retornar homepages de VENUES (ex: casadochoro.com.br, teatroopuscitta.com.br)
   ❌ NUNCA retornar homepages de PLATAFORMAS (ex: sympla.com.br, ingresso.com)
   ❌ NUNCA retornar AGREGADORES genéricos (ex: shazam.com/events, concerts50.com, songkick.com)
   ❌ NUNCA retornar páginas de PROGRAMAÇÃO GERAL (ex: /programacao, /agenda, /calendario)

2. O link DEVE conter IDENTIFICADOR ÚNICO do evento (um destes formatos):
   - ID numérico: /evento/nome-do-evento/123456
   - Slug com data: /evento-nome-18-11-2025
   - Hash alfanumérico: /shows/nome__abc123de/
   - Parâmetro único: ?event_id=789 ou ?eve_cod=15246

3. PLATAFORMAS DE BUSCA (nesta ordem de prioridade):
   🥇 PRIORITÁRIAS (sempre buscar primeiro):
   a) Sympla: sympla.com.br/evento/[nome]/[ID-numerico]
   b) Eventbrite: eventbrite.com.br/e/[nome]-tickets-[ID]
   c) Ticketmaster: ticketmaster.com.br/event/[ID]
   d) Fever: feverup.com/rio-de-janeiro/events/[nome-evento]

   🥈 SECUNDÁRIAS (se prioritárias não tiverem):
   e) Ingresso.com: ingresso.com/evento/[nome]/[ID]
   f) Bileto: bileto.sympla.com.br/event/[ID]

   🥉 VENUES ESPECÍFICOS (apenas com página do evento):
   g) Blue Note: bluenoterio.com.br/shows/[nome-show]__[hash]/
   h) Sites oficiais com link ESPECÍFICO do evento (NÃO homepage)

✅ EXEMPLOS DE LINKS VÁLIDOS:
   ✅ https://www.sympla.com.br/evento/raphael-ghanem-stand-up/2345678
   ✅ https://www.eventbrite.com.br/e/quarteto-de-cordas-da-osb-tickets-987654321
   ✅ https://bluenoterio.com.br/shows/irma-you-and-my-guitar__22hz624n/
   ✅ https://www.ingresso.com/evento/caio-martins-segredo-revelado/15246

❌ EXEMPLOS DE LINKS INVÁLIDOS (NUNCA RETORNAR):
   HOMEPAGES E SITES INSTITUCIONAIS:
   ❌ https://raphaelghanem.com.br (site oficial do artista)
   ❌ https://casadochoro.com.br (homepage do venue)
   ❌ https://teatroopuscitta.com.br (homepage do teatro)
   ❌ https://www.sympla.com.br (homepage da plataforma)

   AGREGADORES GENÉRICOS (não vendem ingressos):
   ❌ https://shazam.com/events/rio-de-janeiro (apenas lista eventos)
   ❌ https://concerts50.com/brazil/rio-de-janeiro (agregador de terceiros)

   PÁGINAS DE CATEGORIA/BUSCA/LISTAGEM:
   ❌ https://www.ingresso.com/espetaculos/categorias/stand-up (categoria genérica)
   ❌ https://www.sympla.com.br/eventos/rio-de-janeiro (listagem por cidade)
   ❌ https://eventbrite.com.br/d/brazil--rio-de-janeiro/events/ (listagem)
   ❌ https://bluenoterio.com.br/shows (listagem de todos os shows - falta ID específico)

   PROGRAMAÇÃO GERAL DE VENUES:
   ❌ https://salaceliciameireles.rj.gov.br/programacao (calendário mensal)
   ❌ https://casadochoro.com.br/programacao (agenda geral)

📋 CHECKLIST ANTES DE RETORNAR UM LINK:
   ✅ O link contém ID/identificador único? (numérico, slug, hash, ou parâmetro)
   ✅ O link é de uma PLATAFORMA de venda (Sympla, Eventbrite, etc) OU página específica do venue?
   ✅ O link aponta para UMA página específica de evento (não listagem/categoria)?
   ✅ O link NÃO é homepage do artista/venue/plataforma?
   ✅ O link NÃO é de agregador genérico (Shazam, Concerts50, etc)?

   SE TODAS AS RESPOSTAS FOREM ✅ → retornar link
   SE QUALQUER RESPOSTA FOR ❌ → retornar null

4. SE NÃO ENCONTRAR link específico:
   - Busque em TODAS as plataformas prioritárias (Sympla, Eventbrite, Ticketmaster, Fever)
   - Busque em plataformas secundárias (Ingresso.com, Bileto)
   - APENAS APÓS TENTAR TODAS AS FONTES: retorne null
   - NÃO retorne links genéricos "por garantia" (null é MELHOR que link inválido)
"""

        # Montar prompt completo
        return (
            common_header
            + tipos_section
            + keywords_section
            + venues_section
            + sources_section
            + instrucoes_especiais
            + required_fields
            + return_format
        )

    def _get_saturdays_in_period(self, start_date, end_date) -> list[dict]:
        """
        Retorna lista de sábados no período de busca.

        Args:
            start_date: Data inicial (datetime)
            end_date: Data final (datetime)

        Returns:
            Lista de dicts com info de cada sábado: [{"date": datetime, "date_str": "15/11/2025"}, ...]
        """
        from datetime import timedelta

        saturdays = []
        current = start_date

        # Iterar dia por dia até end_date
        while current <= end_date:
            # weekday() retorna 5 para sábado (0=segunda, 6=domingo)
            if current.weekday() == 5:
                saturdays.append({
                    "date": current,
                    "date_str": current.strftime("%d/%m/%Y")
                })
            current += timedelta(days=1)

        return saturdays


    def _build_prompt_from_config(self, config: dict, context: dict) -> str:
        """
        Constrói prompt a partir de configuração YAML.

        Args:
            config: Configuração carregada do YAML (categoria ou venue)
            context: Contexto com variáveis de data (start_date_str, end_date_str, etc)

        Returns:
            Prompt completo formatado
        """
        # Nomes dos campos variam se é categoria ou venue
        # Para categoria: venues_sugeridos
        # Para venue: pode não ter venues_sugeridos (usar lista vazia)

        venues_list = config.get("venues_sugeridos", config.get("fontes_prioritarias", []))

        return self._build_focused_prompt(
            categoria=config["nome"],
            tipo_busca=config["tipo_busca"],
            descricao=config["descricao"],
            tipos_evento=config["tipos_evento"],
            palavras_chave=config["palavras_chave"],
            venues_sugeridos=venues_list if isinstance(venues_list, list) else [],
            instrucoes_especiais=config.get("instrucoes_especiais", ""),
            start_date_str=context["start_date_str"],
            end_date_str=context["end_date_str"],
            month_year_str=context["month_year_str"],
            month_str=context["month_str"]
        )

    def _get_search_task(self, prompt: str, search_name: str, config: dict):
        """
        Retorna tarefa de busca (paralela ou sequencial) baseado em configuração.

        Args:
            prompt: Prompt de busca
            search_name: Nome da busca (para logs)
            config: Configuração do YAML com campo opcional 'parallel_queries'

        Returns:
            Coroutine para asyncio.gather()
        """
        n_parallel = config.get("parallel_queries", 1)

        if n_parallel <= 1:
            # Busca sequencial
            return self._run_micro_search(prompt, search_name)
        else:
            # Busca paralela
            logger.info(f"   ⚡ Configurando busca paralela para {search_name} ({n_parallel} queries)")
            return self._run_parallel_micro_search(prompt, search_name, n_parallel)

    async def search_all_sources(self) -> dict[str, Any]:
        """Busca eventos usando Perplexity Sonar Pro com 6 micro-searches focadas."""
        logger.info(f"{self.log_prefix} Iniciando busca de eventos com Perplexity Sonar Pro...")

        # ═══════════════════════════════════════════════════════════
        # PRIORIDADE 1: SCRAPERS CUSTOMIZADOS (Blue Note + Sala Cecília Meireles)
        # ═══════════════════════════════════════════════════════════
        logger.info(f"{self.log_prefix} 🎫 Buscando eventos via scrapers customizados...")
        from utils.eventim_scraper import EventimScraper

        # Blue Note
        blue_note_scraped = EventimScraper.scrape_blue_note_events()
        if blue_note_scraped:
            logger.info(f"✓ Encontrados {len(blue_note_scraped)} eventos Blue Note no Eventim")
        else:
            logger.warning("⚠️  Nenhum evento Blue Note encontrado no scraper")

        # Sala Cecília Meireles
        cecilia_meireles_scraped = EventimScraper.scrape_cecilia_meireles_events()
        if cecilia_meireles_scraped:
            logger.info(f"✓ Encontrados {len(cecilia_meireles_scraped)} eventos Sala Cecília Meireles")
        else:
            logger.warning("⚠️  Nenhum evento Sala Cecília Meireles encontrado no scraper")

        # CCBB Rio
        ccbb_scraped = EventimScraper.scrape_ccbb_events()
        if ccbb_scraped:
            logger.info(f"✓ Encontrados {len(ccbb_scraped)} eventos CCBB")
        else:
            logger.warning("⚠️  Nenhum evento CCBB encontrado no scraper")

        # Teatro Municipal (Fever - JSON-LD)
        teatro_municipal_scraped = EventimScraper.scrape_teatro_municipal_fever_events()
        if teatro_municipal_scraped:
            logger.info(f"✓ Encontrados {len(teatro_municipal_scraped)} eventos Teatro Municipal (Fever)")
        else:
            logger.warning("⚠️  Nenhum evento Teatro Municipal encontrado no scraper Fever")

        # ═══════════════════════════════════════════════════════════
        # CARREGAR PROMPTS DO YAML
        # ═══════════════════════════════════════════════════════════
        # Construir contexto de datas para interpolação
        context = self.prompt_loader.build_context(
            SEARCH_CONFIG['start_date'],
            SEARCH_CONFIG['end_date']
        )

        logger.info(f"{self.log_prefix} Criando prompts a partir do YAML...")

        # ═══════════════════════════════════════════════════════════
        # CARREGAMENTO DINÂMICO DE CATEGORIAS E VENUES (baseado em config.py)
        # ═══════════════════════════════════════════════════════════
        # Importar configurações habilitadas
        categorias_ids = ENABLED_CATEGORIES  # Vem de config.py
        venues_ids = ENABLED_VENUES  # Vem de config.py

        logger.info(f"{self.log_prefix} Configuração ativa:")
        logger.info(f"{self.log_prefix}   Categorias habilitadas ({len(categorias_ids)}): {', '.join(categorias_ids) if categorias_ids else 'NENHUMA'}")
        logger.info(f"{self.log_prefix}   Venues habilitados ({len(venues_ids)}): {', '.join(venues_ids) if venues_ids else 'NENHUM'}")

        # Carregar configurações de categorias habilitadas e construir prompts
        prompts_categorias = {}
        configs_categorias = {}

        for cat_id in categorias_ids:
            config = self.prompt_loader.get_categoria(cat_id, context)
            prompts_categorias[cat_id] = self._build_prompt_from_config(config, context)
            configs_categorias[cat_id] = config

        # Carregar configurações de venues habilitados e construir prompts
        prompts_venues = {}
        configs_venues = {}

        for venue_id in venues_ids:
            config = self.prompt_loader.get_venue(venue_id, context)
            prompts_venues[venue_id] = self._build_prompt_from_config(config, context)
            configs_venues[venue_id] = config

        # ═══════════════════════════════════════════════════════════
        # Calcular total de prompts
        # ═══════════════════════════════════════════════════════════
# Calcular total de prompts (categorias + venues)
        total_categorias = len(categorias_ids)
        total_prompts = total_categorias + len(venues_ids)
        logger.info(f"{self.log_prefix} ✅ {total_prompts} prompts criados com sucesso")

        try:
            # ═══════════════════════════════════════════════════════════
            # EXECUÇÃO PARALELA DAS MICRO-SEARCHES (DINÂMICO)
            # ═══════════════════════════════════════════════════════════
            logger.info(f"{self.log_prefix} Executando {total_prompts} micro-searches em paralelo...")

            # Construir lista de searches dinamicamente com metadados
            searches = []
            search_metadata = []  # Rastreamento de tipo/id/nome para cada busca

            # Adicionar categorias habilitadas (exceto outdoor_parques - tratado separadamente)
            for cat_id in categorias_ids:
                if cat_id == "outdoor_parques":
                    continue  # Substituído por buscas de sábados

                # Obter display name do YAML
                display_name = configs_categorias[cat_id].get("nome", cat_id)

                searches.append(self._get_search_task(
                    prompts_categorias[cat_id],
                    display_name,
                    configs_categorias[cat_id]
                ))
                search_metadata.append({
                    "type": "category",
                    "id": cat_id,
                    "name": display_name
                })
                logger.debug(f"   ✓ Adicionada busca de categoria: {display_name}")

            # Adicionar venues habilitados
            for venue_id in venues_ids:
                # Obter display name do YAML
                display_name = configs_venues[venue_id].get("nome", venue_id)

                searches.append(self._get_search_task(
                    prompts_venues[venue_id],
                    display_name,
                    configs_venues[venue_id]
                ))
                search_metadata.append({
                    "type": "venue",
                    "id": venue_id,
                    "name": display_name
                })
                logger.debug(f"   ✓ Adicionada busca de venue: {display_name}")

            logger.info(f"{self.log_prefix} ✅ {len(searches)} buscas preparadas: {len([m for m in search_metadata if m['type'] == 'category'])} categorias, {len([m for m in search_metadata if m['type'] == 'saturday'])} sábados, {len([m for m in search_metadata if m['type'] == 'venue'])} venues")

            # Executar todas as buscas em paralelo
            results = await asyncio.gather(*searches)

            logger.info(f"✓ Todas as {total_prompts} micro-searches concluídas")

            # ═══════════════════════════════════════════════════════════
            # PROCESSAR RESULTADOS DINAMICAMENTE (baseado em search_metadata)
            # ═══════════════════════════════════════════════════════════
            # Resultados são organizados por índice seguindo a ordem de search_metadata
            logger.info(f"{self.log_prefix} 📦 Processando {len(results)} resultados...")

            # Mapear resultados para seus metadados
            results_map = {}
            for i, metadata in enumerate(search_metadata):
                result_type = metadata["type"]
                result_id = metadata["id"]
                result_name = metadata["name"]

                # Armazenar resultado com seus metadados
                results_map[i] = {
                    "result": results[i],
                    "metadata": metadata
                }

                logger.debug(f"   [{i}] {result_type.upper()}: {result_name}")

            # ═══════════════════════════════════════════════════════════
            # MERGE INTELIGENTE DOS RESULTADOS COM PYDANTIC
            # ═══════════════════════════════════════════════════════════
            logger.info("🔗 Fazendo merge dos resultados...")

            # Helper function: Filter events by date
            def filter_events_by_date(eventos: list[dict], search_name: str) -> list[dict]:
                """
                Filtra eventos com datas inválidas (fora do período).

                CRÍTICO: Perplexity retorna 5-48% de eventos fora do período,
                mesmo com instruções explícitas. Este filtro é obrigatório.
                """
                if not eventos:
                    return []

                start_date = SEARCH_CONFIG['start_date']
                end_date = SEARCH_CONFIG['end_date']

                valid_events = []
                invalid_events = []

                for evento in eventos:
                    # Tentar múltiplos campos de data
                    date_str = (
                        evento.get('data') or
                        evento.get('data_completa') or
                        evento.get('data_inicio') or
                        ''
                    )

                    if not date_str:
                        invalid_events.append((evento.get('titulo', 'SEM TÍTULO'), 'Sem campo de data'))
                        continue

                    # Validar data
                    validation = DateParser.validate_event_date(date_str, start_date, end_date)

                    if validation['is_valid']:
                        valid_events.append(evento)
                    else:
                        titulo = evento.get('titulo', 'SEM TÍTULO')
                        invalid_events.append((titulo, validation['reason']))

                # Log estatísticas de filtro
                total = len(eventos)
                filtered = len(invalid_events)

                if filtered > 0:
                    pct = (filtered / total * 100) if total > 0 else 0
                    logger.warning(
                        f"⚠️  {search_name}: Filtrados {filtered}/{total} eventos ({pct:.0f}%) "
                        f"com datas inválidas"
                    )
                    for titulo, reason in invalid_events[:3]:  # Log primeiros 3
                        logger.debug(f"   • {titulo}: {reason}")
                    if len(invalid_events) > 3:
                        logger.debug(f"   ... e mais {len(invalid_events) - 3} eventos")
                else:
                    logger.info(f"✓ {search_name}: Todos os {total} eventos têm datas válidas")

                return valid_events

            # Helper function: Clean markdown from JSON
            def clean_json_from_markdown(text: str) -> str:
                """Remove markdown code blocks and extra text from JSON responses.

                Handles cases like:
                - # Eventos na Sala Cecília Meireles\n\nCom base na busca...\n\n```json\n{...}\n```
                - Plain JSON with preamble text
                - Multiple markdown blocks (uses last one)
                """
                if not text or text.strip() == "":
                    return ""

                import re

                # Remove leading/trailing whitespace
                text = text.strip()

                # STEP 1: Try to find JSON within markdown code blocks
                # Pattern: ```json ... ``` or ``` ... ```
                code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
                matches = re.findall(code_block_pattern, text)
                if matches:
                    # Use the last match (usually the complete JSON)
                    text = matches[-1].strip()

                # STEP 2: Remove ANYTHING before the first { or [
                # This handles preamble text like headers, explanations, etc.
                json_start_brace = text.find('{')
                json_start_bracket = text.find('[')

                # Find the earliest valid JSON start
                valid_starts = [pos for pos in [json_start_brace, json_start_bracket] if pos != -1]
                if valid_starts:
                    json_start = min(valid_starts)
                    text = text[json_start:]

                # STEP 3: Remove ANYTHING after the last } or ]
                # Find matching closing bracket
                if text.startswith('{'):
                    # Find the last } that matches the structure
                    depth = 0
                    for i, char in enumerate(text):
                        if char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                text = text[:i+1]
                                break
                elif text.startswith('['):
                    # Find the last ] that matches the structure
                    depth = 0
                    for i, char in enumerate(text):
                        if char == '[':
                            depth += 1
                        elif char == ']':
                            depth -= 1
                            if depth == 0:
                                text = text[:i+1]
                                break

                return text.strip()

            # Helper function: Parse categoria com Pydantic
            def safe_parse_categoria(result_data, search_name: str) -> list[dict]:
                """Parse categoria usando Pydantic validation."""
                try:
                    # 🔍 DEBUG: Mostrar detalhes dos dados recebidos
                    logger.info(f"🔍 DEBUG [{search_name}] Dados recebidos:")
                    logger.info(f"   • Tipo: {type(result_data)}")

                    # 🛠️ CORREÇÃO: Aceitar tanto string quanto list
                    if isinstance(result_data, list):
                        logger.info(f"   • Dados em formato LIST - processamento direto")
                        logger.info(f"   • Length: {len(result_data)}")
                        # Dados já são lista de eventos - usar diretamente
                        if not result_data:
                            logger.warning(f"⚠️  Busca {search_name} retornou lista vazia")
                            return []
                        eventos = result_data
                        # FILTRO CRÍTICO: Remover eventos com datas inválidas
                        eventos_filtrados = filter_events_by_date(eventos, search_name)
                        logger.info(f"✓ Busca {search_name}: {len(eventos_filtrados)} eventos processados (lista direta)")
                        return eventos_filtrados
                    elif isinstance(result_data, str):
                        logger.info(f"   • Dados em formato STRING - parseando JSON")
                        logger.info(f"   • Length: {len(result_data)}")
                        if result_data.strip() == "":
                            logger.warning(f"⚠️  Busca {search_name} retornou string vazia")
                            return []
                        # Limpar markdown antes de parsear
                        clean_json = clean_json_from_markdown(result_data)
                        if not clean_json:
                            logger.warning(f"⚠️  Busca {search_name} retornou JSON vazio após limpeza")
                            return []
                        # Use Pydantic para validar e parsear
                        resultado = ResultadoBuscaCategoria.model_validate_json(clean_json)
                        logger.info(f"✓ Busca {search_name}: {len(resultado.eventos)} eventos validados")
                        # Converter Pydantic models para dicts
                        eventos = [evento.model_dump() for evento in resultado.eventos]
                        # FILTRO CRÍTICO: Remover eventos com datas inválidas
                        eventos_filtrados = filter_events_by_date(eventos, search_name)
                        return eventos_filtrados
                    else:
                        logger.error(f"❌ Tipo de dados inesperado na busca {search_name}: {type(result_data)}")
                        return []

                except ValidationError as e:
                    logger.error(f"❌ Schema inválido na busca {search_name}:")
                    for error in e.errors():
                        logger.error(f"   • {error['loc']}: {error['msg']}")
                    if isinstance(result_data, str):
                        logger.error(f"   Conteúdo (primeiros 200 chars): {result_data[:200]}")
                    else:
                        logger.error(f"   Dados: {result_data}")
                    return []
                except Exception as e:
                    logger.error(f"❌ Erro inesperado na busca {search_name}: {e}")
                    logger.error(f"   Tipo: {type(result_data)}")
                    return []

            # Helper function: Parse venue (formato diferente, mantém dict)
            def safe_parse_venue(result_str: str, venue_name: str) -> list[dict]:
                """Parse venue usando JSON simples (formato: {venue_name: [eventos]}).

                Inclui fallback com normalização unicode para lidar com acentuação.
                """
                try:
                    import unicodedata

                    if not result_str or not isinstance(result_str, str) or result_str.strip() == "":
                        logger.warning(f"⚠️  Busca {venue_name} retornou vazio")
                        return []
                    # Limpar markdown antes de parsear
                    clean_json = clean_json_from_markdown(result_str)
                    if not clean_json:
                        logger.warning(f"⚠️  Busca {venue_name} retornou JSON vazio após limpeza")
                        return []
                    data = json.loads(clean_json)

                    # STEP 1: Tentar match exato primeiro
                    eventos = data.get(venue_name, [])

                    # STEP 2: Se não encontrou, tentar com normalização unicode (fallback)
                    if not eventos and venue_name:
                        # Normalizar nome do venue esperado (NFD = decompor acentos)
                        normalized_expected = unicodedata.normalize('NFD', venue_name)

                        # Tentar encontrar chave com normalização
                        for key in data.keys():
                            normalized_key = unicodedata.normalize('NFD', key)
                            if normalized_key == normalized_expected:
                                eventos = data.get(key, [])
                                logger.info(
                                    f"⚙️  Fallback unicode: '{key}' → '{venue_name}' "
                                    f"({len(eventos)} eventos)"
                                )
                                break

                    if eventos:
                        logger.info(f"✓ Busca {venue_name}: {len(eventos)} eventos encontrados")
                        # FILTRO CRÍTICO: Remover eventos com datas inválidas
                        eventos_filtrados = filter_events_by_date(eventos, venue_name)
                        return eventos_filtrados
                    else:
                        logger.warning(f"⚠️  Nenhum evento encontrado para {venue_name} (chaves disponíveis: {list(data.keys())})")
                        return []
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON inválido na busca {venue_name}: {e}")
                    logger.error(f"   Conteúdo (primeiros 200 chars): {result_str[:200]}")
                    return []

            # ═══════════════════════════════════════════════════════════
            # PARSE DINÂMICO DE RESULTADOS (baseado em search_metadata)
            # ═══════════════════════════════════════════════════════════
            logger.info(f"{self.log_prefix} 🔄 Iniciando parse dinâmico de {len(results)} resultados...")

            # Coleções de eventos por tipo
            eventos_categorias = {}  # {categoria_id: [eventos]}
            eventos_outdoor_saturdays = []  # Lista consolidada de eventos outdoor de sábados
            eventos_venues = {}  # {venue_display_name: [eventos]}

            # Iterar sobre todos os resultados usando metadados
            for i, result_data in results_map.items():
                result_str = result_data["result"]
                metadata = result_data["metadata"]
                result_type = metadata["type"]
                result_id = metadata["id"]
                result_name = metadata["name"]

                logger.debug(f"{self.log_prefix} Processando resultado {i}: {result_type}/{result_id}")

                # ═══════════════════════════════════════════════════════════
                # CATEGORIAS: Parse com safe_parse_categoria
                # ═══════════════════════════════════════════════════════════
                if result_type == "category":
                    eventos_parsed = safe_parse_categoria(result_str, result_name)
                    eventos_categorias[result_id] = eventos_parsed
                    logger.debug(f"   ✓ Categoria '{result_name}': {len(eventos_parsed)} eventos")

                # ═══════════════════════════════════════════════════════════
                # SÁBADOS OUTDOOR: Consolidar todos em uma única lista
                # ═══════════════════════════════════════════════════════════
                elif result_type == "saturday":
                    eventos_parsed = safe_parse_categoria(result_str, result_name)
                    saturday_date = metadata["saturday_data"]["date_str"]
                    if eventos_parsed:
                        logger.info(f"   ✓ Sábado {saturday_date}: {len(eventos_parsed)} eventos outdoor")
                        eventos_outdoor_saturdays.extend(eventos_parsed)
                    else:
                        logger.debug(f"   ⚠️  Sábado {saturday_date}: 0 eventos outdoor")

                # ═══════════════════════════════════════════════════════════
                # VENUES: Parse com safe_parse_venue
                # ═══════════════════════════════════════════════════════════
                elif result_type == "venue":
                    eventos_parsed = safe_parse_venue(result_str, result_name)
                    eventos_venues[result_name] = eventos_parsed
                    logger.debug(f"   ✓ Venue '{result_name}': {len(eventos_parsed)} eventos")

            # ═══════════════════════════════════════════════════════════
            # SCRAPER PRIORITY: Adicionar eventos de scrapers com prioridade
            # ═══════════════════════════════════════════════════════════
            # Mapeamento de scrapers para categoria/venue
            scraper_mappings = {
                "jazz": ("categoria", "jazz", blue_note_scraped, "Blue Note Rio - Av. Atlântica, 1910, Copacabana, Rio de Janeiro", "Jazz"),
                "sala_cecilia": ("venue", "Sala Cecília Meireles", cecilia_meireles_scraped, "Sala Cecília Meireles - Rua da Lapa, 47, Centro, Rio de Janeiro", "Sala Cecília Meireles"),
                "teatro_municipal": ("venue", "Teatro Municipal do Rio de Janeiro", teatro_municipal_scraped, "Teatro Municipal do Rio de Janeiro - Praça Floriano, s/n, Centro, Rio de Janeiro", "Teatro Municipal do Rio de Janeiro"),
                "ccbb": ("venue", "CCBB Rio - Centro Cultural Banco do Brasil", ccbb_scraped, "CCBB Rio - Centro Cultural Banco do Brasil - Rua Primeiro de Março, 66, Centro, Rio de Janeiro", "CCBB Rio - Centro Cultural Banco do Brasil"),
            }

            for scraper_key, (target_type, target_key, scraped_events, location, field_value) in scraper_mappings.items():
                if not scraped_events:
                    continue

                logger.info(f"🎫 [PRIORIDADE] Processando {len(scraped_events)} eventos do scraper {scraper_key}...")

                # Preparar eventos do scraper
                scraper_formatted = []
                for scraped_event in scraped_events:
                    event_dict = {
                        "titulo": scraped_event["titulo"],
                        "data": scraped_event["data"],
                        "horario": scraped_event["horario"],
                        "local": location,
                        "preco": "Consultar link",
                        "link_ingresso": scraped_event["link"],
                        "descricao": None,  # Será enriquecido depois
                        "link_valid": True  # Scraper oficial = link confiável
                    }

                    # Adicionar campo apropriado (categoria ou venue)
                    if target_type == "categoria":
                        event_dict["categoria"] = field_value
                    else:
                        event_dict["venue"] = field_value

                    scraper_formatted.append(event_dict)

                # Adicionar scraped events com prioridade (primeiro na lista)
                if target_type == "categoria":
                    # Categoria: mesclar com eventos Perplexity, removendo duplicatas
                    existing_events = eventos_categorias.get(target_key, [])
                    merged_events = scraper_formatted.copy()

                    # Adicionar eventos Perplexity que não são duplicatas
                    duplicates_count = 0
                    for perplexity_event in existing_events:
                        if not any(e.get("titulo", "").lower() == perplexity_event.get("titulo", "").lower()
                                   for e in merged_events):
                            merged_events.append(perplexity_event)
                        else:
                            duplicates_count += 1

                    eventos_categorias[target_key] = merged_events
                    logger.info(f"✓ Scraper {scraper_key}: {len(scraped_events)} eventos adicionados, {duplicates_count} duplicatas Perplexity removidas")

                else:  # venue
                    # Venue: mesclar com eventos Perplexity, removendo duplicatas
                    existing_events = eventos_venues.get(target_key, [])
                    merged_events = scraper_formatted.copy()

                    # Adicionar eventos Perplexity que não são duplicatas
                    duplicates_count = 0
                    for perplexity_event in existing_events:
                        if not any(e.get("titulo", "").lower() == perplexity_event.get("titulo", "").lower()
                                   for e in merged_events):
                            merged_events.append(perplexity_event)
                        else:
                            duplicates_count += 1

                    eventos_venues[target_key] = merged_events
                    logger.info(f"✓ Scraper {scraper_key}: {len(scraped_events)} eventos adicionados, {duplicates_count} duplicatas Perplexity removidas")

            # Log consolidado de sábados outdoor
            if eventos_outdoor_saturdays:
                logger.info(f"✓ Total eventos outdoor (todos os sábados): {len(eventos_outdoor_saturdays)} eventos")

            # ═══════════════════════════════════════════════════════════
            # CONSOLIDAR EVENTOS OUTDOOR DOS SÁBADOS (adicionar à categoria outdoor_parques)
            # ═══════════════════════════════════════════════════════════
            if eventos_outdoor_saturdays:
                # Se outdoor_parques está habilitado, adicionar eventos dos sábados
                if "outdoor_parques" in eventos_categorias:
                    # Já existe - deveria estar vazio (outdoor genérico foi substituído por sábados)
                    eventos_categorias["outdoor_parques"].extend(eventos_outdoor_saturdays)
                else:
                    # Criar categoria outdoor_parques com eventos dos sábados
                    eventos_categorias["outdoor_parques"] = eventos_outdoor_saturdays

            # ═══════════════════════════════════════════════════════════
            # MONTAR ESTRUTURA DE EVENTOS GERAIS (todas as categorias)
            # ═══════════════════════════════════════════════════════════
            todos_eventos_gerais = []
            for cat_id, eventos_cat in eventos_categorias.items():
                todos_eventos_gerais.extend(eventos_cat)
                logger.debug(f"   Categoria '{cat_id}': {len(eventos_cat)} eventos adicionados ao merge geral")

            # OTIMIZAÇÃO: Deduplicação precoce ANTES de validação/enriquecimento
            eventos_antes_dedup = len(todos_eventos_gerais)
            todos_eventos_gerais = deduplicate_events(todos_eventos_gerais)
            eventos_removidos = eventos_antes_dedup - len(todos_eventos_gerais)
            if eventos_removidos > 0:
                logger.info(
                    f"🔄 Deduplicação precoce: {eventos_removidos} eventos duplicados removidos "
                    f"({eventos_antes_dedup} → {len(todos_eventos_gerais)})"
                )

            # Estrutura final de eventos gerais
            eventos_gerais_merged = {"eventos": todos_eventos_gerais}

            # ═══════════════════════════════════════════════════════════
            # ESTRUTURA DE EVENTOS DE VENUES (já está pronta)
            # ═══════════════════════════════════════════════════════════
            eventos_locais_merged = eventos_venues

            total_venues_before = sum(len(v) for v in eventos_locais_merged.values())
            logger.info(
                f"✓ Merge dinâmico concluído: {len(todos_eventos_gerais)} eventos gerais, "
                f"{total_venues_before} eventos de venues"
            )

            # Normalizar nomes de venues (consolidar CCBB Teatro I/II/III, etc.)
            logger.info(f"🔗 Normalizando nomes de venues...")
            eventos_locais_merged = self._normalize_venue_names(eventos_locais_merged)

            # Aplicar limitação de eventos por venue
            logger.info(f"📊 Aplicando limitação de {MAX_EVENTS_PER_VENUE} eventos por venue...")
            eventos_locais_merged = self._limit_events_per_venue(eventos_locais_merged)

            total_venues_after = sum(len(v) for v in eventos_locais_merged.values())
            if total_venues_after < total_venues_before:
                logger.info(
                    f"📊 Limitação aplicada: {total_venues_before} eventos → {total_venues_after} eventos "
                    f"({total_venues_before - total_venues_after} removidos)"
                )

            # Retornar no formato compatível com o resto do sistema
            try:
                json_geral = json.dumps(eventos_gerais_merged, ensure_ascii=False)
                json_especial = json.dumps(eventos_locais_merged, ensure_ascii=False)

                result = {
                    "perplexity_geral": json_geral,
                    "perplexity_especial": json_especial,
                    "search_timestamp": datetime.now().isoformat(),
                }
                return result
            except Exception as json_error:
                logger.error(f"❌ Erro na serialização JSON: {json_error}")
                import traceback
                traceback.print_exc()
                raise

        except Exception as e:
            logger.error(f"❌ ERRO CRÍTICO nas micro-searches: {type(e).__name__}: {e}")
            logger.error("📍 Local do erro:")
            import traceback
            import sys
            exc_type, exc_value, exc_traceback = sys.exc_info()

            # Logar o traceback completo
            logger.error("=== TRACEBACK COMPLETO ===")
            traceback.print_exc()
            logger.error("=========================")

            # Logar informações sobre onde o erro ocorreu
            if exc_traceback:
                frame = exc_traceback.tb_frame
                lineno = exc_traceback.tb_lineno
                filename = frame.f_code.co_filename
                logger.error(f"Arquivo: {filename}, Linha: {lineno}")
                logger.error(f"Função: {frame.f_code.co_name}")

            # Retornar JSONs vazios como fallback (para não quebrar o pipeline)
            logger.warning("⚠️  Retornando JSONs vazios como fallback")
            return {
                "perplexity_geral": "{}",
                "perplexity_especial": "{}",
                "search_timestamp": datetime.now().isoformat(),
            }

    def _find_event_ticket_link_batch(self, events_batch: list[dict]) -> dict[str, str]:
        """Busca links de múltiplos eventos em uma única chamada (batch)."""
        if not events_batch:
            return {}

        # Construir prompt com lista de eventos
        eventos_texto = []
        for i, event in enumerate(events_batch, 1):
            titulo = event.get("titulo", "")
            data = event.get("data", "")
            local = event.get("local", "")
            eventos_texto.append(f"{i}. {titulo} | Data: {data} | Local: {local}")

        # Usar PromptBuilder para construir prompt estruturado
        prompt = (
            PromptBuilder()
            .add_header(
                "MISSÃO CRÍTICA",
                f"Encontrar links ESPECÍFICOS de venda/informações para estes {len(events_batch)} eventos no Rio de Janeiro."
            )
            .add_section("EVENTOS", "\n".join(eventos_texto))
            .add_raw("\nESTRATÉGIA DE BUSCA OBRIGATÓRIA (siga esta ordem):\n\nPara CADA evento:")
            .add_numbered_list(
                "",
                [
                    """**PRIORIDADE MÁXIMA - Site Oficial do Venue**:
   - Blue Note Rio → acesse bluenoterio.com e busque na agenda/programação
   - Teatro Municipal → acesse theatromunicipal.rj.gov.br
   - Sala Cecília Meirelles → acesse salaceliciameireles.com.br
   - Casa do Choro → acesse casadochoro.com.br/agenda
   - Outros venues → busque "[nome venue] agenda programação\"""",
                    """**Plataformas de Ingressos** (use termos EXATOS):
   - Sympla: busque "site:sympla.com.br [titulo evento completo] rio"
   - Ingresso.com: busque "site:ingresso.com [titulo evento completo]"
   - Eventbrite: busque "site:eventbrite.com.br [titulo evento completo]"
   - Bilheteria Digital, Ticket360, Uhuu""",
                    """**Redes Sociais/Instagram** (último recurso):
   - Busque Instagram oficial do venue com link na bio ou stories
   - Posts recentes sobre o evento específico"""
                ],
                emoji_prefix=True
            )
            .add_criteria({
                "ACEITE APENAS": [
                    "URLs que levam DIRETAMENTE à página do evento específico",
                    "URLs com ID único, slug do evento, ou data na URL",
                    """Exemplos válidos:
     * sympla.com.br/evento/nome-evento-123456
     * bluenoterio.com/shows/artista-data-20250115
     * eventbrite.com.br/e/titulo-evento-tickets-789012"""
                ],
                "REJEITE ABSOLUTAMENTE": [
                    "Homepages: bluenoterio.com, casadochoro.com.br",
                    "Páginas de listagem: /agenda, /shows, /eventos, /programacao",
                    "URLs genéricas sem identificador do evento",
                    "Links de redes sociais (exceto se for o ÚNICO link disponível)"
                ]
            }, title="CRITÉRIOS DE ACEITAÇÃO (seja RIGOROSO)")
            .add_numbered_list(
                "VALIDAÇÃO FINAL:\nAntes de retornar cada link",
                [
                    "Confirme que a URL contém elemento único (ID, nome, data)",
                    "Verifique que não é página genérica",
                    "Se tiver dúvida, retorne null"
                ]
            )
            .add_json_example(
                {
                    "1": "https://url-especifica-evento-1.com/... ou null",
                    "2": "https://url-especifica-evento-2.com/... ou null"
                },
                "FORMATO JSON (sem comentários)"
            )
            .add_raw("⚠️ IMPORTANTE: Prefira retornar null do que um link genérico. Links ruins serão rejeitados na validação.")
            .build()
        )

        try:
            response = self.search_agent.run(prompt)

            # Usar safe_json_parse para extração consistente
            from utils.json_helpers import safe_json_parse
            links_map = safe_json_parse(
                response.content,
                default={}
            )

            # Converter chaves para int se necessário e validar formato
            result = {}
            for key, value in links_map.items():
                # Validar que o link não é genérico
                if value and value != "null" and isinstance(value, str):
                    # Checar se não é link genérico básico
                    generic_endings = ['/shows/', '/eventos/', '/agenda/', '/programacao/', '/calendar/']
                    is_generic = any(value.rstrip('/').endswith(ending.rstrip('/')) for ending in generic_endings)

                    # Também verificar se é apenas homepage (sem path específico)
                    from urllib.parse import urlparse
                    parsed = urlparse(value)
                    path = parsed.path.rstrip('/')

                    if is_generic or not path or path == '/':
                        logger.warning(f"   ⚠️ Link genérico rejeitado: {value}")
                        result[str(key)] = None
                    else:
                        result[str(key)] = value
                else:
                    result[str(key)] = None

            return result

        except Exception as e:
            logger.error(f"Erro na busca batch de links: {e}")
            return {}

    def _search_missing_links(self, events: list[dict]) -> list[dict]:
        """Busca links para eventos que não têm link, processando em batches."""
        # Identificar eventos sem link
        events_without_links = []
        events_indices = []

        for i, event in enumerate(events):
            if not event.get("link_ingresso"):
                events_without_links.append(event)
                events_indices.append(i)

        if not events_without_links:
            logger.info("Todos os eventos já possuem links")
            return events

        logger.info(f"🔗 Buscando links para {len(events_without_links)} eventos sem link...")

        # Processar em batches de 5
        batch_size = 5
        total_found = 0

        for batch_start in range(0, len(events_without_links), batch_size):
            batch_end = min(batch_start + batch_size, len(events_without_links))
            batch = events_without_links[batch_start:batch_end]

            logger.info(f"   Processando batch {batch_start//batch_size + 1} ({len(batch)} eventos)...")

            # Buscar links para este batch
            links_map = self._find_event_ticket_link_batch(batch)

            # Atribuir links encontrados
            for local_idx, event in enumerate(batch):
                batch_key = str(local_idx + 1)
                if batch_key in links_map and links_map[batch_key]:
                    event["link_ingresso"] = links_map[batch_key]
                    event["link_source"] = "busca_complementar_batch"
                    total_found += 1
                    logger.info(f"   ✓ Link encontrado para: {event.get('titulo')}")

        logger.info(f"✓ Busca complementar concluída: {total_found}/{len(events_without_links)} links encontrados")
        return events

    def _filter_excluded_events(self, events: list[dict], category_name: str = "") -> list[dict]:
        """Filtra eventos que contêm palavras de exclusão no título ou descrição.

        Args:
            events: Lista de eventos para filtrar
            category_name: Nome da categoria/venue (para logging)

        Returns:
            Lista de eventos filtrados (sem eventos que contêm keywords de exclusão)
        """
        from config import EVENT_CATEGORIES, GLOBAL_EXCLUDE_KEYWORDS

        # Iniciar com exclusões GLOBAIS (infantil, LGBTQ+, etc) - aplicadas a TODOS os eventos
        exclude_keywords = list(GLOBAL_EXCLUDE_KEYWORDS)

        # Adicionar exclusões específicas de outdoor (shows mainstream) se aplicável
        outdoor_exclude = EVENT_CATEGORIES.get("outdoor", {}).get("exclude", [])
        if outdoor_exclude:
            exclude_keywords.extend(outdoor_exclude)

        if not exclude_keywords:
            return events

        filtered = []
        removed_count = 0

        for event in events:
            titulo = event.get("titulo", "").lower()
            descricao_raw = event.get("descricao", "") or ""  # Handle None values
            descricao = descricao_raw.lower()
            combined_text = f"{titulo} {descricao}"

            # Verificar se contém alguma palavra de exclusão
            matched_keyword = None
            for keyword in exclude_keywords:
                if keyword.lower() in combined_text:
                    matched_keyword = keyword
                    break

            if matched_keyword:
                removed_count += 1
                logger.info(f"   ❌ Evento filtrado ({category_name}): '{event.get('titulo')}' [match: '{matched_keyword}']")
            else:
                filtered.append(event)

        if removed_count > 0:
            logger.info(f"✓ Filtro de exclusão aplicado em {category_name}: {removed_count} eventos removidos, {len(filtered)} mantidos")

        return filtered

    def process_with_llm(self, raw_events: dict[str, Any]) -> str:
        """Combina e limpa resultados das duas buscas Perplexity."""
        logger.info("Combinando dados das 2 buscas Perplexity...")

        # Extrair dados das duas buscas
        data_geral = raw_events.get("perplexity_geral", "{}")
        data_especial = raw_events.get("perplexity_especial", "{}")

        # Usar clean_json_response do json_helpers (centralizado)
        from utils.json_helpers import clean_json_response
        data_geral_clean = clean_json_response(data_geral)
        data_especial_clean = clean_json_response(data_especial)

        # Combinar em um único JSON
        combined = f'{{"eventos_gerais": {data_geral_clean}, "eventos_locais_especiais": {data_especial_clean}}}'

        logger.info("Dados combinados das 2 buscas")

        # Parsear para aplicar busca complementar de links
        try:
            combined_data = json.loads(combined)

            # Extrair todos os eventos para busca complementar
            all_events = []

            # Eventos gerais
            if "eventos_gerais" in combined_data and "eventos" in combined_data["eventos_gerais"]:
                all_events.extend(combined_data["eventos_gerais"]["eventos"])

            # Eventos de locais especiais
            if "eventos_locais_especiais" in combined_data:
                for local_name, local_events in combined_data["eventos_locais_especiais"].items():
                    if isinstance(local_events, list):
                        all_events.extend([e for e in local_events if isinstance(e, dict)])

            # Aplicar busca complementar de links
            if all_events:
                self._search_missing_links(all_events)

            # ═══════════════════════════════════════════════════════════
            # APLICAR FILTRO DE EXCLUSÃO (remover samba, axé, mainstream)
            # ═══════════════════════════════════════════════════════════
            logger.info("🔍 Aplicando filtro de exclusão...")

            # Filtrar eventos gerais (categorias: Jazz, Teatro-Comédia, Outdoor-FimDeSemana)
            if "eventos_gerais" in combined_data and "eventos" in combined_data["eventos_gerais"]:
                original_count = len(combined_data["eventos_gerais"]["eventos"])
                combined_data["eventos_gerais"]["eventos"] = self._filter_excluded_events(
                    combined_data["eventos_gerais"]["eventos"],
                    "eventos_gerais"
                )
                final_count = len(combined_data["eventos_gerais"]["eventos"])
                logger.info(f"📊 Eventos gerais: {original_count} → {final_count} (removidos: {original_count - final_count})")

            # Filtrar eventos de locais especiais (Casa do Choro, Sala Cecília, Teatro Municipal, Artemis)
            if "eventos_locais_especiais" in combined_data:
                for local_name, local_events in combined_data["eventos_locais_especiais"].items():
                    if isinstance(local_events, list) and local_events:
                        original_count = len(local_events)
                        combined_data["eventos_locais_especiais"][local_name] = self._filter_excluded_events(
                            local_events,
                            local_name
                        )
                        final_count = len(combined_data["eventos_locais_especiais"][local_name])
                        if original_count != final_count:
                            logger.info(f"📊 {local_name}: {original_count} → {final_count} (removidos: {original_count - final_count})")

            logger.info("✅ Filtro de exclusão aplicado com sucesso")

            # Retornar JSON atualizado
            return json.dumps(combined_data, ensure_ascii=False, indent=2)

        except json.JSONDecodeError as e:
            logger.error(f"Erro ao parsear JSON combinado: {e}")
            return combined
