#!/usr/bin/env python3
"""
Script de teste isolado para o scraper da Sala Cecília Meireles.
Valida extração de dados e links de compra de ingresso.
"""
import sys
from datetime import datetime, timedelta

# Configurar SEARCH_CONFIG antes de importar o scraper
import config
config.SEARCH_CONFIG = {
    'start_date': datetime.now(),
    'end_date': datetime.now() + timedelta(days=30)
}

from utils.eventim_scraper import EventimScraper


def test_cecilia_scraper():
    """Testa scraper Sala Cecília Meireles isoladamente."""
    print("=" * 80)
    print("TESTE: Scraper Sala Cecília Meireles")
    print("=" * 80)
    print()

    # Executar scraper
    print("🎼 Executando scraper...")
    eventos = EventimScraper.scrape_cecilia_meireles_events()

    if not eventos:
        print("❌ FALHA: Nenhum evento extraído!")
        return False

    print(f"✅ {len(eventos)} eventos extraídos com sucesso!")
    print()
    print("=" * 80)
    print("DETALHES DOS EVENTOS")
    print("=" * 80)

    # Validação
    all_valid = True
    valid_ticket_links = 0

    for i, evento in enumerate(eventos, 1):
        print(f"\n[{i}] {evento.get('titulo', 'SEM TÍTULO')}")
        print(f"    📅 Data: {evento.get('data', 'N/A')}")
        print(f"    🕐 Horário: {evento.get('horario', 'N/A')}")
        print(f"    🔗 Link: {evento.get('link', 'N/A')}")

        # Validações
        errors = []
        if not evento.get('titulo'):
            errors.append("Título vazio")
        if not evento.get('data'):
            errors.append("Data vazia")
        if not evento.get('horario'):
            errors.append("Horário vazio")
        if not evento.get('link'):
            errors.append("Link vazio")
        elif 'funarj.eleventickets.com' in evento.get('link', ''):
            valid_ticket_links += 1
            print(f"    ✅ Link de compra válido (funarj.eleventickets.com)")
        elif 'salaceciliameireles.rj.gov.br/programacao/' in evento.get('link', ''):
            print(f"    ℹ️  Link informativo (página do evento)")
        else:
            errors.append("Link não é de compra nem de página do evento")

        if errors:
            all_valid = False
            print(f"    ⚠️  Problemas: {', '.join(errors)}")

    print()
    print("=" * 80)
    print("RESUMO DA VALIDAÇÃO")
    print("=" * 80)
    print(f"Total de eventos: {len(eventos)}")
    print(f"Links de compra diretos (funarj.eleventickets.com): {valid_ticket_links}/{len(eventos)}")
    print(f"Taxa de links de compra: {valid_ticket_links/len(eventos)*100:.1f}%")

    if all_valid:
        print("\n✅ TODOS OS EVENTOS PASSARAM NA VALIDAÇÃO BÁSICA")
    else:
        print("\n⚠️  ALGUNS EVENTOS TÊM PROBLEMAS (veja detalhes acima)")

    # Critério de sucesso: pelo menos 80% dos links devem ser de compra
    success = (valid_ticket_links / len(eventos)) >= 0.8 if eventos else False

    if success:
        print("\n🎉 TESTE PASSOU! Scraper está funcionando corretamente.")
        print(f"   {valid_ticket_links}/{len(eventos)} eventos com links de compra diretos")
        return True
    else:
        print(f"\n❌ TESTE FALHOU! Poucos links de compra diretos ({valid_ticket_links}/{len(eventos)})")
        print("   Esperado: pelo menos 80% dos eventos com links funarj.eleventickets.com")
        return False


if __name__ == "__main__":
    success = test_cecilia_scraper()
    sys.exit(0 if success else 1)
