"""Agente de retry inteligente para complementar eventos insuficientes."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from config import (
    EVENT_CATEGORIES,
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

    def _is_weekend_event(self, event: dict) -> bool:
        """Verifica se evento ocorre em sábado ou domingo.

        Args:
            event: Dicionário do evento com campo 'data'

        Returns:
            True se evento é sábado ou domingo, False caso contrário
        """
        data_str = event.get("data", "")
        if not data_str:
            return False

        try:
            # Parse data no formato DD/MM/YYYY
            data = datetime.strptime(data_str, "%d/%m/%Y")
            # weekday(): 0=segunda, 1=terça, ..., 5=sábado, 6=domingo
            return data.weekday() in [5, 6]
        except ValueError:
            logger.warning(f"Data inválida no evento: {data_str}")
            return False

    def _check_saturday_coverage(self, verified_events: list[dict]) -> list[str]:
        """Verifica se cada sábado tem pelo menos 1 evento outdoor.

        Args:
            verified_events: Lista de eventos verificados

        Returns:
            Lista de sábados descobertos (formato DD/MM/YYYY)
        """
        from config import SEARCH_CONFIG

        # Listar todos os sábados no intervalo
        start_date = SEARCH_CONFIG["start_date"]
        end_date = SEARCH_CONFIG["end_date"]

        saturdays = []
        current = start_date
        while current <= end_date:
            if current.weekday() == 5:  # 5 = sábado
                saturdays.append(current.strftime("%d/%m/%Y"))
            current += timedelta(days=1)

        # Verificar quais sábados TÊM eventos outdoor
        saturdays_with_outdoor = set()

        for event in verified_events:
            # Verificar se é outdoor
            categoria = event.get("categoria", "").lower()
            if "outdoor" not in categoria and "ar livre" not in categoria:
                continue

            # Verificar se é sábado
            data_str = event.get("data", "")
            if not data_str:
                continue

            try:
                data = datetime.strptime(data_str, "%d/%m/%Y")
                if data.weekday() == 5:  # sábado
                    saturdays_with_outdoor.add(data_str)
            except ValueError:
                continue

        # Retornar sábados SEM eventos outdoor
        saturdays_uncovered = [s for s in saturdays if s not in saturdays_with_outdoor]

        if saturdays_uncovered:
            logger.warning(
                f"⚠️  Sábados SEM eventos outdoor: {len(saturdays_uncovered)}/{len(saturdays)} "
                f"({', '.join(saturdays_uncovered[:3])}...)" if len(saturdays_uncovered) > 3
                else f"⚠️  Sábados SEM eventos outdoor: {', '.join(saturdays_uncovered)}"
            )

        return saturdays_uncovered

    def _check_category_minimums(self, verified_events: list[dict]) -> dict[str, int]:
        """Verifica se categorias atingiram seus mínimos configurados.

        Returns:
            Dict com categorias que não atingiram mínimo: {categoria: faltam}
        """
        categories_missing = {}

        for category_key, category_config in EVENT_CATEGORIES.items():
            min_events = category_config.get("min_events")
            if not min_events:
                continue  # Categoria sem mínimo configurado

            # Mapear nome de config para nome de categoria usado nos eventos
            category_name_map = {
                "jazz": "Jazz",
                "musica_classica": "Música Clássica",
                "teatro": "Teatro",
                "comedia": "Comédia",
                "cinema": "Cinema",
                "feira_gastronomica": "Feira Gastronômica",
                "feira_artesanato": "Feira de Artesanato",
                "outdoor_parques": "Outdoor/Parques",
                "cursos_cafe": "Cursos de Café",
            }

            category_display_name = category_name_map.get(category_key, category_key)

            # Contar eventos desta categoria
            count = sum(
                1 for event in verified_events
                if event.get("categoria") == category_display_name
            )

            if count < min_events:
                categories_missing[category_display_name] = min_events - count
                logger.warning(
                    f"⚠️  Categoria '{category_display_name}': {count}/{min_events} eventos "
                    f"(faltam {min_events - count})"
                )

        return categories_missing

    def needs_retry(self, verified_data: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        """Verifica se precisa de retry e retorna análise dos gaps."""
        verified_events = verified_data.get("verified_events", [])
        total_count = len(verified_events)

        # MUDANÇA: Contar apenas eventos de sábado/domingo
        weekend_events = [e for e in verified_events if self._is_weekend_event(e)]
        weekend_count = len(weekend_events)
        weekday_count = total_count - weekend_count

        logger.info(f"Verificando threshold: {weekend_count} eventos de fim de semana (mínimo: {MIN_EVENTS_THRESHOLD})")
        logger.info(f"Total de eventos: {total_count} ({weekday_count} em dias de semana serão ignorados para threshold)")

        # Verificar se há eventos dos venues obrigatórios
        missing_required_venues = self._check_required_venues(verified_events)

        # Verificar cobertura de outdoor por sábado
        saturdays_uncovered = self._check_saturday_coverage(verified_events)

        # Verificar se categorias atingiram seus mínimos
        categories_missing = self._check_category_minimums(verified_events)

        # Precisa retry se:
        # 1. Não atingir mínimo de eventos de fim de semana, OU
        # 2. Faltar venue obrigatório, OU
        # 3. Algum sábado sem evento outdoor, OU
        # 4. Alguma categoria não atingiu seu mínimo configurado
        if (weekend_count >= MIN_EVENTS_THRESHOLD and
            not missing_required_venues and
            not saturdays_uncovered and
            not categories_missing):
            return False, {}

        # Analisar gaps por categoria (para backwards compatibility do prompt)
        rejected_events = verified_data.get("rejected_events", [])

        categories = {
            "jazz": 0,
            "musica_classica": 0,
            "comedia": 0,
            "outdoor": 0,
            "teatro": 0,
            "cinema": 0,
            "feira_gastronomica": 0,
            "feira_artesanato": 0,
            "casa_choro": 0,
            "sala_cecilia": 0,
            "teatro_municipal": 0,
        }

        # Contar eventos aprovados por categoria (atualizado para categorias granulares)
        for event in verified_events:
            categoria = event.get("categoria", "")
            if categoria == "Jazz":
                categories["jazz"] += 1
            elif categoria == "Música Clássica":
                categories["musica_classica"] += 1
            elif categoria == "Comédia":
                categories["comedia"] += 1
            elif categoria == "Outdoor/Parques":
                categories["outdoor"] += 1
            elif categoria == "Teatro":
                categories["teatro"] += 1
            elif categoria == "Cinema":
                categories["cinema"] += 1
            elif categoria == "Feira Gastronômica":
                categories["feira_gastronomica"] += 1
            elif categoria == "Feira de Artesanato":
                categories["feira_artesanato"] += 1

            # Venues (verificar local)
            local_lower = str(event.get("local", "")).lower()
            if "casa do choro" in local_lower:
                categories["casa_choro"] += 1
            elif "cecília meirelles" in local_lower:
                categories["sala_cecilia"] += 1
            elif "municipal" in local_lower:
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
            "events_needed": MIN_EVENTS_THRESHOLD - weekend_count,
            "categories": categories,
            "categories_missing": categories_missing,  # {categoria: faltam}
            "recoverable_events": recoverable,
            "gaps": [k for k, v in categories.items() if v == 0],
            "missing_required_venues": missing_required_venues,
            "saturdays_uncovered": saturdays_uncovered,
        }

        if missing_required_venues:
            logger.warning(f"Venues obrigatórios faltantes: {missing_required_venues}")

        if saturdays_uncovered:
            logger.warning(f"⚠️  {len(saturdays_uncovered)} sábados sem outdoor: {', '.join(saturdays_uncovered)}")

        if categories_missing:
            logger.warning(f"⚠️  Categorias abaixo do mínimo: {categories_missing}")

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
        categories_missing = analysis.get("categories_missing", {})  # {categoria: faltam}
        missing_required_venues = analysis.get("missing_required_venues", [])

        # Montar prompt direcionado para gaps
        gap_descriptions = []

        # PRIORIDADE ALTÍSSIMA: Categorias abaixo do mínimo configurado
        if "Jazz" in categories_missing:
            faltam = categories_missing["Jazz"]
            gap_descriptions.append(f"""
🚨 CATEGORIA ABAIXO DO MÍNIMO: JAZZ (FALTAM {faltam} EVENTOS)
- Mínimo configurado: {EVENT_CATEGORIES['jazz']['min_events']} eventos
- Atual: {categories.get('jazz', 0)} eventos
- NECESSÁRIO: Encontrar mais {faltam} eventos de jazz
- Buscar em: Blue Note Rio, Maze Jazz Club, Clube do Jazz, Jazz nos Fundos, bares com jazz ao vivo
- Palavras-chave: "jazz Rio Janeiro {month_year_str}", "shows jazz Copacabana", "jazz ao vivo"
""")

        if "Música Clássica" in categories_missing:
            faltam = categories_missing["Música Clássica"]
            gap_descriptions.append(f"""
🚨 CATEGORIA ABAIXO DO MÍNIMO: MÚSICA CLÁSSICA (FALTAM {faltam} EVENTOS)
- Mínimo configurado: {EVENT_CATEGORIES['musica_classica']['min_events']} eventos
- Atual: {categories.get('musica_classica', 0)} eventos
- NECESSÁRIO: Encontrar mais {faltam} eventos de música clássica
- Buscar em: Sala Cecília Meirelles, Teatro Municipal, OSB, concertos de câmara
- Palavras-chave: "música clássica Rio {month_year_str}", "concerto orquestra", "recital"
""")

        # PRIORIDADE MÁXIMA: Venues obrigatórios faltantes
        if "blue_note" in missing_required_venues:
            gap_descriptions.append(f"""
🎺 BUSCA ULTRA-PRIORITÁRIA: BLUE NOTE RIO (VENUE OBRIGATÓRIO)
- Endereço: Av. Nossa Senhora de Copacabana, 2241 - Copacabana, Rio de Janeiro
- Buscar: bluenoterio.com, Instagram @bluenoteriodejaneiro
- Tipos: jazz, blues, MPB, soul, R&B, música instrumental
- Palavras-chave: "Blue Note Rio {month_year_str}", "shows Blue Note Copacabana", "jazz Blue Note"
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

        # PRIORIDADE: Se há sábados sem outdoor, buscar especificamente
        saturdays_uncovered = analysis.get("saturdays_uncovered", [])
        if saturdays_uncovered:
            saturdays_list = ', '.join(saturdays_uncovered[:5])  # Mostrar até 5
            more_text = f" (e mais {len(saturdays_uncovered) - 5})" if len(saturdays_uncovered) > 5 else ""
            gap_descriptions.append(f"""
🚨 BUSCA ULTRA-PRIORITÁRIA: OUTDOOR NOS SÁBADOS DESCOBERTOS
- FOCO PRINCIPAL: Buscar eventos ao ar livre especificamente para as datas: {saturdays_list}{more_text}
- Locais: Aterro do Flamengo, Jockey Club, Marina da Glória, Parque Lage, Jardim Botânico, Quinta da Boa Vista
- Tipos: festivais, shows ao ar livre, feiras culturais, food trucks com música, eventos em parques
- Palavras-chave: "festival Rio sábado {month_str}", "evento ao ar livre sábado", "show outdoor Rio fim de semana"
- MÍNIMO: Pelo menos 1 evento para CADA sábado descoberto ({len(saturdays_uncovered)} eventos necessários)
""")
        elif "outdoor" in gaps or categories.get("outdoor", 0) < 2:
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

            # Log da resposta bruta para debug
            logger.debug(f"Resposta bruta do RetryAgent (primeiros 500 chars): {content[:500]}")

            # Limpar JSON usando função compartilhada
            cleaned_content = clean_json_response(content)
            complementary_data = json.loads(cleaned_content)

            logger.info(
                f"Busca complementar concluída. "
                f"Eventos encontrados: {len(complementary_data.get('eventos_complementares', []))}"
            )

            # FALLBACK: Se há eventos do Blue Note, tentar scraping Eventim
            self._enhance_blue_note_links(complementary_data, missing_required_venues)

            return complementary_data

        except json.JSONDecodeError as e:
            logger.error(f"Erro ao fazer parse de JSON na busca complementar: {e}")
            logger.error(f"Conteúdo problemático (primeiros 1000 chars): {content[:1000]}")

            # Fallback: tentar extrair eventos manualmente com regex
            logger.warning("Tentando fallback com extração manual de eventos...")
            try:
                # Tentar encontrar padrão de array de eventos mesmo sem JSON válido
                import re
                eventos_pattern = r'"titulo":\s*"([^"]+)".*?"data":\s*"([^"]+)".*?"local":\s*"([^"]+)"'
                matches = re.findall(eventos_pattern, content, re.DOTALL)

                if matches:
                    logger.info(f"Fallback encontrou {len(matches)} possíveis eventos no texto")
                    # Retornar estrutura vazia mas com observação sobre o problema
                    return {
                        "eventos_complementares": [],
                        "fontes_consultadas": [],
                        "observacoes": f"Erro no formato JSON. Perplexity retornou texto não estruturado. {len(matches)} eventos detectados mas não parseados.",
                    }
            except Exception as fallback_error:
                logger.error(f"Fallback também falhou: {fallback_error}")

            return {
                "eventos_complementares": [],
                "fontes_consultadas": [],
                "observacoes": f"Erro ao fazer parse de JSON: {str(e)}",
            }

        except Exception as e:
            logger.error(f"Erro inesperado na busca complementar: {e}")
            logger.error(f"Resposta bruta: {content[:500] if 'content' in locals() else 'N/A'}")
            return {
                "eventos_complementares": [],
                "fontes_consultadas": [],
                "observacoes": f"Erro na busca: {str(e)}",
            }

    def _enhance_blue_note_links(self, complementary_data: dict, missing_required_venues: list[str]) -> None:
        """
        Melhora links de eventos do Blue Note usando scraping Eventim quando necessário.

        Args:
            complementary_data: Dados dos eventos complementares (será modificado in-place)
            missing_required_venues: Lista de venues obrigatórios faltantes
        """
        if "blue_note" not in missing_required_venues:
            return

        eventos = complementary_data.get("eventos_complementares", [])
        if not eventos:
            return

        # Filtrar apenas eventos do Blue Note
        blue_note_events = [
            e for e in eventos
            if "blue note" in str(e.get("local", "")).lower()
        ]

        if not blue_note_events:
            return

        # Verificar se algum tem link genérico
        has_generic_links = any(
            not e.get("link_ingresso") or
            "bluenoterio.com.br/shows" in str(e.get("link_ingresso", ""))
            for e in blue_note_events
        )

        if not has_generic_links:
            logger.info("✓ Eventos do Blue Note já têm links específicos")
            return

        logger.info("🔍 Detectado: eventos Blue Note com links genéricos. Iniciando scraping Eventim...")

        try:
            from utils.eventim_scraper import EventimScraper

            # Realizar scraping
            scraped_events = EventimScraper.scrape_blue_note_events()

            if not scraped_events:
                logger.warning("⚠️  Scraping Eventim não retornou eventos")
                return

            logger.info(f"✓ Scraping encontrou {len(scraped_events)} eventos no Eventim")

            # Fazer match e atualizar links
            improved_count = 0
            for event in blue_note_events:
                if event.get("link_ingresso") and "eventim.com.br/artist/blue-note-rio/" in event["link_ingresso"]:
                    continue  # Já tem link específico

                # Tentar match
                titulo = event.get("titulo", "")
                matched_link = EventimScraper.match_event_to_scraped(titulo, scraped_events)

                if matched_link:
                    event["link_ingresso"] = matched_link
                    improved_count += 1
                    logger.info(f"✓ Link atualizado para '{titulo}': {matched_link}")

            if improved_count > 0:
                logger.info(f"✅ {improved_count}/{len(blue_note_events)} eventos Blue Note tiveram links melhorados via scraping")
            else:
                logger.warning("⚠️  Nenhum match encontrado entre eventos Perplexity e scraping Eventim")

        except ImportError as e:
            logger.error(f"❌ Erro ao importar EventimScraper: {e}")
        except Exception as e:
            logger.error(f"❌ Erro no scraping/matching Eventim: {e}")

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
