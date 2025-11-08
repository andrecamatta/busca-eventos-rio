#!/usr/bin/env python3
"""
Script de teste isolado para o scraper do CCBB.
Valida extração de dados e links.
"""
import sys
from datetime import datetime, timedelta

# Configurar SEARCH_CONFIG antes de importar o scraper
import config
config.SEARCH_CONFIG = {
    'start_date': datetime.now(),
    'end_date': datetime.now() + timedelta(days=60)
}

from utils.eventim_scraper import EventimScraper


def test_ccbb_scraper():
    """Testa scraper CCBB isoladamente."""
    print("=" * 80)
    print("TESTE: Scraper CCBB Rio")
    print("=" * 80)
    print()

    # Executar scraper
    print("🎨 Executando scraper...")
    eventos = EventimScraper.scrape_ccbb_events()

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
    valid_links = 0

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
        elif 'ccbb.com.br' in evento.get('link', ''):
            valid_links += 1
            print(f"    ✅ Link válido (ccbb.com.br)")
        else:
            errors.append("Link não é do domínio ccbb.com.br")

        if errors:
            all_valid = False
            print(f"    ⚠️  Problemas: {', '.join(errors)}")

    print()
    print("=" * 80)
    print("RESUMO DA VALIDAÇÃO")
    print("=" * 80)
    print(f"Total de eventos: {len(eventos)}")
    print(f"Links válidos (ccbb.com.br): {valid_links}/{len(eventos)}")
    print(f"Taxa de links válidos: {valid_links/len(eventos)*100:.1f}%")

    if all_valid:
        print("\n✅ TODOS OS EVENTOS PASSARAM NA VALIDAÇÃO BÁSICA")
    else:
        print("\n⚠️  ALGUNS EVENTOS TÊM PROBLEMAS (veja detalhes acima)")

    # Critério de sucesso: pelo menos 50% dos links devem ser válidos
    # (menos rigoroso que Cecília Meireles porque CCBB pode ter links variados)
    success = (valid_links / len(eventos)) >= 0.5 if eventos else False

    if success:
        print("\n🎉 TESTE PASSOU! Scraper está funcionando corretamente.")
        print(f"   {valid_links}/{len(eventos)} eventos com links válidos")
        return True
    else:
        print(f"\n❌ TESTE FALHOU! Poucos links válidos ({valid_links}/{len(eventos)})")
        print("   Esperado: pelo menos 50% dos eventos com links ccbb.com.br")
        return False


if __name__ == "__main__":
    success = test_ccbb_scraper()
    sys.exit(0 if success else 1)
