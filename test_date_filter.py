"""Teste para validar filtro crítico de datas."""

from datetime import datetime
from utils.date_helpers import DateParser

def test_date_filter():
    """Testa função de validação de data."""

    print("="*80)
    print("TESTE: Filtro Crítico de Datas")
    print("="*80)

    # Período de teste: 08/11/2025 a 29/11/2025
    start_date = datetime(2025, 11, 8)
    end_date = datetime(2025, 11, 29)

    print(f"\nPeríodo válido: {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}\n")

    # Casos de teste
    test_cases = [
        ("15/11/2025", True, "Data dentro do período"),
        ("08/11/2025", True, "Data no início do período"),
        ("29/11/2025", True, "Data no fim do período"),
        ("01/11/2025", False, "Data anterior ao período"),
        ("05/12/2025", False, "Data posterior ao período"),
        ("15/10/2025", False, "Data muito anterior"),
        ("15/01/2026", False, "Data muito posterior"),
        ("", False, "Data ausente"),
        ("data inválida", False, "Formato inválido"),
    ]

    passed = 0
    failed = 0

    for date_str, expected_valid, description in test_cases:
        result = DateParser.validate_event_date(date_str, start_date, end_date)

        is_valid = result['is_valid']
        reason = result['reason']

        if is_valid == expected_valid:
            status = "[OK]"
            passed += 1
        else:
            status = "[ERRO]"
            failed += 1

        print(f"{status} {description}")
        print(f"     Data: '{date_str}' -> Válido: {is_valid} ({reason})")

    print("\n" + "="*80)
    print(f"RESULTADO: {passed}/{len(test_cases)} testes passaram")
    print("="*80)

    if failed == 0:
        print("\n[SUCESSO] Filtro de datas funcionando corretamente!")
        print("\nPróximo passo: Rodar busca real e verificar logs de filtragem")
        print("Comando: python run_search_agent.py (observe logs com '⚠️  Filtrados')")
        return True
    else:
        print(f"\n[FALHA] {failed} teste(s) falharam")
        return False


if __name__ == "__main__":
    success = test_date_filter()
    exit(0 if success else 1)
