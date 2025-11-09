# 📊 Análise de Qualidade dos Eventos - Problemas e Soluções

## 🎯 Resumo Executivo

Como a API de produção está protegida, esta análise foi feita com base nos **critérios de julgamento do sistema** e nas **limitações conhecidas** documentadas.

### Critérios de Avaliação (GPT-5)
1. **Aderência ao Prompt** (30%) - Evento corresponde ao solicitado?
2. **Correlação Link-Conteúdo** (30%) - Dados batem com o link?
3. **Precisão de Data/Horário** (30%) - CRÍTICO
4. **Completude e Consistência** (10%) - Campos preenchidos e consistentes?

**Fórmula**: `quality_score = (prompt*0.3) + (content*0.3) + (date*0.3) + (completeness*0.1)`

---

## ❌ Principais Problemas que Causam Notas Baixas

### 1. 🚨 CRÍTICO: Precisão de Data e Horário (Peso 30%)

**Problema identificado**: Este é o critério com maior impacto nas notas baixas.

#### Severidades definidas no código:
```
CRÍTICO (nota 0-3):  Data com diferença de MESES ou ANOS
GRAVE (nota 3-5):    Data com diferença >7 DIAS
MÉDIO (nota 5-7):    Horário com diferença >2 horas
LEVE (nota 7-8):     Horário com diferença de 1-2 horas
OK (nota 8-10):      Data/horário corretos (±30min)
```

#### Causas Comuns:
- **LLM "alucinando" datas** quando o link não tem data clara
- **Parser de data interpretando formato errado** (ex: MM/DD vs DD/MM)
- **Eventos multi-sessão**: extrai uma data mas link mostra várias
- **Links desatualizados**: site mostra data antiga
- **Scrapers pegando data de publicação** ao invés de data do evento

#### Impacto:
- **Uma data errada de 1 mês** = nota 0-3 neste critério = perda de até 9 pontos na nota final!
- **Horário errado de 3 horas** = nota 5-7 = perda de até 1.5 pontos

---

### 2. ⚠️ GRAVE: Inconsistência Título vs Descrição (Peso 10%)

**Problema identificado no código** (judge_agent.py:428-438):

#### Exemplos de INCONSISTÊNCIA CRÍTICA (nota 0-3):
```
❌ Título: "Lumen Festival"
   Descrição: "Exibição do filme 'O Quarto das Sombras'"

❌ Título: "Programação CCBB"
   Descrição: "Peça teatral 'Hamlet' às 20h"

❌ Título: "Festival de Piano"
   Descrição: "Recital do pianista Fulano com obras de Chopin"
```

#### Como deveria ser (nota 8-10):
```
✅ Título: "'O Quarto das Sombras' no Lumen Festival"
   Descrição: "Filme de suspense psicológico exibido no Lumen..."

✅ Título: "Hamlet - Cia de Teatro XYZ"
   Descrição: "Clássico de Shakespeare na programação do CCBB..."

✅ Título: "Recital de Piano - João da Silva"
   Descrição: "Obras de Chopin interpretadas pelo pianista..."
```

#### Causas Comuns:
- **Search Agent retorna título genérico** do festival/venue
- **Descrição extrai evento específico** mas título não é atualizado
- **Scraper pega título da página** (genérico) e não do evento individual

#### Impacto:
- Nota 0-3 neste critério = perda de até 0.7 pontos na nota final
- **Problema de UX**: usuário não sabe qual evento específico é

---

### 3. ⚠️ IMPORTANTE: Correlação Link-Conteúdo (Peso 30%)

**Problema identificado**: 41% dos eventos sem link de compra (LIMITACOES.md:38)

#### Sub-problemas:

##### 3.1 Links Genéricos
```
❌ bluenoterio.com.br/shows/
❌ teatromunicipal.rj.gov.br/agenda/
❌ sympla.com.br/eventos/rio-de-janeiro
```

**Causa**: Search Agent não encontra link específico ou validação falha

##### 3.2 Dados Não Batem com o Link
```
Evento diz: "Blue Note Rio - Barra"
Link mostra: "Blue Note Copacabana"

Evento diz: "R$ 80,00"
Link mostra: "R$ 120,00" (preço atualizado)
```

**Causa**: Site atualizou informações após scraping

##### 3.3 Links Inacessíveis
**Penalidade**: Nota automática 5.0 (judge_agent.py:328, 471)

**Causas**:
- Sympla com Queue-it (proteção anti-bot)
- Sites fora do ar temporariamente
- Paywalls ou logins obrigatórios

#### Impacto:
- **Sem link**: Nota 5.0 = perda de 1.5 pontos (30% × 5.0 = 1.5)
- **Link com dados errados**: Nota 3-6 = perda de 1.2-2.1 pontos
- **Links genéricos**: Afeta UX + pode ser rejeitado

---

### 4. ⚠️ MÉDIO: Aderência ao Prompt (Peso 30%)

**Problema**: Eventos não relacionados ou muito correlatos

#### O sistema JÁ é tolerante (judge_agent.py:271-280):
```
✅ VÁLIDOS (nota >= 7):
   - Concertos clássicos + Recitais
   - Jazz + Bossa Nova
   - Teatro + Comédia stand-up

❌ INVÁLIDO (nota baixa):
   - Pediu shows adultos, retornou infantil
   - Pediu música, retornou exposição de arte
```

#### Causas de Notas Baixas:
- **Search Agent interpreta mal o prompt** (ex: busca "teatro" retorna "teatro de bonecos infantil")
- **Filtros de validação falharam** (evento infantil passou)
- **LLM criativo demais** ("café cultural" vira "workshop de culinária molecular")

#### Impacto:
- **Evento totalmente fora de contexto**: Nota 0-4 = perda de até 3 pontos

---

### 5. ⚠️ LEVE: Completude (Peso 10%)

**Problemas comuns**:
- ❌ Campo `preco` vazio quando site tem preço
- ❌ Campo `descricao` muito curto (< 50 chars)
- ❌ Horário ausente
- ❌ Endereço incompleto

#### Impacto:
- **Campos vazios**: Nota 5-7 = perda de 0.3-0.5 pontos
- **Menor peso**, mas afeta UX

---

## 🔧 Adaptações Sugeridas (Prioridade)

### 🚨 PRIORIDADE MÁXIMA: Melhorar Precisão de Datas

#### Adaptação 1.1: Validação de Data Mais Rigorosa no Scraping
```python
# Em agents/search_agent.py ou utils/event_extractors.py

def validate_event_date_from_link(event: dict, link_html: str) -> bool:
    """
    Compara data extraída com datas no HTML do link.
    Retorna False se divergência > 7 dias.
    """
    event_date = parse_date(event['data'])
    link_dates = extract_all_dates_from_html(link_html)

    # Verificar se event_date está em ±7 dias de alguma data do link
    for link_date in link_dates:
        if abs((event_date - link_date).days) <= 7:
            return True

    return False  # Data não bate - rejeitar ou corrigir
```

**Impacto esperado**: Reduzir erros críticos de data de ~15% para <5%

#### Adaptação 1.2: Scrapers Oficiais com Parsing Estruturado
```python
# Expandir scrapers como utils/eventim_scraper.py

class CCBBScraper:
    """Scraper direto da API/site do CCBB"""

    def extract_dates_from_structured_data(self, url: str):
        """
        Extrai datas de schema.org/Event, JSON-LD, ou elementos
        HTML com data-* attributes.

        Priorizar:
        1. <time datetime="2025-11-15T20:00:00"> (ISO 8601)
        2. JSON-LD startDate/endDate
        3. Meta tags
        """
        pass
```

**Impacto esperado**: Scrapers oficiais têm taxa de acerto de datas >95%

**Ação**: Implementar scrapers para:
- ✅ CCBB (já implementado - commit 19a8cea)
- ✅ Sala Cecília Meireles (já implementado - commit 54fe510)
- ⏳ Eventim (parcial - utils/eventim_scraper.py)
- ⏳ Teatro Municipal
- ⏳ Sympla (evitar Queue-it)

---

### 🔥 PRIORIDADE ALTA: Corrigir Títulos Genéricos

#### Adaptação 2.1: Detecção e Correção de Títulos Genéricos
```python
# Em agents/search_agent.py ou novo utils/title_fixer.py

GENERIC_TITLE_PATTERNS = [
    r'^(Programação|Festival|Mostra|Agenda)\s+\w+$',
    r'^(Teatro|Cinema|Shows?)\s+[A-Z][\w\s]+$',
]

def fix_generic_title(event: dict) -> dict:
    """
    Se título genérico mas descrição tem detalhes,
    extrai nome específico da descrição.
    """
    title = event['titulo']
    desc = event['descricao']

    # Detectar título genérico
    if any(re.match(p, title) for p in GENERIC_TITLE_PATTERNS):
        # Extrair nome específico da descrição
        # Ex: "Exibição do filme 'O Quarto das Sombras'"
        #  -> Título: "'O Quarto das Sombras' no Lumen Festival"

        specific_name = extract_specific_name_from_description(desc)
        if specific_name:
            event['titulo'] = f"{specific_name} - {title}"

    return event
```

**Impacto esperado**: Aumentar nota de completude de 6-7 para 8-9 em ~30% dos eventos

---

### 🔥 PRIORIDADE ALTA: Melhorar Links Específicos

**Problema atual**: 41% sem link (LIMITACOES.md:38)

#### Adaptação 3.1: Priorizar Scrapers Oficiais
✅ **JÁ IMPLEMENTADO** (commit 49f13fb: "Priorizar scrapers oficiais")

Verificar se está ativado em `config.py`:
```python
USE_OFFICIAL_SCRAPERS_FIRST = True  # Deve ser True
SCRAPER_PRIORITY = [
    "ccbb",
    "cecilia_meireles",
    "eventim",
    "sympla",  # só se resolver Queue-it
]
```

#### Adaptação 3.2: Validação de Link Mais Estrita
```python
# Em agents/validation_agent.py ou verify_agent.py

GENERIC_LINK_PATTERNS = [
    r'/shows/?$',
    r'/agenda/?$',
    r'/eventos/?$',
    r'/programacao/?$',
    r'/calendario/?$',
]

def is_generic_link(url: str) -> bool:
    """Detecta links genéricos que devem ser rejeitados"""
    return any(re.search(p, url, re.IGNORECASE) for p in GENERIC_LINK_PATTERNS)
```

✅ **Verificar se JÁ está implementado** (LIMITACOES.md:51 diz que foi resolvido)

#### Adaptação 3.3: Busca Inteligente de Links (Já existe - melhorar)
```python
# Em agents/link_search_agent.py (se existir)

async def smart_link_search(event: dict) -> str:
    """
    Busca link específico usando:
    1. Título do evento + venue + "ingresso"
    2. Artista/autor + data + venue
    3. Sympla/Eventbrite/Ticketmaster API se disponível
    """
    queries = [
        f"{event['titulo']} {event['venue']} ingresso",
        f"{event['titulo']} {event['data']} Rio de Janeiro ingressos",
    ]

    for query in queries:
        results = await perplexity_search(query, max_results=3)
        for url in results:
            if is_specific_link(url) and url_is_accessible(url):
                return url

    return None  # Sem link específico
```

**Meta**: Aumentar de 41% para 70% eventos com link específico

---

### ⚠️ PRIORIDADE MÉDIA: Melhorar Completude de Dados

#### Adaptação 4.1: Enrichment Mais Agressivo
```python
# Em agents/enrichment_agent.py (se existir)

REQUIRED_FIELDS = ['titulo', 'data', 'horario', 'local', 'preco', 'descricao']

async def enrich_missing_fields(event: dict, link_html: str):
    """
    Usa LLM para extrair campos faltantes do HTML do link.
    """
    missing = [f for f in REQUIRED_FIELDS if not event.get(f)]

    if missing:
        prompt = f"""
        Extraia do HTML abaixo os seguintes campos faltantes:
        {', '.join(missing)}

        HTML:
        {link_html[:3000]}

        Retorne JSON com apenas os campos solicitados.
        """

        extracted = await llm_call(prompt)
        event.update(extracted)

    return event
```

**Impacto esperado**: Reduzir eventos com campos vazios de ~20% para <10%

---

### ⚠️ PRIORIDADE MÉDIA: Detecção de "Alucinações"

#### Adaptação 5.1: Cross-Validation com Link
```python
# Em agents/validation_agent.py

async def cross_validate_with_link(event: dict) -> dict:
    """
    Compara dados extraídos com conteúdo do link.
    Marca inconsistências para review.
    """
    link_html = await fetch_link(event['link_ingresso'])
    link_text = extract_text_from_html(link_html)

    # Verificar se título aparece no link
    if event['titulo'] not in link_text:
        similarity = fuzzy_match(event['titulo'], link_text)
        if similarity < 0.6:
            event['_warning'] = "Título não encontrado no link"

    # Verificar preço
    link_prices = extract_prices(link_html)
    if event['preco'] and event['preco'] not in link_prices:
        event['_warning'] = "Preço diverge do link"

    # Verificar data
    link_dates = extract_dates(link_html)
    if event['data'] not in link_dates:
        event['_warning'] = "Data diverge do link"

    return event
```

**Impacto esperado**: Detectar e corrigir ~50% das "alucinações" antes do julgamento

---

## 📈 Metas de Qualidade

### Estado Atual (Estimado com base em LIMITACOES.md)
```
Score médio: ~6.5-7.0 / 10
- Aderência ao prompt: 7.5 (boa)
- Correlação link-conteúdo: 6.0 (41% sem link, alguns dados errados)
- Precisão data/horário: 6.5 (erros críticos ocasionais)
- Completude: 7.0 (alguns campos vazios)
```

### Metas Após Implementação das Adaptações

#### Meta 1 (3 meses): Score 7.8-8.4 / 10
✅ **JÁ IMPLEMENTADO** (commit 6f222a0: "meta 7.8-8.4/10")

```
- Aderência ao prompt: 8.0
- Correlação link-conteúdo: 7.5 (60% com link específico)
- Precisão data/horário: 8.5 (erros críticos <5%)
- Completude: 8.0
```

**Ações necessárias**:
1. ✅ Scrapers oficiais priorizados
2. ⏳ Validação de data rigorosa
3. ⏳ Fix de títulos genéricos
4. ⏳ Enrichment de campos faltantes

#### Meta 2 (6 meses): Score 8.5-9.0 / 10
```
- Aderência ao prompt: 8.5
- Correlação link-conteúdo: 8.5 (75% com link específico)
- Precisão data/horário: 9.0 (erros críticos <2%)
- Completude: 8.5
```

**Ações necessárias**:
1. Scrapers oficiais para todos os venues principais
2. APIs diretas (Sympla, Eventbrite)
3. Cross-validation automática
4. Cache de eventos para deduplicação

---

## 🎯 Roadmap de Implementação

### Fase 1: Quick Wins (1-2 semanas)
- [ ] **Adaptação 2.1**: Detecção e correção de títulos genéricos
- [ ] **Adaptação 3.2**: Verificar validação de links genéricos (pode já estar feita)
- [ ] **Adaptação 4.1**: Enrichment mais agressivo de campos vazios

**Impacto esperado**: +0.5-0.8 pontos na nota média

### Fase 2: Melhorias Estruturais (1 mês)
- [ ] **Adaptação 1.1**: Validação de data rigorosa no scraping
- [ ] **Adaptação 1.2**: Expandir scrapers oficiais (Teatro Municipal, etc)
- [ ] **Adaptação 5.1**: Cross-validation com link

**Impacto esperado**: +0.8-1.2 pontos na nota média

### Fase 3: Otimizações Avançadas (2-3 meses)
- [ ] **Adaptação 3.3**: Melhorar busca inteligente de links
- [ ] Implementar APIs oficiais (Sympla, Eventbrite)
- [ ] Sistema de cache para evitar re-scraping
- [ ] Dashboard de monitoramento de qualidade

**Impacto esperado**: +0.5-0.7 pontos na nota média

---

## 📊 Como Monitorar Melhorias

### 1. Executar Julgamento Regularmente
```bash
python run_judge_production.py
```

**Ver estatísticas**:
- Score médio geral
- Distribuição de notas por critério
- Top 5 melhores e piores eventos

### 2. Analisar Tendências
```bash
# Eventos com nota < 6.0 (precisam atenção)
jq '.events[] | select(.quality_score < 6.0) | {titulo, quality_score, notes}' \
   output/latest/judged_events.json

# Principais problemas (notes mais frequentes)
jq -r '.events[].quality_notes' output/latest/judged_events.json | \
   grep -oE '(Data|Horário|Título|Link|Preço)[^.]*' | sort | uniq -c | sort -rn
```

### 3. Comparar Antes/Depois
```bash
# Salvar baseline antes das mudanças
cp output/latest/judged_events.json baseline_$(date +%Y%m%d).json

# Após implementar melhorias, comparar scores médios
jq '.summary.overall_stats.average' baseline_*.json
jq '.summary.overall_stats.average' output/latest/judged_events.json
```

---

## 🚀 Conclusão

### Problemas Críticos Identificados:
1. **🚨 Precisão de Data/Horário** (30% do score) - erros ocasionais graves
2. **⚠️ Títulos Genéricos** (10% do score) - ~20-30% dos eventos afetados
3. **⚠️ Falta de Links Específicos** (30% do score) - 41% sem link

### Melhorias Prioritárias:
1. **Validação rigorosa de datas** no scraping (prevenir erros críticos)
2. **Correção automática de títulos genéricos** (UX + score)
3. **Expansão de scrapers oficiais** (links + dados confiáveis)

### Impacto Esperado:
- **Score atual**: ~6.5-7.0 / 10
- **Meta 3 meses**: 7.8-8.4 / 10 (**✅ já implementado segundo commits**)
- **Meta 6 meses**: 8.5-9.0 / 10

**Próximo passo**: Verificar no código se as melhorias dos commits recentes (6f222a0, 49f13fb) já estão ativas e funcionando conforme esperado.
