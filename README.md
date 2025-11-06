# 🎭 Busca Eventos Rio - Sistema Multi-Agente

Sistema inteligente de busca de eventos culturais no Rio de Janeiro usando **Agno** (framework multi-agente) + **OpenRouter** (múltiplos LLMs).

## 🎯 Funcionalidades

Busca automatizada de eventos nas seguintes categorias:
- 🎺 **Shows de jazz**
- 😂 **Teatro comédia** (exceto infantil)
- 🏛️ **Locais especiais**: Casa do Choro, Sala Cecília Meirelles, Teatro Municipal
- 🌳 **Eventos ao ar livre** (fim de semana)

### Pipeline Multi-Agente

1. **🔍 Search Agent** (Gemini Flash 1.5 8B)
   - Busca em múltiplas fontes (DuckDuckGo, web scraping, APIs)
   - Extrai informações básicas dos eventos
   - Estrutura dados com LLM

2. **✅ Verify Agent** (Claude 3.5 Sonnet)
   - Valida informações (datas, links, consistência)
   - Remove duplicatas
   - Verifica critérios (ex: comédia não infantil)
   - Enriquece descrições

3. **📱 Format Agent** (Gemini Flash 1.5)
   - Organiza por data crescente
   - Formata para WhatsApp com emojis
   - Cria resumos de até 200 palavras
   - Output pronto para Ctrl+C + Ctrl+V

## 🚀 Instalação

### Pré-requisitos
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (gerenciador de pacotes)

### Setup

```bash
# Clonar/navegar para o diretório
cd busca_eventos

# Criar arquivo .env com sua chave OpenRouter
cp .env.example .env
# Editar .env e adicionar: OPENROUTER_API_KEY=sua_chave_aqui

# Instalar dependências com uv
uv pip install -e .

# Ou instalar apenas as dependências
uv pip install -r pyproject.toml
```

### Obter API Key do OpenRouter

1. Acesse https://openrouter.ai/keys
2. Crie uma conta (se necessário)
3. Gere uma API key
4. Adicione ao arquivo `.env`:
   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   ```

## 📖 Uso

### Execução Simples

```bash
python main.py
```

### Ou com uv

```bash
uv run main.py
```

### Saída

O script gera os seguintes arquivos em `output/`:

- **`eventos_whatsapp.txt`** - Mensagem formatada para WhatsApp (copiar e colar)
- **`raw_events.json`** - Eventos brutos coletados
- **`structured_events.json`** - Eventos estruturados pelo LLM
- **`verified_events.json`** - Eventos verificados e validados
- **`busca_eventos.log`** - Logs de execução

## ⚙️ Configuração

### `config.py`

Personalize os parâmetros de busca:

```python
# Período de busca
SEARCH_CONFIG = {
    "days_ahead": 21,  # Alterar para mais/menos semanas
}

# Modelos OpenRouter
MODELS = {
    "search": "google/gemini-flash-1.5-8b",  # Busca rápida
    "verify": "anthropic/claude-3.5-sonnet",  # Verificação rigorosa
    "format": "google/gemini-flash-1.5",     # Formatação
}

# Tamanho do resumo
MAX_DESCRIPTION_LENGTH = 200  # palavras
```

### Categorias de Eventos

Edite `EVENT_CATEGORIES` em `config.py` para adicionar/remover categorias:

```python
EVENT_CATEGORIES = {
    "jazz": {
        "keywords": ["jazz", "show jazz", "música jazz"],
    },
    # ... adicionar mais categorias
}
```

## 🏗️ Arquitetura

```
busca_eventos/
├── main.py              # Orquestrador principal
├── config.py            # Configurações
├── agents/              # Agentes Agno
│   ├── search_agent.py  # Busca de eventos
│   ├── verify_agent.py  # Verificação e validação
│   └── format_agent.py  # Formatação WhatsApp
├── tools/               # Ferramentas de busca
│   ├── web_search.py    # DuckDuckGo
│   └── scraper.py       # Web scraping
└── output/              # Resultados (criado automaticamente)
```

## 🔧 Desenvolvimento

### Executar testes

```bash
uv run pytest
```

### Linting

```bash
uv run ruff check .
uv run ruff format .
```

### Adicionar dependências

```bash
uv pip install nome-pacote
# Atualizar pyproject.toml manualmente
```

## 📝 Exemplo de Saída

```
🎭 EVENTOS RIO - Próximas 3 Semanas
Atualizado em: 05/11/2025 às 14:30

📅 **15/11/2025 - Sexta**
🎺 **Quarteto de Jazz - Casa do Choro**
⏰ 20h | 💰 R$ 40-60
📍 Casa do Choro - Centro
🎫 https://casadochoro.com.br/ingressos
📝 Show intimista com quarteto de jazz apresentando clássicos
brasileiros e composições autorais...

📅 **16/11/2025 - Sábado**
😂 **Stand-up: Paulo Vieira**
⏰ 21h | 💰 R$ 80-150
📍 Teatro Municipal
🎫 https://ingressos.com/paulo-vieira
📝 Comédia stand-up com um dos maiores nomes do humor brasileiro...
```

## ⚠️ Limitações

- **Web Scraping**: Seletores CSS podem quebrar se sites mudarem estrutura
- **Datas**: Alguns sites não expõem datas em formato estruturado
- **APIs**: Sympla/Eventbrite podem requerer autenticação adicional
- **Custos**: OpenRouter cobra por token (modelos otimizados para custo-benefício)

## 🤝 Contribuindo

Melhorias são bem-vindas! Áreas para contribuir:

- Adicionar mais fontes de eventos
- Melhorar extração de datas/horários
- Implementar cache de resultados
- Adicionar mais categorias
- Integração com APIs oficiais (Sympla, Eventbrite)

## 📄 Licença

MIT

## 🙏 Créditos

- **Agno**: Framework multi-agente Python
- **OpenRouter**: API unificada para múltiplos LLMs
- **DuckDuckGo Search**: Busca web gratuita
