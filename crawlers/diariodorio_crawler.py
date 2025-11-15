"""
DiarioDoRio Crawler - Stage 1: Pre-crawl and cache
Downloads 8 pages from diariodorio.com/agenda and caches articles for later search.
"""

import json
import logging
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from config import FIRECRAWL_API_KEY

logger = logging.getLogger(__name__)


class DiarioDoRioCrawler:
    """Pre-crawl DiarioDoRio /agenda pages and cache for search stage"""

    BASE_URL = "https://diariodorio.com"
    CACHE_DIR = Path("data/cache")
    CACHE_FILE = "diariodorio_latest.json"
    CACHE_MAX_AGE_HOURS = 96  # 4 dias

    def __init__(self):
        """Initialize Firecrawl API configuration"""
        if not FIRECRAWL_API_KEY:
            raise ValueError("FIRECRAWL_API_KEY not set in environment")

        self.api_key = FIRECRAWL_API_KEY
        self.api_url = "https://api.firecrawl.dev/v2/scrape"
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _scrape_with_retry(self, url: str, max_retries: int = 3) -> Optional[Dict]:
        """Scrape URL with retry logic for rate limiting using Firecrawl API v2"""
        for attempt in range(max_retries):
            try:
                # Use Firecrawl API v2 directly as per playground config
                payload = {
                    "url": url,
                    "onlyMainContent": False,  # Critical: False to get full page content
                    "formats": ["markdown"]
                }

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                response = requests.post(self.api_url, json=payload, headers=headers, timeout=60)

                # Handle rate limiting
                if response.status_code == 429:
                    wait_time = (attempt + 1) * 10
                    logger.warning(f"   Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                # Check for success
                if response.status_code != 200:
                    logger.error(f"   API error {response.status_code}: {response.text[:200]}")
                    return None

                result = response.json()

                # v2 API returns: {success: true, data: {markdown: "...", ...}}
                if not result.get('success'):
                    logger.error(f"   Scraping failed: {result.get('error', 'Unknown error')}")
                    return None

                return result.get('data', {})

            except requests.exceptions.Timeout:
                logger.warning(f"   Timeout on attempt {attempt + 1}, retrying...")
                continue
            except Exception as e:
                logger.error(f"   Error scraping {url}: {e}")
                return None

        logger.error(f"   Failed to scrape {url} after {max_retries} attempts")
        return None

    def _scrape_article(self, title_url_tuple: tuple) -> Optional[Dict]:
        """
        Scrape single article (thread-safe helper for parallel execution).

        Args:
            title_url_tuple: Tuple of (title, url)

        Returns:
            Article dict or None if failed
        """
        title, url = title_url_tuple

        result = self._scrape_with_retry(url)
        if not result or 'markdown' not in result:
            logger.warning(f"   Failed to scrape article: {url}")
            return None

        # Clean and return article
        article_content = self._clean_article_content(result['markdown'])
        return {
            "url": url,
            "title": title,
            "markdown": article_content,
            "scraped_at": datetime.now().isoformat()
        }

    def _extract_article_links(self, markdown: str) -> List[tuple]:
        """
        Extract article links from /agenda page markdown.
        Returns list of (title, url) tuples.
        """
        # Pattern: [Title](url) or [Title](url "tooltip")
        # Capture URL until space or closing paren
        link_pattern = r'\[([^\]]+)\]\((https://diariodorio\.com/[^\s\)"]+)'
        matches = re.findall(link_pattern, markdown)

        # Filter to get only event article links (not navigation, categories, images)
        event_links = []
        for title, link in matches:
            # Skip image markdown syntax
            if title.startswith('!['):
                continue

            # Skip pure number titles
            if title.strip().isdigit():
                continue

            # Skip image file URLs
            if any(link.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']):
                continue

            # Skip comment sections and fragments
            if '#respond' in link or '#comment' in link:
                continue

            # Skip wp-content uploads
            if '/wp-content/' in link:
                continue

            # Parse URL path
            path = link.replace(self.BASE_URL, '').strip('/')
            path_segments = [s for s in path.split('/') if s]

            # Skip short paths (usually categories/pages)
            if len(path) < 20:
                continue

            # Skip known category/tag/author URLs
            if any(skip in link for skip in ['/categoria/', '/tag/', '/author/', '/page/']):
                continue

            # Skip 2-segment category pages like /economia/mercado-imobiliario/
            if len(path_segments) == 2:
                known_categories = [
                    'economia', 'cultura', 'edital', 'educacao', 'esporte',
                    'gastronomia', 'historias-do-rio', 'meio-ambiente', 'politica',
                    'saude', 'seguranca', 'turismo', 'carnaval', 'cidade'
                ]
                if path_segments[0] in known_categories:
                    continue

            # Skip "History and Background" and "Social Responsibility" static pages
            if any(static in link for static in ['/history-and-background', '/social-responsibility']):
                continue

            event_links.append((title, link))

        return event_links

    def _clean_article_content(self, markdown: str) -> str:
        """Clean article markdown using intelligent structure analysis

        DiarioDoRio articles typically have:
        - Navigation menus at top
        - Article title (longest line)
        - Subtitle/lead
        - Body paragraphs
        - "Serviço:" section with event details
        - Related articles/navigation at bottom

        Strategy: Find title, extract until "Serviço:" or related articles section
        """
        if not markdown:
            return ""

        lines = markdown.split('\n')

        # Navigation patterns to skip
        nav_patterns = [
            'Facebook', 'Instagram', 'Twitter', 'Youtube', 'Linkedin', 'RSS',
            '- [Agenda](', '- [Carnaval](', '- [Economia](', '- [Cultura](',
            '- [Últimas notícias](', '- [Colunistas](', 'Diário do Rio',
            'Buscar', '[Search]', '#### ÚLTIMAS NOTÍCIAS', 'O Jornal 100% Carioca',
        ]

        # Step 1: Find article title (look for H1 heading first, then longest line)
        article_start = 0

        # First, try to find H1 heading (# Title)
        for i, line in enumerate(lines[:len(lines)//2]):
            stripped = line.strip()
            # Look for H1 markdown heading
            if stripped.startswith('# ') and len(stripped) > 20:
                article_start = i
                break

        # If no H1 found, fall back to longest substantial line
        if article_start == 0:
            max_length = 0
            for i, line in enumerate(lines[:len(lines)//2]):
                stripped = line.strip()
                # Look for substantial text (likely title) - avoid navigation
                if (len(stripped) > 30 and
                    not any(pat in line for pat in nav_patterns) and
                    not stripped.startswith('- [') and
                    not stripped.startswith('http') and
                    not stripped.startswith('![')):  # Skip images
                    if len(stripped) > max_length:
                        max_length = len(stripped)
                        article_start = i

        # Step 2: Find article end
        article_end = len(lines)

        # Look for "Serviço:" section (marks end of article body)
        for i in range(article_start, len(lines)):
            if lines[i].strip().startswith('Serviço:'):
                # Include Serviço section (useful info), find where it actually ends
                for j in range(i, len(lines)):
                    # End of Serviço = start of related articles or "Foto:"
                    if (lines[j].startswith('### [') or
                        lines[j].strip().startswith('Foto:') or
                        '#### ÚLTIMAS NOTÍCIAS' in lines[j]):
                        article_end = j
                        break
                break

        # If no "Serviço:", look for related articles section
        if article_end == len(lines):
            for i in range(article_start + 10, len(lines)):
                line = lines[i]
                # Detect start of related articles
                if (line.startswith('### [') or '#### ÚLTIMAS NOTÍCIAS' in line):
                    # Count similar patterns
                    related_count = sum(1 for l in lines[i:i+5] if l.startswith('### ['))
                    if related_count >= 2:
                        article_end = i
                        break

        # Step 3: Clean the extracted section
        article_lines = lines[article_start:article_end]
        cleaned_lines = []

        for line in article_lines:
            stripped = line.strip()

            # Skip empty
            if not stripped:
                continue

            # Skip navigation patterns
            if any(pat in line for pat in nav_patterns):
                continue

            # Skip very short lines (likely fragments)
            if len(stripped) < 10:
                continue

            # Skip standalone article links
            if line.startswith('### [') and line.endswith(')'):
                continue

            # Skip image captions alone
            if stripped.startswith('![') and stripped.endswith(')'):
                continue

            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def crawl_and_cache(self, num_pages: int = 8) -> Dict:
        """
        Crawl N pages of /agenda and cache article content.

        Caches article markdown for 4 days to reduce API calls.

        Args:
            num_pages: Number of /agenda pages to crawl (default 8)

        Returns:
            Dict with cache metadata
        """
        logger.info(f"DiarioDoRio Crawler: Starting crawl...")

        # Verificar cache existente
        cached_articles = None
        cache_path = self.CACHE_DIR / self.CACHE_FILE

        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    old_cache = json.load(f)

                # Verificar idade dos artigos
                scraped_at = datetime.fromisoformat(old_cache.get('scraped_at', '2000-01-01'))
                age = datetime.now() - scraped_at

                # Reutilizar artigos se < 4 dias
                if age < timedelta(hours=self.CACHE_MAX_AGE_HOURS):
                    cached_articles = old_cache.get('articles', [])
                    logger.info(f"   Reutilizando {len(cached_articles)} artigos do cache ({age.total_seconds()/3600:.1f}h)")
                else:
                    logger.info(f"   Cache de artigos expirado ({age.total_seconds()/3600:.1f}h > {self.CACHE_MAX_AGE_HOURS}h)")
            except Exception as e:
                logger.warning(f"   Erro ao ler cache: {e}")

        # Step 1: Obter artigos (cache ou baixar novo)
        if cached_articles:
            # Usar artigos do cache
            articles = cached_articles
        else:
            # Baixar novos artigos
            all_article_links = []
            for page_num in range(1, num_pages + 1):
                if page_num == 1:
                    url = f"{self.BASE_URL}/agenda/"
                else:
                    url = f"{self.BASE_URL}/agenda/page/{page_num}/"

                logger.info(f"   Crawling page {page_num}/{num_pages}: {url}")
                result = self._scrape_with_retry(url)

                if not result or 'markdown' not in result:
                    logger.warning(f"   Failed to get markdown from page {page_num}")
                    continue

                # Extract article links
                article_links = self._extract_article_links(result['markdown'])
                logger.info(f"   Found {len(article_links)} article links on page {page_num}")

                # Add to collection (deduplicate by URL)
                existing_urls = {link[1] for link in all_article_links}
                new_links = [link for link in article_links if link[1] not in existing_urls]
                all_article_links.extend(new_links)

            logger.info(f"DiarioDoRio Crawler: Total {len(all_article_links)} unique articles found")

            # Step 2: Scrape articles in parallel (5 concurrent workers)
            logger.info(f"DiarioDoRio Crawler: Scraping articles with 5 parallel workers...")
            articles = []

            with ThreadPoolExecutor(max_workers=5) as executor:
                # Submit all scraping tasks
                futures = {
                    executor.submit(self._scrape_article, link): link
                    for link in all_article_links
                }

                # Collect results as they complete
                for i, future in enumerate(as_completed(futures), 1):
                    link = futures[future]
                    title = link[0]

                    logger.info(f"   [{i}/{len(all_article_links)}] Completed: {title[:60]}...")

                    try:
                        result = future.result()
                        if result:
                            articles.append(result)
                    except Exception as e:
                        logger.error(f"   Exception scraping {link[1]}: {e}")

        # Step 3: Extract events with LLM (process article by article for accurate URL mapping)
        logger.info(f"DiarioDoRio Crawler: Extracting events with LLM (processing {len(articles)} articles)...")
        from utils.llm_extraction import extract_events_batch_with_llm

        extracted_events = []

        # Process articles one by one to ensure each event gets the correct article URL
        for idx, article in enumerate(articles, 1):
            logger.info(f"   Processing article {idx}/{len(articles)}: {article['title'][:60]}...")

            try:
                # Extract events from this single article
                events = extract_events_batch_with_llm([(article['title'], article['markdown'])])

                # Inject article URL as link_referencia for all events from this article
                for event in events:
                    event['link_referencia'] = article['url']
                    event['source'] = 'diariodorio'

                if events:
                    logger.info(f"      → Found {len(events)} event(s)")
                    extracted_events.extend(events)

            except Exception as e:
                logger.error(f"   Error extracting events from article '{article['title']}': {e}")

        logger.info(f"DiarioDoRio Crawler: Extracted {len(extracted_events)} events from {len(articles)} articles")

        # Step 4: Save cache
        cache_data = {
            "scraped_at": datetime.now().isoformat(),
            "num_pages": num_pages,
            "num_articles": len(articles),
            "articles": articles,
            "extracted_events": extracted_events
        }

        cache_path = self.CACHE_DIR / self.CACHE_FILE
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        logger.info(f"DiarioDoRio Crawler: Cached {len(articles)} articles to {cache_path}")
        return cache_data

    @classmethod
    def get_cache_age(cls) -> Optional[timedelta]:
        """Get age of current cache file, or None if doesn't exist"""
        cache_path = cls.CACHE_DIR / cls.CACHE_FILE
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            scraped_at = datetime.fromisoformat(cache_data['scraped_at'])
            age = datetime.now() - scraped_at
            return age
        except Exception as e:
            logger.error(f"Error reading cache age: {e}")
            return None

    @classmethod
    def load_cache(cls) -> Optional[Dict]:
        """Load cached articles, or None if cache doesn't exist/is invalid"""
        cache_path = cls.CACHE_DIR / cls.CACHE_FILE
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            return cache_data
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            return None

    @classmethod
    def should_refresh_cache(cls) -> bool:
        """Check if cache should be refreshed (too old or doesn't exist)"""
        age = cls.get_cache_age()
        if age is None:
            logger.info("DiarioDoRio cache not found, needs refresh")
            return True

        if age > timedelta(hours=cls.CACHE_MAX_AGE_HOURS):
            logger.info(f"DiarioDoRio cache is {age.total_seconds()/3600:.1f}h old (> {cls.CACHE_MAX_AGE_HOURS}h), needs refresh")
            return True

        logger.info(f"DiarioDoRio cache is {age.total_seconds()/3600:.1f}h old, still valid")
        return False


if __name__ == "__main__":
    # Test standalone crawler
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

    crawler = DiarioDoRioCrawler()
    cache_data = crawler.crawl_and_cache(num_pages=8)

    print(f"\n{'='*80}")
    print("CRAWLER TEST COMPLETE")
    print(f"{'='*80}")
    print(f"Pages crawled: {cache_data['num_pages']}")
    print(f"Articles cached: {cache_data['num_articles']}")
    print(f"Cache file: {crawler.CACHE_DIR / crawler.CACHE_FILE}")
