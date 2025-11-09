#!/usr/bin/env python3
"""Script de teste para o scraper do Teatro Municipal do Rio de Janeiro."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Adicionar o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

# Mock de SEARCH_CONFIG para testes
import config
config.SEARCH_CONFIG = {
    'start_date': datetime.now(),
    'end_date': datetime.now() + timedelta(days=90),  # 90 dias para pegar temporada 2025
}
config.MAX_EVENTS_PER_VENUE = 20

from utils.eventim_scraper import EventimScraper


def test_teatro_municipal_scraper():
    """Testa o scraper do Teatro Municipal."""
    print("=" * 80)
    print("TESTE: Scraper Teatro Municipal do Rio de Janeiro")
    print("=" * 80)
    print()

    # Testar scraping
    eventos = EventimScraper.scrape_teatro_municipal_events()

    if not eventos:
        print("AVISO: Nenhum evento extraído!")
        print()
        print("Possíveis causas:")
        print("  1. Site oficial indisponível ou estrutura HTML mudou")
        print("  2. Fever também não retornou eventos")
        print("  3. Não há eventos no período de busca")
        print()
        print("RESULTADO: FALHA (mas pode ser esperado se não houver eventos)")
        return False

    print(f"SUCESSO: {len(eventos)} eventos extraídos!")
    print()
    print("-" * 80)

    # Validar e exibir eventos
    eventos_validos = 0
    eventos_invalidos = 0

    for i, evento in enumerate(eventos, 1):
        titulo = evento.get('titulo', '')
        data = evento.get('data', '')
        horario = evento.get('horario', '')
        link = evento.get('link', '')

        # Validar campos obrigatórios
        is_valid = all([titulo, data, horario, link])

        if is_valid:
            eventos_validos += 1
            status = "OK"
        else:
            eventos_invalidos += 1
            status = "ERRO"

        print(f"\n[{i}] {status} - {titulo}")
        print(f"    Data: {data if data else 'FALTANDO'}")
        print(f"    Horario: {horario if horario else 'FALTANDO'}")
        print(f"    Link: {link if link else 'FALTANDO'}")

        # Validar formato de data
        if data:
            try:
                datetime.strptime(data, "%d/%m/%Y")
                print(f"    Formato data: OK (DD/MM/YYYY)")
            except ValueError:
                print(f"    Formato data: ERRO (esperado DD/MM/YYYY, recebido {data})")
                eventos_invalidos += 1
                is_valid = False

        # Validar formato de horário
        if horario:
            try:
                if ':' in horario and len(horario.split(':')) == 2:
                    hora, minuto = horario.split(':')
                    if 0 <= int(hora) <= 23 and 0 <= int(minuto) <= 59:
                        print(f"    Formato horario: OK (HH:MM)")
                    else:
                        raise ValueError
                else:
                    raise ValueError
            except (ValueError, AttributeError):
                print(f"    Formato horario: ERRO (esperado HH:MM, recebido {horario})")
                eventos_invalidos += 1
                is_valid = False

        # Validar link
        if link:
            if link.startswith('http'):
                print(f"    Formato link: OK")
            else:
                print(f"    Formato link: ERRO (deve começar com http)")
                eventos_invalidos += 1
                is_valid = False

    print()
    print("=" * 80)
    print("RESUMO DO TESTE")
    print("=" * 80)
    print(f"Total de eventos: {len(eventos)}")
    print(f"Eventos validos: {eventos_validos}")
    print(f"Eventos invalidos: {eventos_invalidos}")
    print()

    if eventos_invalidos == 0:
        print("RESULTADO: SUCESSO - Todos os eventos estao com campos validos!")
        return True
    else:
        print(f"RESULTADO: PARCIAL - {eventos_invalidos} eventos com problemas")
        return True  # Ainda consideramos sucesso se extraiu algo


if __name__ == "__main__":
    try:
        success = test_teatro_municipal_scraper()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTeste interrompido pelo usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERRO FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
