"""Agente de retry inteligente para complementar eventos insuficientes."""

import json
import logging
from datetime import datetime
from typing import Any

from config import (
    MIN_EVENTS_THRESHOLD,
    REQUIRED_VENUES,
    SEARCH_CONFIG,
)
from utils.agent_factory import AgentFactory
from utils.json_helpers import clean_json_response

logger = logging.getLogger(__name__)


class RetryAgent:
    """Agente responsável por realizar buscas complementares quando eventos < threshold."""

    def __init__(self):
        self.agent = AgentFactory.create_agent(
            name="Event Retry Agent",
            model_type="search",  # Usar Perplexity Sonar Pro para busca
            description="Agente especializado em buscar eventos complementares quando quantidade inicial é insuficiente",
            instructions=[
                "Analisar gaps nas categorias de eventos encontrados",
                "Identificar eventos rejeitados que podem ser recuperados com mais informações",
                "Realizar buscas complementares específicas",
                "Focar em categorias com poucos ou zero eventos",
            ],
            markdown=True,
        )

    def needs_retry(self, verified_data: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        """Verifica se precisa de retry e retorna análise dos gaps."""
        verified_count = len(verified_data.get("verified_events", []))
        verified_events = verified_data.get("verified_events", [])

        logger.info(f"Verificando threshold: {verified_count} eventos (mínimo: {MIN_EVENTS_THRESHOLD})")

        # Verificar se há eventos dos venues obrigatórios
        missing_required_venues = self._check_required_venues(verified_events)

        # Precisa retry se não atingir o mínimo OU se faltar algum venue obrigatório
        if verified_count >= MIN_EVENTS_THRESHOLD and not missing_required_venues:
            return False, {}

        # Analisar gaps por categoria
        verified_events = verified_data.get("verified_events", [])
        rejected_events = verified_data.get("rejected_events", [])

        categories = {
            "jazz": 0,
            "comedia": 0,
            "outdoor": 0,
            "casa_choro": 0,
            "sala_cecilia": 0,
            "teatro_municipal": 0,
        }

        # Contar eventos aprovados por categoria
        for event in verified_events:
            categoria = event.get("categoria", "").lower()
            if "jazz" in categoria:
                categories["jazz"] += 1
            elif "comédia" in categoria or "stand-up" in categoria:
                categories["comedia"] += 1
            elif "outdoor" in categoria or "ar livre" in categoria:
                categories["outdoor"] += 1
            elif "casa do choro" in str(event.get("local", "")).lower():
                categories["casa_choro"] += 1
            elif "cecília meirelles" in str(event.get("local", "")).lower():
                categories["sala_cecilia"] += 1
            elif "municipal" in str(event.get("local", "")).lower():
                categories["teatro_municipal"] += 1

        # Identificar eventos rejeitados recuperáveis
        recoverable = []
        for event in rejected_events:
            motivo = event.get("motivo_rejeicao", "").lower()
            # Recuperável se rejeitado por: link genérico, falta de info secundária
            if ("link genérico" in motivo or
                "link não específico" in motivo or
                "consultar" in motivo):
                recoverable.append(event)

        analysis = {
            "events_needed": MIN_EVENTS_THRESHOLD - verified_count,
            "categories": categories,
            "recoverable_events": recoverable,
            "gaps": [k for k, v in categories.items() if v == 0],
            "missing_required_venues": missing_required_venues,
        }

        if missing_required_venues:
            logger.warning(f"Venues obrigatórios faltantes: {missing_required_venues}")

        logger.info(f"Análise de gaps: {json.dumps(analysis, indent=2, ensure_ascii=False)}")
        return True, analysis

    def _check_required_venues(self, verified_events: list[dict]) -> list[str]:
        """Verifica se há pelo menos 1 evento de cada venue obrigatório."""
        missing = []

        for venue_key, venue_names in REQUIRED_VENUES.items():
            # Verificar se há pelo menos 1 evento de qualquer variação do nome deste venue
            has_event = False
            for event in verified_events:
                event_venue = str(event.get("local", "")).lower()
                # Verificar se alguma das variações do nome aparece no local do evento
                for venue_name in venue_names:
                    if venue_name.lower() in event_venue:
                        has_event = True
                        break
                if has_event:
                    break

            if not has_event:
                missing.append(venue_key)
                logger.info(f"Venue obrigatório faltante: {venue_key} (variações: {venue_names})")

        return missing

    async def search_complementary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Realiza buscas complementares baseadas na análise de gaps."""
        logger.info("Iniciando buscas complementares...")

        # Preparar variáveis de data dinâmicas
        start_date_str = SEARCH_CONFIG['start_date'].strftime('%d/%m/%Y')
        end_date_str = SEARCH_CONFIG['end_date'].strftime('%d/%m/%Y')
        month_year_str = SEARCH_CONFIG['start_date'].strftime('%B %Y')  # ex: "novembro 2025"
        month_str = SEARCH_CONFIG['start_date'].strftime('%B').lower()  # ex: "novembro"

        gaps = analysis.get("gaps", [])
        events_needed = analysis.get("events_needed", 0)
        categories = analysis.get("categories", {})
        missing_required_venues = analysis.get("missing_required_venues", [])

        # Montar prompt direcionado para gaps
        gap_descriptions = []

        # PRIORIDADE MÁXIMA: Venues obrigatórios faltantes
        if "blue_note" in missing_required_venues:
            gap_descriptions.append(f"""
🎺 BUSCA ULTRA-PRIORITÁRIA: BLUE NOTE RIO (VENUE OBRIGATÓRIO)
- Endereço: Av. Afrânio de Melo Franco, 290 - Leblon, Rio de Janeiro
- Buscar: bluenoterio.com, Instagram @bluenoteriodejaneiro
- Tipos: jazz, blues, MPB, soul, R&B, música instrumental
- Palavras-chave: "Blue Note Rio {month_year_str}", "shows Blue Note Leblon", "jazz Blue Note"
- MÍNIMO: 1-2 eventos (OBRIGATÓRIO)
""")

        if "jazz" in gaps or categories.get("jazz", 0) < 2:
            gap_descriptions.append(f"""
🎺 BUSCA COMPLEMENTAR: JAZZ NO RIO DE JANEIRO
- Buscar ESPECIFICAMENTE: Blue Note Rio, Maze Jazz Club, Clube do Jazz, Jazz nos Fundos, Beco das Garrafas
- Tipos: jazz tradicional, bebop, jazz fusion, bossa nova, jazz contemporâneo, smooth jazz
- Bares com jazz ao vivo: Copacabana Palace, Hotel Fasano, Miranda Bar
- Palavras-chave: "jazz Rio Janeiro {month_year_str}", "shows jazz Copacabana", "jazz ao vivo Zona Sul Rio"
- MÍNIMO: 3-5 eventos de jazz
""")

        if "comedia" in gaps or categories.get("comedia", 0) < 2:
            gap_descriptions.append(f"""
😄 BUSCA COMPLEMENTAR: COMÉDIA E STAND-UP (ADULTO)
- Buscar: peças de comédia, stand-up comedy, humor adulto, improv
- Venues: Estação Net Rio, Teatro Riachuelo, Teatro Clara Nunes, Vivo Rio, Teatro das Artes
- Comediantes conhecidos: Rafael Portugal, Thiago Ventura, Afonso Padilha, Clarice Falcão
- Palavras-chave: "stand-up Rio {month_year_str}", "teatro comédia adulto Rio", "humor Rio shows"
- EXCLUIR: teatro infantil, shows para crianças
- MÍNIMO: 3-5 eventos de comédia
""")

        if "outdoor" in gaps or categories.get("outdoor", 0) < 2:
            gap_descriptions.append(f"""
🌳 BUSCA COMPLEMENTAR: EVENTOS AO AR LIVRE EM FIM DE SEMANA
- Dias: APENAS sábados e domingos entre {start_date_str} e {end_date_str}
- Locais: Aterro do Flamengo, Jockey Club, Marina da Glória, Parque Lage, Jardim Botânico, Quinta da Boa Vista
- Tipos: festivais, shows ao ar livre, feiras culturais, food trucks com música, eventos em parques
- Palavras-chave: "festival Rio fim de semana {month_str}", "evento ao ar livre sábado domingo", "show outdoor Rio"
- MÍNIMO: 2-3 eventos outdoor
""")

        if "casa_choro" in gaps or categories.get("casa_choro", 0) < 2:
            gap_descriptions.append("""
🎶 BUSCA ULTRA-ESPECÍFICA: CASA DO CHORO
- Endereço: Rua da Carioca, 38 - Centro, Rio de Janeiro
- Buscar em: casadochoro.com.br, Instagram @casadochororj, Sympla "Casa do Choro", Eventbrite
- Também buscar: "roda de choro Rio Centro", "choro Rua da Carioca", "escola de choro Rio"
- MÍNIMO: 2-4 eventos
""")

        if "sala_cecilia" in gaps or categories.get("sala_cecilia", 0) == 0 or "sala_cecilia" in missing_required_venues:
            priority = "ULTRA-PRIORITÁRIA (OBRIGATÓRIO)" if "sala_cecilia" in missing_required_venues else "ULTRA-ESPECÍFICA"
            gap_descriptions.append(f"""
🎻 BUSCA {priority}: SALA CECÍLIA MEIRELLES
- Endereço: Largo da Lapa, 47 - Lapa, Rio de Janeiro
- Buscar: salaceliciameireles.com.br, redes sociais oficiais
- Tipos: concertos, música erudita, música de câmara, recitais
- Alternativas de busca: "concertos Lapa Rio", "música clássica Rio {month_str}", "recitais Rio de Janeiro"
- MÍNIMO: 1-2 eventos {'(OBRIGATÓRIO)' if 'sala_cecilia' in missing_required_venues else ''}
""")

        if "teatro_municipal" in gaps or categories.get("teatro_municipal", 0) == 0 or "teatro_municipal" in missing_required_venues:
            priority = "ULTRA-PRIORITÁRIA (OBRIGATÓRIO)" if "teatro_municipal" in missing_required_venues else "ULTRA-ESPECÍFICA"
            gap_descriptions.append(f"""
🎭 BUSCA {priority}: TEATRO MUNICIPAL DO RIO DE JANEIRO
- Endereço: Praça Floriano, s/n - Centro, Rio de Janeiro
- Buscar: theatromunicipal.rj.gov.br, Instagram @theatromunicipalrj
- Tipos: óperas, balés, Orquestra Sinfônica Brasileira (OSB), eventos especiais
- Alternativas: "ópera Rio {month_str}", "ballet Teatro Municipal", "OSB concertos {month_year_str}"
- MÍNIMO: 1-2 eventos {'(OBRIGATÓRIO)' if 'teatro_municipal' in missing_required_venues else ''}
""")

        if not gap_descriptions:
            # Se não há gaps específicos mas ainda falta eventos, buscar genérico
            gap_descriptions.append("""
🔍 BUSCA GERAL COMPLEMENTAR
Busque MAIS eventos culturais no Rio de Janeiro nas categorias: jazz, comédia adulta, eventos ao ar livre fim de semana.
Inclua eventos de teatros, centros culturais, casas de show que não foram cobertos ainda.
""")

        gaps_text = "\n".join(gap_descriptions)

        prompt = f"""
MISSÃO: Encontrar {events_needed} EVENTOS ADICIONAIS para completar o mínimo de {MIN_EVENTS_THRESHOLD} eventos.

PERÍODO: {SEARCH_CONFIG['start_date'].strftime('%d/%m/%Y')} a {SEARCH_CONFIG['end_date'].strftime('%d/%m/%Y')}

SITUAÇÃO ATUAL:
{json.dumps(categories, indent=2, ensure_ascii=False)}

GAPS IDENTIFICADOS (PRIORIDADE MÁXIMA):
{gaps_text}

ESTRATÉGIA DE BUSCA:
1. Focar nas categorias com ZERO ou poucos eventos (gaps acima)
2. Buscar em MÚLTIPLAS fontes por categoria
3. Buscar eventos em dias/horários alternativos
4. Incluir eventos gratuitos e pagos
5. Verificar redes sociais dos venues (muitos eventos só são anunciados lá)

INFORMAÇÕES OBRIGATÓRIAS:
- Título completo do evento
- Data (DD/MM/YYYY)
- Horário
- Local completo (nome + endereço)
- Preço (ou "Gratuito" ou "Consultar no link")
- Link para compra/informações (pode ser link do evento específico OU link do venue com menção ao evento)
- Descrição detalhada

FORMATO DE RETORNO:
{{
  "eventos_complementares": [
    {{
      "categoria": "Jazz|Teatro-Comédia|Outdoor-FimDeSemana|Casa-Choro|Sala-Cecilia|Teatro-Municipal",
      "titulo": "...",
      "data": "DD/MM/YYYY",
      "horario": "...",
      "local": "...",
      "preco": "...",
      "link_ingresso": "...",
      "descricao": "..."
    }}
  ],
  "fontes_consultadas": ["lista de URLs/fontes usadas"],
  "observacoes": "comentários sobre a busca"
}}

OBJETIVO: Encontrar NO MÍNIMO {events_needed} eventos adicionais VÁLIDOS.
"""

        try:
            response = self.agent.run(prompt)
            content = response.content

            # Limpar JSON usando função compartilhada
            cleaned_content = clean_json_response(content)
            complementary_data = json.loads(cleaned_content)

            logger.info(
                f"Busca complementar concluída. "
                f"Eventos encontrados: {len(complementary_data.get('eventos_complementares', []))}"
            )

            return complementary_data

        except Exception as e:
            logger.error(f"Erro na busca complementar: {e}")
            return {
                "eventos_complementares": [],
                "fontes_consultadas": [],
                "observacoes": f"Erro na busca: {str(e)}",
            }

    def analyze_recoverable(self, recoverable_events: list[dict]) -> list[dict]:
        """Analisa eventos rejeitados que podem ser recuperados."""
        if not recoverable_events:
            return []

        logger.info(f"Analisando {len(recoverable_events)} eventos recuperáveis...")

        # Estratégia: se evento foi rejeitado apenas por link genérico mas tem infos completas,
        # podemos tentar "recuperá-lo" adicionando observação
        recovered = []

        for event in recoverable_events:
            # Verificar se tem informações mínimas
            has_title = bool(event.get("titulo") or event.get("titulo_evento"))
            has_date = bool(event.get("data"))
            has_local = bool(event.get("local"))

            if has_title and has_date and has_local:
                # Adicionar observação e marcar como "recuperado"
                event["recuperado"] = True
                event["observacao_recuperacao"] = (
                    "Evento recuperado: informações completas mas link genérico. "
                    "Recomenda-se buscar link específico manualmente se necessário."
                )
                recovered.append(event)

        logger.info(f"Eventos recuperados: {len(recovered)}")
        return recovered
