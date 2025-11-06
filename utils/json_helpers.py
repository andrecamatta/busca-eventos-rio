"""Utilitários para limpeza e extração de JSON de respostas LLM."""

import json
import logging
import re

logger = logging.getLogger(__name__)


def extract_json_from_markdown(content: str) -> str:
    """
    Remove markdown code blocks (```json ou ```) do conteúdo.

    Args:
        content: String contendo JSON potencialmente em markdown blocks

    Returns:
        String com JSON limpo, pronto para parse
    """
    # Remover markdown blocks
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    return content


def remove_js_comments(line: str) -> str:
    """
    Remove comentários JavaScript (//) de uma linha, respeitando strings.

    Args:
        line: Linha de texto que pode conter comentários

    Returns:
        Linha sem comentários
    """
    in_string = False
    quote_char = None
    result = []
    i = 0

    while i < len(line):
        char = line[i]

        # Verificar início/fim de string
        if char in ['"', "'"] and (i == 0 or line[i-1] != '\\'):
            if not in_string:
                in_string = True
                quote_char = char
            elif char == quote_char:
                in_string = False
                quote_char = None

        # Verificar início de comentário (fora de strings)
        if not in_string and i < len(line) - 1:
            if line[i:i+2] == '//':
                break

        result.append(char)
        i += 1

    return ''.join(result)


def clean_json_response(content: str, remove_comments: bool = True) -> str:
    """
    Limpa completamente uma resposta JSON de LLM.

    Remove:
    - Markdown code blocks (```json ou ```)
    - Comentários JavaScript (//)
    - Linhas vazias

    Args:
        content: Resposta do LLM contendo JSON
        remove_comments: Se True, remove comentários //

    Returns:
        JSON limpo, pronto para json.loads()

    Raises:
        ValueError: Se não conseguir extrair JSON válido
    """
    # 1. Remover markdown blocks
    content = extract_json_from_markdown(content)

    # 2. Remover comentários se solicitado
    if remove_comments:
        lines = []
        for line in content.split("\n"):
            cleaned_line = remove_js_comments(line)
            if cleaned_line.strip():
                lines.append(cleaned_line)
        content = "\n".join(lines)

    # 3. Fallback: tentar encontrar JSON com regex se ainda não está limpo
    if not content or content[0] not in ['{', '[']:
        logger.warning("Conteúdo não inicia com { ou [, tentando extrair com regex...")
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        else:
            raise ValueError("Não foi possível extrair JSON válido do conteúdo")

    return content


def safe_json_parse(content: str, default: dict | list | None = None) -> dict | list:
    """
    Faz parse de JSON com tratamento de erros seguro.

    Args:
        content: String JSON para fazer parse
        default: Valor padrão a retornar em caso de erro

    Returns:
        Objeto Python (dict ou list) ou default em caso de erro
    """
    try:
        cleaned = clean_json_response(content)
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Erro ao fazer parse de JSON: {e}")
        logger.debug(f"Conteúdo problemático: {content[:500]}...")

        if default is not None:
            return default
        raise
