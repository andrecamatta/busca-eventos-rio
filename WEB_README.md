# 📅 Calendário Web de Eventos Culturais Rio

Aplicação web com calendário interativo para visualização dos eventos culturais encontrados pelo sistema de busca.

## ✨ Funcionalidades

- **📆 Calendário em grade mensal** (estilo Google Calendar) com FullCalendar.js
- **🔍 Filtros avançados** por categoria (Jazz, Teatro-Comédia, Outdoor) e venue específico
- **🔄 Atualização automática** agendada diariamente às 6h da manhã
- **💬 Compartilhamento no WhatsApp** com um clique
- **📱 Responsive design** - funciona perfeitamente em desktop e mobile
- **🎨 Cores por categoria** para fácil identificação visual
- **⚡ API RESTful** com FastAPI para integração com outros sistemas

## 🚀 Instalação Local

### 1. Instalar dependências

```bash
uv sync
```

### 2. Executar busca inicial de eventos

```bash
uv run python main.py
```

### 3. Iniciar servidor web

```bash
./start_web.sh
# ou
uv run uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Acessar a aplicação

Abra o navegador em: **http://localhost:8000**

## 📡 Endpoints da API

### **GET /**
Página principal com calendário interativo

### **GET /api/events**
Lista eventos em formato FullCalendar
- Query params: `categoria` (opcional), `venue` (opcional)
- Exemplo: `http://localhost:8000/api/events?categoria=Jazz`

### **GET /api/stats**
Estatísticas dos eventos
```json
{
  "total_eventos": 46,
  "por_categoria": {"Jazz": 10, "Teatro-Comédia": 15},
  "por_venue": {"Blue Note": 5, "Teatro Municipal": 3},
  "ultima_atualizacao": "2025-11-07T16:14:14.476946"
}
```

### **GET /api/categories**
Lista todas as categorias disponíveis

### **GET /api/venues**
Lista todos os venues disponíveis

### **POST /api/refresh**
Força atualização manual dos eventos (executa main.py em background)

## 🌐 Deploy no Railway

### 1. Preparar repositório

Certifique-se de que os arquivos estão commitados no Git:

```bash
git add .
git commit -m "Add web calendar application"
git push
```

### 2. Deploy no Railway

1. Acesse [railway.app](https://railway.app)
2. Clique em **"New Project" → "Deploy from GitHub repo"**
3. Selecione o repositório `busca_eventos`
4. Railway detectará automaticamente o `railway.json` e `Procfile`

### 3. Configurar variáveis de ambiente

No painel do Railway, adicione as variáveis:

```
OPENROUTER_API_KEY=your_api_key_here
PORT=8000
```

### 4. Deploy automático

O Railway fará o deploy automaticamente. A aplicação estará disponível em:
```
https://seu-projeto.railway.app
```

## 🎨 Estrutura do Projeto Web

```
web/
├── app.py                 # FastAPI application
├── static/
│   ├── css/
│   │   └── style.css      # Estilos customizados
│   └── js/
│       └── calendar.js    # Lógica do calendário
└── templates/
    └── index.html         # Página principal
```

## 🔧 Personalização

### Alterar horário da atualização automática

Edite `web/app.py` linha ~129:

```python
scheduler.add_job(
    run_event_search,
    trigger="cron",
    hour=6,  # ← Altere aqui (0-23)
    minute=0,
    id="daily_event_search"
)
```

### Alterar cores das categorias

Edite `web/app.py` linha ~88:

```python
color_map = {
    "Jazz": "#3498db",           # Azul
    "Teatro-Comédia": "#e74c3c", # Vermelho
    "Outdoor-FimDeSemana": "#2ecc71", # Verde
}
```

### Adicionar novos filtros

1. Adicione o filtro em `web/templates/index.html`
2. Capture o valor em `web/static/js/calendar.js` na função `applyFilters()`
3. Adicione o parâmetro na query da API em `fetchEvents()`

## 📋 Notas Técnicas

- **Framework**: FastAPI 0.115+
- **Frontend**: FullCalendar.js 6.1.10 + Bootstrap 5.3
- **Agendamento**: APScheduler 3.10+
- **Servidor**: Uvicorn com hot-reload em desenvolvimento
- **Dados**: Lê arquivos JSON de `output/latest/`

## 🐛 Troubleshooting

### Calendário não mostra eventos

- Verifique se `output/latest/` existe e contém `verified_events.json`
- Execute `python main.py` para gerar eventos
- Verifique os logs do servidor: `tail -f /tmp/web_app_test.log`

### Erro ao iniciar servidor

```bash
# Reinstalar dependências
uv sync --reinstall

# Verificar porta em uso
lsof -i :8000
```

### Atualização automática não funciona

- Verifique se o scheduler está ativo nos logs
- Certifique-se de que o `OPENROUTER_API_KEY` está configurado
- Verifique permissões de escrita em `output/`

## 📞 Suporte

Para problemas ou dúvidas:
1. Verifique os logs do servidor
2. Teste os endpoints da API diretamente
3. Consulte a documentação do FastAPI: http://localhost:8000/docs

## 🎉 Próximos Passos

Possíveis melhorias futuras:
- [ ] Adicionar autenticação para atualização manual
- [ ] Implementar cache Redis para performance
- [ ] Adicionar exportação para Google Calendar (.ics)
- [ ] Criar view de lista/timeline como alternativa
- [ ] Adicionar notificações push para novos eventos
- [ ] Implementar busca full-text nos eventos
