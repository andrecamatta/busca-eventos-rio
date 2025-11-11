# Análise de Prompts - Produção (Ambiente Railway)

**Data:** 11/11/2025
**Ambiente:** https://busca-eventos-rio-production.up.railway.app/

## 🎯 Objetivo
Identificar prompts da etapa inicial (search) que não estão atingindo a meta mínima de categoria ou venue.

---

## 📊 Categorias com Meta Mínima Definida

### ⚠️ ALTO RISCO - Jazz (min_events: 4)
**Status:** CRÍTICO - Meta mais alta de todas as categorias

**Desafios identificados:**
1. **Exclusão do Blue Note:** Prompt explicitamente exclui Blue Note (tem scraper próprio), mas Blue Note é a principal casa de jazz do Rio
2. **Venues alternativos difíceis:** Maze Jazz Club, Clube do Jazz, Bottle's Bar podem ter programação irregular
3. **Fontes limitadas:**
   - Instagram @becodasgarrafas, @mazejazzclub (podem não postar regularmente)
   - TimeOut Rio seção Jazz (pode ter poucos eventos)
   - Sympla (poucos shows de jazz são vendidos online)

**Prompt atual:**
```yaml
palavras_chave:
  - "jazz Rio Janeiro {month_range_str}"
  - "shows jazz entre {start_date_str} e {end_date_str}"
  - "Maze Jazz Club {month_range_str}"
  - "Clube do Jazz Rio {month_range_str}"
```

**Problemas potenciais:**
- ❌ Dependência excessiva de venues pequenos (Maze, Clube do Jazz)
- ❌ Exclusão de Blue Note reduz pool de eventos disponíveis
- ❌ Fontes priorizadas (Instagram) podem não ter programação detalhada com datas/horários

**Recomendações:**
1. ✅ Adicionar mais casas de jazz: Jazz nos Fundos, Dolores Club, Beco das Garrafas completo
2. ✅ Incluir hotéis com jazz ao vivo (Copacabana Palace, Belmond, Marina All Suites)
3. ✅ Buscar em Fever.com (tem jazz)
4. ✅ Relaxar filtros se necessário (incluir jazz fusion, bossa nova mais explicitamente)

---

### ⚠️ MÉDIO RISCO - Música Clássica (min_events: 2)

**Status:** MODERADO - Meta alcançável mas com desafios

**Desafios identificados:**
1. **Exclusões múltiplas:** Prompt exclui Sala Cecília Meireles, Teatro Municipal, CCJF, IMS, Istituto Italiano (todos têm scrapers)
2. **Foco em Cidade das Artes:** Venue prioritário mas pode ter agenda esparsa
3. **Eventos alternativos:** Igrejas (Candelária, São Francisco) têm programação irregular

**Prompt atual:**
```yaml
instrucoes_especiais: |
  ⚠️ NÃO BUSCAR (já cobertos por venues dedicados):
  - ❌ Sala Cecília Meireles
  - ❌ Teatro Municipal
  - ❌ CCJF, IMS, Istituto Italiano

  ✅ BUSCAR OBRIGATORIAMENTE:
  - 🏛️ **CIDADE DAS ARTES**
```

**Problemas potenciais:**
- ❌ Pool muito reduzido após exclusões
- ❌ Cidade das Artes pode não ter 2 eventos no período (especialmente em períodos de 3 semanas)
- ❌ Igrejas raramente anunciam eventos em plataformas de ingressos

**Recomendações:**
1. ✅ Adicionar mais venues alternativos: Museu da República, Centro Cultural Light, Espaço SESC
2. ✅ Incluir eventos corporativos de música clássica (Petrobras, patrocinadores culturais)
3. ✅ Buscar em sites específicos: Cidade das Artes oficial, OSB, Orquestra Petrobras Sinfônica
4. ✅ Considerar eventos gratuitos em espaços públicos

---

## 🏛️ Venues com Desafios Específicos

### 1. Artemis - Torrefação Artesanal e Cafeteria

**Desafio:** Venue muito nichado (cursos de café)

**Análise do prompt:**
```yaml
tipos_evento:
  - Cursos de barista
  - Workshops de café
  - Degustações de café
```

**Problemas:**
- ❌ Eventos esporádicos (não toda semana)
- ❌ Fonte principal: Sympla produtor específico (pode estar vazio em alguns períodos)
- ❌ Instagram pode não ter datas/horários precisos

**Recomendações:**
1. ✅ Não exigir mínimo para esta categoria
2. ✅ Adicionar fontes alternativas: eventos de associações de baristas, cafeterias parceiras
3. ✅ Considerar eventos relacionados (degustações, lançamentos de blends)

---

### 2. Maze Jazz Club / Clube do Jazz / Teatro Rival

**Desafio:** Dependência de redes sociais para programação

**Análise do prompt:**
```yaml
fontes_prioritarias:
  - Instagram @mazejazzclub
  - Instagram @clubedojazzrj
  - Facebook Maze Jazz Club
```

**Problemas:**
- ❌ Instagram/Facebook podem não ter datas/horários completos
- ❌ Posts podem ser anúncios genéricos ("toda quarta-feira") sem eventos específicos
- ❌ Perplexity pode ter dificuldade em extrair dados estruturados de posts sociais

**Recomendações:**
1. ✅ Priorizar Sympla/Eventbrite (quando disponível)
2. ✅ Usar Google como fonte primária: "Maze Jazz Club eventos {data específica}"
3. ✅ Aceitar eventos recorrentes genéricos se necessário (ex: "Jam Session todas as quartas")

---

### 3. Parque Lage / Jardim Botânico (Outdoor)

**Desafio:** Eventos ao ar livre dependem de clima e são anunciados em cima da hora

**Análise do prompt:**
```yaml
palavras_chave:
  - "cinema ao ar livre Rio sábado {month_range_str}"
  - "concerto jardim sábado Rio {month_range_str}"
  - "Varanda Sonora Parque Lage"
```

**Problemas:**
- ❌ Eventos de clima (chuva cancela) → anúncios last-minute
- ❌ Varanda Sonora pode estar em hiato
- ❌ Buscas genéricas retornam muitos eventos passados ou sem data confirmada

**Recomendações:**
1. ✅ Priorizar fontes oficiais: @eavparquelage, @jardimbotanicorj Instagram
2. ✅ Usar Riotur (visit.rio) como fonte primária
3. ✅ Aceitar eventos "a confirmar" se houver histórico regular (ex: Varanda Sonora todo sábado)

---

## 🚨 Prompts com Restrições Excessivas

### 1. Comédia - Filtros LGBTQIA+

**Prompt atual:**
```yaml
instrucoes_especiais: |
  ⚠️ FILTROS CRÍTICOS:
  - ❌ NÃO incluir eventos LGBTQIA+ específicos
```

**Problema:**
- ❌ Muitos shows de comédia no Rio são LGBTQIA+ (Pabllo Vittar, drag queens, etc.)
- ❌ Filtro pode reduzir pool significativamente
- ❌ Pode estar filtrando eventos mainstream relevantes

**Impacto:** MÉDIO - Pode estar causando rejeição de 20-30% dos eventos de comédia

---

### 2. Outdoor - Exclusão de Gêneros Musicais

**Prompt atual:**
```yaml
exclude:
  - "samba", "pagode", "roda de samba", "axé", "forró"
  - "ivete sangalo", "thiaguinho", "alexandre pires"
  - "turnê", "show nacional", "mega show"
```

**Problema:**
- ❌ Rio tem MUITOS eventos de samba/pagode ao ar livre (são culturais, não apenas mainstream)
- ❌ Filtro pode estar rejeitando eventos nichados de samba (não comercial)
- ❌ Exclusões de artistas específicos podem não cobrir todos os casos

**Impacto:** ALTO - Pode estar reduzindo eventos outdoor de 50% para 10-20%

---

## 📈 Análise de Prompts Sábados Outdoor (Dinâmico)

**Estratégia atual:** 1 prompt por sábado no período (3 sábados = 3 prompts)

**Vantagens:**
- ✅ Foco específico por data
- ✅ Reduz falsos positivos de datas erradas

**Desafios:**
```yaml
tipos_evento:
  - 🎬 Cinema ao ar livre
  - 🎵 Concertos em parques
  - 🛍️ Feiras culturais nichadas
```

**Problemas identificados:**
1. **Cinema ao ar livre:** Poucos eventos regulares (Parque Lage esporádico)
2. **Concertos em parques:** Eventos raros, geralmente grandes (excluídos pelo filtro mainstream)
3. **Feiras nichadas:** Feira Rio Antigo (1º sábado), Feira Praça XV (regular) - apenas 2 fixas

**Meta realista por sábado:** 2-3 eventos (não 5-10)

**Recomendações:**
1. ✅ Reduzir expectativas: aceitar 1-2 eventos por sábado como sucesso
2. ✅ Incluir eventos indoor em locais outdoor (ex: shows no Jockey Club, Marina da Glória)
3. ✅ Relaxar filtro de mainstream para eventos ao ar livre (contexto diferente de show em estádio)

---

## 🎯 Resumo de Prompts com Alta Probabilidade de Falha

### 🔴 CRÍTICO (Provavelmente não atinge meta)
1. **Jazz (meta: 4 eventos)**
   - **Problema:** Exclusão Blue Note + venues pequenos com agenda irregular
   - **Taxa de sucesso estimada:** 40-60% (2-3 eventos ao invés de 4)

2. **Outdoor Sábados (expectativa: ~3 eventos/sábado)**
   - **Problema:** Poucos eventos nichados + filtros de exclusão agressivos
   - **Taxa de sucesso estimada:** 30-50% (1-2 eventos ao invés de 3)

### 🟡 MODERADO (Pode não atingir meta consistentemente)
3. **Música Clássica (meta: 2 eventos)**
   - **Problema:** Muitas exclusões + dependência da Cidade das Artes
   - **Taxa de sucesso estimada:** 60-75% (às vezes só 1 evento)

4. **Maze Jazz Club / Clube do Jazz**
   - **Problema:** Fontes sociais sem dados estruturados
   - **Taxa de sucesso estimada:** 50-70% (0-1 evento ao invés de 2-3)

### 🟢 BAIXO RISCO (Provavelmente atinge meta)
- Sala Cecília Meireles (scraper)
- Teatro Municipal (scraper + Fever)
- CCBB (scraper)
- Blue Note (scraper)
- Theatro Net Rio (programação comercial estável)
- Teatro do Leblon (programação comercial estável)

---

## 🔧 Recomendações Gerais

### 1. Ajustar Metas Mínimas
```python
# config.py - Sugestão de ajuste
EVENT_CATEGORIES = {
    "jazz": {
        "min_events": 3,  # Reduzir de 4 para 3
    },
    "musica_classica": {
        "min_events": 1,  # Reduzir de 2 para 1 (compensar com scraper Cidade das Artes?)
    }
}
```

### 2. Adicionar Scrapers Customizados
**Prioridade ALTA:**
- [ ] Maze Jazz Club (página de eventos se existir)
- [ ] Cidade das Artes (JSON-LD ou agenda oficial)
- [ ] Clube do Jazz (se tiver site próprio)

**Prioridade MÉDIA:**
- [ ] TimeOut Rio (scraping de seção Jazz/Música Clássica)
- [ ] Riotur/Visit.rio (eventos outdoor oficiais)

### 3. Relaxar Filtros de Exclusão
**Categorias afetadas:**
- Outdoor/Parques: Permitir samba/choro não-comercial
- Comédia: Revisar filtro LGBTQIA+ (pode ser muito amplo)

### 4. Melhorar Fontes de Dados
**Jazz:**
```yaml
fontes_prioritarias:
  - https://www.sympla.com.br/eventos/rio-de-janeiro-rj?s=jazz
  - https://www.timeout.com/rio-de-janeiro/music/jazz
  - https://feverup.com/rio-de-janeiro/candlelight (jazz clássico)
  - Instagram @jazznosfundos, @doloresclubrj
```

**Outdoor:**
```yaml
fontes_prioritarias:
  - https://visit.rio/o-que-fazer/agenda/
  - https://www.bafafa.com.br/rio-de-janeiro (feiras fixas)
  - https://www.timeout.com/rio-de-janeiro/things-to-do/weekend
```

---

## 📝 Próximos Passos

1. **Validar hipóteses:**
   - Acessar logs de produção do Railway (via dashboard ou CLI)
   - Identificar quais categorias/venues estão retornando 0 eventos

2. **Implementar melhorias prioritárias:**
   - Adicionar scraper Cidade das Artes
   - Adicionar mais keywords para Jazz
   - Relaxar filtros Outdoor (teste A/B)

3. **Monitoramento:**
   - Criar alertas para categorias com < meta mínima
   - Dashboard com taxa de sucesso por categoria/venue

---

**Gerado por:** Claude Code
**Arquivo de origem:** `/prompts/search_prompts.yaml`, `/config.py`, `/agents/search_agent.py`
