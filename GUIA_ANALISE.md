# Guia de Análise de Execução - Sistema de Busca de Eventos

## 📊 1. ANÁLISE DE PERFORMANCE

### 1.1 Tempo de Execução
**O que analisar:**
- Tempo total de execução
- Tempo por fase (Busca → Verificação → Enriquecimento → Retry → Formatação)
- Gargalos (fases que demoram mais)

**Onde verificar:**
```bash
# Ver tempo total nos logs
grep "Tempo total de execução" output/latest/*.log

# Ver tempo por fase
grep "FASE" output/latest/*.log
```

**Metas:**
- ✅ Execução completa: < 5 minutos
- ⚠️ Alerta: 5-10 minutos
- ❌ Problema: > 10 minutos

---

## 🔗 2. ANÁLISE DE QUALIDADE DE LINKS

### 2.1 Estatísticas de Links
**O que analisar:**
```bash
# Ver estatísticas de validação
grep "Estatísticas de Validação" -A 10 output/latest/*.log
```

**Métricas importantes:**
- Taxa de links válidos na 1ª tentativa
- Quantos links precisaram de busca inteligente
- Quantos links genéricos foram detectados
- Quantos links foram corrigidos via IA

**Flags de atenção:**
- 🚨 Taxa de links genéricos > 20% → Prompt de busca precisa melhorar
- 🚨 Taxa de busca inteligente > 50% → SearchAgent não está retornando links
- 🚨 Taxa de correção IA < 30% → Link search não está encontrando alternativas

### 2.2 Qualidade dos Links no Output Final
**O que analisar:**
```bash
# Ver eventos sem link
jq '.verified_events[] | select(.link_ingresso == null) | {titulo, categoria}' output/latest/verified_events.json

# Ver links genéricos que passaram
grep "shows/$\|agenda/$\|eventos/$" output/latest/eventos_whatsapp.txt
```

**Metas:**
- ✅ > 70% dos eventos com links específicos
- ⚠️ 50-70% com links
- ❌ < 50% com links

---

## ❌ 3. ANÁLISE DE REJEIÇÕES

### 3.1 Taxa de Rejeição
**O que analisar:**
```bash
# Contar eventos rejeitados
jq '.rejected_events | length' output/latest/verified_events.json

# Ver motivos de rejeição
jq '.rejected_events[] | .motivo_rejeicao' output/latest/verified_events.json | sort | uniq -c
```

**Métricas:**
- Taxa de rejeição = rejeitados / (aprovados + rejeitados)
- Taxa saudável: < 30%

**Motivos comuns e ações:**

| Motivo | Ação Sugerida |
|--------|---------------|
| "Data fora do período" | Verificar prompt de busca - está especificando período correto? |
| "Link genérico" | Melhorar validação de links ou prompt de busca |
| "Teatro infantil" | Filtros de exclusão funcionando corretamente |
| "Evento duplicado" | Consolidação funcionando bem |
| "Informações incompletas" | SearchAgent precisa extrair mais dados |

### 3.2 Eventos Recuperáveis
**O que analisar:**
```bash
# Ver se RetryAgent tentou recuperar eventos
grep "eventos recuperáveis\|Tentando recuperar" output/latest/*.log
```

---

## 📅 4. COBERTURA DE CATEGORIAS E FINS DE SEMANA

### 4.1 Distribuição por Categoria
**O que analisar:**
```bash
# Contar por categoria
jq '.verified_events[] | .categoria' output/latest/verified_events.json | sort | uniq -c
```

**Metas:**
- Jazz: 3-5 eventos
- Teatro/Comédia: 2-4 eventos
- Outdoor (fim de semana): 3-6 eventos
- Venues especiais (Teatro Municipal, Cecília Meireles): 2-4 cada

### 4.2 Distribuição Sábado vs Domingo
**O que analisar:**
```bash
# Contar eventos por dia da semana
jq '.verified_events[] | .data' output/latest/verified_events.json | while read date; do
    python3 -c "from datetime import datetime; d=datetime.strptime('$date', '\"%d/%m/%Y\"'); print(['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'][d.weekday()])"
done | sort | uniq -c
```

**Metas:**
- ✅ Pelo menos 10 eventos em sábado/domingo
- ⚠️ Verificar se há desequilíbrio (ex: 9 sábados, 1 domingo)

---

## 🎯 5. CHECKLIST DE VALIDAÇÃO FINAL

### 5.1 Qualidade do Output WhatsApp
**Verificar em `output/latest/eventos_whatsapp.txt`:**

- [ ] Todos os eventos têm título claro
- [ ] Datas e horários estão corretos e legíveis
- [ ] Locais incluem endereço completo
- [ ] Preços estão claros (valor ou "Grátis" ou "Consultar")
- [ ] Links são específicos (não terminam em `/shows/`, `/agenda/`)
- [ ] Descrições são informativas (não genéricas)
- [ ] Emojis apropriados para cada categoria

### 5.2 Venues Obrigatórios
**Verificar:**
```bash
# Verificar se há eventos dos venues obrigatórios
grep -i "teatro municipal\|cecília meireles\|blue note" output/latest/eventos_whatsapp.txt
```

- [ ] Teatro Municipal: pelo menos 1 evento
- [ ] Sala Cecília Meireles: pelo menos 1 evento
- [ ] Blue Note: pelo menos 1 evento (desejável)

---

## 🔍 6. IDENTIFICAR OPORTUNIDADES DE MELHORIA

### 6.1 Problemas de Prompt
**Sinais:**
- Eventos com descrições muito curtas/genéricas
- Links genéricos frequentes
- Informações importantes faltando (horário, preço)

**Ação:** Revisar prompts em `agents/search_agent.py`

### 6.2 Problemas de Validação
**Sinais:**
- Eventos claramente errados passando (infantil, data errada)
- Eventos bons sendo rejeitados

**Ação:** Ajustar regras em `agents/validation_agent.py` ou `agents/verify_agent.py`

### 6.3 Problemas de Busca
**Sinais:**
- Poucas opções em categorias específicas
- Mesmos venues/eventos sempre

**Ação:** Expandir keywords em `config.py` ou melhorar prompts

### 6.4 Problemas de Performance
**Sinais:**
- Enriquecimento demorando muito
- Muitas buscas inteligentes de link
- ValidationAgent processando tudo com LLM

**Ação:** Otimizar validação condicional, limitar buscas, paralelizar melhor

---

## 📈 7. MÉTRICAS DE SUCESSO

### Score de Qualidade (0-100)
```
Score = (
    (eventos_com_link_especifico / total) * 30 +
    (eventos_fim_semana / 10) * 25 +
    (1 - taxa_rejeicao) * 20 +
    (cobertura_categorias / 5) * 15 +
    (venues_obrigatorios / 3) * 10
) * 100
```

**Interpretação:**
- 90-100: 🌟 Excelente
- 75-89: ✅ Bom
- 60-74: ⚠️ Aceitável (melhorias necessárias)
- < 60: ❌ Precisa de ajustes urgentes

---

## 🛠️ 8. COMANDOS ÚTEIS PARA ANÁLISE

```bash
# Ver estrutura completa de um evento
jq '.verified_events[0]' output/latest/verified_events.json

# Contar eventos por local
jq -r '.verified_events[] | .local' output/latest/verified_events.json | sort | uniq -c | sort -rn

# Ver eventos sem descrição enriquecida
jq '.verified_events[] | select(.descricao_enriquecida == null) | .titulo' output/latest/verified_events.json

# Ver tempo de cada fase
grep -E "FASE|Tempo total" output/latest/*.log

# Ver warnings importantes
grep "WARNING\|⚠️\|❌" output/latest/*.log | grep -v "Queue"
```
