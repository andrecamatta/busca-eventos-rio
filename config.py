"""Configurações do sistema de busca de eventos."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# Carregar .env do diretório raiz do projeto
BASE_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

# OpenRouter API Configuration
OPENROUTER_API_KEY: Final[str] = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"

# Firecrawl API Configuration
FIRECRAWL_API_KEY: Final[str] = os.getenv("FIRECRAWL_API_KEY", "")

# Modelos OpenRouter por função (otimização de custo vs performance)
MODELS: Final[dict[str, str]] = {
    "search": "perplexity/sonar",               # Sonar: Web search rápido e econômico (Perplexity indexing)
    "search_complementary": "google/gemini-2.5-flash:online",  # Gemini Flash com web search (Exa.ai indexing)
    "search_simple": "perplexity/sonar",        # Sonar: Web search simples
    "light": "google/gemini-2.5-flash",         # QueryOptimizer, FormatAgent (10-20x mais rápido, ~90% menor custo)
    "important": "google/gemini-2.5-flash",     # Verify, Validation, Enrichment, Retry (teste de qualidade)
    "judge": "openai/gpt-5",                    # Julgamento de qualidade de eventos (high effort)
    "link_consensus": "openai/gpt-5-mini:online",  # Tiebreaker para consenso de links (GPT-5 Mini com web search)
}

# Modelo para extração de eventos DiarioDoRio
GEMINI_FLASH_MODEL: Final[str] = "google/gemini-2.5-flash"

# Configurações de busca
SEARCH_CONFIG: Final[dict] = {
    "location": "Rio de Janeiro",
    "days_ahead": 21,  # 3 semanas
    "start_date": datetime.now(),
    "end_date": datetime.now() + timedelta(days=21),
}

# NOTA: EVENT_CATEGORIES foi migrado para prompts/search_prompts.yaml
# Use utils.category_registry.CategoryRegistry para acessar categorias dinamicamente

# Lista GLOBAL de exclusões (aplicada a TODOS os eventos, independente de categoria)
GLOBAL_EXCLUDE_KEYWORDS: Final[list[str]] = [
    # Conteúdo infantil/familiar (termos EXPLÍCITOS apenas)
    "infantil", "criança", "crianças", "kids", "criancas",
    "infanto-juvenil", "infanto juvenil",
    "para toda família", "para toda a família",  # Manter apenas expressão completa
    "sessão infantil", "sessao infantil",
    "indicado para crianças", "indicado para criancas",
    "filme infantil", "filmes infantis", "cinema infantil",
    "sessão dupla", "sessao dupla",
    "oficina infantil", "oficina-infantil",
    "atividade infantil", "atividades infantis",
    "para crianças", "para criancas",
    "pequenos artistas",
    # REMOVIDO: "família", "familia", "family" - muito genérico, remove eventos legítimos
    # REMOVIDO: "crianças e famílias" - muito genérico

    # Conteúdo LGBTQIAPN+
    "lgbt", "lgbtq", "lgbtqia", "lgbtqiapn",
    "pride", "parada gay", "parada lgbtq",
    "diversidade sexual", "queer", "drag queen", "drag king",
    # Eventos conversacionais/educativos não-desejados
    "roda de conversa", "mediação cultural", "mediacao cultural",
    "bate-papo", "debate",
    # REMOVIDO: "palestra" - muito genérico, vários eventos têm palestras complementares
]

# Venues obrigatórios (deve ter pelo menos 1 evento de cada)
REQUIRED_VENUES: Final[dict[str, list[str]]] = {
    "teatro_municipal": ["Teatro Municipal", "Theatro Municipal"],
    "sala_cecilia": ["Sala Cecília Meireles", "Cecília Meireles", "Cecilia Meireles", "Sala Cecília Meirelles", "Cecília Meirelles"],
    "blue_note": ["Blue Note Rio", "Blue Note", "BlueNote"],
    "artemis": ["Artemis", "Artemis Torrefação", "Artemis - Torrefação Artesanal e Cafeteria"],
}

# Endereços reais dos venues (para validação rigorosa)
VENUE_ADDRESSES: Final[dict[str, list[str]]] = {
    "artemis_torrefacao": [
        "Rua Conde de Bonfim, 751, Tijuca, Rio de Janeiro",
        "Conde de Bonfim, 751, Tijuca",
        "Tijuca, Rio de Janeiro",
    ],
    "blue_note": [
        "Av. Atlântica, 1910 - Copacabana, Rio de Janeiro - RJ",
        "Avenida Atlântica, 1910, Copacabana",
        "Av. Atlântica, 1910, Leme, Rio de Janeiro",
        "Copacabana, Rio de Janeiro",
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
    "ccbb_rio": [
        "Rua Primeiro de Março, 66, Centro, Rio de Janeiro",
        "R. Primeiro de Março, 66, Centro",
        "Centro, Rio de Janeiro",
    ],
    "sesc_copacabana": [
        "Rua Domingos Ferreira, 160, Copacabana, Rio de Janeiro",
        "Domingos Ferreira, 160, Copacabana",
        "Copacabana, Rio de Janeiro",
    ],
    "sesc_flamengo": [
        "Rua Marquês de Abrantes, 99, Flamengo, Rio de Janeiro",
        "Marquês de Abrantes, 99, Flamengo",
        "Flamengo, Rio de Janeiro",
    ],
    "sesc_tijuca": [
        "Rua Barão de Mesquita, 539, Tijuca, Rio de Janeiro",
        "Barão de Mesquita, 539, Tijuca",
        "Tijuca, Rio de Janeiro",
    ],
    "sesc_engenho": [
        "Rua Borja Reis, 291, Engenho de Dentro, Rio de Janeiro",
        "Borja Reis, 291, Engenho de Dentro",
        "Engenho de Dentro, Rio de Janeiro",
    ],
    "mam_cinema": [
        "Av. Infante Dom Henrique, 85, Parque do Flamengo, Rio de Janeiro",
        "Parque do Flamengo",
        "Flamengo, Rio de Janeiro",
    ],
    "theatro_net": [
        "Rua Siqueira Campos, 143, Copacabana, Rio de Janeiro",
        "Siqueira Campos, 143, Copacabana",
        "Copacabana, Rio de Janeiro",
    ],
    "parque_lage": [
        "Rua Jardim Botânico, 414, Jardim Botânico, Rio de Janeiro",
        "Jardim Botânico, 414",
        "Jardim Botânico, Rio de Janeiro",
    ],
    "ims": [
        "Rua Marquês de São Vicente, 476, Gávea, Rio de Janeiro",
        "Marquês de São Vicente, 476, Gávea",
        "Gávea, Rio de Janeiro",
    ],
    "oi_futuro": [
        "Rua Dois de Dezembro, 63, Ipanema, Rio de Janeiro",
        "Dois de Dezembro, 63, Flamengo",
        "Ipanema, Rio de Janeiro",
        "Flamengo, Rio de Janeiro",
    ],
    "ccjf": [
        "Av. Rio Branco, 241, Centro, Rio de Janeiro",
        "Rio Branco, 241, Centro",
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
HTTP_TIMEOUT: Final[int] = 15  # Otimizado: reduzido de 30s para 15s (links lentos geralmente têm problemas)
MAX_RETRIES: Final[int] = 3
LINK_VALIDATION_MAX_CONCURRENT: Final[int] = 30  # Otimizado: aumentado de 10 para 30 (3x mais requisições paralelas)

# Threshold mínimo de eventos válidos (apenas eventos de SÁBADO/DOMINGO contam para o threshold)
MIN_EVENTS_THRESHOLD: Final[int] = 10

# Horas mínimas de antecedência para eventos do próprio dia
MIN_HOURS_ADVANCE: Final[int] = 3  # Eventos hoje só aparecem se faltam +3h

# Nível de rigor da validação individual
# "permissive": aceita eventos com pequenas inconsistências, usa LLM para decidir
# "strict": regras rígidas, rejeita qualquer inconsistência
VALIDATION_STRICTNESS: Final[str] = "permissive"

# Configurações de enriquecimento de descrições
ENRICHMENT_ENABLED: Final[bool] = False  # OTIMIZAÇÃO: Desabilitado para economizar -20 chamadas API
TITLE_ENHANCEMENT_ENABLED: Final[bool] = False  # OTIMIZAÇÃO: Desabilitado para economizar -20 chamadas Gemini
EVENT_CLASSIFIER_ENABLED: Final[bool] = False  # OTIMIZAÇÃO: Desabilitado, SearchAgent já categoriza (-3 chamadas Gemini)
ENRICHMENT_MIN_DESC_LENGTH: Final[int] = 40  # palavras - abaixo disso, tentar enriquecer
ENRICHMENT_MAX_SEARCHES: Final[int] = 30  # Otimizado: reduzido de 50 para 30 (evitar buscas desnecessárias)
ENRICHMENT_BATCH_SIZE: Final[int] = 10  # Otimizado: aumentado de 3 para 10 (processar mais eventos em paralelo)
ENRICHMENT_GENERIC_TERMS: Final[list[str]] = [
    "consultar",
    "elenco rotativo",
    "a confirmar",
    "músicos cariocas",
    "artistas locais",
    "evento tradicional",
    "programa a confirmar",
    "solistas a confirmar",
    "músicos da casa",
]  # termos que indicam descrição genérica

# Mapeamento de venues para consolidação (aliases)
VENUE_ALIASES: Final[dict[str, str]] = {
    # CCBB - consolidar todos os sub-venues
    "CCBB Teatro e Cinema": "CCBB Rio - Centro Cultural Banco do Brasil",
    "CCBB Teatro I": "CCBB Rio - Centro Cultural Banco do Brasil",
    "CCBB Teatro II": "CCBB Rio - Centro Cultural Banco do Brasil",
    "CCBB Teatro III": "CCBB Rio - Centro Cultural Banco do Brasil",
    "CCBB Cinema": "CCBB Rio - Centro Cultural Banco do Brasil",

    # Sala Cecília Meireles - variações de nome
    "Cecília Meirelles": "Sala Cecília Meireles",
    "Sala Cecilia Meireles": "Sala Cecília Meireles",
}

# Configurações de validação de qualidade de links
LINK_QUALITY_THRESHOLD: Final[int] = 65  # score mínimo (0-100) para aceitar link (aumentado para rejeitar links genéricos)
LINK_MAX_INTELLIGENT_SEARCHES: Final[int] = 5  # máximo de tentativas de busca inteligente (aumentado para melhor recovery)
REQUIRE_SPECIFIC_ARTISTS: Final[bool] = True  # rejeitar eventos sem artistas específicos
ACCEPT_GENERIC_EVENTS: Final[list[str]] = [
    "roda de choro",
    "jam session",
    "open mic",
    "sarau",
]  # tipos de eventos que aceitam "músicos da casa"

# Configurações de validação de conteúdo de links
LINK_VALIDATION: Final[dict[str, float]] = {
    "title_match_threshold": 0.7,  # % mínima de palavras do título no HTML
    "venue_match_threshold": 0.4,   # % mínima de palavras do local no HTML
    "min_page_length": 50,          # caracteres mínimos (detectar soft 404s)
    "min_description_words": 20,    # palavras mínimas na descrição
}

# Status de validação de links (constantes para evitar typos)
class LinkStatus:
    """Status possíveis de validação de links."""
    ACCESSIBLE = "accessible"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    FORBIDDEN = "forbidden"
    ERROR = "error"

# Configurações de consenso de links (Fase 2 - Anti-alucinação)
LINK_CONSENSUS_ENABLED: Final[bool] = True  # Habilitar consenso multi-modelo
LINK_CONSENSUS_SEARCHES: Final[int] = 2  # Número de buscas independentes no Perplexity (otimizado: 2 em vez de 3)
LINK_CONSENSUS_THRESHOLD: Final[float] = 0.5  # 50% precisam concordar (1/2 = consenso simples)
LINK_CONSENSUS_USE_GPT5_TIEBREAKER: Final[bool] = True  # Usar GPT-5 Mini como desempate em caso de empate (crítico com 2 buscas)

# Configurações de eventos contínuos (temporadas, exposições)
# NOTA: "mostra" removido para evitar consolidação indevida de filmes de festivais de cinema
CONTINUOUS_EVENT_KEYWORDS: Final[list[str]] = [
    "exposição",
    "exposicao",
    # "mostra",  # REMOVIDO: causava consolidação de filmes de festivais de cinema
    "temporada",
    "em cartaz",
    "visitação",
    "visitacao",
]

CONTINUOUS_EVENT_TYPES: Final[dict[str, str]] = {
    "exposição": "Exposição",
    "exposicao": "Exposição",
    # "mostra": "Mostra",  # REMOVIDO: sincronizado com KEYWORDS
    "temporada": "Temporada",
}

# Limitação de eventos por venue
MAX_EVENTS_PER_VENUE: Final[int] = 25  # máximo de eventos por venue individual

# Configurações de julgamento de qualidade
JUDGE_BATCH_SIZE: Final[int] = 10  # Otimizado: aumentado de 5 para 10 (menos batches, mais eventos por chamada GPT-5)
JUDGE_TIMEOUT: Final[int] = 300  # timeout em segundos por batch (5 minutos)
JUDGE_EFFORT: Final[str] = "high"  # esforço do modelo GPT-5
JUDGE_MAX_LINK_CHARS: Final[int] = 2000  # máximo de chars do HTML do link para análise

# ═══════════════════════════════════════════════════════════
# CONFIGURAÇÃO DE TESTE / PRODUÇÃO
# ═══════════════════════════════════════════════════════════
# Controla quais categorias e venues são habilitados (permite testes focados e end-to-end baratos)

# Categorias habilitadas (controla busca, validação e thresholds)
# IDs disponíveis (novos): shows, teatro, gastronomia, atividades_ar_livre, cinema,
#                          exposicoes, literatura, festas, jazz, comedia, musica_classica,
#                          artesanato, cursos
ENABLED_CATEGORIES: Final[list[str]] = [
    "jazz",  # Shows de jazz (Blue Note, Maze Jazz Club, etc.)
    "gastronomia",  # Eventos gastronômicos e feiras de comida
    "atividades_ar_livre",  # Cinema ao ar livre, shows em parques, feiras culturais
    # Outras categorias disponíveis:
    # "musica_classica", "teatro", "comedia", "cinema",
    # "shows", "exposicoes", "literatura", "festas", "artesanato", "cursos",
]

# Mínimos de eventos por categoria (apenas para categorias habilitadas)
CATEGORY_MIN_EVENTS: Final[dict[str, int]] = {
    # "outdoor_parques": 0,  # Sem mínimo para teste
    # Descomente para produção:
    # "jazz": 4,
    # "musica_classica": 2,
}

# Venues habilitados (controla busca e validação)
# IDs disponíveis: casa_choro, sala_cecilia, teatro_municipal, artemis, ccbb, oi_futuro, ims,
#                  parque_lage, ccjf, mam_cinema, theatro_net, ccbb_teatro_cinema,
#                  istituto_italiano, maze_jazz, teatro_leblon, clube_jazz_rival, estacao_net
ENABLED_VENUES: Final[list[str]] = [
    # TESTE: nenhum venue habilitado (scrapers Blue Note/Cecília/CCBB/Municipal rodam sempre)
    # Descomente para produção:
    # "casa_choro", "sala_cecilia", "teatro_municipal", "artemis", "ccbb",
    # "oi_futuro", "ims", "parque_lage", "ccjf", "mam_cinema",
    # "theatro_net", "ccbb_teatro_cinema", "istituto_italiano",
    # "maze_jazz", "teatro_leblon", "clube_jazz_rival", "estacao_net",
]

# Thresholds globais (genéricos - não dependem de categorias específicas)
MIN_WEEKEND_EVENTS: Final[int] = 2  # Mínimo de eventos de fim de semana (sábado/domingo)
MIN_TOTAL_EVENTS: Final[int] = 2    # Mínimo de eventos no total

def get_enabled_required_venues() -> dict[str, list[str]]:
    """Retorna apenas venues obrigatórios que estão habilitados em ENABLED_VENUES."""
    if not ENABLED_VENUES:
        return {}

    active_venues = {}
    for venue_key, venue_names in REQUIRED_VENUES.items():
        if venue_key in ENABLED_VENUES:
            active_venues[venue_key] = venue_names

    return active_venues


def get_enabled_category_minimums() -> dict[str, int]:
    """Retorna mínimos de eventos apenas para categorias habilitadas."""
    minimums = {}
    for category_id in ENABLED_CATEGORIES:
        min_events = CATEGORY_MIN_EVENTS.get(category_id, 0)
        if min_events > 0:
            minimums[category_id] = min_events

    return minimums
