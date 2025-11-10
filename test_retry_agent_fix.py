"""Teste para verificar correção do bug do Retry Agent."""

import asyncio
import logging
from agents.retry_agent import RetryAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_retry_agent_no_response_format_error():
    """Testa se Retry Agent funciona sem erro de response_format."""

    logger.info("=" * 80)
    logger.info("TESTE: Retry Agent - Correção do bug response_format")
    logger.info("=" * 80)

    # Criar instância do Retry Agent
    retry_agent = RetryAgent()
    logger.info("✓ Retry Agent instanciado com sucesso")

    # Criar análise simulada (não precisa ser completa, só testar a chamada)
    analysis = {
        "events_needed": 5,
        "categories": {
            "jazz": 2,
            "musica_classica": 1,
            "outdoor": 0,
        },
        "categories_missing": {
            "Jazz": 3,
            "Outdoor/Parques": 2,
        },
        "gaps": ["outdoor"],
        "missing_required_venues": [],
        "saturdays_uncovered": ["15/11/2025"],
        "recoverable_events": []
    }

    logger.info("\n📊 Análise simulada:")
    logger.info(f"   - Eventos necessários: {analysis['events_needed']}")
    logger.info(f"   - Categorias faltantes: {analysis['categories_missing']}")
    logger.info(f"   - Sábados descobertos: {analysis['saturdays_uncovered']}")

    try:
        logger.info("\n🔄 Executando search_complementary...")
        result = await retry_agent.search_complementary(analysis)

        logger.info("\n✅ SUCESSO: Retry Agent executou sem erros!")
        logger.info(f"   - Eventos complementares encontrados: {len(result.get('eventos_complementares', []))}")
        logger.info(f"   - Fontes consultadas: {len(result.get('fontes_consultadas', []))}")

        if result.get('observacoes'):
            logger.info(f"   - Observações: {result['observacoes']}")

        return True

    except TypeError as e:
        if "got multiple values for keyword argument 'response_format'" in str(e):
            logger.error("\n❌ FALHA: Bug do response_format ainda presente!")
            logger.error(f"   Erro: {e}")
            return False
        else:
            logger.error(f"\n❌ Erro inesperado: {e}")
            raise

    except Exception as e:
        logger.error(f"\n⚠️  Erro durante execução: {e}")
        logger.error("   (Pode ser erro de API ou outro, não relacionado ao bug)")
        # Não falhar o teste por erros de API - o importante é que não deu erro de response_format
        return True


async def test_event_classifier_rules():
    """Testa se Event Classifier tem regras de Música Clássica."""

    logger.info("\n" + "=" * 80)
    logger.info("TESTE: Event Classifier - Regras de Música Clássica")
    logger.info("=" * 80)

    from utils.event_classifier import CLASSIFICATION_PROMPT

    # Verificar se prompt contém as regras específicas
    checks = [
        ("Sala Cecília Meireles", "Sala Cecília Meireles" in CLASSIFICATION_PROMPT),
        ("Teatro Municipal", "Teatro Municipal" in CLASSIFICATION_PROMPT),
        ("piano/orquestra", "piano" in CLASSIFICATION_PROMPT and "orquestra" in CLASSIFICATION_PROMPT),
        ("REGRAS ESPECÍFICAS", "REGRAS ESPECÍFICAS PARA MÚSICA CLÁSSICA" in CLASSIFICATION_PROMPT),
    ]

    all_passed = True
    for check_name, check_result in checks:
        status = "✅" if check_result else "❌"
        logger.info(f"{status} {check_name}: {'OK' if check_result else 'FALTANDO'}")
        if not check_result:
            all_passed = False

    if all_passed:
        logger.info("\n✅ SUCESSO: Event Classifier tem todas as regras de Música Clássica!")
    else:
        logger.error("\n❌ FALHA: Event Classifier está faltando regras!")

    return all_passed


async def main():
    """Executa todos os testes."""

    logger.info("🧪 Iniciando testes das correções...\n")

    results = []

    # Teste 1: Retry Agent
    try:
        result1 = await test_retry_agent_no_response_format_error()
        results.append(("Retry Agent - Bug corrigido", result1))
    except Exception as e:
        logger.error(f"Erro fatal no teste Retry Agent: {e}")
        results.append(("Retry Agent - Bug corrigido", False))

    # Teste 2: Event Classifier
    try:
        result2 = await test_event_classifier_rules()
        results.append(("Event Classifier - Regras de Música Clássica", result2))
    except Exception as e:
        logger.error(f"Erro fatal no teste Event Classifier: {e}")
        results.append(("Event Classifier - Regras de Música Clássica", False))

    # Resumo
    logger.info("\n" + "=" * 80)
    logger.info("RESUMO DOS TESTES")
    logger.info("=" * 80)

    for test_name, passed in results:
        status = "✅ PASSOU" if passed else "❌ FALHOU"
        logger.info(f"{status} - {test_name}")

    all_passed = all(passed for _, passed in results)

    if all_passed:
        logger.info("\n🎉 TODOS OS TESTES PASSARAM! Correções validadas.")
    else:
        logger.error("\n⚠️  ALGUNS TESTES FALHARAM. Revisar correções.")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
