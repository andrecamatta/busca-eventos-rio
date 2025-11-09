"""Agente de enriquecimento de títulos genéricos de eventos.

Este agente analisa eventos com títulos genéricos (ex: "Atos de Fala", "Festival Internacional de Piano")
e extrai detalhes específicos da descrição para tornar os títulos mais informativos.

Exemplo:
    Antes: "Festival Internacional de Piano"
    Depois: "Festival Internacional de Piano - Martha Argerich"
"""

import asyncio
import json
import logging
from collections import Counter
from typing import Any

from utils.agent_factory import AgentFactory

logger = logging.getLogger(__name__)
LOG_PREFIX = "[TitleEnhancementAgent] ✨"


# Palavras que indicam título genérico
GENERIC_TITLE_INDICATORS = [
    "festival",
    "show",
    "tributo",
    "apresenta",
    "sessão",
    "espetáculo",
    "concerto",
    "recital",
    "turnê",
    "tour",
]


def is_generic_title(title: str) -> bool:
    """Verifica se um título é genérico e precisa de enriquecimento.

    Critérios:
    1. Título muito curto (≤2 palavras) SEMPRE genérico
    2. Título curto (3 palavras) genérico se não for nome próprio claro
    3. Título médio (4-5 palavras) genérico se contém palavra indicadora
    4. Não contém travessão (já tem subtítulo)
    """
    if not title or " - " in title or " – " in title:
        return False

    words = title.split()
    if len(words) > 5:
        return False

    title_lower = title.lower()
    has_indicator = any(indicator in title_lower for indicator in GENERIC_TITLE_INDICATORS)

    # Títulos muito curtos (1-2 palavras) são sempre genéricos
    if len(words) <= 2:
        return True

    # Títulos de 3 palavras: genérico se tem indicador OU não tem nome próprio
    if len(words) == 3:
        # Se tem indicador, é genérico
        if has_indicator:
            return True
        # Se todas as palavras começam com minúscula (exceto preposições), provavelmente é genérico
        capitalized = sum(1 for w in words if w[0].isupper())
        return capitalized <= 1  # No máximo 1 palavra capitalizada = genérico

    # Títulos 4-5 palavras: genérico apenas se tem indicador
    return has_indicator


def extract_detail_from_description(title: str, description: str, local: str) -> str:
    """Usa Gemini Flash para extrair detalhe específico da descrição.

    Args:
        title: Título original do evento
        description: Descrição completa do evento
        local: Local do evento

    Returns:
        Detalhe específico extraído ou vazio se não encontrar
    """
    agent = AgentFactory.create_agent(
        name="Title Enhancement Agent",
        model_type="light",  # Gemini Flash - rápido e barato
        description="Extrai detalhes específicos de descrições de eventos para enriquecer títulos",
        instructions=[
            "Você analisa descrições de eventos e extrai o detalhe mais específico e relevante.",
            "Seu objetivo é identificar O QUE diferencia este evento de outros similares.",
            "Retorne APENAS o detalhe (máximo 5 palavras), sem explicações.",
            "Se não houver detalhe relevante, retorne: KEEP_ORIGINAL"
        ],
        markdown=False
    )

    prompt = f"""TÍTULO ATUAL: {title}
LOCAL: {local}
DESCRIÇÃO: {description}

TAREFA:
Identifique o detalhe específico mais importante que diferencia este evento:

CATEGORIAS:
- Festival/Concerto → nome do artista principal ou solista
- Espetáculo/Peça → nome da companhia OU tema específico da obra
- Série/Temporada → tema específico do episódio
- Tributo → apenas "Tributo [Artista]"

REGRAS:
1. Extraia APENAS 1 detalhe (máximo 4-5 palavras)
2. NÃO inclua "com", "apresentando", "traz", etc
3. NÃO repita info já no título
4. Se não houver detalhe RELEVANTE, retorne: KEEP_ORIGINAL
5. Priorize nomes próprios (artistas, companhias)

EXEMPLOS:

Título: "Festival Internacional de Piano"
Descrição: "...apresenta a renomada pianista Martha Argerich interpretando obras de Chopin..."
→ Martha Argerich

Título: "Atos de Fala"
Descrição: "...espetáculo teatral da Cia Sutil de Teatro que explora..."
→ Cia Sutil de Teatro

Título: "Show de Jazz"
Descrição: "Noite de jazz com standards e improvisações clássicas do gênero..."
→ KEEP_ORIGINAL

Título: "Tributo aos Beatles"
Descrição: "Banda Let It Be apresenta os maiores sucessos dos Beatles..."
→ Banda Let It Be

Agora analise e retorne APENAS o detalhe ou KEEP_ORIGINAL:"""

    try:
        response = agent.run(prompt)
        content = response.content.strip()

        if "KEEP_ORIGINAL" in content:
            return ""

        # Limpar possíveis prefixos
        content = content.replace("Detalhe:", "").replace("→", "").strip()

        # Validar tamanho
        if len(content) > 50 or len(content) < 3:
            return ""

        return content

    except Exception as e:
        logger.error(f"{LOG_PREFIX} Erro ao extrair detalhe: {e}")
        return ""


def add_date_suffix_to_duplicates(events: list[dict]) -> list[dict]:
    """Adiciona sufixo com data curta para títulos ainda duplicados após enhancement.

    Args:
        events: Lista de eventos

    Returns:
        Lista com títulos desambiguados
    """
    # Contar títulos duplicados
    titles = [e.get("titulo", "") for e in events]
    title_counts = Counter(titles)
    duplicates = {t for t, c in title_counts.items() if c > 1}

    if not duplicates:
        return events

    logger.info(f"{LOG_PREFIX} {len(duplicates)} títulos ainda duplicados, adicionando data...")

    # Adicionar data aos duplicados
    for event in events:
        title = event.get("titulo", "")
        if title in duplicates:
            data = event.get("data", "")
            if data:
                # Formato: DD/MM → (DD/MM)
                date_short = "/".join(data.split("/")[:2])  # DD/MM
                event["titulo"] = f"{title} ({date_short})"

    return events


async def enhance_event_titles(events: list[dict]) -> list[dict]:
    """Enriquece títulos genéricos de eventos usando análise de descrição.

    Args:
        events: Lista de eventos a processar

    Returns:
        Lista de eventos com títulos enriquecidos
    """
    logger.info(f"{LOG_PREFIX} Iniciando enriquecimento de títulos para {len(events)} eventos")

    # Identificar eventos com títulos genéricos
    generic_events = [(i, e) for i, e in enumerate(events) if is_generic_title(e.get("titulo", ""))]
    logger.info(f"{LOG_PREFIX} Encontrados {len(generic_events)} eventos com títulos genéricos")

    if not generic_events:
        logger.info(f"{LOG_PREFIX} Nenhum evento precisa de enriquecimento")
        return events

    # Processar eventos em lote (rate limiting)
    enhanced_count = 0
    batch_size = 10

    for i in range(0, len(generic_events), batch_size):
        batch = generic_events[i:i + batch_size]

        for idx, event in batch:
            title = event.get("titulo", "")
            description = event.get("descricao", "")
            local = event.get("local", "")

            if not description or len(description) < 50:
                logger.debug(f"{LOG_PREFIX} Descrição muito curta para '{title}', pulando")
                continue

            # Extrair detalhe
            detail = extract_detail_from_description(title, description, local)

            if detail:
                enhanced_title = f"{title} - {detail}"
                events[idx]["titulo"] = enhanced_title
                enhanced_count += 1
                logger.info(f"{LOG_PREFIX} '{title}' → '{enhanced_title}'")

        # Rate limiting entre batches
        if i + batch_size < len(generic_events):
            await asyncio.sleep(0.5)

    logger.info(f"{LOG_PREFIX} ✓ {enhanced_count}/{len(generic_events)} títulos enriquecidos com IA")

    # Adicionar data aos títulos ainda duplicados
    events = add_date_suffix_to_duplicates(events)

    return events


async def run(input_file: str, output_file: str) -> None:
    """Executa o agente de enriquecimento de títulos.

    Args:
        input_file: Caminho para arquivo JSON com eventos enriquecidos
        output_file: Caminho para salvar eventos com títulos melhorados
    """
    logger.info(f"{LOG_PREFIX} Carregando eventos de {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Suportar formato com wrapper ou lista direta
    if isinstance(data, dict):
        events = data.get("enriched_events") or data.get("eventos") or []
    else:
        events = data

    logger.info(f"{LOG_PREFIX} {len(events)} eventos carregados")

    # Enriquecer títulos
    enhanced_events = await enhance_event_titles(events)

    # Salvar resultado
    logger.info(f"{LOG_PREFIX} Salvando eventos em {output_file}")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(enhanced_events, f, ensure_ascii=False, indent=2)

    logger.info(f"{LOG_PREFIX} ✓ Enriquecimento de títulos concluído")


if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) != 3:
        print("Uso: python title_enhancement_agent.py <input_file> <output_file>")
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    asyncio.run(run(sys.argv[1], sys.argv[2]))
