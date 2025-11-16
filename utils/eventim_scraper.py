"""
Scraper para extrair links de eventos do Eventim.
Usado como fallback quando Perplexity não consegue encontrar os links.
"""
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

import config
from utils.date_helpers import DateParser
from utils.text_helpers import normalize_string

logger = logging.getLogger(__name__)


class EventimScraper:
    """Scraper para páginas do Eventim e outros sites que não são indexadas por search engines."""

    @staticmethod
    def scrape_cecilia_meireles_events() -> List[Dict[str, str]]:
        """
        Scrape eventos da Sala Cecília Meireles diretamente do site usando BeautifulSoup.

        Returns:
            Lista de eventos: [{"titulo": str, "data": str, "horario": str, "link": str}, ...]
        """
        url = "https://salaceciliameireles.rj.gov.br/programacao/"

        try:
            logger.info(f"🎼 Scraping Sala Cecília Meireles: {url}")

            # Request HTTP
            headers = {
                "User-Agent": config.USER_AGENT
            }

            response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)

            if response.status_code != 200:
                logger.error(f"❌ Erro HTTP {response.status_code} ao acessar {url}")
                return []

            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            event_divs = soup.find_all('div', class_='event')

            logger.info(f"📄 Encontrados {len(event_divs)} eventos no HTML")

            eventos = []
            start_date = config.SEARCH_CONFIG['start_date']
            end_date = config.SEARCH_CONFIG['end_date']
            max_events = config.MAX_EVENTS_PER_VENUE

            for event_div in event_divs:
                try:
                    # Extrair título: <div class='title'>Título</div>
                    title_elem = event_div.find('div', class_='title')
                    if not title_elem:
                        continue

                    titulo = title_elem.get_text(strip=True)
                    if not titulo:
                        continue

                    # Extrair data: <span class="day">8 nov</span> sáb 17H
                    date_elem = event_div.find('span', class_='day')
                    if not date_elem:
                        continue

                    date_text = date_elem.get_text(strip=True)  # "8 nov"
                    date_parts = date_text.split()
                    if len(date_parts) < 2:
                        continue

                    day = date_parts[0]
                    month_text = date_parts[1]

                    # Parse mês e ano
                    month = DateParser.parse_month(month_text)
                    year = DateParser.determine_year(month, day)
                    data = f"{day.zfill(2)}/{month}/{year}"

                    # Verificar se data está no range
                    try:
                        event_date = datetime.strptime(data, "%d/%m/%Y")
                        if event_date < start_date or event_date > end_date:
                            logger.debug(f"⏭️  Evento fora do range: {data}")
                            continue
                    except ValueError:
                        logger.warning(f"⚠️  Data inválida: {data}")
                        continue

                    # Extrair horário do texto completo da data (ex: "8 nov sáb 17H")
                    date_full_elem = event_div.find('div', class_='date')
                    horario_raw = "20H00"  # Default
                    if date_full_elem:
                        date_full_text = date_full_elem.get_text(strip=True)
                        # Procurar padrão de hora (ex: "17H", "19H30")
                        import re
                        time_match = re.search(r'(\d{1,2}H\d{0,2})', date_full_text)
                        if time_match:
                            horario_raw = time_match.group(1)

                    horario = DateParser.normalize_time(horario_raw)

                    # Extrair link de ingresso com PRIORIDADE para plataformas de venda
                    ticket_link = None
                    PURCHASE_PLATFORMS = ['sympla.com', 'eventim.com', 'eleventickets.com', 'ingressodigital.com']

                    # 1. Buscar TODOS os links no evento
                    all_links = event_div.find_all('a', href=True)

                    # 2. Priorizar plataformas externas de venda (mais confiáveis)
                    for link_elem in all_links:
                        href = link_elem.get('href', '')
                        if any(platform in href.lower() for platform in PURCHASE_PLATFORMS):
                            ticket_link = href if href.startswith('http') else f"https://salaceciliameireles.rj.gov.br{href}"
                            logger.debug(f"✓ Link de compra encontrado ({href.split('/')[2]}): {titulo}")
                            break

                    # 3. Fallback: buscar botão de ingresso (pode ser página interna)
                    if not ticket_link:
                        button_elem = event_div.find('a', class_='button-rounded')
                        if button_elem and button_elem.get('href'):
                            href = button_elem.get('href')
                            ticket_link = href if href.startswith('http') else f"https://salaceciliameireles.rj.gov.br{href}"

                    # 4. Último fallback: qualquer link do evento
                    if not ticket_link:
                        event_link_elem = event_div.find('a', href=True)
                        if event_link_elem:
                            href = event_link_elem.get('href')
                            ticket_link = href if href.startswith('http') else f"https://salaceciliameireles.rj.gov.br{href}"

                    # 5. Garantir URL completa e válida
                    if not ticket_link or ticket_link == url:
                        # Usar página principal como último recurso
                        ticket_link = url

                    # Construir evento
                    evento = {
                        "titulo": titulo,
                        "data": data,
                        "horario": horario,
                        "link": ticket_link or url,
                        "local": "Sala Cecília Meireles - Largo da Lapa, 47 - Lapa, Rio de Janeiro",
                        "venue": "Sala Cecília Meireles",
                    }

                    eventos.append(evento)
                    logger.debug(f"✓ {titulo} - {data} às {horario}")

                    # Limitar eventos por venue
                    if len(eventos) >= max_events:
                        logger.info(f"⚠️  Limite de {max_events} eventos atingido para Sala Cecília Meireles")
                        break

                except Exception as e:
                    logger.warning(f"⚠️  Erro ao processar evento: {e}")
                    continue

            logger.info(f"✅ {len(eventos)} eventos Sala Cecília Meireles extraídos com sucesso")
            return eventos

        except httpx.TimeoutException:
            logger.error(f"⏱️  Timeout ao acessar {url}")
            return []
        except Exception as e:
            logger.error(f"❌ Erro ao scraping Sala Cecília Meireles: {e}")
            return []

    @staticmethod
    def scrape_blue_note_events() -> List[Dict[str, str]]:
        """
        Scrape eventos do Blue Note Rio diretamente do site usando BeautifulSoup.

        Returns:
            Lista de eventos: [{"titulo": str, "data": str, "horario": str, "link": str}, ...]
        """
        url = "https://bluenoterio.com.br/shows/"

        try:
            logger.info(f"🎷 Scraping Blue Note Rio: {url}")

            # Request HTTP
            headers = {
                "User-Agent": config.USER_AGENT
            }

            response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)

            if response.status_code != 200:
                logger.error(f"❌ Erro HTTP {response.status_code} ao acessar {url}")
                return []

            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            articles = soup.find_all('article')

            logger.info(f"📄 Encontrados {len(articles)} articles no HTML")

            eventos = []
            start_date = config.SEARCH_CONFIG['start_date']
            end_date = config.SEARCH_CONFIG['end_date']
            max_events = config.MAX_EVENTS_PER_VENUE

            for article in articles:
                try:
                    # Extrair data: <p class='post-date'><span>08</span>nov</p>
                    date_elem = article.find('p', class_='post-date')
                    if not date_elem:
                        continue

                    day_elem = date_elem.find('span')
                    day = day_elem.get_text(strip=True) if day_elem else None
                    month_text = date_elem.get_text(strip=True).replace(day, '') if day else None

                    if not day or not month_text:
                        continue

                    month = DateParser.parse_month(month_text)
                    year = DateParser.determine_year(month, day)
                    data = f"{day.zfill(2)}/{month}/{year}"

                    # Verificar se data está no range
                    try:
                        event_date = datetime.strptime(data, "%d/%m/%Y")
                        if event_date < start_date or event_date > end_date:
                            logger.debug(f"⏭️  Evento fora do range: {data}")
                            continue
                    except ValueError:
                        logger.warning(f"⚠️  Data inválida: {data}")
                        continue

                    # Extrair horário: <p class='post-time'>20H00</p>
                    time_elem = article.find('p', class_='post-time')
                    horario_raw = time_elem.get_text(strip=True) if time_elem else "20H00"
                    horario = DateParser.normalize_time(horario_raw)

                    # Extrair título: <h2 class="blog-shortcode-post-title entry-title"><a>TÍTULO</a></h2>
                    title_elem = article.find('h2', class_='blog-shortcode-post-title')
                    if not title_elem:
                        continue

                    title_link = title_elem.find('a')
                    titulo = title_link.get_text(strip=True) if title_link else None
                    page_link = title_link.get('href') if title_link else None

                    if not titulo:
                        continue

                    # Garantir URL completa
                    if page_link and not page_link.startswith('http'):
                        page_link = f"https://bluenoterio.com.br{page_link}"

                    # Construir evento
                    evento = {
                        "titulo": titulo,
                        "data": data,
                        "horario": horario,
                        "link": page_link or url,
                        "local": "Blue Note Rio - Av. Atlântica, 1910 - Copacabana, Rio de Janeiro",
                        "venue": "Blue Note Rio",
                    }

                    eventos.append(evento)
                    logger.debug(f"✓ {titulo} - {data} às {horario}")

                    # Limitar eventos por venue
                    if len(eventos) >= max_events:
                        logger.info(f"⚠️  Limite de {max_events} eventos atingido para Blue Note")
                        break

                except Exception as e:
                    logger.warning(f"⚠️  Erro ao processar article: {e}")
                    continue

            logger.info(f"✅ {len(eventos)} eventos Blue Note extraídos com sucesso")
            return eventos

        except httpx.TimeoutException:
            logger.error(f"⏱️  Timeout ao acessar {url}")
            return []
        except Exception as e:
            logger.error(f"❌ Erro ao scraping Blue Note: {e}")
            return []

    @staticmethod
    def scrape_ccbb_events() -> List[Dict[str, str]]:
        """
        Scrape eventos do CCBB Rio diretamente do site usando BeautifulSoup.

        Returns:
            Lista de eventos: [{"titulo": str, "data": str, "horario": str, "link": str}, ...]
        """
        url = "https://ccbb.com.br/rio-de-janeiro/programacao/"

        try:
            logger.info(f"🎨 Scraping CCBB Rio: {url}")

            # Request HTTP
            headers = {
                "User-Agent": config.USER_AGENT
            }

            response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)

            if response.status_code != 200:
                logger.error(f"❌ Erro HTTP {response.status_code} ao acessar {url}")
                return []

            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            eventos = []
            start_date = config.SEARCH_CONFIG['start_date']
            end_date = config.SEARCH_CONFIG['end_date']
            max_events = config.MAX_EVENTS_PER_VENUE

            # Abordagem simplificada: buscar todos os headings (títulos de eventos)
            headings = soup.find_all(['h2', 'h3', 'h4'])
            logger.info(f"📄 Encontrados {len(headings)} headings no HTML")

            processed_titles = set()  # Evitar duplicatas
            import re

            for heading in headings:
                try:
                    titulo = heading.get_text(strip=True)

                    # Filtros básicos de qualidade
                    if not titulo or len(titulo) < 3:
                        continue
                    if titulo.lower() in ['saiba mais', 'ingresso', 'comprar', 'ver mais', 'em cartaz', 'buscar', 'resultados']:
                        continue
                    if titulo in processed_titles:
                        continue

                    # Buscar container pai (div/section) que contém o evento
                    parent = heading.find_parent(['div', 'section', 'article'])
                    if not parent:
                        continue

                    # Buscar data no container pai
                    parent_text = parent.get_text()

                    # Detectar range de datas (exposições de longa duração): "DD/MM/YY a DD/MM/YY"
                    date_range_match = re.search(r'(\d{2}/\d{2}/\d{2,4})\s*a\s*(\d{2}/\d{2}/\d{2,4})', parent_text)

                    if date_range_match:
                        # Usar data de TÉRMINO para exposições de longa duração
                        date_text = date_range_match.group(2)  # Segunda data (término)
                        logger.debug(f"📅 Range detectado para '{titulo}': {date_range_match.group(1)} a {date_text}")
                    else:
                        # Evento pontual - buscar data única
                        date_match = re.search(r'(\d{2}/\d{2}/\d{2,4})', parent_text)
                        if not date_match:
                            logger.debug(f"⏭️  Evento sem data: {titulo}")
                            continue
                        date_text = date_match.group(1)

                    # Normalizar data para DD/MM/YYYY
                    if len(date_text) == 8:  # DD/MM/YY
                        parts = date_text.split('/')
                        year = int(parts[2])
                        if year < 100:
                            year = 2000 + year
                        data = f"{parts[0]}/{parts[1]}/{year}"
                    else:
                        data = date_text

                    # Verificar se data está no range
                    try:
                        event_date = datetime.strptime(data, "%d/%m/%Y")
                        # Para exposições, aceitar se data de término >= hoje (apenas date, sem hora)
                        if event_date.date() < start_date.date():
                            logger.debug(f"⏭️  Evento fora do range (passado): {data}")
                            continue
                        if event_date > end_date:
                            logger.debug(f"⏭️  Evento fora do range (futuro): {data}")
                            continue
                    except ValueError:
                        logger.warning(f"⚠️  Data inválida: {data}")
                        continue

                    # Buscar TODOS os links no container pai
                    all_links = parent.find_all('a', href=True)
                    event_link = url  # Default para página principal
                    sympla_link = None
                    other_links = []

                    # Categorizar links por prioridade
                    for link_elem in all_links:
                        href = link_elem.get('href', '')

                        # Normalizar URL
                        if href.startswith('http'):
                            full_url = href
                        elif href.startswith('/'):
                            full_url = f"https://ccbb.com.br{href}"
                        else:
                            continue

                        # Preferência 1: Sympla
                        if 'sympla.com' in full_url:
                            sympla_link = full_url
                            break  # Sympla encontrado, parar busca
                        # Outros links válidos
                        elif 'ccbb.com.br' in full_url or 'ingressos.ccbb' in full_url:
                            other_links.append(full_url)

                    # Escolher melhor link por prioridade
                    if sympla_link:
                        event_link = sympla_link
                        logger.debug(f"✓ Link Sympla encontrado para: {titulo}")
                    elif other_links:
                        event_link = other_links[0]

                    # Horário: usar padrão 10:00 (horário de abertura do CCBB)
                    horario = "10:00"
                    time_match = re.search(r'(\d{1,2})[hH:](\d{2})', parent_text)
                    if time_match:
                        hora = time_match.group(1).zfill(2)
                        minuto = time_match.group(2)
                        horario = f"{hora}:{minuto}"

                    # Construir evento
                    evento = {
                        "titulo": titulo,
                        "data": data,
                        "horario": horario,
                        "link": event_link,
                        "local": "CCBB Rio - Centro Cultural Banco do Brasil - Rua Primeiro de Março, 66, Centro, Rio de Janeiro",
                        "venue": "CCBB Rio - Centro Cultural Banco do Brasil",
                    }

                    eventos.append(evento)
                    processed_titles.add(titulo)
                    logger.debug(f"✓ {titulo} - {data} às {horario}")

                    # Limitar eventos por venue
                    if len(eventos) >= max_events:
                        logger.info(f"⚠️  Limite de {max_events} eventos atingido para CCBB")
                        break

                except Exception as e:
                    logger.warning(f"⚠️  Erro ao processar heading: {e}")
                    continue

            # ETAPA 2: Scraping profundo de festivais para extrair sessões individuais
            logger.info(f"📽️  Iniciando scraping profundo de festivais...")
            festival_sessions = EventimScraper._scrape_festival_sessions(eventos, start_date, end_date)

            if festival_sessions:
                logger.info(f"✅ {len(festival_sessions)} sessões individuais extraídas de festivais")
                # Substituir eventos de festival pelas sessões individuais
                non_festival_events = [e for e in eventos if not EventimScraper._is_festival(e.get('titulo', ''))]
                eventos = non_festival_events + festival_sessions

            logger.info(f"✅ {len(eventos)} eventos CCBB extraídos com sucesso (com sessões de festivais)")
            return eventos

        except httpx.TimeoutException:
            logger.error(f"⏱️  Timeout ao acessar {url}")
            return []
        except Exception as e:
            logger.error(f"❌ Erro ao scraping CCBB: {e}")
            return []

    @staticmethod
    def _is_festival(titulo: str) -> bool:
        """Detecta se um título é de um festival/mostra."""
        festival_keywords = ['festival', 'mostra', 'temporada', 'série']
        return any(kw in titulo.lower() for kw in festival_keywords)

    @staticmethod
    def _scrape_festival_sessions(eventos: List[Dict], start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Faz scraping profundo de links de festivais para extrair sessões individuais.

        Args:
            eventos: Lista de eventos base (pode conter festivais)
            start_date: Data inicial do range
            end_date: Data final do range

        Returns:
            Lista de sessões individuais extraídas de festivais
        """
        import re
        sessions = []
        headers = {"User-Agent": config.USER_AGENT}

        for evento in eventos:
            titulo = evento.get('titulo', '')
            link = evento.get('link', '')

            # Só processar se for festival e tiver link do sistema de ingressos CCBB
            if not EventimScraper._is_festival(titulo):
                continue
            if 'ingressos.ccbb.com.br' not in link:
                continue

            logger.info(f"🎬 Scraping sessões do festival: {titulo}")

            try:
                response = httpx.get(link, headers=headers, timeout=15.0, follow_redirects=True)
                if response.status_code != 200:
                    logger.warning(f"⚠️  Erro ao acessar festival: {response.status_code}")
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Procurar por sessões/filmes individuais
                # Estratégia: buscar por elementos que contenham data + horário + título
                session_elements = soup.find_all(['div', 'article', 'section'], class_=re.compile(r'sessao|session|filme|movie|event', re.I))

                if not session_elements:
                    # Fallback: buscar qualquer elemento com data e horário
                    session_elements = soup.find_all(['div', 'article'])

                for session_elem in session_elements[:20]:  # Limitar a 20 sessões por festival
                    try:
                        session_text = session_elem.get_text()

                        # Extrair data (formato DD/MM/YYYY ou DD/MM)
                        date_match = re.search(r'(\d{2})/(\d{2})(?:/(\d{4}))?', session_text)
                        if not date_match:
                            continue

                        day = date_match.group(1)
                        month = date_match.group(2)
                        year = date_match.group(3) if date_match.group(3) else str(DateParser.determine_year(month, day))
                        data = f"{day}/{month}/{year}"

                        # Validar data
                        try:
                            event_date = datetime.strptime(data, "%d/%m/%Y")
                            if event_date.date() < start_date.date() or event_date > end_date:
                                continue
                        except ValueError:
                            continue

                        # Extrair horário
                        time_match = re.search(r'(\d{1,2})[hH:](\d{2})', session_text)
                        horario = f"{time_match.group(1).zfill(2)}:{time_match.group(2)}" if time_match else "19:00"

                        # Extrair título da sessão/filme
                        # Procurar por headings ou strong tags
                        session_title_elem = session_elem.find(['h3', 'h4', 'h5', 'strong', 'b'])
                        if session_title_elem:
                            session_title = session_title_elem.get_text(strip=True)
                        else:
                            # Usar primeira linha de texto significativa
                            lines = [l.strip() for l in session_text.split('\n') if len(l.strip()) > 5]
                            session_title = lines[0] if lines else f"Sessão {data}"

                        # Limpar título
                        session_title = re.sub(r'\d{2}/\d{2}(/\d{4})?', '', session_title).strip()
                        session_title = re.sub(r'\d{1,2}[hH:]\d{2}', '', session_title).strip()

                        if not session_title or len(session_title) < 3:
                            session_title = f"Sessão {data}"

                        # Construir título completo: "Nome do Filme - Festival"
                        full_title = f"{session_title} - {titulo}"

                        # Buscar link específico da sessão
                        session_link_elem = session_elem.find('a', href=True)
                        session_link = link  # Default: link do festival

                        if session_link_elem:
                            href = session_link_elem.get('href', '')
                            if href.startswith('http'):
                                session_link = href
                            elif href.startswith('/'):
                                session_link = f"https://ingressos.ccbb.com.br{href}"

                        # Criar evento da sessão
                        session_event = {
                            "titulo": full_title,
                            "data": data,
                            "horario": horario,
                            "link": session_link,
                            "local": "CCBB Rio - Centro Cultural Banco do Brasil - Rua Primeiro de Março, 66, Centro, Rio de Janeiro",
                            "venue": "CCBB Rio - Centro Cultural Banco do Brasil",
                        }

                        sessions.append(session_event)
                        logger.debug(f"  ✓ Sessão: {session_title} - {data} às {horario}")

                    except Exception as e:
                        logger.debug(f"  ⚠️  Erro ao processar sessão: {e}")
                        continue

            except httpx.TimeoutException:
                logger.warning(f"⏱️  Timeout ao acessar festival: {titulo}")
                continue
            except Exception as e:
                logger.warning(f"⚠️  Erro ao fazer scraping do festival '{titulo}': {e}")
                continue

        return sessions

    @staticmethod
    def scrape_teatro_municipal_fever_events() -> List[Dict[str, str]]:
        """
        Scrape eventos do Teatro Municipal via Fever usando JSON-LD estruturado.

        Fonte: https://feverup.com/pt/rio-de-janeiro/venue/theatro-municipal-do-rio-de-janeiro

        Returns:
            Lista de eventos: [{"titulo": str, "data": str, "horario": str, "link": str}, ...]
        """
        url = "https://feverup.com/pt/rio-de-janeiro/venue/theatro-municipal-do-rio-de-janeiro"

        try:
            logger.info(f"🎭 Scraping Teatro Municipal (Fever): {url}")

            # Request HTTP
            headers = {"User-Agent": config.USER_AGENT}
            response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)

            if response.status_code != 200:
                logger.error(f"❌ Erro HTTP {response.status_code} ao acessar {url}")
                return []

            # Parse HTML e extrair JSON-LD
            soup = BeautifulSoup(response.text, 'html.parser')
            json_ld_scripts = soup.find_all('script', type='application/ld+json')

            eventos = []
            start_date = config.SEARCH_CONFIG['start_date']
            end_date = config.SEARCH_CONFIG['end_date']
            max_events = config.MAX_EVENTS_PER_VENUE

            # Buscar JSON-LD do tipo "Place" (venue) que contém array de eventos
            for script in json_ld_scripts:
                try:
                    data = json.loads(script.string)

                    # Verificar se é o JSON-LD do venue (tem array "event")
                    if data.get('@type') == 'Place' and 'event' in data:
                        events_data = data['event']
                        logger.info(f"📄 Encontrados {len(events_data)} eventos no JSON-LD")

                        for event_data in events_data:
                            try:
                                # Extrair dados do evento
                                titulo = event_data.get('name', '').strip()
                                if not titulo:
                                    continue

                                # Parse data ISO 8601: "2025-11-22T17:00:00-03:00"
                                start_date_iso = event_data.get('startDate', '')
                                if not start_date_iso:
                                    continue

                                # Converter para datetime
                                event_date = datetime.fromisoformat(start_date_iso.replace('Z', '+00:00'))

                                # Validar se está no range
                                if event_date.replace(tzinfo=None) < start_date or event_date.replace(tzinfo=None) > end_date:
                                    logger.debug(f"⏭️  Evento fora do range: {event_date.date()}")
                                    continue

                                # Formatar data e horário
                                data_formatted = event_date.strftime("%d/%m/%Y")
                                horario = event_date.strftime("%H:%M")

                                # Extrair link do evento
                                link = event_data.get('url', '')
                                if not link.startswith('http'):
                                    link = f"https://feverup.com{link}"

                                # Construir evento
                                evento = {
                                    "titulo": titulo,
                                    "data": data_formatted,
                                    "horario": horario,
                                    "link": link,
                                    "local": "Theatro Municipal do Rio de Janeiro - Praça Floriano, s/nº - Cinelândia, Rio de Janeiro",
                                    "venue": "Theatro Municipal do Rio de Janeiro",
                                }

                                eventos.append(evento)
                                logger.debug(f"✓ {titulo} - {data_formatted} às {horario}")

                                # Limitar eventos por venue
                                if len(eventos) >= max_events:
                                    logger.info(f"⚠️  Limite de {max_events} eventos atingido para Teatro Municipal")
                                    break

                            except Exception as e:
                                logger.warning(f"⚠️  Erro ao processar evento: {e}")
                                continue

                        # JSON-LD do venue encontrado, parar busca
                        break

                except json.JSONDecodeError as e:
                    logger.debug(f"⚠️  JSON-LD inválido: {e}")
                    continue

            logger.info(f"✅ {len(eventos)} eventos Teatro Municipal extraídos com sucesso (Fever)")
            return eventos

        except httpx.TimeoutException:
            logger.error(f"⏱️  Timeout ao acessar {url}")
            return []
        except Exception as e:
            logger.error(f"❌ Erro ao scraping Teatro Municipal (Fever): {e}")
            return []

    @staticmethod
    def match_event_to_scraped(event_title: str, scraped_events: List[Dict]) -> Optional[str]:
        """
        Tenta fazer match de um evento com os eventos scrapados.

        Args:
            event_title: Título do evento a buscar
            scraped_events: Lista de eventos scrapados

        Returns:
            Link do evento se encontrado, None caso contrário
        """
        if not scraped_events:
            return None

        event_normalized = normalize_string(event_title)

        # Tentar match exato primeiro
        for scraped in scraped_events:
            scraped_title = scraped.get('titulo', '')
            if normalize_string(scraped_title) == event_normalized:
                logger.info(f"✓ Match exato: '{event_title}' → {scraped['link']}")
                return scraped['link']

        # Tentar match parcial (palavras-chave principais)
        words = event_normalized.split()
        significant_words = [w for w in words if len(w) > 3][:3]  # Primeiras 3 palavras importantes

        if significant_words:
            for scraped in scraped_events:
                scraped_title_norm = normalize_string(scraped.get('titulo', ''))
                # Se pelo menos 2 palavras significativas aparecem no título scrapado
                matches = sum(1 for w in significant_words if w in scraped_title_norm)
                if matches >= min(2, len(significant_words)):
                    logger.info(f"✓ Match parcial: '{event_title}' → {scraped['link']}")
                    return scraped['link']

        logger.warning(f"⚠️  Nenhum match para: {event_title}")
        return None
