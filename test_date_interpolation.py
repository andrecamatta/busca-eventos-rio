"""Teste para verificar correção do bug de interpolação cross-month."""

import logging
from datetime import datetime
from utils.prompt_loader import PromptLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_single_month():
    """Testa cenário de mês único."""

    logger.info("=" * 80)
    logger.info("TESTE 1: Mês Único (08/11/2025 - 29/11/2025)")
    logger.info("=" * 80)

    loader = PromptLoader()
    start_date = datetime(2025, 11, 8)
    end_date = datetime(2025, 11, 29)

    context = loader.build_context(start_date, end_date)

    # Validações
    assert context["start_date_str"] == "08/11/2025", f"start_date_str incorreto: {context['start_date_str']}"
    assert context["end_date_str"] == "29/11/2025", f"end_date_str incorreto: {context['end_date_str']}"
    assert context["month_str"] == "novembro", f"month_str incorreto: {context['month_str']}"
    assert context["month_year_str"] == "novembro 2025", f"month_year_str incorreto: {context['month_year_str']}"
    assert context["month_range_str"] == "novembro 2025", f"month_range_str incorreto: {context['month_range_str']}"

    logger.info("\n✅ Contexto gerado corretamente:")
    logger.info(f"   start_date_str: {context['start_date_str']}")
    logger.info(f"   end_date_str: {context['end_date_str']}")
    logger.info(f"   month_str: {context['month_str']}")
    logger.info(f"   month_year_str: {context['month_year_str']}")
    logger.info(f"   month_range_str: {context['month_range_str']}")

    # Testar interpolação em prompt
    prompt_config = loader.get_categoria("jazz", context)
    palavras_chave = prompt_config["palavras_chave"]

    logger.info("\n✅ Prompts interpolados corretamente:")
    logger.info(f"   Palavra-chave 1: {palavras_chave[0]}")
    logger.info(f"   Palavra-chave 2: {palavras_chave[1]}")

    assert "novembro 2025" in palavras_chave[0], "Interpolação falhou em palavras_chave[0]"
    assert "08/11/2025" in palavras_chave[1] and "29/11/2025" in palavras_chave[1], "Interpolação falhou em palavras_chave[1]"

    logger.info("\n✅ TESTE 1 PASSOU\n")
    return True


def test_cross_month_same_year():
    """Testa cenário cross-month no mesmo ano."""

    logger.info("=" * 80)
    logger.info("TESTE 2: Cross-Month Mesmo Ano (25/11/2025 - 05/12/2025)")
    logger.info("=" * 80)

    loader = PromptLoader()
    start_date = datetime(2025, 11, 25)
    end_date = datetime(2025, 12, 5)

    context = loader.build_context(start_date, end_date)

    # Validações
    assert context["start_date_str"] == "25/11/2025", f"start_date_str incorreto: {context['start_date_str']}"
    assert context["end_date_str"] == "05/12/2025", f"end_date_str incorreto: {context['end_date_str']}"
    assert context["month_str"] == "novembro", f"month_str incorreto: {context['month_str']}"
    assert context["month_year_str"] == "novembro/dezembro 2025", f"month_year_str incorreto: {context['month_year_str']}"
    assert context["month_range_str"] == "novembro/dezembro 2025", f"month_range_str incorreto: {context['month_range_str']}"

    logger.info("\n✅ Contexto gerado corretamente:")
    logger.info(f"   start_date_str: {context['start_date_str']}")
    logger.info(f"   end_date_str: {context['end_date_str']}")
    logger.info(f"   month_str: {context['month_str']}")
    logger.info(f"   month_year_str: {context['month_year_str']}")  # DEVE incluir novembro/dezembro!
    logger.info(f"   month_range_str: {context['month_range_str']}")

    # Testar interpolação em prompt
    prompt_config = loader.get_categoria("outdoor", context)
    palavras_chave = prompt_config["palavras_chave"]

    logger.info("\n✅ Prompts interpolados corretamente:")
    logger.info(f"   Palavra-chave 1: {palavras_chave[0]}")
    logger.info(f"   Palavra-chave 2: {palavras_chave[1]}")

    assert "novembro/dezembro 2025" in palavras_chave[0], "Interpolação falhou - não detectou cross-month"
    assert "25/11/2025" in palavras_chave[5] and "05/12/2025" in palavras_chave[5], "Interpolação de datas explícitas falhou"

    logger.info("\n✅ TESTE 2 PASSOU - Cross-month detectado corretamente!\n")
    return True


def test_cross_year():
    """Testa cenário cross-year (virada de ano)."""

    logger.info("=" * 80)
    logger.info("TESTE 3: Cross-Year (20/12/2025 - 10/01/2026)")
    logger.info("=" * 80)

    loader = PromptLoader()
    start_date = datetime(2025, 12, 20)
    end_date = datetime(2026, 1, 10)

    context = loader.build_context(start_date, end_date)

    # Validações
    assert context["start_date_str"] == "20/12/2025", f"start_date_str incorreto: {context['start_date_str']}"
    assert context["end_date_str"] == "10/01/2026", f"end_date_str incorreto: {context['end_date_str']}"
    assert context["month_str"] == "dezembro", f"month_str incorreto: {context['month_str']}"
    assert context["month_year_str"] == "dezembro 2025/janeiro 2026", f"month_year_str incorreto: {context['month_year_str']}"
    assert context["month_range_str"] == "dezembro 2025/janeiro 2026", f"month_range_str incorreto: {context['month_range_str']}"

    logger.info("\n✅ Contexto gerado corretamente:")
    logger.info(f"   start_date_str: {context['start_date_str']}")
    logger.info(f"   end_date_str: {context['end_date_str']}")
    logger.info(f"   month_str: {context['month_str']}")
    logger.info(f"   month_year_str: {context['month_year_str']}")  # DEVE incluir dezembro 2025/janeiro 2026!
    logger.info(f"   month_range_str: {context['month_range_str']}")

    # Testar interpolação em prompt
    prompt_config = loader.get_categoria("musica_classica", context)
    palavras_chave = prompt_config["palavras_chave"]

    logger.info("\n✅ Prompts interpolados corretamente:")
    logger.info(f"   Palavra-chave 1: {palavras_chave[0]}")
    logger.info(f"   Palavra-chave 5: {palavras_chave[5]}")

    assert "dezembro 2025/janeiro 2026" in palavras_chave[0], "Interpolação falhou - não detectou cross-year"
    assert "20/12/2025" in palavras_chave[5] and "10/01/2026" in palavras_chave[5], "Interpolação de datas explícitas falhou"

    logger.info("\n✅ TESTE 3 PASSOU - Cross-year detectado corretamente!\n")
    return True


def main():
    """Executa todos os testes."""

    logger.info("\n" + "🧪" * 40)
    logger.info("SUITE DE TESTES - DATE INTERPOLATION FIX")
    logger.info("🧪" * 40 + "\n")

    results = []

    # Teste 1: Mês único
    try:
        result1 = test_single_month()
        results.append(("Mês único (Nov 8-29)", result1))
    except Exception as e:
        logger.error(f"❌ TESTE 1 FALHOU: {e}")
        results.append(("Mês único (Nov 8-29)", False))

    # Teste 2: Cross-month
    try:
        result2 = test_cross_month_same_year()
        results.append(("Cross-month (Nov 25 - Dec 5)", result2))
    except Exception as e:
        logger.error(f"❌ TESTE 2 FALHOU: {e}")
        results.append(("Cross-month (Nov 25 - Dec 5)", False))

    # Teste 3: Cross-year
    try:
        result3 = test_cross_year()
        results.append(("Cross-year (Dec 20 - Jan 10)", result3))
    except Exception as e:
        logger.error(f"❌ TESTE 3 FALHOU: {e}")
        results.append(("Cross-year (Dec 20 - Jan 10)", False))

    # Resumo
    logger.info("=" * 80)
    logger.info("RESUMO DOS TESTES")
    logger.info("=" * 80)

    for test_name, passed in results:
        status = "✅ PASSOU" if passed else "❌ FALHOU"
        logger.info(f"{status} - {test_name}")

    all_passed = all(passed for _, passed in results)

    if all_passed:
        logger.info("\n🎉 TODOS OS TESTES PASSARAM!")
        logger.info("\n✅ Correção validada:")
        logger.info("   - Mês único: mantém comportamento original")
        logger.info("   - Cross-month: gera 'novembro/dezembro 2025'")
        logger.info("   - Cross-year: gera 'dezembro 2025/janeiro 2026'")
        logger.info("\n🚀 O bug de perda de eventos cross-month foi CORRIGIDO!")
    else:
        logger.error("\n⚠️  ALGUNS TESTES FALHARAM. Revisar implementação.")

    logger.info("=" * 80)

    return all_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
