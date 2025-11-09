"""Agente de busca de eventos."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from agents.base_agent import BaseAgent
from config import SEARCH_CONFIG, MAX_EVENTS_PER_VENUE
from models.event_models import ResultadoBuscaCategoria
from utils.deduplicator import deduplicate_events
from utils.prompt_templates import PromptBuilder
from utils.prompt_loader import get_prompt_loader

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
        if result and result.strip():
            preview = result[:500].replace('\n', ' ')
            logger.debug(f"   📄 Resposta Perplexity [{search_name}]: {preview}...")

        logger.info(f"   ✓ Busca concluída: {search_name}")
        return result

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

    def _build_saturday_outdoor_prompt(self, saturday_date_str: str, month_str: str) -> str:
        """
        Constrói prompt ultra-focado para buscar eventos outdoor em UM sábado específico.

        Args:
            saturday_date_str: Data do sábado no formato DD/MM/YYYY
            month_str: Nome do mês em inglês (ex: "november")

        Returns:
            Prompt completo formatado
        """
        return f"""
🎯 BUSCA ULTRA-FOCADA: Eventos Outdoor no Rio APENAS no dia {saturday_date_str} (SÁBADO)

OBJETIVO: Encontrar eventos culturais ao ar livre ESPECIFICAMENTE neste sábado.

TIPOS DE EVENTOS:
- 🎬 Cinema ao ar livre
- 🎵 Concertos em parques
- 🛍️ Feiras culturais nichadas
- 🌳 Eventos em parques/jardins

ESTRATÉGIA DE BUSCA - FOCO EM EVENTOS RECORRENTES:

1. 🔍 **Feiras Recorrentes aos Sábados**:
   - Feira da Praça XV (todos os sábados): site:bafafa.com.br "feira praça xv" {saturday_date_str}
   - Feira Rio Antigo (1º sábado): site:visit.rio "feira rio antigo" {month_str}
   - Feiras de artesanato em parques: site:timeout.com/rio-de-janeiro feira {month_str}

2. 🔍 **Cinema ao Ar Livre**:
   - "cinema ao ar livre rio sábado {saturday_date_str}"
   - Parque Lage, Jardim Botânico, Aterro: site:parquelage.rj.gov.br cinema {month_str}

3. 🔍 **Concertos em Parques**:
   - "concerto jardim botânico {saturday_date_str}"
   - "música ao ar livre rio {saturday_date_str}"

4. 🔍 **Eventos em Locais Específicos**:
   - Jardim Botânico: Instagram @jardimbotanicorj
   - Parque Lage: Instagram @parquelage
   - Quinta da Boa Vista: eventos culturais

FONTES OBRIGATÓRIAS:
- site:bafafa.com.br eventos rio {saturday_date_str}
- site:visit.rio agenda {saturday_date_str}
- site:timeout.com/rio-de-janeiro fim-de-semana

⚠️ EXCLUSÕES:
- ❌ Samba, pagode, forró, axé
- ❌ Eventos esportivos (corridas, maratonas)
- ❌ Mega shows em estádios

INFORMAÇÕES OBRIGATÓRIAS:
- titulo: Nome do evento
- data: {saturday_date_str} (fixo - este sábado)
- horario: HH:MM (obrigatório)
- local: Nome + endereço completo
- preco: Valor ou "Gratuito"
- link_ingresso: URL específica ou null
- descricao: Resumo do evento

FORMATO DE RETORNO:
{{
  "eventos": [
    {{
      "categoria": "Outdoor/Parques",
      "titulo": "Nome do evento",
      "data": "{saturday_date_str}",
      "horario": "HH:MM",
      "local": "Nome + Endereço",
      "preco": "Valor",
      "link_ingresso": "URL ou null",
      "descricao": "Resumo"
    }}
  ]
}}

IMPORTANTE:
- Retornar APENAS eventos confirmados para {saturday_date_str}
- Se não encontrar eventos: retornar {{"eventos": []}}
- Priorizar eventos RECORRENTES (feiras fixas aos sábados)
"""

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

        # Teatro Municipal - REMOVIDO
        # Site oficial não tem estrutura adequada para scraping
        # Fever carrega eventos via JavaScript (não scrapável)
        # Perplexity consegue encontrar os eventos via busca web
        teatro_municipal_scraped = []
        logger.info("✓ Teatro Municipal: delegado para Perplexity (Fever usa JS)")

        # ═══════════════════════════════════════════════════════════
        # CARREGAR PROMPTS DO YAML
        # ═══════════════════════════════════════════════════════════
        # Construir contexto de datas para interpolação
        context = self.prompt_loader.build_context(
            SEARCH_CONFIG['start_date'],
            SEARCH_CONFIG['end_date']
        )

        logger.info(f"{self.log_prefix} Criando prompts a partir do YAML...")


        # Carregar configurações de categorias e construir prompts
        categorias_ids = ["jazz", "comedia", "musica_classica", "outdoor", "cinema", "feira_gastronomica", "feira_artesanato"]
        prompts_categorias = {}

        for cat_id in categorias_ids:
            config = self.prompt_loader.get_categoria(cat_id, context)
            prompts_categorias[cat_id] = self._build_prompt_from_config(config, context)

        # Carregar configurações de venues e construir prompts
        venues_ids = [
            "casa_choro", "sala_cecilia", "teatro_municipal", "artemis", "ccbb",
            "oi_futuro", "ims", "parque_lage", "ccjf", "mam_cinema",
            "theatro_net", "ccbb_teatro_cinema",
            "istituto_italiano", "maze_jazz", "teatro_leblon", "clube_jazz_rival", "estacao_net"
        ]
        prompts_venues = {}

        for venue_id in venues_ids:
            config = self.prompt_loader.get_venue(venue_id, context)
            prompts_venues[venue_id] = self._build_prompt_from_config(config, context)

        # ═══════════════════════════════════════════════════════════
        # BUSCAS SEPARADAS PARA SÁBADOS OUTDOOR (dinâmico)
        # ═══════════════════════════════════════════════════════════
        start_date = SEARCH_CONFIG['start_date']
        end_date = SEARCH_CONFIG['end_date']
        saturdays = self._get_saturdays_in_period(start_date, end_date)
        saturday_prompts = []
        saturday_names = []

        for saturday in saturdays:
            saturday_date_str = saturday["date_str"]
            month_str = saturday["date"].strftime("%B").lower()
            prompt = self._build_saturday_outdoor_prompt(saturday_date_str, month_str)
            saturday_prompts.append(prompt)
            saturday_names.append(f"Outdoor Sábado {saturday_date_str}")

        logger.info(f"{self.log_prefix} 🗓️  {len(saturdays)} sábados identificados no período: {[s['date_str'] for s in saturdays]}")

        total_prompts = len(categorias_ids) - 1 + len(saturday_prompts) + len(venues_ids)  # -1 para remover "outdoor" genérico
        logger.info(f"{self.log_prefix} ✅ {total_prompts} prompts criados com sucesso")

        try:
            # ═══════════════════════════════════════════════════════════
            # EXECUÇÃO PARALELA DAS MICRO-SEARCHES
            # ═══════════════════════════════════════════════════════════
            logger.info(f"{self.log_prefix} Executando {total_prompts} micro-searches em paralelo...")

            # Preparar lista de searches (categorias + sábados + venues)
            searches = [
                self._run_micro_search(prompts_categorias["jazz"], "Jazz"),
                self._run_micro_search(prompts_categorias["comedia"], "Comédia"),
                self._run_micro_search(prompts_categorias["musica_classica"], "Música Clássica"),
                # OUTDOOR: substituído por buscas separadas por sábado
                self._run_micro_search(prompts_categorias["cinema"], "Cinema"),
                self._run_micro_search(prompts_categorias["feira_gastronomica"], "Feira Gastronômica"),
                self._run_micro_search(prompts_categorias["feira_artesanato"], "Feira de Artesanato"),
            ]

            # Adicionar buscas de sábados outdoor
            for i, saturday_prompt in enumerate(saturday_prompts):
                searches.append(self._run_micro_search(saturday_prompt, saturday_names[i]))

            # Adicionar buscas de venues
            searches.extend([
                self._run_micro_search(prompts_venues["casa_choro"], "Casa do Choro"),
                self._run_micro_search(prompts_venues["sala_cecilia"], "Sala Cecília Meireles"),
                self._run_micro_search(prompts_venues["teatro_municipal"], "Teatro Municipal"),
                self._run_micro_search(prompts_venues["artemis"], "Artemis"),
                self._run_micro_search(prompts_venues["ccbb"], "CCBB Rio"),
                self._run_micro_search(prompts_venues["oi_futuro"], "Oi Futuro"),
                self._run_micro_search(prompts_venues["ims"], "IMS"),
                self._run_micro_search(prompts_venues["parque_lage"], "Parque Lage"),
                self._run_micro_search(prompts_venues["ccjf"], "CCJF"),
                self._run_micro_search(prompts_venues["mam_cinema"], "MAM Cinema"),
                self._run_micro_search(prompts_venues["theatro_net"], "Theatro Net Rio"),
                self._run_micro_search(prompts_venues["ccbb_teatro_cinema"], "CCBB Teatro/Cinema"),
                self._run_micro_search(prompts_venues["istituto_italiano"], "Istituto Italiano"),
                self._run_micro_search(prompts_venues["maze_jazz"], "Maze Jazz Club"),
                self._run_micro_search(prompts_venues["teatro_leblon"], "Teatro do Leblon"),
                self._run_micro_search(prompts_venues["clube_jazz_rival"], "Clube do Jazz/Rival"),
                self._run_micro_search(prompts_venues["estacao_net"], "Estação Net"),
            ])

            # Executar todas as buscas em paralelo
            results = await asyncio.gather(*searches)

            # Desempacotar resultados
            # Formato: [jazz, comedia, musica_classica, cinema, feira_gast, feira_art, sábados..., venues...]
            result_jazz = results[0]
            result_comedia = results[1]
            result_musica_classica = results[2]
            result_cinema = results[3]
            result_feira_gastronomica = results[4]
            result_feira_artesanato = results[5]

            # Resultados dos sábados outdoor (dinâmico) - consolidar todos
            saturday_results = results[6:6 + len(saturdays)]
            logger.info(f"🗓️  Processando {len(saturday_results)} resultados de sábados outdoor...")

            # Resultados dos venues (após sábados)
            venues_start_idx = 6 + len(saturdays)
            result_casa_choro = results[venues_start_idx]
            result_sala_cecilia = results[venues_start_idx + 1]
            result_teatro_municipal = results[venues_start_idx + 2]
            result_artemis = results[venues_start_idx + 3]
            result_ccbb = results[venues_start_idx + 4]
            result_oi_futuro = results[venues_start_idx + 5]
            result_ims = results[venues_start_idx + 6]
            result_parque_lage = results[venues_start_idx + 7]
            result_ccjf = results[venues_start_idx + 8]
            result_mam_cinema = results[venues_start_idx + 9]
            result_theatro_net = results[venues_start_idx + 10]
            result_ccbb_teatro_cinema = results[venues_start_idx + 11]
            result_istituto_italiano = results[venues_start_idx + 12]
            result_maze_jazz = results[venues_start_idx + 13]
            result_teatro_leblon = results[venues_start_idx + 14]
            result_clube_jazz_rival = results[venues_start_idx + 15]
            result_estacao_net = results[venues_start_idx + 16]

            logger.info(f"✓ Todas as {total_prompts} micro-searches concluídas")

            # ═══════════════════════════════════════════════════════════
            # MERGE INTELIGENTE DOS RESULTADOS COM PYDANTIC
            # ═══════════════════════════════════════════════════════════
            logger.info("🔗 Fazendo merge dos resultados...")

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
            def safe_parse_categoria(result_str: str, search_name: str) -> list[dict]:
                """Parse categoria usando Pydantic validation."""
                try:
                    if not result_str or result_str.strip() == "":
                        logger.warning(f"⚠️  Busca {search_name} retornou vazio")
                        return []
                    # Limpar markdown antes de parsear
                    clean_json = clean_json_from_markdown(result_str)
                    if not clean_json:
                        logger.warning(f"⚠️  Busca {search_name} retornou JSON vazio após limpeza")
                        return []
                    # Use Pydantic para validar e parsear
                    resultado = ResultadoBuscaCategoria.model_validate_json(clean_json)
                    logger.info(f"✓ Busca {search_name}: {len(resultado.eventos)} eventos validados")
                    # Converter Pydantic models para dicts
                    return [evento.model_dump() for evento in resultado.eventos]
                except ValidationError as e:
                    logger.error(f"❌ Schema inválido na busca {search_name}:")
                    for error in e.errors():
                        logger.error(f"   • {error['loc']}: {error['msg']}")
                    logger.error(f"   Conteúdo (primeiros 200 chars): {result_str[:200]}")
                    return []
                except Exception as e:
                    logger.error(f"❌ Erro inesperado na busca {search_name}: {e}")
                    return []

            # Helper function: Parse venue (formato diferente, mantém dict)
            def safe_parse_venue(result_str: str, venue_name: str) -> list[dict]:
                """Parse venue usando JSON simples (formato: {venue_name: [eventos]}).

                Inclui fallback com normalização unicode para lidar com acentuação.
                """
                try:
                    import unicodedata

                    if not result_str or result_str.strip() == "":
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
                    else:
                        logger.warning(f"⚠️  Nenhum evento encontrado para {venue_name} (chaves disponíveis: {list(data.keys())})")

                    return eventos
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON inválido na busca {venue_name}: {e}")
                    logger.error(f"   Conteúdo (primeiros 200 chars): {result_str[:200]}")
                    return []

            # ═══════════════════════════════════════════════════════════
            # MERGE JAZZ: Scraper Blue Note TEM PRIORIDADE sobre Perplexity
            # ═══════════════════════════════════════════════════════════
            eventos_jazz = []

            # PASSO 1: Adicionar eventos do SCRAPER primeiro (prioridade alta - links oficiais)
            if blue_note_scraped:
                logger.info(f"🎫 [PRIORIDADE] Adicionando {len(blue_note_scraped)} eventos Blue Note do scraper oficial...")
                for scraped_event in blue_note_scraped:
                    # Converter para formato EventoCategoria
                    jazz_event = {
                        "titulo": scraped_event["titulo"],
                        "data": scraped_event["data"],
                        "horario": scraped_event["horario"],
                        "local": "Blue Note Rio - Av. Atlântica, 1910, Copacabana, Rio de Janeiro",
                        "preco": "Consultar link",
                        "link_ingresso": scraped_event["link"],
                        "descricao": None,  # Será enriquecido depois
                        "categoria": "Jazz"
                    }
                    eventos_jazz.append(jazz_event)
                    logger.debug(f"   ✓ Scraper: {jazz_event['titulo']}")
                logger.info(f"✓ {len(eventos_jazz)} eventos do scraper Blue Note adicionados")

            # PASSO 2: Adicionar eventos do PERPLEXITY como complemento (apenas não-duplicatas)
            eventos_jazz_perplexity = safe_parse_categoria(result_jazz, "Jazz")
            logger.debug(f"Jazz parsed from Perplexity - {len(eventos_jazz_perplexity)} eventos")

            if eventos_jazz_perplexity:
                duplicatas_perplexity = 0
                for perplexity_event in eventos_jazz_perplexity:
                    # Verificar duplicata por título (case-insensitive)
                    if not any(e.get("titulo", "").lower() == perplexity_event.get("titulo", "").lower()
                               for e in eventos_jazz):
                        eventos_jazz.append(perplexity_event)
                        logger.debug(f"   ✓ Perplexity: {perplexity_event.get('titulo')}")
                    else:
                        duplicatas_perplexity += 1
                        logger.debug(f"   ⏭️  Duplicata do Perplexity ignorada (scraper tem prioridade): {perplexity_event.get('titulo')}")

                if duplicatas_perplexity > 0:
                    logger.info(f"⏭️  {duplicatas_perplexity} duplicatas do Perplexity ignoradas (scraper tem prioridade)")

            logger.info(f"✓ Total de eventos Jazz após merge: {len(eventos_jazz)} eventos")

            eventos_comedia = safe_parse_categoria(result_comedia, "Comédia")
            logger.debug(f"Comédia parsed - {len(eventos_comedia)} eventos")

            eventos_musica_classica = safe_parse_categoria(result_musica_classica, "Música Clássica")
            logger.debug(f"Música Clássica parsed - {len(eventos_musica_classica)} eventos")

            # Processar eventos outdoor dos sábados (consolidar todos os resultados)
            eventos_outdoor = []
            for i, saturday_result in enumerate(saturday_results):
                saturday_date = saturdays[i]["date_str"]
                eventos_sab = safe_parse_categoria(saturday_result, "Outdoor/Parques")
                if eventos_sab:
                    logger.info(f"   ✓ Sábado {saturday_date}: {len(eventos_sab)} eventos outdoor")
                    eventos_outdoor.extend(eventos_sab)
                else:
                    logger.debug(f"   ⚠️  Sábado {saturday_date}: 0 eventos outdoor")

            logger.info(f"✓ Total eventos outdoor (todos os sábados): {len(eventos_outdoor)} eventos")

            eventos_cinema = safe_parse_categoria(result_cinema, "Cinema")
            logger.debug(f"Cinema parsed - {len(eventos_cinema)} eventos")

            eventos_feira_gastronomica = safe_parse_categoria(result_feira_gastronomica, "Feira Gastronômica")
            logger.debug(f"Feira Gastronômica parsed - {len(eventos_feira_gastronomica)} eventos")

            eventos_feira_artesanato = safe_parse_categoria(result_feira_artesanato, "Feira de Artesanato")
            logger.debug(f"Feira de Artesanato parsed - {len(eventos_feira_artesanato)} eventos")

            # Merge eventos gerais (todas as 7 categorias)
            todos_eventos_gerais = (
                eventos_jazz +
                eventos_comedia +
                eventos_musica_classica +
                eventos_outdoor +
                eventos_cinema +
                eventos_feira_gastronomica +
                eventos_feira_artesanato
            )

            # OTIMIZAÇÃO: Deduplicação precoce ANTES de validação/enriquecimento
            # Economiza chamadas de API processando apenas eventos únicos
            eventos_antes_dedup = len(todos_eventos_gerais)
            todos_eventos_gerais = deduplicate_events(todos_eventos_gerais)
            eventos_removidos = eventos_antes_dedup - len(todos_eventos_gerais)
            if eventos_removidos > 0:
                logger.info(
                    f"🔄 Deduplicação precoce: {eventos_removidos} eventos duplicados removidos "
                    f"({eventos_antes_dedup} → {len(todos_eventos_gerais)})"
                )

            # Criar estrutura de eventos gerais
            eventos_gerais_merged = {"eventos": todos_eventos_gerais}

            # Parse eventos de venues
            eventos_casa_choro = safe_parse_venue(result_casa_choro, "Casa do Choro")
            logger.debug(f"Casa do Choro parsed - {len(eventos_casa_choro)} eventos")

            # ═══════════════════════════════════════════════════════════
            # MERGE SALA CECÍLIA MEIRELES: Scraper TEM PRIORIDADE sobre Perplexity
            # ═══════════════════════════════════════════════════════════
            eventos_sala_cecilia = []

            # PASSO 1: Adicionar eventos do SCRAPER primeiro (prioridade alta - links oficiais)
            if cecilia_meireles_scraped:
                logger.info(f"🎼 [PRIORIDADE] Adicionando {len(cecilia_meireles_scraped)} eventos Sala Cecília Meireles do scraper oficial...")
                for scraped_event in cecilia_meireles_scraped:
                    # Converter para formato EventoVenue
                    cecilia_event = {
                        "titulo": scraped_event["titulo"],
                        "data": scraped_event["data"],
                        "horario": scraped_event["horario"],
                        "local": "Sala Cecília Meireles - Rua da Lapa, 47, Centro, Rio de Janeiro",
                        "preco": "Consultar link",
                        "link_ingresso": scraped_event["link"],
                        "descricao": None,  # Será enriquecido depois
                        "venue": "Sala Cecília Meireles"
                    }
                    eventos_sala_cecilia.append(cecilia_event)
                    logger.debug(f"   ✓ Scraper: {cecilia_event['titulo']}")
                logger.info(f"✓ {len(eventos_sala_cecilia)} eventos do scraper Sala Cecília Meireles adicionados")

            # PASSO 2: Adicionar eventos do PERPLEXITY como complemento (apenas não-duplicatas)
            eventos_sala_cecilia_perplexity = safe_parse_venue(result_sala_cecilia, "Sala Cecília Meireles")
            logger.debug(f"Sala Cecília Meireles parsed from Perplexity - {len(eventos_sala_cecilia_perplexity)} eventos")

            if eventos_sala_cecilia_perplexity:
                duplicatas_perplexity = 0
                for perplexity_event in eventos_sala_cecilia_perplexity:
                    # Verificar duplicata por título (case-insensitive)
                    if not any(e.get("titulo", "").lower() == perplexity_event.get("titulo", "").lower()
                               for e in eventos_sala_cecilia):
                        eventos_sala_cecilia.append(perplexity_event)
                        logger.debug(f"   ✓ Perplexity: {perplexity_event.get('titulo')}")
                    else:
                        duplicatas_perplexity += 1
                        logger.debug(f"   ⏭️  Duplicata do Perplexity ignorada (scraper tem prioridade): {perplexity_event.get('titulo')}")

                if duplicatas_perplexity > 0:
                    logger.info(f"⏭️  {duplicatas_perplexity} duplicatas do Perplexity ignoradas (scraper tem prioridade)")

            logger.info(f"✓ Total de eventos Sala Cecília Meireles após merge: {len(eventos_sala_cecilia)} eventos")

            # ═══════════════════════════════════════════════════════════
            # MERGE TEATRO MUNICIPAL: Scraper TEM PRIORIDADE sobre Perplexity
            # ═══════════════════════════════════════════════════════════
            eventos_teatro_municipal = []

            # PASSO 1: Adicionar eventos do SCRAPER primeiro (prioridade alta - links oficiais)
            if teatro_municipal_scraped:
                logger.info(f"🎭 [PRIORIDADE] Adicionando {len(teatro_municipal_scraped)} eventos Teatro Municipal do scraper oficial...")
                for scraped_event in teatro_municipal_scraped:
                    # Converter para formato EventoVenue
                    municipal_event = {
                        "titulo": scraped_event["titulo"],
                        "data": scraped_event["data"],
                        "horario": scraped_event["horario"],
                        "local": "Teatro Municipal do Rio de Janeiro - Praça Floriano, s/n, Centro, Rio de Janeiro",
                        "preco": "Consultar link",
                        "link_ingresso": scraped_event["link"],
                        "descricao": None,  # Será enriquecido depois
                        "venue": "Teatro Municipal do Rio de Janeiro"
                    }
                    eventos_teatro_municipal.append(municipal_event)
                    logger.debug(f"   ✓ Scraper: {municipal_event['titulo']}")
                logger.info(f"✓ {len(eventos_teatro_municipal)} eventos do scraper Teatro Municipal adicionados")

            # PASSO 2: Adicionar eventos do PERPLEXITY como complemento (apenas não-duplicatas)
            eventos_teatro_municipal_perplexity = safe_parse_venue(result_teatro_municipal, "Teatro Municipal do Rio de Janeiro")
            logger.debug(f"Teatro Municipal parsed from Perplexity - {len(eventos_teatro_municipal_perplexity)} eventos")

            if eventos_teatro_municipal_perplexity:
                duplicatas_perplexity = 0
                for perplexity_event in eventos_teatro_municipal_perplexity:
                    # Verificar duplicata por título (case-insensitive)
                    if not any(e.get("titulo", "").lower() == perplexity_event.get("titulo", "").lower()
                               for e in eventos_teatro_municipal):
                        eventos_teatro_municipal.append(perplexity_event)
                        logger.debug(f"   ✓ Perplexity: {perplexity_event.get('titulo')}")
                    else:
                        duplicatas_perplexity += 1
                        logger.debug(f"   ⏭️  Duplicata do Perplexity ignorada (scraper tem prioridade): {perplexity_event.get('titulo')}")

                if duplicatas_perplexity > 0:
                    logger.info(f"⏭️  {duplicatas_perplexity} duplicatas do Perplexity ignoradas (scraper tem prioridade)")

            logger.info(f"✓ Total de eventos Teatro Municipal após merge: {len(eventos_teatro_municipal)} eventos")

            eventos_artemis = safe_parse_venue(result_artemis, "Artemis - Torrefação Artesanal e Cafeteria")
            logger.debug(f"Artemis parsed - {len(eventos_artemis)} eventos")

            # ═══════════════════════════════════════════════════════════
            # MERGE CCBB: Scraper TEM PRIORIDADE sobre Perplexity
            # ═══════════════════════════════════════════════════════════
            eventos_ccbb = []

            # PASSO 1: Adicionar eventos do SCRAPER primeiro (prioridade alta - links oficiais)
            if ccbb_scraped:
                logger.info(f"🎨 [PRIORIDADE] Adicionando {len(ccbb_scraped)} eventos CCBB do scraper oficial...")
                for scraped_event in ccbb_scraped:
                    # Converter para formato EventoVenue
                    ccbb_event = {
                        "titulo": scraped_event["titulo"],
                        "data": scraped_event["data"],
                        "horario": scraped_event["horario"],
                        "local": "CCBB Rio - Centro Cultural Banco do Brasil - Rua Primeiro de Março, 66, Centro, Rio de Janeiro",
                        "preco": "Consultar link",
                        "link_ingresso": scraped_event["link"],
                        "descricao": None,  # Será enriquecido depois
                        "venue": "CCBB Rio - Centro Cultural Banco do Brasil"
                    }
                    eventos_ccbb.append(ccbb_event)
                    logger.debug(f"   ✓ Scraper: {ccbb_event['titulo']}")
                logger.info(f"✓ {len(eventos_ccbb)} eventos do scraper CCBB adicionados")

            # PASSO 2: Adicionar eventos do PERPLEXITY como complemento (apenas não-duplicatas)
            eventos_ccbb_perplexity = safe_parse_venue(result_ccbb, "CCBB Rio - Centro Cultural Banco do Brasil")
            logger.debug(f"CCBB Rio parsed from Perplexity - {len(eventos_ccbb_perplexity)} eventos")

            if eventos_ccbb_perplexity:
                duplicatas_perplexity = 0
                for perplexity_event in eventos_ccbb_perplexity:
                    # Verificar duplicata por título (case-insensitive)
                    if not any(e.get("titulo", "").lower() == perplexity_event.get("titulo", "").lower()
                               for e in eventos_ccbb):
                        eventos_ccbb.append(perplexity_event)
                        logger.debug(f"   ✓ Perplexity: {perplexity_event.get('titulo')}")
                    else:
                        duplicatas_perplexity += 1
                        logger.debug(f"   ⏭️  Duplicata do Perplexity ignorada (scraper tem prioridade): {perplexity_event.get('titulo')}")

                if duplicatas_perplexity > 0:
                    logger.info(f"⏭️  {duplicatas_perplexity} duplicatas do Perplexity ignoradas (scraper tem prioridade)")

            logger.info(f"✓ Total de eventos CCBB após merge: {len(eventos_ccbb)} eventos")

            eventos_oi_futuro = safe_parse_venue(result_oi_futuro, "Oi Futuro")
            logger.debug(f"Oi Futuro parsed - {len(eventos_oi_futuro)} eventos")

            eventos_ims = safe_parse_venue(result_ims, "IMS - Instituto Moreira Salles")
            logger.debug(f"IMS parsed - {len(eventos_ims)} eventos")

            eventos_parque_lage = safe_parse_venue(result_parque_lage, "Parque Lage")
            logger.debug(f"Parque Lage parsed - {len(eventos_parque_lage)} eventos")

            eventos_ccjf = safe_parse_venue(result_ccjf, "CCJF - Centro Cultural Justiça Federal")
            logger.debug(f"CCJF parsed - {len(eventos_ccjf)} eventos")

            eventos_mam_cinema = safe_parse_venue(result_mam_cinema, "MAM Cinema")
            logger.debug(f"MAM Cinema parsed - {len(eventos_mam_cinema)} eventos")

            eventos_theatro_net = safe_parse_venue(result_theatro_net, "Theatro Net Rio")
            logger.debug(f"Theatro Net Rio parsed - {len(eventos_theatro_net)} eventos")

            eventos_ccbb_teatro_cinema = safe_parse_venue(result_ccbb_teatro_cinema, "CCBB Teatro e Cinema")
            logger.debug(f"CCBB Teatro e Cinema parsed - {len(eventos_ccbb_teatro_cinema)} eventos")

            eventos_istituto_italiano = safe_parse_venue(result_istituto_italiano, "Istituto Italiano di Cultura")
            logger.debug(f"Istituto Italiano parsed - {len(eventos_istituto_italiano)} eventos")

            eventos_maze_jazz = safe_parse_venue(result_maze_jazz, "Maze Jazz Club")
            logger.debug(f"Maze Jazz Club parsed - {len(eventos_maze_jazz)} eventos")

            eventos_teatro_leblon = safe_parse_venue(result_teatro_leblon, "Teatro do Leblon")
            logger.debug(f"Teatro do Leblon parsed - {len(eventos_teatro_leblon)} eventos")

            eventos_clube_jazz_rival = safe_parse_venue(result_clube_jazz_rival, "Clube do Jazz / Teatro Rival")
            logger.debug(f"Clube do Jazz/Rival parsed - {len(eventos_clube_jazz_rival)} eventos")

            eventos_estacao_net = safe_parse_venue(result_estacao_net, "Estação Net (Ipanema e Botafogo)")
            logger.debug(f"Estação Net parsed - {len(eventos_estacao_net)} eventos")

            # Criar estrutura de eventos de venues
            eventos_locais_merged = {
                "Casa do Choro": eventos_casa_choro,
                "Sala Cecília Meireles": eventos_sala_cecilia,
                "Teatro Municipal do Rio de Janeiro": eventos_teatro_municipal,
                "Artemis - Torrefação Artesanal e Cafeteria": eventos_artemis,
                "CCBB Rio - Centro Cultural Banco do Brasil": eventos_ccbb,
                "Oi Futuro": eventos_oi_futuro,
                "IMS - Instituto Moreira Salles": eventos_ims,
                "Parque Lage": eventos_parque_lage,
                "CCJF - Centro Cultural Justiça Federal": eventos_ccjf,
                "MAM Cinema": eventos_mam_cinema,
                "Theatro Net Rio": eventos_theatro_net,
                "CCBB Teatro e Cinema": eventos_ccbb_teatro_cinema,
                "Istituto Italiano di Cultura": eventos_istituto_italiano,
                "Maze Jazz Club": eventos_maze_jazz,
                "Teatro do Leblon": eventos_teatro_leblon,
                "Clube do Jazz / Teatro Rival": eventos_clube_jazz_rival,
                "Estação Net (Ipanema e Botafogo)": eventos_estacao_net,
            }

            total_venues_before = sum(len(v) for v in eventos_locais_merged.values())
            logger.info(
                f"✓ Merge concluído: {len(todos_eventos_gerais)} eventos gerais, "
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
        outdoor_exclude = EVENT_CATEGORIES.get("outdoor_parques", {}).get("exclude", [])
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
