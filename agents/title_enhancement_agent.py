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


def extract_detail_from_description(title: str, description: str, local: str, horario: str = "") -> str:
    """Usa Gemini Flash com estratégias em cascata para garantir enriquecimento.

    Estratégias (em ordem):
    1. Artista/Companhia principal
    2. Tema/Obra específica
    3. Horário diferenciado (matinê, noturno)
    4. Sessão numerada

    Args:
        title: Título original do evento
        description: Descrição completa do evento
        local: Local do evento
        horario: Horário do evento

    Returns:
        Detalhe específico extraído (sempre retorna algo)
    """
    agent = AgentFactory.create_agent(
        name="Title Enhancement Agent",
        model_type="light",  # Gemini Flash - rápido e barato
        description="Extrai detalhes específicos de descrições de eventos para enriquecer títulos",
        instructions=[
            "Você analisa descrições de eventos e extrai detalhes que diferenciam cada apresentação.",
            "Use estratégias em cascata: artista → tema → característica temporal.",
            "NUNCA retorne KEEP_ORIGINAL - sempre encontre algo para enriquecer.",
            "Retorne APENAS o detalhe (máximo 5 palavras), sem explicações."
        ],
        markdown=False
    )

    prompt = f"""TÍTULO: {title}
LOCAL: {local}
HORÁRIO: {horario}
DESCRIÇÃO: {description}

TAREFA: Extrair detalhe para enriquecer o título usando estratégias em CASCATA:

ESTRATÉGIA 1 - ARTISTA/COMPANHIA (prioridade máxima):
- Nome do artista principal, solista, banda ou companhia
- Exemplo: "Martha Argerich", "Cia Sutil de Teatro", "Banda Let's Bowie"

ESTRATÉGIA 2 - TEMA/OBRA ESPECÍFICA (se não houver artista):
- Título da obra, tema da apresentação, repertório específico
- Exemplo: "Movimentos Urbanos", "Repertório Chopin", "Obras Românticas"

ESTRATÉGIA 3 - CARACTERÍSTICA TEMPORAL (se não houver tema):
- Baseado no horário: "Sessão Matinê" (antes 15h), "Sessão Noturna" (depois 20h)
- Para múltiplas datas: "1ª Semana", "2ª Semana"

REGRAS IMPORTANTES:
1. Máximo 4-5 palavras
2. NÃO repetir informação já no título
3. NÃO incluir palavras como "com", "apresentando", "traz"
4. SEMPRE retornar algo - use cascata até encontrar
5. Priorizar nomes próprios quando possível

EXEMPLOS:

Título: "Festival Internacional de Piano"
Descrição: "...apresenta a renomada pianista Martha Argerich..."
→ Martha Argerich

Título: "Atos de Fala"
Descrição: "...espetáculo teatral da Cia Sutil de Teatro..."
→ Cia Sutil de Teatro

Título: "Show de Jazz"
Descrição: "Noite de jazz com standards clássicos..."
Horário: 21:00
→ Sessão Noturna

Título: "Concerto de Natal"
Descrição: "Apresentação com obras natalinas e músicas sacras..."
→ Repertório Sacro

Agora analise e retorne o melhor detalhe possível:"""

    try:
        response = agent.run(prompt)
        content = response.content.strip()

        # Limpar possíveis prefixos
        content = content.replace("Detalhe:", "").replace("→", "").replace("Estratégia", "").strip()

        # Validar tamanho
        if len(content) < 3 or len(content) > 50:
            # Fallback: usar horário
            return generate_time_based_suffix(horario)

        return content

    except Exception as e:
        logger.error(f"{LOG_PREFIX} Erro ao extrair detalhe: {e}")
        return generate_time_based_suffix(horario)


def generate_time_based_suffix(horario: str) -> str:
    """Gera sufixo baseado no horário como último recurso.

    Args:
        horario: Horário no formato HH:MM

    Returns:
        Sufixo descritivo baseado no horário
    """
    if not horario or ":" not in horario:
        return "Sessão Especial"

    try:
        hora = int(horario.split(":")[0])
        if hora < 12:
            return "Sessão Matinal"
        elif hora < 15:
            return "Sessão Vespertina"
        elif hora < 19:
            return "Sessão Tarde"
        else:
            return "Sessão Noturna"
    except:
        return "Sessão Especial"


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
            horario = event.get("horario", "")

            if not description or len(description) < 50:
                logger.debug(f"{LOG_PREFIX} Descrição muito curta para '{title}', pulando")
                continue

            # Extrair detalhe (sempre retorna algo com estratégias em cascata)
            detail = extract_detail_from_description(title, description, local, horario)

            if detail:
                enhanced_title = f"{title} - {detail}"
                events[idx]["titulo"] = enhanced_title
                enhanced_count += 1
                logger.info(f"{LOG_PREFIX} '{title}' → '{enhanced_title}'")

        # Rate limiting entre batches
        if i + batch_size < len(generic_events):
            await asyncio.sleep(0.5)

    logger.info(f"{LOG_PREFIX} ✓ {enhanced_count}/{len(generic_events)} títulos enriquecidos")

    # Verificar se ainda há duplicatas (não deveria haver com estratégias em cascata)
    from collections import Counter
    titles = [e.get("titulo", "") for e in events]
    duplicates = sum(1 for t, c in Counter(titles).items() if c > 1)
    if duplicates > 0:
        logger.warning(f"{LOG_PREFIX} ⚠️  {duplicates} títulos ainda duplicados após enriquecimento")

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
