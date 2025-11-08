"""
Scraper para extrair links de eventos do Eventim.
Usado como fallback quando Perplexity não consegue encontrar os links.
"""
import logging
import json
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class EventimScraper:
    """Scraper para páginas do Eventim que não são indexadas por search engines."""

    @staticmethod
    def scrape_blue_note_events() -> List[Dict[str, str]]:
        """
        Scrape eventos do Blue Note Rio usando Perplexity (não usa scraping direto).

        IMPORTANTE: Esta função foi desativada pois o SearchAgent já busca Blue Note
        via Perplexity Sonar Pro nas micro-searches de Jazz e venues específicos.

        Returns:
            Lista vazia (busca delegada ao SearchAgent)
        """
        logger.info("⚠️  Blue Note scraper desativado - eventos buscados via Perplexity no SearchAgent")
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
