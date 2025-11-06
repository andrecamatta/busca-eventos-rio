# Sistema de Evals - Busca de Eventos

Sistema de avaliação automatizada para validar se as diferentes fases do projeto estão atingindo suas expectativas.

## Estrutura

```
evals/
  __init__.py
  eval_search.py      # Eval da FASE 1 (Busca Perplexity)
  README.md           # Este arquivo
```

---

## eval_search.py - FASE 1: Busca com Perplexity

Avalia se a busca do Perplexity está retornando eventos conforme as expectativas definidas nos prompts.

### Expectativas Avaliadas

#### Eventos Gerais (por categoria)
- **Jazz**: 8-12 eventos
- **Teatro-Comédia**: 8-12 eventos
- **Outdoor-FimDeSemana**: 8-12 eventos

#### Eventos de Venues Específicos
- **Casa do Choro**: 3-5 eventos (mínimo)
- **Sala Cecília Meirelles**: 3-5 eventos (mínimo)
- **Teatro Municipal do Rio de Janeiro**: 3-5 eventos (mínimo)

#### Completude dos Campos (obrigatórios)
- Data válida (formato DD/MM/YYYY)
- Horário
- Local completo
- Descrição
- Link (opcional, apenas informativo)

### Uso

```bash
# Rodar eval básico
python evals/eval_search.py

# Especificar arquivo de output
python evals/eval_search.py --output output/structured_events.json

# Ajustar threshold de aprovação
python evals/eval_search.py --threshold 70  # Default: 80
```

### Exit Codes

- `0`: PASS (score >= threshold)
- `1`: FAIL (score < threshold)
- `2`: ERRO (arquivo não encontrado ou erro de execução)

### Exemplo de Saída

```
======================================================================
EVAL: Busca Perplexity (FASE 1)
======================================================================
Arquivo: output/structured_events.json

📊 EVENTOS GERAIS:
   Total: 9 eventos

   Jazz: 3/8-12 ⚠️  BELOW
   Teatro-Comédia: 2/8-12 ⚠️  BELOW
   Outdoor-FimDeSemana: 4/8-12 ⚠️  BELOW

🏛️  EVENTOS DE VENUES:
   Total: 2 eventos

   Casa do Choro: 2/3-5 ⚠️  BELOW
   Sala Cecília Meirelles: 0/3-5 ❌ CRITICAL
   Teatro Municipal do Rio de Janeiro: 0/3-5 ❌ CRITICAL

📋 COMPLETUDE DOS CAMPOS:

   ✅ Data (obrigatório): 11/11 (100%)
   ✅ Horario (obrigatório): 11/11 (100%)
   ✅ Local (obrigatório): 11/11 (100%)
   ✅ Descricao (obrigatório): 11/11 (100%)
   ✅ Link (opcional): 5/11 (45%)

   Data válida (formato): 11/11 (100%)

======================================================================
SCORE FINAL: 40% (4/10 critérios OK)
STATUS: ❌ FAIL
======================================================================
```

### Interpretação dos Status

- `✅ OK`: Dentro da meta esperada
- `✅ ABOVE`: Acima da meta (ainda OK)
- `⚠️  BELOW`: Abaixo da meta (warning)
- `❌ CRITICAL`: Categoria/venue sem eventos (crítico)

---

## Futuras Expansões

### eval_validation.py - FASE 2: Validação
- Avaliar acurácia das validações de data
- Medir falsos positivos/negativos
- Verificar detecção de divergências

### eval_enrichment.py - FASE 3: Enriquecimento
- Avaliar qualidade das descrições enriquecidas
- Verificar uso de contexto adicional

### eval_end_to_end.py - Sistema Completo
- Métricas de ponta a ponta
- Comparação com ground truth (golden dataset)
- Precision, Recall, F1-score

---

## Integração CI/CD

```bash
# Executar todos os evals
python evals/eval_search.py || exit 1
# python evals/eval_validation.py || exit 1  # Futuro
# python evals/eval_end_to_end.py || exit 1  # Futuro
```

---

## Troubleshooting

### Erro: "Arquivo não encontrado"
Certifique-se de que o sistema foi executado e gerou `output/structured_events.json`:
```bash
python main.py
```

### Score muito baixo
Isso indica que os prompts não estão sendo seguidos adequadamente. Possíveis causas:
- Perplexity retornando poucos eventos
- Categorias/venues sendo ignorados
- Período de busca muito restritivo

Verifique os logs do sistema e ajuste os prompts em `agents/search_agent.py`.
