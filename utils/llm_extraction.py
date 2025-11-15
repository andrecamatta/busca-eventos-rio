#!/usr/bin/env python3
"""
LLM-based event extraction from DiarioDoRio articles.

Uses Gemini Flash to extract structured event data from article markdown.
"""

import json
import logging
from typing import Any

from openai import OpenAI

from config import GEMINI_FLASH_MODEL, OPENROUTER_API_KEY

logger = logging.getLogger(__name__)


def extract_events_batch_with_llm(batch_data: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """
    Extract events from a batch of DiarioDoRio articles using Gemini Flash.

    Args:
        batch_data: List of (title, markdown) tuples representing articles

    Returns:
        List of extracted events with structured fields
    """
    if not batch_data:
        return []

    # Build prompt for batch extraction
    articles_text = []
    for idx, (title, markdown) in enumerate(batch_data, 1):
        articles_text.append(f"""
=== ARTIGO {idx}: {title} ===
{markdown}
""")

    prompt = f"""Você é um extrator de eventos culturais do Rio de Janeiro.

Analise os artigos abaixo do site "Diário do Rio" e extraia TODOS os eventos mencionados.

Para cada evento, retorne um objeto JSON com:
- evento_numero: número sequencial do evento (1, 2, 3...)
- titulo: nome/título do evento (string)
- data: data no formato DD/MM/YYYY (se houver múltiplas datas, use a primeira)
- horario: horário de início (formato HH:MM, ou "A confirmar" se não mencionado)
- local: nome do local + endereço completo (rua, bairro, cidade)
- preco: preço do ingresso ("Grátis", "R$ XX", "A confirmar", etc)
- categoria: uma das categorias: Jazz, Música Clássica, Teatro, Comédia, Cinema, Shows, Exposições, Literatura, Festas, Gastronomia, Artesanato, Cursos e Workshops, Atividades ao Ar Livre
- descricao: breve descrição do evento (2-3 frases)

IMPORTANTE:
- Se um artigo menciona múltiplos eventos, extraia TODOS eles separadamente
- Se não houver informação de horário, use "A confirmar"
- Se não houver informação de preço, use "A confirmar"
- Para eventos ao ar livre (feiras, festivais, cinema ao ar livre), use categoria "Atividades ao Ar Livre"
- Para eventos gastronômicos (feiras de comida, festivais gastronômicos), use categoria "Gastronomia"
- NÃO invente informações que não estão no texto

Retorne APENAS um array JSON válido com os eventos extraídos.

ARTIGOS:
{"".join(articles_text)}

Responda APENAS com o array JSON, sem explicações adicionais."""

    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )

        response = client.chat.completions.create(
            model=GEMINI_FLASH_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0.1,  # Low temperature for factual extraction
            max_tokens=4000,
        )

        result = response.choices[0].message.content.strip()

        # Remove markdown code blocks if present
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]
        result = result.strip()

        # Parse JSON
        events = json.loads(result)

        if not isinstance(events, list):
            logger.warning(f"LLM returned non-list response: {type(events)}")
            return []

        logger.info(f"   Extracted {len(events)} events from batch of {len(batch_data)} articles")
        return events

    except json.JSONDecodeError as e:
        logger.error(f"   Failed to parse LLM response as JSON: {e}")
        logger.error(f"   Response: {result[:500]}...")
        return []
    except Exception as e:
        logger.error(f"   Error calling LLM for event extraction: {e}")
        return []
