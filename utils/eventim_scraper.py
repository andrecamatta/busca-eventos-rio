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

logger = logging.getLogger(__name__)


class EventimScraper:
    """Scraper para páginas do Eventim que não são indexadas por search engines."""

    @staticmethod
    def _parse_month(month_str: str) -> str:
        """Converte mês abreviado para número."""
        months = {
            'jan': '01', 'fev': '02', 'mar': '03', 'abr': '04',
            'mai': '05', 'jun': '06', 'jul': '07', 'ago': '08',
            'set': '09', 'out': '10', 'nov': '11', 'dez': '12'
        }
        return months.get(month_str.lower()[:3], '01')

    @staticmethod
    def _normalize_time(time_str: str) -> str:
        """Converte formato de hora: '20H00' ou '20h00' → '20:00'."""
        if not time_str:
            return "20:00"

        # Substituir H ou h por :
        normalized = time_str.upper().replace('H', ':').replace('h', ':')

        # Garantir formato HH:MM
        parts = normalized.split(':')
        if len(parts) == 2:
            hour = parts[0].zfill(2)
            minute = parts[1][:2].zfill(2)
            return f"{hour}:{minute}"

        return "20:00"  # Fallback

    @staticmethod
    def _determine_year(month: str, day: str) -> str:
        """Determina o ano do evento baseado no mês/dia."""
        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.month

        event_month = int(month)
        event_day = int(day)

        # Se o mês já passou este ano, usar próximo ano
        if event_month < current_month:
            return str(current_year + 1)
        elif event_month == current_month and event_day < current_date.day:
            return str(current_year + 1)
        else:
            return str(current_year)

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

                    month = EventimScraper._parse_month(month_text)
                    year = EventimScraper._determine_year(month, day)
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
                    horario = EventimScraper._normalize_time(horario_raw)

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

        # Normalizar título para comparação
        def normalize(text: str) -> str:
            import unicodedata
            text = text.lower()
            text = unicodedata.normalize('NFKD', text)
            text = text.encode('ascii', 'ignore').decode('ascii')
            # Remover pontuação
            text = ''.join(c if c.isalnum() or c.isspace() else ' ' for c in text)
            return ' '.join(text.split())

        event_normalized = normalize(event_title)

        # Tentar match exato primeiro
        for scraped in scraped_events:
            scraped_title = scraped.get('titulo', '')
            if normalize(scraped_title) == event_normalized:
                logger.info(f"✓ Match exato: '{event_title}' → {scraped['link']}")
                return scraped['link']

        # Tentar match parcial (palavras-chave principais)
        words = event_normalized.split()
        significant_words = [w for w in words if len(w) > 3][:3]  # Primeiras 3 palavras importantes

        if significant_words:
            for scraped in scraped_events:
                scraped_title_norm = normalize(scraped.get('titulo', ''))
                # Se pelo menos 2 palavras significativas aparecem no título scrapado
                matches = sum(1 for w in significant_words if w in scraped_title_norm)
                if matches >= min(2, len(significant_words)):
                    logger.info(f"✓ Match parcial: '{event_title}' → {scraped['link']}")
                    return scraped['link']

        logger.warning(f"⚠️  Nenhum match para: {event_title}")
        return None
