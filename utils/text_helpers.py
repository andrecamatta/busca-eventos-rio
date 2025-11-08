"""
Utilitários centralizados para manipulação de texto.
Elimina duplicação de lógica de normalização em múltiplos arquivos.
"""

import re
import unicodedata
from typing import Optional


def normalize_string(
    text: str,
    remove_accents: bool = True,
    remove_punctuation: bool = True,
    lowercase: bool = True,
    normalize_spaces: bool = True
) -> str:
    """
    Normaliza string para comparação com opções configuráveis.

    Args:
        text: Texto a ser normalizado
        remove_accents: Se deve remover acentos (padrão: True)
        remove_punctuation: Se deve normalizar pontuação (padrão: True)
        lowercase: Se deve converter para minúsculas (padrão: True)
        normalize_spaces: Se deve normalizar espaços extras (padrão: True)

    Returns:
        Texto normalizado

    Examples:
        >>> normalize_string("São Paulo – Teatro")
        'sao paulo - teatro'
        >>> normalize_string("São Paulo", remove_accents=False)
        'são paulo'
    """
    if not text:
        return ""

    result = text

    # Normalizar pontuação se solicitado
    if remove_punctuation:
        # Substituir travessões e variantes por hífen simples
        # U+2013 EN DASH (–), U+2014 EM DASH (—), U+2015 HORIZONTAL BAR (―)
        result = result.replace('–', '-').replace('—', '-').replace('―', '-')
        # Remover outros caracteres de pontuação problemáticos
        result = result.replace('|', '-').replace('/', '-')

    # Remover acentos se solicitado
    if remove_accents:
        # NFD decomposition + remoção de caracteres de combinação
        result = unicodedata.normalize('NFD', result)
        result = ''.join(char for char in result if unicodedata.category(char) != 'Mn')

    # Lowercase se solicitado
    if lowercase:
        result = result.lower()

    # Normalizar espaços se solicitado
    if normalize_spaces:
        result = result.strip()
        result = ' '.join(result.split())

    return result


def clean_location_name(location: str) -> str:
    """
    Limpa e normaliza nome de local para comparação.

    Args:
        location: Nome do local

    Returns:
        Local normalizado e limpo

    Examples:
        >>> clean_location_name("Teatro Riachuelo, Rio de Janeiro.")
        'teatro riachuelo rio de janeiro'
    """
    # Normalizar básico
    normalized = normalize_string(location)

    # Remover pontuação final
    normalized = re.sub(r"[,.]$", "", normalized)

    return normalized


def remove_extra_spaces(text: str) -> str:
    """
    Remove espaços extras de um texto, mantendo apenas espaços simples.

    Args:
        text: Texto com possíveis espaços extras

    Returns:
        Texto com espaços normalizados

    Examples:
        >>> remove_extra_spaces("Hello    world  !")
        'Hello world !'
    """
    return re.sub(r"\s+", " ", text.strip())


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Trunca texto se exceder comprimento máximo.

    Args:
        text: Texto a truncar
        max_length: Comprimento máximo
        suffix: Sufixo a adicionar se truncado (padrão: "...")

    Returns:
        Texto truncado se necessário

    Examples:
        >>> truncate_text("Um texto muito longo", 10)
        'Um texto...'
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def extract_words(text: str) -> list[str]:
    """
    Extrai palavras de um texto (remove pontuação e espaços).

    Args:
        text: Texto de entrada

    Returns:
        Lista de palavras

    Examples:
        >>> extract_words("Hello, world!")
        ['hello', 'world']
    """
    # Normalizar e remover pontuação
    normalized = normalize_string(text)
    # Extrair apenas palavras (alfanuméricos e hífens)
    words = re.findall(r'\w+(?:-\w+)*', normalized)
    return words


def calculate_word_overlap(text1: str, text2: str) -> float:
    """
    Calcula sobreposição de palavras entre dois textos (0.0 a 1.0).

    Args:
        text1: Primeiro texto
        text2: Segundo texto

    Returns:
        Proporção de palavras em comum (0.0 a 1.0)

    Examples:
        >>> calculate_word_overlap("hello world", "world peace")
        0.5
    """
    words1 = set(extract_words(text1))
    words2 = set(extract_words(text2))

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union) if union else 0.0
