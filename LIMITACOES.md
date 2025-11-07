# ⚠️ Limitações e Status do Projeto

## Status Atual: **✅ FUNCIONAL E TESTADO**

O sistema foi executado com sucesso em produção e está gerando eventos de forma confiável.

**Última execução**: 06/11/2025 (duração: ~8 minutos)
**Resultado**: 16 eventos válidos de 17 encontrados inicialmente (score: 91%)

## ✅ Funcionalidades Implementadas e Funcionando

### 1. **Busca Web em Tempo Real**
- ✅ Usa Perplexity Sonar Pro para busca web em tempo real
- ✅ Busca paralela em 7 categorias/venues simultaneamente
- ✅ Extração estruturada de eventos com validação Pydantic
- ✅ Sistema de retry automático para buscas complementares

### 2. **Extração de Datas/Horários**
- ✅ Parser robusto de múltiplos formatos de data
- ✅ Validação de datas com range configurável
- ✅ Suporte a festivais multi-dia com validação de range
- ✅ Correção automática de datas divergentes (modo permissive)

### 3. **Validação de Links**
- ✅ Validação HTTP com timeout de 30s
- ✅ Detecção de links genéricos (homepages, listagens)
- ✅ Busca inteligente de links específicos para eventos sem link
- ✅ Retry automático para erros temporários (3 tentativas)

### 4. **Enriquecimento e Formatação**
- ✅ Enriquecimento de descrições usando Perplexity
- ✅ Consolidação e remoção de duplicatas
- ✅ Formatação otimizada para WhatsApp

## ⚠️ Limitações Conhecidas

### 1. **Cobertura de Links**
- ⚠️ ~41% dos eventos não têm link de compra de ingresso
- **Causa**: Eventos gratuitos, venues sem sistema online, ou links não encontrados
- **Mitigação**: Busca complementar implementada, mas nem sempre eficaz

### 2. **APIs Não Implementadas**
- ❌ Sympla API direta não está implementada
- ❌ Eventbrite API direta não está implementada
- **Impacto**: Depende de busca web via Perplexity (funciona mas pode ser menos precisa)
- **Solução futura**: Implementar APIs oficiais se credenciais disponíveis

## 🐛 Problemas Resolvidos Recentemente (06/11/2025)

### ✅ **Links Genéricos**
- **Problema**: Links como `bluenoterio.com.br/shows/` passavam pela validação
- **Solução**: Melhorada detecção de links genéricos com padrões regex e validação de path

### ✅ **Festivais Multi-dia**
- **Problema**: Eventos como "Conexão Rio Festival" eram rejeitados por divergência de data
- **Solução**: Implementada validação de range para festivais com múltiplos dias

### ✅ **Timeout HTTP Insuficiente**
- **Problema**: Sympla com Queue-it excedia timeout de 10s
- **Solução**: Aumentado timeout para 30s globalmente

### ✅ **Logs de Debug Poluindo Output**
- **Problema**: 20+ linhas de logs "🔍 DEBUG:" em nível INFO
- **Solução**: Convertidos para logger.debug() ou removidos

## ⚠️ Problemas Ativos

### 1. **Custos de API**
- Perplexity Sonar Pro: ~$0.003-0.015 por 1000 tokens
- Processamento completo: estimado $0.50-2.00 USD por execução
- **Mitigação**: Usar modelos mais baratos para produção (já configurado)

### 2. **Qualidade dos Resultados**
- Busca pode retornar eventos genéricos ou desatualizados
- LLM ocasionalmente "alucina" informações
- **Mitigação**: Validação rigorosa em múltiplas camadas implementada

### 3. **Cobertura de Venues Específicos**
- Casa do Choro teve 0 eventos na busca inicial (requeria busca complementar)
- **Impacto**: Sistema detecta e faz busca complementar automaticamente

## 🔧 Melhorias Recomendadas

### Prioridade Alta
1. ✅ ~~Testar com API key real~~ (CONCLUÍDO)
2. **Melhorar cobertura de links** - Apenas 41% dos eventos têm link
3. **Implementar cache de resultados** - Evitar buscas repetidas
4. **Refatorar agentes de validação** - Consolidar verify_agent.py e validation_agent.py

### Prioridade Média
5. **Implementar APIs oficiais** - Sympla e Eventbrite para links mais confiáveis
6. ✅ ~~Adicionar retry logic robusto~~ (CONCLUÍDO)
7. **Adicionar testes automatizados** - pytest com mocks
8. **Monitoramento de custos** - Rastrear gastos com tokens

### Prioridade Baixa
9. **Interface web** - Dashboard para configuração e monitoramento
10. **Notificações** - Email ou Telegram quando novos eventos são encontrados
11. **Banco de dados** - Histórico de eventos e deduplicação entre execuções
12. **CI/CD** - Automação de testes e deploy

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

## 📊 Estimativa de Custos (Última Execução: 06/11/2025)

Modelos em uso (via OpenRouter):

| Componente | Modelo | Função | Custo Estimado |
|-----------|--------|---------|----------------|
| Busca | Perplexity Sonar Pro | Busca web em tempo real | $0.003/1K tokens |
| Verificação | Gemini Flash 1.5 | Validação de eventos | $0.0001/1K tokens |
| Enriquecimento | Perplexity Sonar Pro | Descrições detalhadas | $0.003/1K tokens |
| Formatação | Gemini Flash 1.5 | Formatação WhatsApp | $0.0001/1K tokens |

**Custo real estimado por execução completa**: $0.50 - $2.00 USD

Fatores de custo:
- Quantidade de eventos encontrados
- Complexidade das descrições
- Número de buscas complementares necessárias
- Quantidade de validações HTTP

## 🚀 Próximos Passos Recomendados

### Para Uso Regular
1. **Executar semanalmente** - Sistema já testado e funcional
2. **Monitorar logs** - Verificar `busca_eventos.log` para problemas
3. **Revisar eventos rejeitados** - Verificar se há falsos positivos em `rejected_events`
4. **Ajustar filtros** - Atualizar venues e categorias em `config.py` conforme necessário

### Para Desenvolvimento
1. **Implementar melhorias de links** - Aumentar cobertura de 41% para >70%
2. **Adicionar cache** - Evitar buscas repetidas em execuções próximas
3. **Refatorar validação** - Consolidar código duplicado
4. **Adicionar testes** - pytest para garantir qualidade em mudanças futuras

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
