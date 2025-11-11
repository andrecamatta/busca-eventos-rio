# Recomendações para Melhorar as Buscas

**Data:** 11/11/2025
**Baseado em:** Dados reais de produção Railway (31 eventos)

---

## 🎯 Foco das Melhorias

Baseado na análise dos logs de produção, as melhorias devem focar em:

1. ✅ **Jazz e Música Clássica:** NÃO MEXER - estão superando as metas
2. 🔴 **Outdoor/Parques:** PRIORIDADE CRÍTICA - 0 eventos em 2 de 3 sábados
3. 🟡 **Comédia e Feira Gastronômica:** Otimizar para aumentar volume (atualmente 3 encontrados cada)

---

## 🔴 PRIORIDADE 1: Outdoor/Parques

### Problema Atual
```yaml
# Resultados reais da última execução (11/11/2025 12:56):
- Sábado 15/11: 0 eventos ❌
- Sábado 22/11: 0 eventos ❌

# Execução anterior (06:00):
- Sábado 1: 3 eventos ✅
- Sábado 2: 2 eventos ✅
- Sábado 3: 0 eventos ❌

# Taxa de falha: 66% (2 de 3 sábados retornam 0 eventos)
```

### Análise do Prompt Atual

**Problema 1: Filtros de Exclusão Muito Agressivos**
```yaml
EXCLUIR:
  ❌ Samba/pagode/forró, shows mainstream, mega eventos, esportes
```

**Impacto:** Rio tem MUITOS eventos de samba/choro outdoor que são culturais e nichados (não mainstream). Estamos excluindo eventos válidos.

**Problema 2: Buscas por Datas Específicas Muito Restritivas**
- Sistema busca eventos em 3 sábados específicos (ex: 15/11, 22/11, 29/11)
- Se o evento outdoor está em outro sábado, não é encontrado

**Problema 3: Poucos Eventos Nichados Outdoor no Rio**
- Cinema ao ar livre é raro (Parque Lage esporádico)
- Concertos em parques são raros e geralmente grandes
- Feiras nichadas: apenas 2 fixas (Rio Antigo 1º sábado, Praça XV)

---

### ✅ Recomendações para Outdoor/Parques

#### 1. Relaxar Filtros de Exclusão

**ANTES:**
```yaml
EXCLUIR:
  ❌ Samba/pagode/forró, shows mainstream, mega eventos
```

**DEPOIS:**
```yaml
INCLUIR (mas com critérios):
  ✅ Choro e samba não-comercial em locais outdoor (Parque Lage, Jardim Botânico)
  ✅ Shows acústicos em parques (mesmo se MPB/samba acústico)
  ✅ Eventos de médio porte (não apenas micro eventos)

EXCLUIR (mais específico):
  ❌ Shows mainstream em estádios (Maracanã, Jeunesse Arena)
  ❌ Mega festivais (Rock in Rio, Tim Festival)
  ❌ Eventos esportivos (corridas, pedaladas)
  ❌ Artistas mainstream: Ivete Sangalo, Thiaguinho, Alexandre Pires, etc.
  ❌ "turnê nacional", "mega show"
```

#### 2. Ampliar Janela de Busca

**ANTES:**
- 3 prompts dinâmicos, cada um buscando 1 sábado específico

**DEPOIS:**
```yaml
# Em vez de buscar "sábado 15/11 específico", buscar:
palavras_chave:
  - "eventos outdoor sábado Rio {month_str}"
  - "cinema ao ar livre Rio fim de semana {month_str}"
  - "shows parques Rio sábado {month_str}"
  - "feiras culturais fim de semana Rio {month_str}"

# Deixar a validação filtrar por data, mas buscar TODOS os sábados do mês
instrucoes_especiais: |
  🎯 BUSCAR eventos outdoor aos SÁBADOS E DOMINGOS em {month_str}

  PERÍODO ALVO: {start_date_str} a {end_date_str}

  ⚠️ NÃO restringir busca a datas específicas - buscar TODOS os fins de semana
  ⚠️ Validação filtrará depois para o período correto
```

#### 3. Incluir Eventos Indoor em Locais Outdoor

**ADICIONAR aos venues_sugeridos:**
```yaml
venues_sugeridos:
  # Locais outdoor tradicionais:
  - Jardim Botânico
  - Parque Lage
  - Aterro do Flamengo

  # NOVOS: Locais com área outdoor (indoor/outdoor):
  - Jockey Club (shows e eventos na área aberta)
  - Marina da Glória (eventos culturais)
  - Forte de Copacabana (eventos outdoor)
  - Praça Mauá (eventos culturais)
  - Boulevard Olímpico (eventos culturais)
```

#### 4. Adicionar Mais Fontes Específicas

**ADICIONAR:**
```yaml
fontes_prioritarias:
  # Atuais:
  - Riotur (visit.rio/agenda)
  - Bafafá Rio
  - TimeOut Rio

  # NOVOS:
  - "Agenda Rio Prefeitura" (eventos oficiais)
  - Instagram @visitrio, @rio.prefeitura
  - Facebook "Fim de Semana no Rio"
  - Site G1 Rio - seção "Fim de Semana"
  - "O Que Fazer no Rio" (portais turísticos)
```

#### 5. Aceitar Eventos Recorrentes Vagos

**ADICIONAR:**
```yaml
instrucoes_especiais: |
  ⚠️ ACEITAR eventos recorrentes se:
  - Evento acontece TODOS os sábados/domingos (ex: Feira Praça XV)
  - Há confirmação que acontece no período {start_date_str} a {end_date_str}
  - Exemplo: "Feira de Artesanato Praça XV - Todos os Domingos"

  ✅ Usar eh_recorrente: true para esses casos
```

---

## 🟡 PRIORIDADE 2: Comédia

### Status Atual
- Busca: 3 eventos encontrados ✅
- Validação: 0 aprovados ❌ (problema de formato de horário)

**OBJETIVO:** Aumentar volume de eventos encontrados de 3 para 5-7

### ✅ Recomendações

#### 1. Adicionar Mais Venues Específicos

**ADICIONAR:**
```yaml
venues_sugeridos:
  # Atuais:
  - Theatro Net Rio
  - Teatro Riachuelo
  - Teatro do Leblon

  # NOVOS:
  - Teatro Rival Petrobras (stand-up)
  - Teatro Clara Nunes
  - Teatro dos Quatro
  - Bares com stand-up: Comedy Club, The Pub Rio
  - Casas de show com comédia: Miranda Bar, Casa da Matriz
```

#### 2. Adicionar Mais Plataformas de Busca

**ADICIONAR:**
```yaml
fontes_prioritarias:
  # Atuais:
  - Sympla
  - Eventbrite

  # NOVOS:
  - Uhuu.com (stand-up)
  - TicketOffice.com.br
  - Bilheteria Express
  - Instagram dos teatros (@theatronetrio, @teatroleblon)
```

#### 3. Palavras-Chave Mais Específicas

**ADICIONAR:**
```yaml
palavras_chave:
  # Atuais:
  - "stand-up Rio Janeiro {month_range_str}"
  - "comédia Rio {month_range_str}"

  # NOVOS:
  - "Rafael Portugal Rio {month_str}"
  - "Afonso Padilha Rio {month_str}"
  - "Thiago Ventura Rio {month_str}"
  - "Clarice Falcão Rio {month_str}"
  - "Fábio Porchat Rio {month_str}"
  - "stand-up Theatro Net {month_str}"
  - "comédia Teatro Rival {month_str}"
  - "show humor Sympla Rio {month_str}"
```

#### 4. Revisar Filtro LGBTQIA+

**AVALIAR REMOVER ESTE FILTRO:**
```yaml
# Filtro atual (pode ser muito restritivo):
⚠️ FILTROS CRÍTICOS:
  - ❌ NÃO incluir eventos LGBTQIA+ específicos

# Problema: Muitos shows de comédia no Rio têm temática LGBTQIA+
# e são eventos mainstream relevantes (ex: Pabllo Vittar stand-up)

# Sugestão: Remover este filtro ou tornar mais específico:
⚠️ FILTROS CRÍTICOS:
  - ❌ NÃO incluir eventos infantis ou "para toda família"
  - ✅ INCLUIR comédia adulta de qualquer temática
  - ✅ Stand-up de comediantes conhecidos (independente de orientação)
```

---

## 🟡 PRIORIDADE 3: Feira Gastronômica

### Status Atual
- Busca: 3 eventos encontrados ✅
- Validação: 0 aprovados ❌ (problema de formato de horário)

**OBJETIVO:** Aumentar volume de 3 para 5-7 eventos

### ✅ Recomendações

#### 1. Adicionar Eventos de Food Trucks

**ADICIONAR:**
```yaml
tipos_evento:
  # Atuais:
  - Feiras gastronômicas
  - Food festivals

  # NOVOS:
  - Eventos de food trucks
  - Mercados de rua gastronômicos
  - Festivais de comida de rua
  - Rodadas gastronômicas (bares/restaurantes)

palavras_chave:
  # Atuais:
  - "feira gastronômica Rio {month_str}"
  - "food festival Rio {month_year_str}"

  # NOVOS:
  - "food truck Rio fim de semana {month_str}"
  - "festival food truck Rio {month_str}"
  - "food trucks Aterro Flamengo {month_str}"
  - "Rota Gastronômica Rio {month_str}"
  - "mercado gastronômico Rio sábado {month_str}"
  - "feira de produtores Rio {month_str}"
```

#### 2. Adicionar Locais Específicos

**ADICIONAR:**
```yaml
venues_sugeridos:
  # Atuais:
  - Parques e praças

  # NOVOS:
  - Jockey Club (Mercado Jockey)
  - Marina da Glória (food trucks)
  - Aterro do Flamengo (festivais)
  - Parque Madureira (eventos gastronômicos)
  - Quinta da Boa Vista (feiras)
  - Lagoa Rodrigo de Freitas (food trucks)
  - Centro Cultural Light (feiras gastronômicas indoor)
```

#### 3. Incluir Eventos Híbridos

**ADICIONAR:**
```yaml
instrucoes_especiais: |
  ✅ INCLUIR eventos híbridos:
  - Feiras com gastronomia + música (ex: festival com food trucks + show)
  - Eventos de cerveja artesanal com gastronomia
  - Feiras de orgânicos e gastronomia
  - Mercados de agricultores com área gastronômica

  ⚠️ Validar que tem componente gastronômico SIGNIFICATIVO
  ⚠️ Não incluir shows com apenas "área de alimentação"
```

---

## 🟢 PRIORIDADE 4: Melhorias Gerais para Todas as Categorias

### 1. Adicionar Data/Horário em Todas as Buscas

**PROBLEMA ATUAL:** Perplexity retorna horários em formato brasileiro ("20h00", "14h às 22h")

**SOLUÇÃO NO PROMPT:**
```yaml
campos_obrigatorios:
  - "horario: formato HH:MM (exemplo: 20:00, 14:00)"

instrucoes_especiais: |
  ⚠️ FORMATO DE HORÁRIO OBRIGATÓRIO: HH:MM

  Exemplos CORRETOS:
  ✅ "horario": "20:00"
  ✅ "horario": "14:00"
  ✅ "horario": "18:30"

  Exemplos INCORRETOS (NÃO usar):
  ❌ "horario": "20h00"
  ❌ "horario": "14h às 22h"
  ❌ "horario": "18h30"

  Se encontrar horário em formato brasileiro, CONVERTER para HH:MM
```

### 2. Priorizar Links de Ingressos

**ADICIONAR em todas as categorias:**
```yaml
instrucoes_especiais: |
  ⚠️ LINK DE INGRESSO É CRÍTICO:

  Prioridade de fontes (nesta ordem):
  1. Sympla (sympla.com.br) - PREFERENCIAL
  2. Eventbrite (eventbrite.com.br)
  3. Fever (feverup.com)
  4. Ingresso.com
  5. Bilheterias oficiais dos venues
  6. Sites oficiais dos eventos

  ✅ Se não encontrar link, marcar: "link_ingresso": null
  ❌ NÃO inventar links
  ❌ NÃO usar links genéricos (home do venue)
```

### 3. Validação de Data Mais Clara

**ADICIONAR em todas as categorias:**
```yaml
instrucoes_especiais: |
  ⚠️ VALIDAÇÃO DE DATA OBRIGATÓRIA:

  Período válido: {start_date_str} a {end_date_str}

  ✅ INCLUIR eventos que:
  - Têm data específica no período
  - São recorrentes e acontecem no período

  ❌ EXCLUIR eventos que:
  - Já passaram
  - Estão fora do período
  - Têm data "a confirmar" sem previsão
```

---

## 📊 Impacto Esperado das Melhorias

### Antes (Atual - 31 eventos)
```
✅ Jazz: 5 eventos (meta: 4)
✅ Música Clássica: 5 eventos (meta: 2)
✅ Cinema: 5 eventos
✅ Feira de Artesanato: 2 eventos
❌ Comédia: 0 eventos (busca: 3)
❌ Feira Gastronômica: 0 eventos (busca: 3)
❌ Outdoor/Parques: 0 eventos
✅ Geral: 13 eventos
```

### Depois (Projeção - 45-50 eventos)
```
✅ Jazz: 5 eventos (meta: 4) [sem mudança]
✅ Música Clássica: 5 eventos (meta: 2) [sem mudança]
✅ Cinema: 5 eventos [sem mudança]
✅ Feira de Artesanato: 2 eventos [sem mudança]
✅ Comédia: 5-7 eventos (+5-7) [busca melhorada + fix validação]
✅ Feira Gastronômica: 5-7 eventos (+5-7) [busca melhorada + fix validação]
✅ Outdoor/Parques: 3-5 eventos (+3-5) [busca melhorada]
✅ Geral: 13 eventos [sem mudança]
```

**Aumento total: +13-19 eventos (+42% a +61%)**

---

## 🚀 Ordem de Implementação Recomendada

### Fase 1: Fixes Críticos (Impacto Imediato)
1. ✅ Implementar `normalize_time_format()` no validador (+6 eventos)
2. ✅ Melhorar prompts Outdoor/Parques (+3-5 eventos)

### Fase 2: Otimizações (Médio Prazo)
3. ✅ Adicionar mais venues e palavras-chave para Comédia (+2-3 eventos extras)
4. ✅ Melhorar buscas de Feira Gastronômica (+2-3 eventos extras)
5. ✅ Revisar filtro LGBTQIA+ de Comédia (teste A/B)

### Fase 3: Melhorias Gerais (Longo Prazo)
6. ✅ Implementar formato de horário no prompt (prevenir futuros problemas)
7. ✅ Adicionar validação de links mais rigorosa
8. ✅ Monitoramento e alertas automáticos

---

**Gerado por:** Claude Code
**Baseado em:** Análise de logs de produção Railway (ANALISE_PROMPTS_PRODUCAO.md)
