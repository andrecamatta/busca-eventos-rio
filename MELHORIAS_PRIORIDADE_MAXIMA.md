# Melhorias de Prioridade Máxima - Qualidade de Eventos

## Validação Rigorosa de Datas

### Problema
Erros de data causam perda de até **9 pontos** no score de qualidade (30% do peso total). LLMs "alucinam" datas quando links não têm data clara.

### Solução Implementada
**`utils/date_validator.py`**: Validador que extrai datas do HTML e compara com data extraída.

- Extrai datas de `<time datetime>`, JSON-LD schema.org, meta tags e texto
- Classifica severidade: OK (0 dias), Leve (≤14 dias), Grave (>30 dias), Crítico (>180 dias)
- Rejeita apenas erros graves/críticos (>30 dias)

### Impacto Esperado
- Reduzir erros críticos de ~15% para <5%
- Aumentar score médio de 6.5-7.0 para 7.8-8.4

### Próximos Passos
Integrar `DateValidator` nos agentes de validação e scrapers oficiais.
