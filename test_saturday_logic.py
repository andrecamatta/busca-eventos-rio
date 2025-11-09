"""Teste: Lógica de cálculo de sábados e consolidação de resultados."""

import sys
from datetime import datetime, timedelta

# Fix encoding para Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')


def test_get_saturdays():
    """Testa cálculo de sábados no período."""
    print("=" * 80)
    print("TESTE 1: Cálculo de Sábados")
    print("=" * 80)

    # Simular período de 30 dias a partir de hoje
    start_date = datetime.now()
    end_date = start_date + timedelta(days=30)

    print(f"\nPeríodo: {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}")

    # Lógica copiada do search_agent.py
    saturdays = []
    current = start_date

    while current <= end_date:
        if current.weekday() == 5:  # 5 = sábado
            saturdays.append({
                "date": current,
                "date_str": current.strftime("%d/%m/%Y")
            })
        current += timedelta(days=1)

    print(f"\n✓ Encontrados {len(saturdays)} sábados:")
    for i, saturday in enumerate(saturdays, 1):
        weekday_name = saturday["date"].strftime("%A")
        print(f"   {i}. {saturday['date_str']} ({weekday_name})")

    # Validar que todos são realmente sábados
    all_saturdays = all(s["date"].weekday() == 5 for s in saturdays)
    print(f"\n✓ Todos são sábados: {all_saturdays}")

    if not all_saturdays:
        print("❌ ERRO: Nem todos os dias são sábados!")
        return False

    if len(saturdays) < 3:
        print("⚠️  AVISO: Menos de 3 sábados no período (esperado ~4-5)")

    print("\n" + "=" * 80)
    print("✅ TESTE 1: PASSOU")
    print("=" * 80)
    return True


def test_results_unpacking():
    """Testa desempacotamento de resultados com número dinâmico de sábados."""
    print("\n" + "=" * 80)
    print("TESTE 2: Desempacotamento de Resultados")
    print("=" * 80)

    # Simular resultados com diferentes números de sábados
    for num_saturdays in [3, 4, 5]:
        print(f"\n--- Testando com {num_saturdays} sábados ---")

        # Simular resultados
        # Formato: [jazz, comedia, musica_classica, cinema, feira_gast, feira_art, sábados..., venues...]
        results = []

        # 6 categorias (outdoor foi removido)
        results.extend([f"result_jazz", "result_comedia", "result_musica_classica",
                       "result_cinema", "result_feira_gast", "result_feira_art"])

        # N sábados
        for i in range(num_saturdays):
            results.append(f"result_saturday_{i+1}")

        # 17 venues
        venues = ["casa_choro", "sala_cecilia", "teatro_municipal", "artemis", "ccbb",
                 "oi_futuro", "ims", "parque_lage", "ccjf", "mam_cinema",
                 "theatro_net", "ccbb_teatro_cinema", "istituto_italiano",
                 "maze_jazz", "teatro_leblon", "clube_jazz_rival", "estacao_net"]

        for venue in venues:
            results.append(f"result_{venue}")

        total_results = len(results)
        expected_total = 6 + num_saturdays + 17

        print(f"   Total de resultados: {total_results}")
        print(f"   Esperado: {expected_total}")

        # Testar desempacotamento
        result_jazz = results[0]
        result_comedia = results[1]
        result_musica_classica = results[2]
        result_cinema = results[3]
        result_feira_gastronomica = results[4]
        result_feira_artesanato = results[5]

        # Sábados
        saturday_results = results[6:6 + num_saturdays]

        # Venues
        venues_start_idx = 6 + num_saturdays
        result_casa_choro = results[venues_start_idx]
        result_artemis = results[venues_start_idx + 3]
        result_estacao_net = results[venues_start_idx + 16]

        # Validações
        assert result_jazz == "result_jazz", "Jazz incorreto"
        assert result_comedia == "result_comedia", "Comédia incorreto"
        assert len(saturday_results) == num_saturdays, f"Sábados incorreto: {len(saturday_results)} != {num_saturdays}"
        assert result_casa_choro == "result_casa_choro", "Casa do Choro incorreto"
        assert result_artemis == "result_artemis", "Artemis incorreto"
        assert result_estacao_net == "result_estacao_net", "Estação Net incorreto"

        print(f"   ✓ Jazz: {result_jazz}")
        print(f"   ✓ Sábados: {len(saturday_results)} resultados")
        print(f"   ✓ Primeiro sábado: {saturday_results[0]}")
        print(f"   ✓ Último sábado: {saturday_results[-1]}")
        print(f"   ✓ Casa do Choro (índice {venues_start_idx}): {result_casa_choro}")
        print(f"   ✓ Artemis (índice {venues_start_idx + 3}): {result_artemis}")
        print(f"   ✓ Estação Net (índice {venues_start_idx + 16}): {result_estacao_net}")
        print(f"   ✅ Desempacotamento correto com {num_saturdays} sábados")

    print("\n" + "=" * 80)
    print("✅ TESTE 2: PASSOU")
    print("=" * 80)
    return True


def test_saturday_consolidation():
    """Testa consolidação de eventos outdoor dos sábados."""
    print("\n" + "=" * 80)
    print("TESTE 3: Consolidação de Eventos Outdoor")
    print("=" * 80)

    # Simular resultados de 4 sábados
    saturday_results_mock = [
        '{"eventos": [{"titulo": "Feira Praça XV", "data": "15/11/2025"}]}',
        '{"eventos": []}',  # Sábado sem eventos
        '{"eventos": [{"titulo": "Cinema Parque Lage", "data": "29/11/2025"}, {"titulo": "Concerto Jardim Botânico", "data": "29/11/2025"}]}',
        '{"eventos": [{"titulo": "Feira Rio Antigo", "data": "06/12/2025"}]}',
    ]

    saturdays_mock = [
        {"date": datetime(2025, 11, 15), "date_str": "15/11/2025"},
        {"date": datetime(2025, 11, 22), "date_str": "22/11/2025"},
        {"date": datetime(2025, 11, 29), "date_str": "29/11/2025"},
        {"date": datetime(2025, 12, 6), "date_str": "06/12/2025"},
    ]

    # Simular função safe_parse_categoria
    import json

    def safe_parse_categoria_mock(result_str, categoria):
        try:
            data = json.loads(result_str)
            return data.get("eventos", [])
        except:
            return []

    # Lógica copiada do search_agent.py
    eventos_outdoor = []
    for i, saturday_result in enumerate(saturday_results_mock):
        saturday_date = saturdays_mock[i]["date_str"]
        eventos_sab = safe_parse_categoria_mock(saturday_result, "Outdoor/Parques")
        if eventos_sab:
            print(f"   ✓ Sábado {saturday_date}: {len(eventos_sab)} eventos outdoor")
            eventos_outdoor.extend(eventos_sab)
        else:
            print(f"   ⚠️  Sábado {saturday_date}: 0 eventos outdoor")

    print(f"\n✓ Total eventos outdoor (todos os sábados): {len(eventos_outdoor)} eventos")

    # Validações
    assert len(eventos_outdoor) == 4, f"Esperado 4 eventos, obteve {len(eventos_outdoor)}"
    assert eventos_outdoor[0]["titulo"] == "Feira Praça XV"
    assert eventos_outdoor[1]["titulo"] == "Cinema Parque Lage"
    assert eventos_outdoor[2]["titulo"] == "Concerto Jardim Botânico"
    assert eventos_outdoor[3]["titulo"] == "Feira Rio Antigo"

    print("\nEventos consolidados:")
    for i, evento in enumerate(eventos_outdoor, 1):
        print(f"   {i}. {evento['titulo']} ({evento['data']})")

    print("\n" + "=" * 80)
    print("✅ TESTE 3: PASSOU")
    print("=" * 80)
    return True


def test_prompt_generation():
    """Testa geração de prompt para sábado específico."""
    print("\n" + "=" * 80)
    print("TESTE 4: Geração de Prompt por Sábado")
    print("=" * 80)

    saturday_date_str = "16/11/2025"
    month_str = "november"

    # Lógica copiada do search_agent.py (_build_saturday_outdoor_prompt)
    prompt = f"""
🎯 BUSCA ULTRA-FOCADA: Eventos Outdoor no Rio APENAS no dia {saturday_date_str} (SÁBADO)

OBJETIVO: Encontrar eventos culturais ao ar livre ESPECIFICAMENTE neste sábado.

ESTRATÉGIA DE BUSCA - FOCO EM EVENTOS RECORRENTES:

1. 🔍 **Feiras Recorrentes aos Sábados**:
   - Feira da Praça XV (todos os sábados): site:bafafa.com.br "feira praça xv" {saturday_date_str}
   - Feira Rio Antigo (1º sábado): site:visit.rio "feira rio antigo" {month_str}

FONTES OBRIGATÓRIAS:
- site:bafafa.com.br eventos rio {saturday_date_str}
- site:visit.rio agenda {saturday_date_str}

FORMATO DE RETORNO:
{{
  "eventos": [
    {{
      "categoria": "Outdoor/Parques",
      "titulo": "Nome do evento",
      "data": "{saturday_date_str}",
      ...
    }}
  ]
}}
"""

    print(f"\nPrompt gerado (primeiros 500 chars):")
    print("-" * 80)
    print(prompt[:500])
    print("-" * 80)

    # Validações
    assert saturday_date_str in prompt, "Data não interpolada"
    assert month_str in prompt, "Mês não interpolado"
    assert "bafafa.com.br" in prompt, "Fonte bafafa ausente"
    assert "visit.rio" in prompt, "Fonte visit.rio ausente"
    assert f'"data": "{saturday_date_str}"' in prompt, "Data no JSON ausente"

    print("\n✓ Data interpolada corretamente")
    print("✓ Mês interpolado corretamente")
    print("✓ Fontes incluídas (bafafa, visit.rio)")
    print("✓ Formato JSON correto")

    print("\n" + "=" * 80)
    print("✅ TESTE 4: PASSOU")
    print("=" * 80)
    return True


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("SUITE DE TESTES: Lógica de Sábados Outdoor")
    print("=" * 80 + "\n")

    tests = [
        ("Cálculo de Sábados", test_get_saturdays),
        ("Desempacotamento de Resultados", test_results_unpacking),
        ("Consolidação de Eventos", test_saturday_consolidation),
        ("Geração de Prompt", test_prompt_generation),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n❌ ERRO no teste '{test_name}': {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Resumo
    print("\n" + "=" * 80)
    print("RESUMO DOS TESTES")
    print("=" * 80)
    for test_name, passed in results:
        status = "✅ PASSOU" if passed else "❌ FALHOU"
        print(f"{status}: {test_name}")

    total = len(results)
    passed_count = sum(1 for _, p in results if p)

    print(f"\nTotal: {passed_count}/{total} testes passaram")

    if passed_count == total:
        print("\n🎉 TODOS OS TESTES PASSARAM!")
    else:
        print("\n⚠️  ALGUNS TESTES FALHARAM - VERIFICAR CÓDIGO")

    print("=" * 80)
