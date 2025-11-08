# 🎭 Busca Eventos Rio - Sistema Multi-Agente + Calendário Web

Sistema inteligente de busca e visualização de eventos culturais no Rio de Janeiro usando **Agno** (framework multi-agente) + **OpenRouter** (múltiplos LLMs) + **FastAPI** (calendário web interativo).

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python)](https://www.python.org/)
[![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=flat&logo=railway)](https://railway.app)

## 🎯 Funcionalidades

### 📅 Calendário Web Interativo (NOVO!)
- **Grade mensal** estilo Google Calendar com FullCalendar.js
- **Filtros avançados** por categoria e venue
- **Compartilhamento WhatsApp** integrado
- **Atualização automática** diária às 6h
- **Design responsivo** com Bootstrap 5
- **API RESTful** com 6 endpoints

### 🤖 Busca Automatizada
Busca inteligente em 20 venues e categorias:
- 🎺 **Jazz** - Blue Note Rio e venues especializados
- 😂 **Teatro comédia** (exceto infantil)
- 🏛️ **16 venues culturais**: CCBB, Teatro Municipal, Casa do Choro, Sesc Rio (4 unidades), MAM Cinema, IMS, Parque Lage, CCJF, Artemis
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

4. **🌐 Web Application** (FastAPI + FullCalendar.js)
   - Calendário interativo com modal de detalhes
   - Filtros dinâmicos e busca inteligente
   - Atualização automática com APScheduler
   - Compartilhamento direto no WhatsApp

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

### 🔍 Buscar Eventos (CLI)

```bash
# Executar busca
uv run python main.py

# Ou simplesmente
python main.py
```

### 🌐 Iniciar Calendário Web

```bash
# Modo desenvolvimento (com hot-reload)
./start_web.sh

# Ou manualmente
uv run uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload
```

Acesse: **http://localhost:8000**

### 📂 Saída

O script gera arquivos em `output/YYYY-MM-DD_HH-MM-SS/`:

- **`eventos_whatsapp.txt`** - Mensagem formatada para WhatsApp (copiar e colar)
- **`raw_events.json`** - Eventos brutos coletados
- **`structured_events.json`** - Eventos estruturados pelo LLM
- **`verified_events.json`** - Eventos verificados e validados (usado pelo calendário web)
- **`enriched_events_initial.json`** - Eventos enriquecidos com descrições detalhadas

**Atalho**: `output/latest/` sempre aponta para a execução mais recente.

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
busca-eventos-rio/
├── main.py                  # Orquestrador principal
├── config.py                # Configurações
├── agents/                  # Agentes Agno
│   ├── search_agent.py      # 20 micro-searches paralelas
│   ├── verify_agent.py      # Validação de links
│   ├── validation_agent.py  # Validação LLM de eventos
│   ├── enrichment_agent.py  # Enriquecimento de descrições
│   ├── format_agent.py      # Formatação WhatsApp
│   └── retry_agent.py       # Retry automático
├── models/
│   └── event_models.py      # Modelos Pydantic
├── utils/
│   ├── agent_factory.py     # Factory de agentes
│   ├── file_manager.py      # Gestão de arquivos
│   └── eventim_scraper.py   # Scraper Eventim (fallback)
├── web/                     # 🆕 Aplicação Web
│   ├── app.py               # FastAPI backend
│   ├── templates/
│   │   └── index.html       # Calendário FullCalendar
│   └── static/
│       ├── css/style.css
│       └── js/calendar.js
├── output/                  # Resultados (criado automaticamente)
├── railway.json             # Config Railway deploy
├── Procfile                 # Railway start command
└── start_web.sh             # Script para iniciar web app
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

## 🌐 API Endpoints

### **GET /**
Página principal com calendário interativo

### **GET /api/events**
Lista eventos em formato FullCalendar
```bash
curl "http://localhost:8000/api/events?categoria=Jazz&venue=Blue%20Note"
```

### **GET /api/stats**
Estatísticas dos eventos
```json
{
  "total_eventos": 46,
  "por_categoria": {"Jazz": 10, "Teatro-Comédia": 15},
  "por_venue": {"Blue Note": 5, "CCBB Rio": 3}
}
```

### **GET /api/categories** & **GET /api/venues**
Lista categorias e venues disponíveis

### **POST /api/refresh**
Força atualização manual dos eventos (executa `main.py` em background)

## 🚀 Deploy no Railway

1. **Conectar repositório**
   ```bash
   # Via Railway CLI
   railway link
   ```

2. **Configurar variáveis**
   ```bash
   railway variables set OPENROUTER_API_KEY=sk-or-v1-...
   ```

3. **Deploy automático**
   O Railway detectará `railway.json` e fará deploy automaticamente!

## ⚠️ Limitações

- **Limite por venue**: Máximo 5 eventos por venue (priorização inteligente por link, descrição, proximidade)
- **Cobertura temporal**: 3 semanas à frente (configurável)
- **Filtros de qualidade**: Exclusão automática de eventos mainstream (samba, pagode, turnês)
- **Custos**: OpenRouter cobra por token (~$0.50-2.00 por execução completa)

## 📚 Documentação Adicional

- **[WEB_README.md](WEB_README.md)** - Documentação completa da aplicação web
- **[GUIA_ANALISE.md](GUIA_ANALISE.md)** - Guia de análise do sistema
- **[LIMITACOES.md](LIMITACOES.md)** - Limitações conhecidas e workarounds

## 🤝 Contribuindo

Melhorias são bem-vindas! Áreas para contribuir:

- Adicionar mais venues culturais
- Melhorar extração de datas/horários
- Implementar cache Redis para performance
- Adicionar exportação para Google Calendar (.ics)
- Criar notificações push para novos eventos
- Integração com APIs oficiais (Sympla, Eventbrite)

## 📄 Licença

MIT

## 🙏 Créditos

- **[Agno](https://github.com/agno-agi/agno)** - Framework multi-agente Python
- **[OpenRouter](https://openrouter.ai/)** - API unificada para múltiplos LLMs
- **[Perplexity AI](https://www.perplexity.ai/)** - Busca web em tempo real (Sonar Pro)
- **[FullCalendar](https://fullcalendar.io/)** - Biblioteca de calendário interativo
- **[FastAPI](https://fastapi.tiangolo.com/)** - Framework web moderno e rápido
- **[Railway](https://railway.app/)** - Plataforma de deploy simplificada

---

**Desenvolvido com 🤖 [Claude Code](https://claude.com/claude-code)**

*Encontre os melhores eventos culturais no Rio de Janeiro!* 🎭🎺🎨
