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
    "search": "perplexity/sonar",               # Busca web em tempo real (otimizado, 80% economia vs Pro)
    "search_simple": "perplexity/sonar",        # Busca web simples (mesmo modelo)
    "light": "google/gemini-2.5-flash",         # QueryOptimizer, FormatAgent (10-20x mais rápido, ~90% menor custo)
    "important": "google/gemini-2.5-flash",     # Verify, Validation, Enrichment, Retry (teste de qualidade)
}

# Configurações de busca
SEARCH_CONFIG: Final[dict] = {
    "location": "Rio de Janeiro",
    "days_ahead": 21,  # 3 semanas
    "start_date": datetime.now(),
    "end_date": datetime.now() + timedelta(days=21),
}

# Categorias de eventos (categorização granular por tipo de evento)
EVENT_CATEGORIES: Final[dict[str, dict]] = {
    "jazz": {
        "keywords": ["jazz", "show jazz", "música jazz", "jazz ao vivo", "jam session jazz"],
        "description": "Shows de jazz",
        "min_events": 4,  # Mínimo de 4 eventos de jazz por execução
    },
    "musica_classica": {
        "keywords": ["música clássica", "musica classica", "concerto", "orquestra", "sinfônica", "sinfonia", "música erudita", "coral", "recital"],
        "description": "Música clássica e erudita",
        "min_events": 2,
    },
    "teatro": {
        "keywords": ["teatro", "peça teatral", "espetáculo teatral", "montagem teatral"],
        "exclude": ["comédia", "stand-up", "humor"],
        "description": "Teatro (exceto comédia)",
    },
    "comedia": {
        "keywords": ["stand-up", "humor", "comédia", "peça cômica", "show de humor"],
        "description": "Comédia e stand-up",
    },
    "cinema": {
        "keywords": ["cinema", "filme", "mostra de cinema", "sessão de cinema", "exibição de filme", "cineclube"],
        "description": "Cinema e mostras de filmes",
    },
    "feira_gastronomica": {
        "keywords": ["feira gastronômica", "feira de comida", "food festival", "festival gastronômico", "mercado gastronômico"],
        "days": ["saturday", "sunday"],
        "description": "Feiras gastronômicas e food festivals",
    },
    "feira_artesanato": {
        "keywords": ["feira de artesanato", "feira de arte", "feira cultural", "artesanato", "feira de design"],
        "days": ["saturday", "sunday"],
        "description": "Feiras de artesanato e arte",
    },
    "outdoor_parques": {
        "keywords": [
            # Locais
            "ao ar livre", "outdoor", "parque", "praia", "jardim botânico", "aterro", "quinta da boa vista",
            "praça", "largo", "orla", "calçadão",
            # Tipos de eventos
            "feira", "feira cultural", "feira de rua", "feirinha",
            "festival", "festival de rua", "festival comunitário",
            "junta local", "corona sunset",
            # Bairros/regiões
            "Ipanema", "Copacabana", "Glória", "Laranjeiras", "Lapa",
            # Temporais
            "fim de semana", "sábado", "domingo",
        ],
        "exclude": [
            # Gêneros musicais específicos (excluir do outdoor)
            "samba", "pagode", "roda de samba", "axé", "forró",
            # Shows mainstream
            "ivete sangalo", "thiaguinho", "alexandre pires", "luan santana",
            "gusttavo lima", "wesley safadão", "simone mendes",
            "turnê", "show nacional", "mega show", "tour brasil",
        ],
        "days": ["saturday", "sunday"],
        "description": "Eventos ao ar livre em fim de semana (culturais/nichados)",
    },
    "cursos_cafe": {
        "keywords": ["curso café", "workshop café", "barista", "degustação café", "coffee tasting"],
        "venues": ["Artemis Torrefação"],
        "description": "Cursos e eventos de café especializado",
    },
}

# Lista GLOBAL de exclusões (aplicada a TODOS os eventos, independente de categoria)
GLOBAL_EXCLUDE_KEYWORDS: Final[list[str]] = [
    # Conteúdo infantil/familiar
    "infantil", "criança", "crianças", "kids", "criancas",
    "infanto-juvenil", "infanto juvenil",
    "família", "familia", "family",
    "para toda família", "para toda a família",
    "sessão infantil", "sessao infantil",
    "indicado para crianças", "indicado para criancas",
    "filme infantil", "filmes infantis", "cinema infantil",
    "sessão dupla", "sessao dupla",
    "oficina infantil", "oficina-infantil",
    "atividade infantil", "atividades infantis",
    "para crianças", "para criancas",
    "pequenos artistas", "crianças e famílias",
    # Conteúdo LGBTQIAPN+
    "lgbt", "lgbtq", "lgbtqia", "lgbtqiapn",
    "pride", "parada gay", "parada lgbtq",
    "diversidade sexual", "queer", "drag queen", "drag king",
    # Eventos conversacionais/educativos não-desejados
    "roda de conversa", "mediação cultural", "mediacao cultural",
    "bate-papo", "palestra", "debate",
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
        "Av. Nossa Senhora de Copacabana, 2241, Copacabana, Rio de Janeiro",
        "Avenida Nossa Senhora de Copacabana, 2241, Copacabana",
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
    "casa_natura": [
        "Shopping Leblon, Av. Afrânio de Melo Franco, 290, Leblon, Rio de Janeiro",
        "Shopping Leblon, Leblon",
        "Leblon, Rio de Janeiro",
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
HTTP_TIMEOUT: Final[int] = 30
MAX_RETRIES: Final[int] = 3

# Threshold mínimo de eventos válidos (apenas eventos de SÁBADO/DOMINGO contam para o threshold)
MIN_EVENTS_THRESHOLD: Final[int] = 10

# Horas mínimas de antecedência para eventos do próprio dia
MIN_HOURS_ADVANCE: Final[int] = 3  # Eventos hoje só aparecem se faltam +3h

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
LINK_QUALITY_THRESHOLD: Final[int] = 50  # score mínimo (0-100) para aceitar link (reduzido para aceitar mais links válidos)
LINK_MAX_INTELLIGENT_SEARCHES: Final[int] = 3  # máximo de tentativas de busca inteligente
REQUIRE_SPECIFIC_ARTISTS: Final[bool] = True  # rejeitar eventos sem artistas específicos
ACCEPT_GENERIC_EVENTS: Final[list[str]] = [
    "roda de choro",
    "jam session",
    "open mic",
    "sarau",
]  # tipos de eventos que aceitam "músicos da casa"

# Configurações de eventos contínuos (temporadas, exposições, mostras)
CONTINUOUS_EVENT_KEYWORDS: Final[list[str]] = [
    "exposição",
    "exposicao",
    "mostra",
    "exibição",
    "exibicao",
    "temporada",
    "em cartaz",
    "visitação",
    "visitacao",
    "aberto ao público",
    "aberto ao publico",
]

CONTINUOUS_EVENT_TYPES: Final[dict[str, str]] = {
    "exposição": "Exposição",
    "exposicao": "Exposição",
    "mostra": "Mostra",
    "exibição": "Exibição",
    "exibicao": "Exibição",
    "temporada": "Temporada",
}

# Limitação de eventos por venue
MAX_EVENTS_PER_VENUE: Final[int] = 25  # máximo de eventos por venue individual
