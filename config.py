"""Configurações do sistema de busca de eventos."""

import os
from datetime import datetime, timedelta
from typing import Final

from dotenv import load_dotenv

load_dotenv()

# OpenRouter API Configuration
OPENROUTER_API_KEY: Final[str] = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"

# Modelos OpenRouter por função (otimização de custo vs performance)
MODELS: Final[dict[str, str]] = {
    "search": "perplexity/sonar-pro",  # Especializado em busca web com internet em tempo real
    "verify": "openai/gpt-5-mini",  # Rápido e econômico para verificação
    "format": "google/gemini-2.5-flash",  # Rápido para formatação
}

# Configurações de busca
SEARCH_CONFIG: Final[dict] = {
    "location": "Rio de Janeiro",
    "days_ahead": 21,  # 3 semanas
    "start_date": datetime.now(),
    "end_date": datetime.now() + timedelta(days=21),
}

# Categorias de eventos
EVENT_CATEGORIES: Final[dict[str, dict]] = {
    "jazz": {
        "keywords": ["jazz", "show jazz", "música jazz", "jazz ao vivo"],
        "description": "Shows de jazz",
    },
    "comedia_teatro": {
        "keywords": ["teatro comédia", "stand-up", "humor", "peça cômica"],
        "exclude": ["infantil", "criança", "kids"],
        "description": "Teatro gênero comédia (exceto infantil)",
    },
    "venues_especiais": {
        "venues": [
            "Casa do Choro",
            "Sala Cecília Meirelles",
            "Teatro Municipal",
        ],
        "description": "Eventos em locais específicos",
    },
    "outdoor_weekend": {
        "keywords": ["ao ar livre", "outdoor", "parque", "praia"],
        "days": ["saturday", "sunday"],
        "description": "Eventos ao ar livre em fim de semana",
    },
    "cursos_cafe": {
        "keywords": ["curso café", "workshop café", "barista", "degustação café", "coffee tasting"],
        "venues": ["Artemis Torrefação"],
        "description": "Cursos e eventos de café especializado",
    },
}

# Venues obrigatórios (deve ter pelo menos 1 evento de cada)
REQUIRED_VENUES: Final[dict[str, list[str]]] = {
    "teatro_municipal": ["Teatro Municipal", "Theatro Municipal"],
    "sala_cecilia": ["Sala Cecília Meirelles", "Cecília Meirelles", "Cecilia Meireles"],
    "blue_note": ["Blue Note Rio", "Blue Note", "BlueNote"],
}

# Endereços reais dos venues (para validação rigorosa)
VENUE_ADDRESSES: Final[dict[str, list[str]]] = {
    "artemis_torrefacao": [
        "Rua Conde de Bonfim, 751, Tijuca, Rio de Janeiro",
        "Conde de Bonfim, 751, Tijuca",
        "Tijuca, Rio de Janeiro",  # aceitar se mencionar Tijuca
    ],
    "blue_note": [
        "Av. Afrânio de Melo Franco, 290, Leblon, Rio de Janeiro",
        "Avenida Afrânio de Melo Franco, 290, Leblon",
        "Leblon, Rio de Janeiro",
    ],
    "teatro_municipal": [
        "Praça Floriano, s/n, Centro, Rio de Janeiro",
        "Praça Floriano, Centro",
        "Cinelândia, Centro, Rio de Janeiro",
    ],
    "sala_cecilia": [
        "Largo da Lapa, 47, Lapa, Rio de Janeiro",
        "Largo da Lapa, 47",
        "Lapa, Rio de Janeiro",
    ],
    "casa_choro": [
        "Rua da Carioca, 38, Centro, Rio de Janeiro",
        "Rua da Carioca, 38",
        "Centro, Rio de Janeiro",
    ],
}

# URLs e APIs para scraping
EVENT_SOURCES: Final[dict[str, str]] = {
    "casa_choro": "https://casadochoro.com.br/agenda/",
    "cecilia_meirelles": "https://www.salaceliciameireles.com.br/",
    "teatro_municipal": "https://theatromunicipal.rj.gov.br/",
    "timeout_rio": "https://www.timeout.com/rio-de-janeiro/teatro",
    "sympla": "https://www.sympla.com.br/eventos/rio-de-janeiro-rj",
}

# User-Agent para web scraping
USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Configurações de cache
CACHE_ENABLED: Final[bool] = True
CACHE_TTL_HOURS: Final[int] = 6

# Configurações de output
MAX_DESCRIPTION_LENGTH: Final[int] = 200  # palavras
OUTPUT_FORMAT: Final[str] = "whatsapp"  # whatsapp, json, markdown

# Configurações de retry e timeout
HTTP_TIMEOUT: Final[int] = 30
MAX_RETRIES: Final[int] = 3

# Threshold mínimo de eventos válidos
MIN_EVENTS_THRESHOLD: Final[int] = 10

# Nível de rigor da validação individual
# "permissive": aceita eventos com pequenas inconsistências, usa LLM para decidir
# "strict": regras rígidas, rejeita qualquer inconsistência
VALIDATION_STRICTNESS: Final[str] = "permissive"

# Configurações de enriquecimento de descrições
ENRICHMENT_ENABLED: Final[bool] = True
ENRICHMENT_MIN_DESC_LENGTH: Final[int] = 40  # palavras - abaixo disso, tentar enriquecer
ENRICHMENT_MAX_SEARCHES: Final[int] = 10  # limite de buscas Perplexity por execução
ENRICHMENT_BATCH_SIZE: Final[int] = 3  # processar N eventos por vez
ENRICHMENT_GENERIC_TERMS: Final[list[str]] = [
    "consultar",
    "elenco rotativo",
    "a confirmar",
    "músicos cariocas",
    "artistas locais",
    "evento tradicional",
]  # termos que indicam descrição genérica
