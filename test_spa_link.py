"""Teste específico para validação de links SPA."""

import asyncio
import logging
from agents.verify_agent import VerifyAgent

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_eleventickets_links():
    """Testa validação de links ElevenTickets (válidos e inválidos)."""

    verify_agent = VerifyAgent()

    # Link INVÁLIDO - padrão de data/hora (deve ser rejeitado)
    invalid_link = "https://funarj.eleventickets.com/#!/apresentacao/7deNOV2025_19:00"

    # Link VÁLIDO - hash SHA1 de 40 caracteres
    valid_link = "https://funarj.eleventickets.com/#!/apresentacao/ef3e10a678e99d0a85dffcb5bc20c60d3e685b03"

    # Evento de teste
    event_invalid = {
        "titulo": "Concerto Clássico – Orquestra Petrobras Sinfônica",
        "data": "07/11/2025",
        "horario": "19:00",
        "local": "Sala Cecília Meireles"
    }

    event_valid = event_invalid.copy()

    print("\n" + "="*80)
    print("TESTE 1: Link INVÁLIDO (padrão de data/hora)")
    print("="*80)
    print(f"Link: {invalid_link}\n")

    import httpx
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        result_invalid = await verify_agent._validate_single_link(
            client,
            invalid_link,
            event=event_invalid,
            attempt_num=1
        )

    print(f"Resultado: {result_invalid}")

    if result_invalid['valid']:
        print("❌ FALHOU: Link inválido foi APROVADO (deveria ser rejeitado)")
    else:
        print("✅ SUCESSO: Link inválido foi REJEITADO como esperado")
        if 'spa_validation' in result_invalid:
            print(f"   Tipo de validação: {result_invalid['spa_validation']['type']}")
            print(f"   Razão: {result_invalid['spa_validation'].get('reason', 'N/A')}")

    print("\n" + "="*80)
    print("TESTE 2: Link VÁLIDO (hash SHA1)")
    print("="*80)
    print(f"Link: {valid_link}\n")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        result_valid = await verify_agent._validate_single_link(
            client,
            valid_link,
            event=event_valid,
            attempt_num=1
        )

    print(f"Resultado: {result_valid}")

    if result_valid['valid']:
        print("✅ SUCESSO: Link válido foi APROVADO como esperado")
        if 'spa_validation' in result_valid:
            print(f"   Tipo de validação: {result_valid['spa_validation']['type']}")
            print(f"   Razão: {result_valid['spa_validation'].get('reason', 'N/A')}")
    else:
        print("❌ FALHOU: Link válido foi REJEITADO (deveria ser aprovado)")

    print("\n" + "="*80)
    print("RESUMO DOS TESTES")
    print("="*80)
    print(f"Link inválido (data/hora): {'✅ REJEITADO' if not result_invalid['valid'] else '❌ APROVADO (ERRO!)'}")
    print(f"Link válido (hash SHA1):   {'✅ APROVADO' if result_valid['valid'] else '❌ REJEITADO (ERRO!)'}")
    print("="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(test_eleventickets_links())
