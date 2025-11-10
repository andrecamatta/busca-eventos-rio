"""Teste do scraper do Teatro Municipal via Fever."""

import asyncio
import logging
from utils.eventim_scraper import EventimScraper
from config import SEARCH_CONFIG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_teatro_municipal_fever():
    """Testa o scraper do Teatro Municipal (Fever)."""

    logger.info("=" * 80)
    logger.info("TESTE: Teatro Municipal Fever Scraper")
    logger.info("=" * 80)

    start_date = SEARCH_CONFIG['start_date']
    end_date = SEARCH_CONFIG['end_date']
    logger.info(f"\nPeríodo: {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}\n")

    # Executar scraper
    eventos = EventimScraper.scrape_teatro_municipal_fever_events()

    logger.info("\n" + "=" * 80)
    logger.info(f"RESULTADO: {len(eventos)} eventos encontrados")
    logger.info("=" * 80)

    if eventos:
        logger.info("\nEVENTOS:")
        for i, evento in enumerate(eventos, 1):
            logger.info(f"\n{i}. {evento['titulo']}")
            logger.info(f"   Data: {evento['data']} às {evento['horario']}")
            logger.info(f"   Link: {evento['link']}")
    else:
        logger.warning("\n⚠️  NENHUM EVENTO ENCONTRADO")
        logger.warning("Possíveis causas:")
        logger.warning("  - Site Fever fora do ar")
        logger.warning("  - Estrutura JSON-LD mudou")
        logger.warning("  - Nenhum evento no período configurado")

    # Validações
    logger.info("\n" + "=" * 80)
    logger.info("VALIDAÇÕES:")
    logger.info("=" * 80)

    if eventos:
        # Verificar se todos têm campos obrigatórios
        campos_ok = all(
            evento.get('titulo') and
            evento.get('data') and
            evento.get('horario') and
            evento.get('link')
            for evento in eventos
        )

        if campos_ok:
            logger.info("✅ Todos os eventos têm campos obrigatórios")
        else:
            logger.error("❌ Alguns eventos estão faltando campos")

        # Verificar formato de data (DD/MM/YYYY)
        import re
        datas_ok = all(
            re.match(r'\d{2}/\d{2}/\d{4}', evento.get('data', ''))
            for evento in eventos
        )

        if datas_ok:
            logger.info("✅ Todas as datas estão no formato DD/MM/YYYY")
        else:
            logger.error("❌ Algumas datas estão em formato incorreto")

        # Verificar links
        links_ok = all(
            evento.get('link', '').startswith('http')
            for evento in eventos
        )

        if links_ok:
            logger.info("✅ Todos os links são URLs válidas")
        else:
            logger.error("❌ Alguns links são inválidos")

        # Resumo final
        logger.info("\n" + "=" * 80)
        if campos_ok and datas_ok and links_ok:
            logger.info("✅ TESTE PASSOU - Scraper funcionando corretamente!")
        else:
            logger.error("❌ TESTE FALHOU - Revisar scraper")
    else:
        logger.warning("⚠️  TESTE INCONCLUSIVO - Nenhum evento para validar")

    logger.info("=" * 80)

    return eventos


if __name__ == "__main__":
    test_teatro_municipal_fever()
