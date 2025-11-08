"""Agente de busca de eventos."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from config import SEARCH_CONFIG, MAX_EVENTS_PER_VENUE
from models.event_models import ResultadoBuscaCategoria
from utils.agent_factory import AgentFactory

logger = logging.getLogger(__name__)

# Prefixo para logs deste agente
LOG_PREFIX = "[SearchAgent] 🔍"


class SearchAgent:
    """Agente responsável por buscar eventos em múltiplas fontes."""

    def __init__(self):
        self.log_prefix = "[SearchAgent] 🔍"

        # Agente de busca com Perplexity Sonar Pro (busca web em tempo real)
        self.search_agent = AgentFactory.create_agent(
            name="Event Search Agent",
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

REGRAS CRÍTICAS PARA LINKS:
- Links devem ser ESPECÍFICOS do evento (não páginas de busca/categoria/listagem)
- ✅ LINKS VÁLIDOS (com ID/nome único do evento):
  * sympla.com.br/evento/nome-do-evento/123456
  * eventbrite.com.br/e/nome-do-evento-tickets-123456
  * ingresso.com/evento/nome-do-evento-123456
  * bluenote.com.br/evento/nome-do-show/
- ❌ LINKS INVÁLIDOS (genéricos - NÃO USAR):
  * ingresso.com/eventos/stand-up?city=rio-de-janeiro (página de categoria)
  * sympla.com.br/eventos/rio-de-janeiro (página de busca)
  * eventbrite.com.br/d/brazil--rio-de-janeiro/events/ (listagem)
  * Qualquer URL com query params de cidade/categoria (?city=, &partnership=)
- Se não encontrar link ESPECÍFICO, use null (busca complementar preencherá depois)
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

REGRAS CRÍTICAS PARA LINKS:
- Links devem ser ESPECÍFICOS do evento (não páginas de busca/categoria/listagem)
- ✅ LINKS VÁLIDOS (com ID/nome único do evento):
  * sympla.com.br/evento/nome-do-evento/123456
  * eventbrite.com.br/e/nome-do-evento-tickets-123456
  * ingresso.com/evento/nome-do-evento-123456
  * bluenote.com.br/evento/nome-do-show/
- ❌ LINKS INVÁLIDOS (genéricos - NÃO USAR):
  * ingresso.com/eventos/stand-up?city=rio-de-janeiro (página de categoria)
  * sympla.com.br/eventos/rio-de-janeiro (página de busca)
  * eventbrite.com.br/d/brazil--rio-de-janeiro/events/ (listagem)
  * Qualquer URL com query params de cidade/categoria (?city=, &partnership=)
- Se não encontrar link ESPECÍFICO, use null (busca complementar preencherá depois)
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

    async def search_all_sources(self) -> dict[str, Any]:
        """Busca eventos usando Perplexity Sonar Pro com 6 micro-searches focadas."""
        logger.info(f"{self.log_prefix} Iniciando busca de eventos com Perplexity Sonar Pro...")

        # ═══════════════════════════════════════════════════════════
        # PRIORIDADE 1: SCRAPER EVENTIM (Blue Note)
        # ═══════════════════════════════════════════════════════════
        logger.info(f"{self.log_prefix} 🎫 Buscando eventos Blue Note via Eventim Scraper...")
        from utils.eventim_scraper import EventimScraper

        blue_note_scraped = EventimScraper.scrape_blue_note_events()
        if blue_note_scraped:
            logger.info(f"✓ Encontrados {len(blue_note_scraped)} eventos Blue Note no Eventim")
        else:
            logger.warning("⚠️  Nenhum evento Blue Note encontrado no scraper")

        # Gerar strings de data dinâmicas
        start_date_str = SEARCH_CONFIG['start_date'].strftime('%d/%m/%Y')
        end_date_str = SEARCH_CONFIG['end_date'].strftime('%d/%m/%Y')
        month_year_str = SEARCH_CONFIG['start_date'].strftime('%B %Y')  # ex: "novembro 2025"
        month_str = SEARCH_CONFIG['start_date'].strftime('%B').lower()  # ex: "novembro"
        year_str = SEARCH_CONFIG['start_date'].strftime('%Y')  # ex: "2025"

        # ═══════════════════════════════════════════════════════════
        # ESTRATÉGIA: 6 MICRO-SEARCHES FOCADAS (DRY + Paralelas)
        # ═══════════════════════════════════════════════════════════
        logger.info(f"{self.log_prefix} Criando 7 prompts micro-focados...")

        # MICRO-SEARCH 1: Jazz
        prompt_jazz = self._build_focused_prompt(
            categoria="Jazz",
            tipo_busca="categoria",
            descricao="Shows de jazz no Rio de Janeiro (jazz tradicional, bebop, fusion, bossa nova)",
            tipos_evento=[
                "Shows de jazz ao vivo",
                "Jazz tradicional, bebop, fusion",
                "Bossa nova, jazz contemporâneo",
                "Jazz em bares, casas de jazz especializadas"
            ],
            palavras_chave=[
                f"site:eventim.com.br/artist/blue-note-rio/ {month_str}",
                f"site:eventim.com.br/artist/blue-note-rio/alegria-tribute",
                f"site:eventim.com.br/artist/blue-note-rio/irma-you-and-my-guitar",
                f"site:eventim.com.br/artist/blue-note-rio/fourplusone",
                f"site:eventim.com.br/artist/blue-note-rio/sete-cabecas",
                f"site:eventim.com.br/artist/blue-note-rio/u2-rio-experience",
                f"site:eventim.com.br/artist/blue-note-rio/zanna",
                f"jazz Rio Janeiro {month_year_str}",
                f"shows jazz {month_str}",
                "Blue Note Rio",
                "Maze Jazz Club"
            ],
            venues_sugeridos=[
                "Blue Note Rio",
                "Maze Jazz Club",
                "Clube do Jazz",
                "Jazz nos Fundos",
                "Bares e hotéis com jazz ao vivo"
            ],
            instrucoes_especiais=f"""
⚠️ IMPORTANTE: Blue Note Rio usa Eventim para venda de ingressos!

✅ FORMATO CORRETO DE LINKS EVENTIM:
eventim.com.br/artist/blue-note-rio/{{evento-normalizado}}-{{id}}/

Exemplos de eventos encontrados:
- eventim.com.br/artist/blue-note-rio/alegria-tribute-to-sade-3977676/
- eventim.com.br/artist/blue-note-rio/irma-you-and-my-guitar-3895518/
- eventim.com.br/artist/blue-note-rio/fourplusone-divas-strong-women-3956417/
- eventim.com.br/artist/blue-note-rio/sete-cabecas-revisitando-acusticos-3973442/

ESTRATÉGIA DE BUSCA (em ordem de prioridade):

1. 🎫 PRIORIDADE MÁXIMA - Busca por evento específico:
   Para CADA show do Blue Note, busque:
   - "site:eventim.com.br/artist/blue-note-rio/{{nome-normalizado}}"
   - Nome normalizado: sem acentos, tudo minúsculo, hífens no lugar de espaços
   - Ex: "Alegria – Tribute to Sade" → "site:eventim.com.br/artist/blue-note-rio/alegria-tribute"

2. 🎺 BUSCA GERAL NA PÁGINA DO ARTISTA:
   - "site:eventim.com.br/artist/blue-note-rio/ {month_str}"
   - Retorna lista completa de eventos do Blue Note

3. 🎺 SITE OFICIAL (último recurso):
   - "site:bluenoterio.com.br/shows/"
   - Use APENAS se não encontrar NENHUM link Eventim

REGRAS PARA LINKS:
- ✅ ACEITAR: eventim.com.br/artist/blue-note-rio/{{evento}}-{{id}}/
- ✅ ACEITAR: bluenoterio.com.br/shows/ (se Eventim falhar)
- ❌ REJEITAR: Links sem identificação do evento

VALIDAÇÃO:
- Data ENTRE {start_date_str} e {end_date_str}
- Sempre priorize links Eventim específicos com ID
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 2: Comédia
        prompt_comedia = self._build_focused_prompt(
            categoria="Comédia",
            tipo_busca="categoria",
            descricao="Stand-up comedy e espetáculos de humor ADULTO no Rio de Janeiro (EXCLUIR eventos infantis)",
            tipos_evento=[
                "Peças teatrais de comédia (adulto)",
                "Stand-up comedy",
                "Humor adulto, espetáculos cômicos",
                "Improv, teatro de improvisação"
            ],
            palavras_chave=[
                f"stand-up Rio {month_str}",
                "teatro comédia adulto Rio de Janeiro",
                "humor adulto Rio",
                "espetáculo cômico Rio"
            ],
            venues_sugeridos=[
                "Estação Net Rio",
                "Teatro Riachuelo",
                "Teatro Clara Nunes",
                "Teatros de comédia especializados"
            ],
            instrucoes_especiais="""
ATENÇÃO - EXCLUSÕES CRÍTICAS (VALIDAÇÃO RIGOROSA):
- REJEITAR IMEDIATAMENTE qualquer evento contendo:

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

- Se menciona "todas as idades" sem clareza de ser adulto → REJEITAR
- APENAS comédia explicitamente para público adulto/maiores de 14/16/18
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 3: Outdoor/Parques
        prompt_outdoor = self._build_focused_prompt(
            categoria="Outdoor/Parques",
            tipo_busca="categoria",
            descricao="Eventos culturais ao ar livre APENAS em sábados e domingos no Rio de Janeiro - INCLUINDO feiras culturais e eventos em praças",
            tipos_evento=[
                "Festivais culturais ao ar livre (sábado/domingo)",
                "Eventos comunitários em parques e praças",
                "Feiras culturais mistas (música + arte + gastronomia)",
                "Eventos de rua em praças públicas",
                "Festivais independentes e alternativos",
                "Shows e performances ao ar livre",
                "Juntas locais e eventos comunitários regulares",
                "Eventos na orla (Copacabana, Ipanema, Leblon)"
            ],
            palavras_chave=[
                f"festival cultural Rio fim de semana {month_str}",
                "evento comunitário parque Rio",
                "festival independente Rio",
                "show ao ar livre Rio",
                f"feira cultural Rio sábado domingo {month_str}",
                f"feira O Fuxico Ipanema {month_str}",
                f"feira das Yabás Madureira {month_str}",
                f"feira da Glória {month_str}",
                f"feirinha Laranjeiras {month_str}",
                f"junta local Rio {month_str}",
                f"corona sunset Copacabana {month_str}",
                f"eventos praça Rio fim de semana {month_str}",
                f"eventos orla Rio sábado domingo {month_str}"
            ],
            venues_sugeridos=[
                "Aterro do Flamengo",
                "Jockey Club Brasileiro",
                "Marina da Glória",
                "Parque Lage",
                "Pista Cláudio Coutinho",
                "Praça Nossa Senhora da Paz (Ipanema)",
                "Praça Paulo da Portela (Madureira)",
                "Praça Marechal Deodoro (Glória)",
                "Praça Paris",
                "Praça XV",
                "Orla de Copacabana",
                "Orla de Ipanema",
                "Avenida Augusto Severo (Glória)",
                "Largo da Carioca"
            ],
            instrucoes_especiais="""
ATENÇÃO - DIAS ESPECÍFICOS:
- APENAS sábados e domingos
- NÃO incluir eventos de segunda a sexta
- Verificar dia da semana da data do evento

ATENÇÃO - EXCLUSÕES CRÍTICAS:
- NÃO incluir: shows mainstream de grandes artistas (Ivete Sangalo, Thiaguinho, Luan Santana, etc.)
- NÃO incluir: samba, pagode, roda de samba, axé, forró (EXCETO se fizer parte de feira cultural mista)
- NÃO incluir: eventos com tags: "turnê", "show nacional", "mega show"
- NÃO incluir: eventos puramente promocionais/comerciais de marcas
- ✅ INCLUIR: feiras culturais mistas, eventos comunitários, festivais independentes
- ✅ INCLUIR: eventos com múltiplos elementos (música + arte + gastronomia)
- FOCO: festivais culturais nichados, performances, eventos comunitários em praças e orlas
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 4: Música Clássica
        prompt_musica_classica = self._build_focused_prompt(
            categoria="Música Clássica",
            tipo_busca="categoria",
            descricao="Concertos e apresentações de música clássica/erudita no Rio de Janeiro",
            tipos_evento=[
                "Concertos de orquestra",
                "Recitais de música erudita",
                "Música de câmara",
                "Apresentações sinfônicas",
                "Coral e ópera"
            ],
            palavras_chave=[
                f"concerto música clássica Rio {month_str}",
                f"orquestra sinfônica Rio {month_year_str}",
                "Theatro Municipal música clássica",
                "Sala Cecília Meireles concerto",
                f"recital piano violino Rio {month_str}",
                "música erudita Rio de Janeiro"
            ],
            venues_sugeridos=[
                "Theatro Municipal",
                "Sala Cecília Meireles",
                "Sala São Paulo",
                "Auditórios e salas de concerto"
            ],
            instrucoes_especiais=f"""
ESTRATÉGIA:
1. Buscar concertos em venues tradicionais (Theatro Municipal, Sala Cecília Meireles)
2. Orquestras: OSB (Orquestra Sinfônica Brasileira), OSESP
3. Festivais de música clássica
4. Recitais de instrumentos clássicos

VALIDAÇÃO:
- Data ENTRE {start_date_str} e {end_date_str}
- EXCLUIR: música popular, jazz, MPB (apenas clássico/erudito)
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 5: Teatro (não-comédia)
        prompt_teatro = self._build_focused_prompt(
            categoria="Teatro",
            tipo_busca="categoria",
            descricao="Peças teatrais dramáticas, experimentais e textos clássicos (EXCLUIR comédia)",
            tipos_evento=[
                "Teatro dramático",
                "Teatro experimental",
                "Textos clássicos",
                "Monólogos e performances"
            ],
            palavras_chave=[
                f"peça teatral Rio {month_str}",
                f"teatro dramático Rio {month_year_str}",
                "espetáculo teatral Rio",
                "montagem teatral adulto Rio"
            ],
            venues_sugeridos=[
                "Teatro Cacilda Becker",
                "Teatro Glauce Rocha",
                "Centro Cultural Banco do Brasil",
                "Teatros independentes"
            ],
            instrucoes_especiais=f"""
IMPORTANTE - EXCLUSÕES:
- EXCLUIR: comédia, stand-up, humor (são categoria separada)
- EXCLUIR: infantil, família
- FOCO: drama, experimental, clássicos, performances artísticas

VALIDAÇÃO:
- Data ENTRE {start_date_str} e {end_date_str}
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 6: Cinema
        prompt_cinema = self._build_focused_prompt(
            categoria="Cinema",
            tipo_busca="categoria",
            descricao="Sessões de cinema, mostras e festivais de filmes no Rio de Janeiro",
            tipos_evento=[
                "Mostras de cinema",
                "Festivais de filmes",
                "Cineclubes",
                "Sessões especiais e retrospectivas"
            ],
            palavras_chave=[
                f"mostra de cinema Rio {month_str}",
                f"festival de filmes Rio {month_year_str}",
                "cineclube Rio",
                "sessão especial cinema Rio",
                "retrospectiva cinema"
            ],
            venues_sugeridos=[
                "Estação NET Rio",
                "Centro Cultural Justiça Federal",
                "MAM Cinema",
                "Cinemas de arte"
            ],
            instrucoes_especiais=f"""
FOCO:
- Mostras temáticas
- Festivais de cinema
- Cineclubes e sessões comentadas
- Retrospectivas de diretores

EXCLUIR:
- Filmes comerciais em cartaz normal
- APENAS eventos especiais/culturais

VALIDAÇÃO:
- Data ENTRE {start_date_str} e {end_date_str}
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 7: Feira Gastronômica
        prompt_feira_gastronomica = self._build_focused_prompt(
            categoria="Feira Gastronômica",
            tipo_busca="categoria",
            descricao="Feiras gastronômicas, food festivals e mercados de comida APENAS em sábados/domingos",
            tipos_evento=[
                "Feiras gastronômicas",
                "Food festivals",
                "Mercados de comida de rua",
                "Festivais de gastronomia"
            ],
            palavras_chave=[
                f"feira gastronômica Rio fim de semana {month_str}",
                f"food festival Rio sábado domingo {month_year_str}",
                "mercado gastronômico Rio",
                "festival gastronomia Rio"
            ],
            venues_sugeridos=[
                "Aterro do Flamengo",
                "Jockey Club",
                "Marina da Glória",
                "Parques e espaços abertos"
            ],
            instrucoes_especiais=f"""
CRÍTICO: APENAS SÁBADOS E DOMINGOS

FOCO:
- Feiras de comida
- Food trucks e mercados
- Festivais gastronômicos

VALIDAÇÃO:
- Data ENTRE {start_date_str} e {end_date_str}
- DIA DA SEMANA: sábado OU domingo
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 8: Feira de Artesanato
        prompt_feira_artesanato = self._build_focused_prompt(
            categoria="Feira de Artesanato",
            tipo_busca="categoria",
            descricao="Feiras de artesanato, arte e design APENAS em sábados/domingos",
            tipos_evento=[
                "Feiras de artesanato",
                "Feiras de arte",
                "Mercados de design",
                "Bazares culturais"
            ],
            palavras_chave=[
                f"feira de artesanato Rio fim de semana {month_str}",
                f"feira de arte Rio sábado domingo {month_year_str}",
                "bazar cultural Rio",
                "feira de design Rio"
            ],
            venues_sugeridos=[
                "Praça General Osório (Ipanema)",
                "Parques",
                "Centros culturais",
                "Espaços abertos"
            ],
            instrucoes_especiais=f"""
CRÍTICO: APENAS SÁBADOS E DOMINGOS

FOCO:
- Artesanato
- Arte local
- Design independente

VALIDAÇÃO:
- Data ENTRE {start_date_str} e {end_date_str}
- DIA DA SEMANA: sábado OU domingo
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 9: Casa do Choro
        prompt_casa_choro = self._build_focused_prompt(
            categoria="Casa do Choro",
            tipo_busca="venue",
            descricao="Eventos na Casa do Choro (Rua da Carioca, 38 - Centro, Rio de Janeiro)",
            tipos_evento=[
                "Shows de choro e música brasileira",
                "Apresentações ao vivo",
                "Eventos culturais no venue"
            ],
            palavras_chave=[
                f"Casa do Choro programação completa {month_year_str}",
                f"site:sympla.com.br Casa do Choro {month_str}",
                f"shows Casa do Choro {month_year_str}",
                "Casa do Choro Rio roda de choro",
                f"roda de choro Centro Rio {month_str}"
            ],
            venues_sugeridos=[
                "Casa do Choro - Rua da Carioca, 38, Centro"
            ],
            instrucoes_especiais=f"""
⚠️ IMPORTANTE: RETORNE **TODOS OS EVENTOS** encontrados no período!
A Casa do Choro pode ter múltiplas apresentações/rodas de choro por mês.

ESTRATÉGIA DE BUSCA MULTI-STEP (execute TODAS as buscas):

1. 🎫 PRIORIDADE MÁXIMA - Plataformas de ingressos:
   - Sympla: "site:sympla.com.br Casa do Choro {month_str} {year_str}"
   - Eventbrite: "site:eventbrite.com.br Casa do Choro Rio"
   - Fever: "site:feverup.com Casa do Choro"

2. 🎭 BUSCA POR PROGRAMAÇÃO COMPLETA:
   - ⚠️ NOTA: Site oficial casadochoro.com.br está instável/quebrado - NÃO usar
   - Busca geral: "Casa do Choro programação completa {month_year_str}"
   - Roda de choro: "roda de choro Casa do Choro Centro Rio {month_str}"

3. 📰 PORTAIS E REDES SOCIAIS:
   - TimeOut Rio: "Casa do Choro {month_year_str}"
   - Instagram: @casadochororj (posts recentes com shows)
   - Veja Rio, O Globo Cultura: agenda Casa do Choro

REGRAS PARA LINKS:
- ✅ PRIORIZAR SEMPRE: Links do Sympla/Eventbrite com ID específico (MAIS CONFIÁVEIS)
- ⚠️ SITE OFICIAL: casadochoro.com.br está instável - NÃO retornar links deste site
- ❌ REJEITAR: Links genéricos sem identificação do evento
- 💡 MELHOR PRÁTICA: Se encontrar evento mas sem link de ingresso, use null no campo link_ingresso

VALIDAÇÃO:
- Data ENTRE {start_date_str} e {end_date_str}
- Confirmar que evento é futuro (não mencionar eventos passados)
- **CRÍTICO:** Priorize Sympla. Site oficial está com problemas técnicos
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 5: Sala Cecília Meireles
        prompt_sala_cecilia = self._build_focused_prompt(
            categoria="Sala Cecília Meireles",
            tipo_busca="venue",
            descricao="Eventos na Sala Cecília Meireles (Lapa, Rio de Janeiro - música clássica e erudita)",
            tipos_evento=[
                "Concertos de música clássica",
                "Música erudita, orquestras",
                "Recitais e apresentações",
                "Eventos de música de câmara"
            ],
            palavras_chave=[
                f"site:salaceciliameireles.rj.gov.br/programacao {month_str} {year_str}",
                f"Sala Cecília Meireles programação completa {month_year_str}",
                f"site:funarj.eleventickets.com/event/ Sala Cecília {month_str}",
                f"Festival Internacional de Piano Sala Cecília {month_str}",
                f"site:sympla.com.br Sala Cecília Meireles {month_str}",
                f"concertos Sala Cecília Meireles {month_str} {year_str}",
                f"Orquestra Petrobras Sinfônica Sala Cecília {month_str}",
                f"site:petrobrasinfonica.com.br Sala Cecília {month_str}"
            ],
            venues_sugeridos=[
                "Sala Cecília Meireles - Lapa"
            ],
            instrucoes_especiais=f"""
⚠️ IMPORTANTE: RETORNE **TODOS OS EVENTOS** encontrados no período, não apenas um ou dois!
A Sala Cecília Meireles costuma ter MÚLTIPLOS eventos por mês (festivais, concertos, recitais).

ESTRATÉGIA DE BUSCA MULTI-STEP (execute TODAS as buscas):

1. 🎭 PRIORIDADE MÁXIMA - SITE OFICIAL (salaceciliameireles.rj.gov.br):
   - Busca direta: "site:salaceciliameireles.rj.gov.br/programacao/ {month_str} {year_str}"
   - ✅ RETORNAR links .gov.br/programacao/{{evento}} - SÃO CONFIÁVEIS
   - Exemplos: salaceciliameireles.rj.gov.br/programacao/07-11-25-orquestra-petrobras/
   - Formato típico: /programacao/DD-MM-AA-nome-evento/

2. 🎫 ALTERNATIVA - FUNARJ (se link .gov.br não disponível):
   - "site:funarj.eleventickets.com/event/ Sala Cecília {{nome_evento}}"
   - RETORNAR apenas se link tiver ID numérico válido
   - ⚠️ REJEITAR links com IDs genéricos como /7 ou /1

3. 🎫 SYMPLA (terceira opção):
   - "site:sympla.com.br Sala Cecília Meireles {month_str} {year_str}"
   - Use se não encontrar nos anteriores

4. 🎵 SITES DE ORQUESTRAS (informação complementar):
   - "site:petrobrasinfonica.com.br Sala Cecília"
   - Pode ter informações sobre eventos específicos

REGRAS PARA LINKS:
- ✅ PRIORIDADE 1: salaceciliameireles.rj.gov.br/programacao/{{evento}}/ (SITE OFICIAL)
- ✅ PRIORIDADE 2: funarj.eleventickets.com/event/{{nome}}/{{id-numérico}}
- ✅ PRIORIDADE 3: sympla.com.br com ID específico
- ⚠️ CUIDADO: Rejeitar links FUNARJ com IDs suspeitos (muito curtos: /1, /7, /10)
- ❌ REJEITAR: Páginas de listagem genéricas (#!/home, /eventos/, etc)

VALIDAÇÃO:
- Data ENTRE {start_date_str} e {end_date_str}
- Confirmar que evento existe (não é apenas menção antiga)
- **CRÍTICO:** Priorize FUNARJ (sistema oficial). Links .gov.br sempre devem ser null
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 6: Teatro Municipal
        prompt_teatro_municipal = self._build_focused_prompt(
            categoria="Teatro Municipal do Rio de Janeiro",
            tipo_busca="venue",
            descricao="Eventos no Teatro Municipal do Rio de Janeiro (Centro - óperas, balés, concertos)",
            tipos_evento=[
                "Óperas e apresentações líricas",
                "Balés clássicos e contemporâneos",
                "Concertos da Orquestra Sinfônica",
                "Eventos culturais especiais"
            ],
            palavras_chave=[
                f"Teatro Municipal Rio programação completa {month_year_str}",
                f"site:sympla.com.br Teatro Municipal {month_str}",
                f"site:feverup.com/m/ Teatro Municipal {month_str}",
                f"site:feverup.com/pt/rio-de-janeiro/venue/theatro-municipal-do-rio-de-janeiro",
                f"site:theatromunicipal.rj.gov.br programação {month_str}",
                f"Madama Butterfly Teatro Municipal {month_str}",
                f"ópera balé Teatro Municipal Rio {month_year_str}",
                "Concerto França-Brasil Teatro Municipal"
            ],
            venues_sugeridos=[
                "Teatro Municipal do Rio de Janeiro - Centro"
            ],
            instrucoes_especiais=f"""
⚠️ IMPORTANTE: RETORNE **TODOS OS EVENTOS** encontrados no período!
Teatro Municipal tem programação variada: óperas, balés, concertos.

ESTRATÉGIA DE BUSCA MULTI-STEP (execute TODAS as buscas):

1. 🎫 PRIORIDADE MÁXIMA - Fever com IDs específicos:
   - Página do venue: "site:feverup.com/pt/rio-de-janeiro/venue/theatro-municipal-do-rio-de-janeiro"
   - Links com IDs: "site:feverup.com/m/ Teatro Municipal {{nome_evento}}"
   - RETORNAR links formato: feverup.com/m/{{número}} (ex: /m/378286)
   - Exemplos conhecidos:
     * Madama Butterfly: /m/378286
     * Tango Revirado: /m/499698
     * Tarde Lírica: /m/498934

2. 🎫 Sympla (alternativa):
   - "site:sympla.com.br Teatro Municipal {month_str} {year_str}"

3. 🏛️ SITE OFICIAL (apenas informação):
   - "site:theatromunicipal.rj.gov.br programação {month_str} {year_str}"
   - ⚠️ Links .gov.br frequentemente dão 404 - use apenas para informação

4. 🎭 EVENTOS CONHECIDOS EM NOVEMBRO (busque especificamente no Fever):
   - "feverup.com/m/ Madama Butterfly Teatro Municipal"
   - "feverup.com/m/ França-Brasil Teatro Municipal"
   - "feverup.com/m/ Negro Spirituals Teatro Municipal"
   - "feverup.com/m/ Ballet Frida Teatro Municipal"

REGRAS PARA LINKS:
- ✅ PRIORIZAR: Links Fever formato /m/{{id}} (ex: feverup.com/m/378286)
- ✅ ACEITAR: Links Sympla com ID específico
- ⚠️ CUIDADO: Links .gov.br - apenas se não houver alternativa Fever/Sympla
- ❌ REJEITAR: Links genéricos sem ID do evento

VALIDAÇÃO:
- Data ENTRE {start_date_str} e {end_date_str}
- Confirmar que evento existe e não é apenas menção antiga
- Se encontrar evento mas link .gov.br parece incerto, busque no Sympla/Fever
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 7: Artemis - Torrefação Artesanal e Cafeteria
        prompt_artemis = self._build_focused_prompt(
            categoria="Artemis - Torrefação Artesanal e Cafeteria",
            tipo_busca="venue",
            descricao="Cursos, workshops e eventos sobre café na Artemis (cursos de barista, degustações, talks sobre café)",
            tipos_evento=[
                "Cursos de barista e métodos de preparo",
                "Workshops de degustação e cupping",
                "Talks e palestras sobre café especial",
                "Eventos de lançamento de cafés",
                "Cursos de torra artesanal"
            ],
            palavras_chave=[
                f"Artemis café {month_year_str}",
                "Artemis curso barista Rio",
                "workshop café Artemis",
                "degustação café Artemis",
                "cupping Artemis Rio",
                "curso café especial Rio"
            ],
            venues_sugeridos=[
                "Artemis Torrefação Artesanal e Cafeteria"
            ],
            instrucoes_especiais="""
ESTRATÉGIA DE BUSCA MULTI-STEP:
1. Site oficial e redes sociais do Artemis (@artemiscafe, Instagram/Facebook)
2. Sympla/Eventbrite: "Artemis café", "curso barista"
3. Portais de gastronomia: cursos de café Rio
4. Busca por: "workshop café especialidade Rio"
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 8: CCBB Rio (Centro Cultural Banco do Brasil)
        prompt_ccbb = self._build_focused_prompt(
            categoria="CCBB Rio - Centro Cultural Banco do Brasil",
            tipo_busca="venue",
            descricao="Eventos culturais no CCBB Rio (Centro - exposições, teatro, cinema, música)",
            tipos_evento=[
                "Exposições de arte",
                "Espetáculos teatrais",
                "Shows e concertos",
                "Sessões de cinema",
                "Palestras e debates culturais"
            ],
            palavras_chave=[
                f"CCBB Rio programação {month_year_str}",
                f"Centro Cultural Banco do Brasil agenda {month_str}",
                f"site:bb.com.br/cultura CCBB Rio {month_str}",
                f"site:sympla.com.br CCBB Rio {month_str}",
                f"exposição CCBB Rio {month_year_str}"
            ],
            venues_sugeridos=[
                "CCBB Rio - Centro Cultural Banco do Brasil, Rua Primeiro de Março, 66, Centro"
            ],
            instrucoes_especiais=f"""
ESTRATÉGIA DE BUSCA:
1. Site oficial CCBB: "site:bb.com.br/cultura ccbbrj programacao {month_str}"
2. Plataformas: Sympla, Fever, Eventbrite
3. Portais culturais: TimeOut Rio, O Globo Cultura

FOCO: Eventos com programação confirmada no período
✅ RETORNAR: Links específicos de Sympla/Fever/site oficial
❌ REJEITAR: Links genéricos de homepage
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 9: Oi Futuro
        prompt_oi_futuro = self._build_focused_prompt(
            categoria="Oi Futuro",
            tipo_busca="venue",
            descricao="Eventos culturais e tecnológicos no Oi Futuro (Ipanema e Flamengo)",
            tipos_evento=[
                "Exposições de arte e tecnologia",
                "Instalações interativas",
                "Shows e performances",
                "Oficinas e workshops",
                "Cinema e videoarte"
            ],
            palavras_chave=[
                f"Oi Futuro programação {month_year_str}",
                f"site:oifuturo.org.br agenda {month_str}",
                f"Oi Futuro Ipanema {month_str}",
                f"Oi Futuro Flamengo {month_str}",
                f"exposição Oi Futuro {month_year_str}"
            ],
            venues_sugeridos=[
                "Oi Futuro Ipanema - Rua Dois de Dezembro, 63",
                "Oi Futuro Flamengo - Rua Dois de Dezembro, 63"
            ],
            instrucoes_especiais=f"""
ESTRATÉGIA DE BUSCA:
1. Site oficial: "site:oifuturo.org.br programacao {month_str}"
2. Busca geral: "Oi Futuro eventos {month_year_str}"
3. Plataformas: Sympla, Eventbrite

NOTA: Oi Futuro tem 2 unidades (Ipanema e Flamengo) - identificar qual!
✅ Eventos gratuitos e pagos
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 10: IMS (Instituto Moreira Salles)
        prompt_ims = self._build_focused_prompt(
            categoria="IMS - Instituto Moreira Salles",
            tipo_busca="venue",
            descricao="Eventos culturais no IMS Rio (fotografia, música, cinema, literatura)",
            tipos_evento=[
                "Exposições de fotografia",
                "Concertos e shows",
                "Sessões de cinema",
                "Palestras e debates",
                "Lançamentos de livros"
            ],
            palavras_chave=[
                f"IMS Rio programação {month_year_str}",
                f"Instituto Moreira Salles agenda {month_str}",
                f"site:ims.com.br Rio {month_str}",
                f"exposição IMS Rio {month_year_str}",
                f"concerto IMS {month_str}"
            ],
            venues_sugeridos=[
                "IMS Rio - Instituto Moreira Salles, Rua Marquês de São Vicente, 476, Gávea"
            ],
            instrucoes_especiais=f"""
ESTRATÉGIA DE BUSCA:
1. Site oficial IMS: "site:ims.com.br rio programacao {month_str}"
2. Busca por tipo: "exposição fotografia IMS Rio", "concerto IMS"
3. Plataformas: Sympla (eventos pagos)

FOCO: Eventos culturais de qualidade (fotografia, música erudita, cinema de arte)
✅ Muitos eventos gratuitos
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 11: Parque Lage
        prompt_parque_lage = self._build_focused_prompt(
            categoria="Parque Lage",
            tipo_busca="venue",
            descricao="Eventos culturais e artísticos no Parque Lage (EAV - Escola de Artes Visuais)",
            tipos_evento=[
                "Exposições de arte contemporânea",
                "Performances e intervenções",
                "Concertos ao ar livre",
                "Workshops e oficinas de arte",
                "Eventos de moda e design"
            ],
            palavras_chave=[
                f"Parque Lage eventos {month_year_str}",
                f"EAV Parque Lage programação {month_str}",
                f"site:eavparquelage.rj.gov.br {month_str}",
                f"exposição Parque Lage {month_year_str}",
                f"concerto Parque Lage {month_str}"
            ],
            venues_sugeridos=[
                "Parque Lage - Escola de Artes Visuais, Rua Jardim Botânico, 414, Jardim Botânico"
            ],
            instrucoes_especiais=f"""
ESTRATÉGIA DE BUSCA:
1. Site oficial EAV: "site:eavparquelage.rj.gov.br programacao {month_str}"
2. Busca geral: "Parque Lage eventos {month_year_str}"
3. Plataformas: Sympla, Eventbrite
4. Redes sociais: @eavparquelage Instagram

FOCO: Arte contemporânea, performances, eventos ao ar livre no jardim histórico
✅ Eventos gratuitos e pagos
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 12: CCJF (Centro Cultural Justiça Federal)
        prompt_ccjf = self._build_focused_prompt(
            categoria="CCJF - Centro Cultural Justiça Federal",
            tipo_busca="venue",
            descricao="Eventos culturais no CCJF (Centro - exposições, música, teatro)",
            tipos_evento=[
                "Exposições de arte",
                "Concertos de música clássica",
                "Espetáculos teatrais",
                "Palestras e debates",
                "Cinema"
            ],
            palavras_chave=[
                f"CCJF Rio programação {month_year_str}",
                f"Centro Cultural Justiça Federal {month_str}",
                f"site:ccjf.trf2.jus.br programacao {month_str}",
                f"exposição CCJF {month_year_str}",
                f"concerto CCJF Rio {month_str}"
            ],
            venues_sugeridos=[
                "CCJF - Centro Cultural Justiça Federal, Av. Rio Branco, 241, Centro"
            ],
            instrucoes_especiais=f"""
ESTRATÉGIA DE BUSCA:
1. Site oficial: "site:ccjf.trf2.jus.br programacao {month_str}"
2. Busca geral: "CCJF Rio eventos {month_year_str}"
3. Plataformas: Sympla (eventos específicos)

FOCO: Programação cultural variada (arte, música, teatro)
✅ Maioria dos eventos gratuitos
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )


        # MICRO-SEARCH 17: Casa Natura Musical
        prompt_casa_natura = self._build_focused_prompt(
            categoria="Casa Natura Musical",
            tipo_busca="venue",
            descricao="Shows de MPB, bossa nova, jazz e música brasileira de qualidade",
            tipos_evento=[
                "Shows de MPB",
                "Bossa nova",
                "Jazz brasileiro",
                "Música instrumental brasileira"
            ],
            palavras_chave=[
                f"Casa Natura Musical programação {month_year_str}",
                f"site:casanaturamusical.com.br agenda {month_str}",
                f"show Casa Natura {month_year_str}",
                f"site:sympla.com.br Casa Natura {month_str}"
            ],
            venues_sugeridos=[
                "Casa Natura Musical - Shopping Leblon, Av. Afrânio de Melo Franco, 290, Leblon"
            ],
            instrucoes_especiais=f"""
ESTRATÉGIA:
1. Site oficial: "site:casanaturamusical.com.br programacao {month_str}"
2. Sympla: eventos com ingressos
3. FOCO: MPB, bossa nova, jazz brasileiro de qualidade
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 18: MAM Cinema
        prompt_mam_cinema = self._build_focused_prompt(
            categoria="MAM Cinema",
            tipo_busca="venue",
            descricao="Cinema curado do Museu de Arte Moderna - sessões e retrospectivas",
            tipos_evento=[
                "Sessões de cinema de arte",
                "Retrospectivas cinematográficas",
                "Cineclubes",
                "Filmes clássicos e contemporâneos"
            ],
            palavras_chave=[
                f"MAM Cinema Rio programação {month_year_str}",
                f"Cinema MAM agenda {month_str}",
                f"site:mam.rio sessões {month_str}",
                f"cineclube MAM Rio {month_year_str}"
            ],
            venues_sugeridos=[
                "MAM Cinema - Museu de Arte Moderna, Av. Infante Dom Henrique, 85, Parque do Flamengo"
            ],
            instrucoes_especiais=f"""
ESTRATÉGIA:
1. Site MAM: "site:mam.rio cinema programacao {month_str}"
2. Cinema curado, retrospectivas, sessões especiais
3. Preços acessíveis, muitas sessões gratuitas
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 19: Theatro Net Rio
        prompt_theatro_net = self._build_focused_prompt(
            categoria="Theatro Net Rio",
            tipo_busca="venue",
            descricao="Teatro comercial - musicais, comédias, dramas",
            tipos_evento=[
                "Musicais",
                "Comédias teatrais",
                "Dramas",
                "Espetáculos teatrais"
            ],
            palavras_chave=[
                f"Theatro Net Rio programação {month_year_str}",
                f"site:theatronetrio.com.br em-cartaz {month_str}",
                f"musical Theatro Net {month_year_str}",
                f"site:ingresso.com Theatro Net Rio {month_str}"
            ],
            venues_sugeridos=[
                "Theatro Net Rio - Rua Siqueira Campos, 143, Copacabana"
            ],
            instrucoes_especiais=f"""
ESTRATÉGIA:
1. Site oficial: "site:theatronetrio.com.br em-cartaz"
2. Ingresso.com: "site:ingresso.com Theatro Net Rio"
3. FOCO: Musicais e espetáculos de longa temporada
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 20: CCBB Teatro e Cinema (expansão)
        prompt_ccbb_teatro_cinema = self._build_focused_prompt(
            categoria="CCBB Teatro e Cinema",
            tipo_busca="venue",
            descricao="Programação de teatro e cinema do CCBB (além de exposições)",
            tipos_evento=[
                "Espetáculos teatrais",
                "Sessões de cinema",
                "Peças de teatro",
                "Filmes e documentários"
            ],
            palavras_chave=[
                f"CCBB Rio teatro programação {month_year_str}",
                f"CCBB Rio cinema {month_str}",
                f"site:bb.com.br/cultura ccbbrj teatro {month_str}",
                f"site:ingressos.ccbb.com.br teatro {month_str}"
            ],
            venues_sugeridos=[
                "CCBB Rio - Teatro I, II, III e Cinema - R. Primeiro de Março, 66, Centro"
            ],
            instrucoes_especiais=f"""
ESTRATÉGIA:
1. Site CCBB: "site:bb.com.br/cultura ccbbrj programacao teatro cinema"
2. Sistema de ingressos: "site:ingressos.ccbb.com.br"
3. FOCO: Teatro e cinema (exposições já cobertas)
✅ Muitos eventos gratuitos
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        logger.info(f"{self.log_prefix} ✅ 21 prompts criados com sucesso")

        try:
            # ═══════════════════════════════════════════════════════════
            # EXECUÇÃO PARALELA DAS 21 MICRO-SEARCHES
            # ═══════════════════════════════════════════════════════════
            logger.info(f"{self.log_prefix} Executando 21 micro-searches em paralelo...")

            # Executar as 21 buscas em paralelo (8 categorias + 13 venues)
            results = await asyncio.gather(
                self._run_micro_search(prompt_jazz, "Jazz"),
                self._run_micro_search(prompt_comedia, "Comédia"),
                self._run_micro_search(prompt_outdoor, "Outdoor/Parques"),
                self._run_micro_search(prompt_musica_classica, "Música Clássica"),
                self._run_micro_search(prompt_teatro, "Teatro"),
                self._run_micro_search(prompt_cinema, "Cinema"),
                self._run_micro_search(prompt_feira_gastronomica, "Feira Gastronômica"),
                self._run_micro_search(prompt_feira_artesanato, "Feira de Artesanato"),
                self._run_micro_search(prompt_casa_choro, "Casa do Choro"),
                self._run_micro_search(prompt_sala_cecilia, "Sala Cecília Meireles"),
                self._run_micro_search(prompt_teatro_municipal, "Teatro Municipal"),
                self._run_micro_search(prompt_artemis, "Artemis"),
                self._run_micro_search(prompt_ccbb, "CCBB Rio"),
                self._run_micro_search(prompt_oi_futuro, "Oi Futuro"),
                self._run_micro_search(prompt_ims, "IMS"),
                self._run_micro_search(prompt_parque_lage, "Parque Lage"),
                self._run_micro_search(prompt_ccjf, "CCJF"),
                self._run_micro_search(prompt_casa_natura, "Casa Natura Musical"),
                self._run_micro_search(prompt_mam_cinema, "MAM Cinema"),
                self._run_micro_search(prompt_theatro_net, "Theatro Net Rio"),
                self._run_micro_search(prompt_ccbb_teatro_cinema, "CCBB Teatro/Cinema"),
            )

            # Desempacotar resultados
            (
                result_jazz,
                result_comedia,
                result_outdoor,
                result_musica_classica,
                result_teatro,
                result_cinema,
                result_feira_gastronomica,
                result_feira_artesanato,
                result_casa_choro,
                result_sala_cecilia,
                result_teatro_municipal,
                result_artemis,
                result_ccbb,
                result_oi_futuro,
                result_ims,
                result_parque_lage,
                result_ccjf,
                result_casa_natura,
                result_mam_cinema,
                result_theatro_net,
                result_ccbb_teatro_cinema,
            ) = results

            logger.info("✓ Todas as 21 micro-searches concluídas")

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

            # Parse categorias com Pydantic validation
            eventos_jazz = safe_parse_categoria(result_jazz, "Jazz")
            logger.debug(f"Jazz parsed from Perplexity - {len(eventos_jazz)} eventos")

            # ═══════════════════════════════════════════════════════════
            # MERGE: Adicionar eventos Blue Note scrapados do Eventim
            # ═══════════════════════════════════════════════════════════
            if blue_note_scraped:
                logger.info(f"🎫 Adicionando {len(blue_note_scraped)} eventos Blue Note do Eventim scraper...")
                for scraped_event in blue_note_scraped:
                    # Converter para formato EventoCategoria
                    jazz_event = {
                        "titulo": scraped_event["titulo"],
                        "data": scraped_event["data"],
                        "horario": scraped_event["horario"],
                        "local": "Blue Note Rio - Av. Nossa Senhora de Copacabana, 2241, Copacabana, Rio de Janeiro",
                        "preco": "Consultar link",
                        "link_ingresso": scraped_event["link"],
                        "descricao": None,  # Será enriquecido depois
                        "categoria": "Jazz"
                    }
                    # Adicionar à lista de jazz (evitando duplicatas por título)
                    if not any(e.get("titulo", "").lower() == jazz_event["titulo"].lower() for e in eventos_jazz):
                        eventos_jazz.append(jazz_event)
                        logger.debug(f"   ✓ Adicionado: {jazz_event['titulo']}")
                    else:
                        logger.debug(f"   ⏭️  Duplicata ignorada: {jazz_event['titulo']}")

                logger.info(f"✓ Total de eventos Jazz após merge: {len(eventos_jazz)}")

            eventos_comedia = safe_parse_categoria(result_comedia, "Comédia")
            logger.debug(f"Comédia parsed - {len(eventos_comedia)} eventos")

            eventos_outdoor = safe_parse_categoria(result_outdoor, "Outdoor/Parques")
            logger.debug(f"Outdoor/Parques parsed - {len(eventos_outdoor)} eventos")

            eventos_musica_classica = safe_parse_categoria(result_musica_classica, "Música Clássica")
            logger.debug(f"Música Clássica parsed - {len(eventos_musica_classica)} eventos")

            eventos_teatro = safe_parse_categoria(result_teatro, "Teatro")
            logger.debug(f"Teatro parsed - {len(eventos_teatro)} eventos")

            eventos_cinema = safe_parse_categoria(result_cinema, "Cinema")
            logger.debug(f"Cinema parsed - {len(eventos_cinema)} eventos")

            eventos_feira_gastronomica = safe_parse_categoria(result_feira_gastronomica, "Feira Gastronômica")
            logger.debug(f"Feira Gastronômica parsed - {len(eventos_feira_gastronomica)} eventos")

            eventos_feira_artesanato = safe_parse_categoria(result_feira_artesanato, "Feira de Artesanato")
            logger.debug(f"Feira de Artesanato parsed - {len(eventos_feira_artesanato)} eventos")

            # Merge eventos gerais (todas as 8 categorias)
            todos_eventos_gerais = (
                eventos_jazz +
                eventos_comedia +
                eventos_outdoor +
                eventos_musica_classica +
                eventos_teatro +
                eventos_cinema +
                eventos_feira_gastronomica +
                eventos_feira_artesanato
            )

            # Criar estrutura de eventos gerais
            eventos_gerais_merged = {"eventos": todos_eventos_gerais}

            # Parse eventos de venues
            eventos_casa_choro = safe_parse_venue(result_casa_choro, "Casa do Choro")
            logger.debug(f"Casa do Choro parsed - {len(eventos_casa_choro)} eventos")

            eventos_sala_cecilia = safe_parse_venue(result_sala_cecilia, "Sala Cecília Meireles")
            logger.debug(f"Sala Cecília Meireles parsed - {len(eventos_sala_cecilia)} eventos")

            eventos_teatro_municipal = safe_parse_venue(result_teatro_municipal, "Teatro Municipal do Rio de Janeiro")
            logger.debug(f"Teatro Municipal parsed - {len(eventos_teatro_municipal)} eventos")

            eventos_artemis = safe_parse_venue(result_artemis, "Artemis - Torrefação Artesanal e Cafeteria")
            logger.debug(f"Artemis parsed - {len(eventos_artemis)} eventos")

            eventos_ccbb = safe_parse_venue(result_ccbb, "CCBB Rio - Centro Cultural Banco do Brasil")
            logger.debug(f"CCBB Rio parsed - {len(eventos_ccbb)} eventos")

            eventos_oi_futuro = safe_parse_venue(result_oi_futuro, "Oi Futuro")
            logger.debug(f"Oi Futuro parsed - {len(eventos_oi_futuro)} eventos")

            eventos_ims = safe_parse_venue(result_ims, "IMS - Instituto Moreira Salles")
            logger.debug(f"IMS parsed - {len(eventos_ims)} eventos")

            eventos_parque_lage = safe_parse_venue(result_parque_lage, "Parque Lage")
            logger.debug(f"Parque Lage parsed - {len(eventos_parque_lage)} eventos")

            eventos_ccjf = safe_parse_venue(result_ccjf, "CCJF - Centro Cultural Justiça Federal")
            logger.debug(f"CCJF parsed - {len(eventos_ccjf)} eventos")

            eventos_casa_natura = safe_parse_venue(result_casa_natura, "Casa Natura Musical")
            logger.debug(f"Casa Natura Musical parsed - {len(eventos_casa_natura)} eventos")

            eventos_mam_cinema = safe_parse_venue(result_mam_cinema, "MAM Cinema")
            logger.debug(f"MAM Cinema parsed - {len(eventos_mam_cinema)} eventos")

            eventos_theatro_net = safe_parse_venue(result_theatro_net, "Theatro Net Rio")
            logger.debug(f"Theatro Net Rio parsed - {len(eventos_theatro_net)} eventos")

            eventos_ccbb_teatro_cinema = safe_parse_venue(result_ccbb_teatro_cinema, "CCBB Teatro e Cinema")
            logger.debug(f"CCBB Teatro e Cinema parsed - {len(eventos_ccbb_teatro_cinema)} eventos")

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
                "Casa Natura Musical": eventos_casa_natura,
                "MAM Cinema": eventos_mam_cinema,
                "Theatro Net Rio": eventos_theatro_net,
                "CCBB Teatro e Cinema": eventos_ccbb_teatro_cinema,
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

        prompt = f"""MISSÃO CRÍTICA: Encontrar links ESPECÍFICOS de venda/informações para estes {len(events_batch)} eventos no Rio de Janeiro.

EVENTOS:
{chr(10).join(eventos_texto)}

ESTRATÉGIA DE BUSCA OBRIGATÓRIA (siga esta ordem):

Para CADA evento:

1️⃣ **PRIORIDADE MÁXIMA - Site Oficial do Venue**:
   - Blue Note Rio → acesse bluenoterio.com e busque na agenda/programação
   - Teatro Municipal → acesse theatromunicipal.rj.gov.br
   - Sala Cecília Meirelles → acesse salaceliciameireles.com.br
   - Casa do Choro → acesse casadochoro.com.br/agenda
   - Outros venues → busque "[nome venue] agenda programação"

2️⃣ **Plataformas de Ingressos** (use termos EXATOS):
   - Sympla: busque "site:sympla.com.br [titulo evento completo] rio"
   - Ingresso.com: busque "site:ingresso.com [titulo evento completo]"
   - Eventbrite: busque "site:eventbrite.com.br [titulo evento completo]"
   - Bilheteria Digital, Ticket360, Uhuu

3️⃣ **Redes Sociais/Instagram** (último recurso):
   - Busque Instagram oficial do venue com link na bio ou stories
   - Posts recentes sobre o evento específico

CRITÉRIOS DE ACEITAÇÃO (seja RIGOROSO):

✅ ACEITE APENAS:
   - URLs que levam DIRETAMENTE à página do evento específico
   - URLs com ID único, slug do evento, ou data na URL
   - Exemplos válidos:
     * sympla.com.br/evento/nome-evento-123456
     * bluenoterio.com/shows/artista-data-20250115
     * eventbrite.com.br/e/titulo-evento-tickets-789012

❌ REJEITE ABSOLUTAMENTE:
   - Homepages: bluenoterio.com, casadochoro.com.br
   - Páginas de listagem: /agenda, /shows, /eventos, /programacao
   - URLs genéricas sem identificador do evento
   - Links de redes sociais (exceto se for o ÚNICO link disponível)

VALIDAÇÃO FINAL:
Antes de retornar cada link:
1. Confirme que a URL contém elemento único (ID, nome, data)
2. Verifique que não é página genérica
3. Se tiver dúvida, retorne null

FORMATO JSON (sem comentários):
{{
  "1": "https://url-especifica-evento-1.com/..." ou null,
  "2": "https://url-especifica-evento-2.com/..." ou null
}}

⚠️ IMPORTANTE: Prefira retornar null do que um link genérico. Links ruins serão rejeitados na validação.
"""

        try:
            response = self.search_agent.run(prompt)
            content = response.content.strip()

            # Limpar markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # Parse JSON
            links_map = json.loads(content)

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

        # Limpar markdown code blocks e comentários
        def clean_json(data):
            # Remover markdown code blocks
            if "```json" in data:
                data = data.split("```json")[1].split("```")[0].strip()
            elif "```" in data:
                data = data.split("```")[1].split("```")[0].strip()

            # Remover comentários JavaScript (// comentários) linha por linha
            lines = data.split("\n")
            cleaned_lines = []
            for line in lines:
                # Se a linha contém //, remover tudo a partir daí (exceto se estiver dentro de string)
                if "//" in line:
                    # Verificar se está dentro de string
                    in_string = False
                    quote_char = None
                    result = []
                    i = 0
                    while i < len(line):
                        char = line[i]
                        if char in ['"', "'"]:
                            if not in_string:
                                in_string = True
                                quote_char = char
                            elif char == quote_char and (i == 0 or line[i - 1] != "\\"):
                                in_string = False
                                quote_char = None
                            result.append(char)
                        elif char == "/" and i + 1 < len(line) and line[i + 1] == "/" and not in_string:
                            # Comentário encontrado fora de string, parar aqui
                            break
                        else:
                            result.append(char)
                        i += 1
                    line = "".join(result).rstrip()
                cleaned_lines.append(line)

            # Remover linhas vazias
            cleaned_lines = [line for line in cleaned_lines if line.strip()]

            return "\n".join(cleaned_lines)

        data_geral_clean = clean_json(data_geral)
        data_especial_clean = clean_json(data_especial)

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
