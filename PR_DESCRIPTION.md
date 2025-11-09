# feat: Validação rigorosa de datas (Prioridade Máxima)

## 🎯 Objetivo

Implementar validação rigorosa de datas para prevenir erros críticos que causam perda de até **9 pontos** no score de qualidade (30% do peso total).

## 📊 Problema Identificado

Erros de data são o **problema mais crítico** segundo análise de qualidade:
- **Peso**: 30% do score total
- **Penalidade**: Diferença de >1 mês = nota 0-3 = perda de até 9 pontos
- **Causa**: LLMs "alucinando" datas quando HTML não tem data clara
- **Frequência estimada**: ~15% dos eventos

## ✅ Solução Implementada

### `utils/date_validator.py`
Validador que extrai datas do HTML e compara com data extraída pelo scraper.

**Extração inteligente de datas:**
- `<time datetime>` (prioridade máxima)
- JSON-LD schema.org startDate/endDate
- Meta tags
- Texto parseado com regex

**Classificação de severidade:**
- ✅ **OK**: 0-7 dias (aceito)
- ⚠️ **Leve**: 8-14 dias (aceito, possível multi-sessão)
- ⚠️ **Médio**: 15-30 dias (aceito com aviso)
- ❌ **Grave**: 31-180 dias (rejeitado)
- ❌ **Crítico**: >180 dias (rejeitado)

## 📈 Impacto Esperado

- Reduzir erros críticos de data: **~15% → <5%**
- Aumentar score médio de qualidade: **6.5-7.0 → 7.8-8.4/10**
- Prevenir perda de até 9 pontos por evento

## 📝 Documentação

- `MELHORIAS_PRIORIDADE_MAXIMA.md` (resumo 120 palavras)
- `ANALISE_QUALIDADE_EVENTOS.md` (análise completa dos problemas)

## 🔄 Próximos Passos

1. Integrar `DateValidator` em `agents/validation_agent.py`
2. Adicionar validação em scrapers oficiais (CCBB, Cecília Meireles)
3. Monitorar redução de erros com `run_judge_production.py`

---

**Branch**: `claude/search-feature-011CUxb7ZNhTSj2bA7HRwbSG`
**Commits**: 2 commits (análise + implementação)
**Refs**: ANALISE_QUALIDADE_EVENTOS.md (Adaptação 1.1 - Prioridade Máxima)
