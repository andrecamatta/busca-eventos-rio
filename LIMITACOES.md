# ⚠️ Limitações e Status do Projeto

## Status Atual: **FUNCIONAL MAS NÃO TESTADO EM PRODUÇÃO**

O código está completo e sintaticamente correto, mas **ainda não foi executado com chaves de API reais**.

## ❌ Funcionalidades NÃO Implementadas Completamente

### 1. **Web Scraping Real**
- ✅ Estrutura básica implementada
- ❌ Seletores CSS são genéricos e precisam ser ajustados para cada site
- ❌ Sites podem bloquear scraping ou mudar estrutura HTML
- **Solução**: Executar e ajustar seletores conforme estrutura real dos sites

### 2. **Extração de Datas/Horários**
- ✅ Lógica de parsing implementada
- ❌ Formatos de data variam muito entre sites
- ❌ LLM pode ter dificuldade em extrair datas não estruturadas
- **Solução**: Testar com dados reais e melhorar prompts

### 3. **Validação de Links**
- ✅ Código de validação HTTP implementado
- ❌ Timeout pode ser muito curto para alguns sites
- ❌ Alguns sites podem requerer JavaScript (não funciona com httpx)
- **Solução**: Ajustar timeouts ou usar Playwright para validação

### 4. **APIs de Terceiros**
- ❌ Sympla API não está implementada (requer credenciais)
- ❌ Eventbrite API não está implementada (requer credenciais)
- ❌ Google Custom Search não implementado
- **Solução**: Adicionar integrações conforme credenciais disponíveis

## ⚠️ Problemas Conhecidos

### 1. **Custos OpenRouter**
- Modelo de verificação (Claude Sonnet) é **caro**
- Processamento de muitos eventos pode gerar custos significativos
- **Mitigação**: Ajustar para modelos mais baratos ou implementar cache

### 2. **Rate Limiting**
- DuckDuckGo pode bloquear se fizer muitas requisições
- Sites podem bloquear IP ao detectar scraping
- **Mitigação**: Adicionar delays entre requisições

### 3. **Qualidade dos Resultados**
- Busca web retorna resultados genéricos (nem sempre são eventos)
- LLM pode "alucinar" informações se dados forem ambíguos
- Descrições podem ser imprecisas
- **Mitigação**: Agente de verificação rigoroso (já implementado)

### 4. **Eventos Fora do Período**
- LLM pode incluir eventos fora das 3 semanas se datas não estiverem claras
- **Mitigação**: Verificador deve remover (já implementado)

### 5. **Eventos Infantis em Comédia**
- Detecção depende de palavras-chave ("infantil", "kids", "criança")
- Pode deixar passar eventos infantis sem essas palavras
- **Mitigação**: Melhorar prompt do verificador

## 🔧 Melhorias Necessárias

### Prioridade Alta
1. **Testar com API key real**
2. **Ajustar seletores CSS após scraping real**
3. **Melhorar extração de datas** (adicionar mais formatos)
4. **Implementar cache de resultados** (evitar buscas repetidas)

### Prioridade Média
5. **Adicionar Playwright** para sites JavaScript-heavy
6. **Implementar APIs oficiais** (Sympla, Eventbrite)
7. **Adicionar retry logic** mais robusto
8. **Melhorar formatação WhatsApp** (testar em dispositivo real)

### Prioridade Baixa
9. **Adicionar testes unitários**
10. **Implementar interface web** (opcional)
11. **Adicionar notificações** (email, Telegram)
12. **Banco de dados** para histórico

## 🧪 Como Testar

### Teste Mínimo (sem API key)
```bash
# Verificar sintaxe
python3 -m py_compile *.py agents/*.py tools/*.py

# Ver estrutura
python3 -c "from config import *; print(EVENT_CATEGORIES)"
```

### Teste Básico (com API key)
```bash
# Configurar .env
echo "OPENROUTER_API_KEY=sua_chave" > .env

# Executar
python main.py
```

### Teste Completo
1. Configurar .env
2. Executar e verificar logs em `busca_eventos.log`
3. Verificar arquivos em `output/`
4. Copiar `output/eventos_whatsapp.txt` e testar no WhatsApp

## 📊 Estimativa de Custos OpenRouter

Com base nos modelos configurados:

| Agente | Modelo | Custo Estimado (1000 tokens) |
|--------|--------|------------------------------|
| Search | Gemini Flash 1.5 8B | $0.0001 - $0.0003 |
| Verify | Claude 3.5 Sonnet | $0.003 - $0.015 |
| Format | Gemini Flash 1.5 | $0.0001 - $0.0005 |

**Custo estimado por execução**: $0.05 - $0.50 USD

(Depende da quantidade de eventos encontrados e tamanho dos dados)

## 🚀 Próximos Passos Recomendados

1. **Execute primeiro com poucos eventos** (teste com 1 semana ao invés de 3)
2. **Monitore logs** para identificar problemas
3. **Ajuste prompts** conforme resultados
4. **Implemente cache** se for executar frequentemente
5. **Considere modelos mais baratos** para produção

## 💡 Dicas de Uso

- **Primeira execução**: Use período curto (7 dias) para testar
- **Horários**: Execute fora de horário de pico para evitar rate limiting
- **Logs**: Sempre verifique `busca_eventos.log` para debugging
- **Output**: Arquivos JSON são úteis para análise e debugging

## 📞 Suporte

Em caso de problemas:
1. Verifique `busca_eventos.log`
2. Verifique se `.env` está configurado
3. Teste conectividade: `curl https://openrouter.ai/api/v1/models`
4. Verifique saldo OpenRouter
