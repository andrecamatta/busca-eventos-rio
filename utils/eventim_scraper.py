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

                    # Extrair link de ingresso: <a class="button button-rounded" href="...">comprar ingressos</a>
                    ticket_link = None
                    ticket_elem = event_div.find('a', class_='button-rounded')
                    if ticket_elem and ticket_elem.get('href'):
                        ticket_link = ticket_elem.get('href')

                    # Se não tiver link de ingresso, usar página do evento
                    if not ticket_link:
                        event_link_elem = event_div.find('a', href=True)
                        if event_link_elem:
                            ticket_link = event_link_elem.get('href')

                    # Garantir URL completa
                    if ticket_link and not ticket_link.startswith('http'):
                        ticket_link = f"https://salaceciliameireles.rj.gov.br{ticket_link}"

                    # Construir evento
                    evento = {
                        "titulo": titulo,
                        "data": data,
                        "horario": horario,
                        "link": ticket_link or url,
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

                    # Buscar link no container pai
                    link_elem = parent.find('a', href=True)
                    event_link = url  # Default para página principal

                    if link_elem:
                        href = link_elem.get('href', '')
                        if href.startswith('http'):
                            event_link = href
                        elif href.startswith('/'):
                            event_link = f"https://ccbb.com.br{href}"

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

            logger.info(f"✅ {len(eventos)} eventos CCBB extraídos com sucesso")
            return eventos

        except httpx.TimeoutException:
            logger.error(f"⏱️  Timeout ao acessar {url}")
            return []
        except Exception as e:
            logger.error(f"❌ Erro ao scraping CCBB: {e}")
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
