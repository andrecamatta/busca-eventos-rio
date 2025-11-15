#!/usr/bin/env python3
"""Script temporário para rodar o crawler DiarioDoRio com logs visíveis."""

import logging
import sys

# Configure logging para mostrar progresso
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Força unbuffered output
sys.stdout.reconfigure(line_buffering=True)

print("=" * 80)
print("INICIANDO CRAWLER DIARIODORIO")
print("=" * 80)

from crawlers.diariodorio_crawler import DiarioDoRioCrawler

crawler = DiarioDoRioCrawler()

print("\nIniciando scraping...")
result = crawler.crawl_and_cache(num_pages=8)

print("\n" + "=" * 80)
print("RESULTADO:")
print(f"  Artigos: {result.get('num_articles', 0)}")
print(f"  Eventos extraídos: {len(result.get('extracted_events', []))}")
print("=" * 80)
