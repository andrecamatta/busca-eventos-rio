# Roadmap de Melhorias - Busca Eventos Rio

**Data:** 11/11/2025
**Baseado em:** Análise de logs de produção Railway (31 eventos atuais)
**Branch base:** `master` (produção)
**Meta:** Aumentar de 31 para 50+ eventos por execução (+61%)

---

## 📊 Situação Atual (Produção)

```
Total: 31 eventos

✅ Funcionando bem:
- Jazz: 5/4 eventos (meta superada)
- Música Clássica: 5/2 eventos (meta superada)
- Cinema: 5 eventos
- Feira de Artesanato: 2 eventos

❌ Com problemas:
- Comédia: 0 eventos (busca encontra 3, validação rejeita 100%)
- Feira Gastronômica: 0 eventos (busca encontra 3, validação rejeita 100%)
- Outdoor/Parques: 0-3 eventos (inconsistente - 66% de falha)
```

---

## 🎯 Roadmap em 3 Fases

### **FASE 1: Fixes Críticos** ⚡ (Impacto: +6-9 eventos)
**Prazo sugerido:** 1-2 dias
**Esforço:** Baixo
**Impacto:** ALTO

### **FASE 2: Otimizações de Prompts** 🔧 (Impacto: +10-15 eventos)
**Prazo sugerido:** 3-5 dias
**Esforço:** Médio
**Impacto:** ALTO

### **FASE 3: Melhorias Estruturais** 🏗️ (Impacto: +5-10 eventos)
**Prazo sugerido:** 1-2 semanas
**Esforço:** Alto
**Impacto:** MÉDIO-ALTO

---

# FASE 1: Fixes Críticos ⚡

## 🔴 **1.1 - Normalização de Formato de Horário**

### Problema
Validador rejeita 100% dos eventos de Comédia e Feira Gastronômica por formato de horário brasileiro.

**Evidência dos logs:**
```
❌ Rafael Portugal: Formato inválido "20h00" (esperado "20:00")
❌ Festival Food Trucks: Formato inválido "14h00 às 22h00"
```

### Solução
Criar função de normalização e aplicar ANTES da validação.

**Arquivo:** `utils/date_helpers.py` (criar se não existir)

```python
import re
from typing import Optional

def normalize_time_format(horario: str) -> str:
    """
    Normaliza formatos de horário brasileiro para HH:MM.

    Exemplos:
        '20h00' → '20:00'
        '14h às 22h' → '14:00'
        '18h30' → '18:30'
        '9h' → '09:00'

    Args:
        horario: Horário em formato brasileiro

    Returns:
        Horário normalizado em formato HH:MM
    """
    if not horario or not isinstance(horario, str):
        return horario

    horario = horario.strip()

    # Se já está no formato HH:MM, retornar
    if re.match(r'^\d{1,2}:\d{2}$', horario):
        # Adicionar zero à esquerda se necessário
        parts = horario.split(':')
        return f"{int(parts[0]):02d}:{parts[1]}"

    # Remover sufixos de faixa ("às", "até", "a")
    horario = re.split(r'\s+(às|até|a)\s+', horario, maxsplit=1)[0]

    # Converter formato brasileiro: "20h00" → "20:00", "9h" → "09:00"
    match = re.match(r'(\d{1,2})h(\d{2})?', horario)
    if match:
        hora = int(match.group(1))
        minuto = match.group(2) or '00'
        return f"{hora:02d}:{minuto}"

    # Se não conseguiu converter, retornar original
    return horario


def validate_time_format(horario: str) -> bool:
    """
    Valida se horário está em formato HH:MM válido.

    Args:
        horario: Horário a validar

    Returns:
        True se válido, False caso contrário
    """
    if not horario or not isinstance(horario, str):
        return False

    # Normalizar antes de validar
    horario_normalizado = normalize_time_format(horario)

    # Validar formato HH:MM
    match = re.match(r'^(\d{2}):(\d{2})$', horario_normalizado)
    if not match:
        return False

    hora, minuto = int(match.group(1)), int(match.group(2))
    return 0 <= hora <= 23 and 0 <= minuto <= 59
```

**Arquivo:** `agents/verify_agent.py`

```python
# Adicionar import no topo:
from utils.date_helpers import normalize_time_format, validate_time_format

# Modificar a função que valida eventos (localizar a função existente):
def validate_event(self, event: dict) -> tuple[bool, str]:
    """Valida evento com normalização de horário."""

    # ... código existente ...

    # ADICIONAR ANTES da validação de horário:
    if 'horario' in event and event['horario']:
        # Normalizar formato brasileiro → HH:MM
        event['horario'] = normalize_time_format(event['horario'])

    # Validação de horário (código existente):
    if 'horario' in event:
        if not validate_time_format(event['horario']):
            return False, f"Formato de horário inválido: {event['horario']}"

    # ... resto do código existente ...
```

### Impacto
- **+6 eventos imediatos** (3 Comédia + 3 Feira Gastronômica)
- **+19% de aumento** (31 → 37 eventos)

### Testes
```python
# Adicionar testes em tests/test_date_helpers.py
def test_normalize_time_format():
    assert normalize_time_format("20h00") == "20:00"
    assert normalize_time_format("14h às 22h") == "14:00"
    assert normalize_time_format("9h") == "09:00"
    assert normalize_time_format("18h30") == "18:30"
    assert normalize_time_format("20:00") == "20:00"  # Já normalizado
```

---

## 🔴 **1.2 - Validação de Links e Eventos Futuros**

### Problema
Perplexity retorna eventos com links expirados ou eventos passados.

**Evidência dos logs:**
```
❌ Afonso Padilha: Link encerrado (evento já passou)
❌ Rafael Portugal: Link 404 Not Found
```

### Solução
Adicionar validação mais rigorosa de data e link.

**Arquivo:** `agents/verify_agent.py`

```python
from datetime import datetime, date

def validate_event_date_and_link(self, event: dict, search_start_date: date) -> tuple[bool, str]:
    """
    Valida se evento está no futuro e link está acessível.

    Args:
        event: Evento a validar
        search_start_date: Data inicial de busca

    Returns:
        (is_valid, error_message)
    """
    # Validar que evento é futuro
    if 'data' in event:
        try:
            event_date = datetime.strptime(event['data'], '%d/%m/%Y').date()

            # Evento deve ser igual ou posterior à data de início
            if event_date < search_start_date:
                return False, f"Evento já passou: data {event['data']} < início {search_start_date}"

        except ValueError:
            return False, f"Data inválida: {event['data']}"

    # Validar link (se existir)
    if event.get('link_ingresso') and event['link_ingresso'] != 'null':
        link = event['link_ingresso']

        # Validar que é URL válida
        if not link.startswith('http'):
            return False, f"Link inválido (sem protocolo): {link}"

        # Detectar links temporários suspeitos
        suspicious_patterns = [
            '/stories/',  # Instagram Stories
            '/p/',  # Instagram posts (podem expirar)
            'facebook.com/events/',  # Facebook events (podem ser removidos)
        ]

        for pattern in suspicious_patterns:
            if pattern in link:
                logger.warning(f"Link suspeito detectado: {link}")
                # Não rejeitar, mas logar warning

    return True, ""


# Integrar na função de validação principal:
def validate_event(self, event: dict, search_start_date: date) -> tuple[bool, str]:
    """Valida evento completo."""

    # ... código existente ...

    # ADICIONAR validação de data e link:
    is_valid, error = self.validate_event_date_and_link(event, search_start_date)
    if not is_valid:
        return False, error

    # ... resto do código ...
```

### Impacto
- **+2-3 eventos** que seriam rejeitados por link morto
- **Redução de 80% em eventos expirados**

---

## 🟡 **1.3 - Especificar Formato JSON em Todos os Prompts**

### Problema
Nem todos os prompts especificam formato JSON esperado, causando erros de parsing.

### Solução
Adicionar especificação JSON consistente em TODOS os prompts.

**Arquivo:** `prompts/search_prompts.yaml`

```yaml
# Adicionar em TODAS as categorias e venues:

instrucoes_especiais: |
  ⚠️ FORMATO DE RETORNO OBRIGATÓRIO - JSON:

  {
    "eventos": [
      {
        "titulo": "Nome completo do evento",
        "data": "DD/MM/YYYY",
        "horario": "HH:MM",
        "local": "Nome do Venue",
        "endereco": "Endereço completo com bairro",
        "preco": "R$ XX,XX ou Gratuito ou Consultar",
        "link_ingresso": "URL completa ou null",
        "descricao": "Resumo informativo do evento",
        "eh_recorrente": false
      }
    ]
  }

  ⚠️ CRÍTICO - VALIDAÇÃO DE DADOS:

  DATAS:
  ✅ Apenas eventos FUTUROS: data >= {start_date_str}
  ✅ Dentro do período: {start_date_str} a {end_date_str}
  ❌ NÃO incluir eventos que já passaram

  HORÁRIOS:
  ✅ Formato: "HH:MM" (ex: "20:00", "14:30", "09:00")
  ❌ NÃO usar: "20h", "20h00", "14h às 22h"

  LINKS:
  ✅ URL completa e específica do evento (Sympla, Eventbrite, site oficial)
  ❌ NÃO usar: links temporários, Instagram Stories, páginas genéricas
  ❌ Se não encontrar link válido: usar null

  QUALIDADE:
  ✅ Título específico com nome do artista/evento
  ✅ Local com nome e endereço completos
  ✅ Descrição informativa (estilo, contexto, detalhes)
  ❌ Evitar: títulos genéricos, artistas vagos ("músicos da casa")

  ❌ NÃO retornar texto livre ou HTML
  ✅ SEMPRE retornar JSON válido
```

**Categorias a atualizar:**
- `comedia`
- `outdoor`
- `feira_gastronomica`
- `feira_artesanato`
- Todos os venues que não têm especificação clara

### Impacto
- **Redução de 90% em erros de parsing**
- **+1-2 eventos** que eram perdidos por formato incorreto

---

# FASE 2: Otimizações de Prompts 🔧

## 🟡 **2.1 - Melhorar Prompts de Outdoor/Parques**

### Problema
0 eventos em 66% das execuções (2 de 3 sábados retornam vazio).

### Solução

**Arquivo:** `prompts/search_prompts.yaml` - seção `outdoor`

```yaml
outdoor:
  nome: Outdoor/Parques
  tipo_busca: categoria
  descricao: Eventos culturais ao ar livre ou em locais com área outdoor em fim de semana

  tipos_evento:
    - Cinema ao ar livre
    - Concertos em parques e jardins
    - Shows acústicos outdoor
    - Feiras culturais nichadas (não mainstream)
    - Feiras gastronômicas outdoor
    - Feiras de artesanato em praças
    - Festivais culturais pequenos/médios
    - Eventos em locais com área outdoor (indoor/outdoor)

  palavras_chave:
    # Cinema outdoor:
    - "cinema ao ar livre Rio fim de semana {month_str}"
    - "cinema céu aberto sábado domingo Rio {month_str}"
    - "sessão outdoor Parque Lage {month_str}"

    # Concertos e shows:
    - "show acústico jardim Rio sábado {month_str}"
    - "concerto parque fim de semana Rio {month_str}"
    - "música ao ar livre Rio {month_str}"
    - "show Jockey Club Rio fim de semana {month_str}"
    - "Marina da Glória eventos sábado {month_str}"

    # Feiras:
    - "Feira Rio Antigo {month_str}"
    - "Feira Praça XV sábado domingo {month_str}"
    - "feira artesanato Jardim Botânico fim de semana {month_str}"
    - "feira cultural Aterro Flamengo {month_str}"
    - "food truck Rio fim de semana {month_str}"

    # Locais específicos:
    - "Quinta Boa Vista eventos culturais sábado {month_str}"
    - "Aterro Flamengo shows fim de semana {month_str}"
    - "Parque Garota Ipanema eventos {month_str}"
    - "Forte Copacabana eventos culturais {month_str}"
    - "Boulevard Olímpico programação fim de semana {month_str}"

  venues_sugeridos:
    # Parques tradicionais:
    - Parque Lage (EAV)
    - Jardim Botânico
    - Quinta da Boa Vista
    - Aterro do Flamengo
    - Parque Garota de Ipanema

    # Praças e largos:
    - Praça XV (feiras fixas)
    - Largo da Carioca (Feira Rio Antigo)
    - Praça Mauá (eventos culturais)

    # NOVOS - Locais indoor/outdoor:
    - Jockey Club (área aberta, shows)
    - Marina da Glória (eventos outdoor)
    - Forte de Copacabana (eventos culturais)
    - Boulevard Olímpico (área externa)
    - Lagoa Rodrigo de Freitas (feiras, food trucks)

  fontes_prioritarias:
    # Prioritárias:
    - "site:visit.rio agenda fim de semana"
    - "site:bafafa.com.br rio-de-janeiro"
    - "site:timeout.com/rio-de-janeiro things-to-do weekend"
    - "site:vejario.abril.com.br fim-de-semana"

    # Sympla/Eventbrite:
    - "site:sympla.com.br rio outdoor"
    - "site:eventbrite.com.br rio fim de semana"

    # Redes oficiais:
    - Instagram @visitrio, @rio.prefeitura
    - Instagram @parquelage, @jardimbotanicorj
    - Instagram @jockeyclubrio, @marinadagloria

    # Portais:
    - G1 Rio - seção "Fim de Semana"
    - O Globo - "O Que Fazer no Rio"

  instrucoes_especiais: |
    ⚠️ ESTRATÉGIA DE BUSCA AMPLIADA:

    PERÍODO: {start_date_str} a {end_date_str}
    FOCO: TODOS os sábados e domingos do período

    🎯 BUSCAR (3 categorias):

    1. EVENTOS OUTDOOR TRADICIONAIS:
       - Cinema ao ar livre (Parque Lage, Jardim Botânico)
       - Concertos em parques (música clássica, jazz, MPB acústico)
       - Feiras fixas (Rio Antigo 1º sábado, Praça XV regular)

    2. EVENTOS EM LOCAIS INDOOR/OUTDOOR:
       - Shows em locais com área aberta (Jockey Club, Marina da Glória)
       - Festivais gastronômicos com área outdoor
       - Eventos culturais em fortes e espaços históricos

    3. EVENTOS HÍBRIDOS:
       - Feiras com música ao vivo outdoor
       - Food trucks + shows acústicos
       - Eventos de cerveja artesanal com área outdoor

    ⚠️ FILTROS REVISADOS:

    ✅ INCLUIR (novo critério mais flexível):
    - Choro e samba ACÚSTICO em locais outdoor (Parque Lage, jardins)
    - Shows de MPB em parques e jardins
    - Eventos culturais de médio porte (não apenas micro eventos)
    - Eventos com componente gastronômico significativo

    ❌ EXCLUIR (mais específico):
    - Shows mainstream em ESTÁDIOS (Maracanã, Jeunesse Arena, Nilton Santos)
    - Mega festivais comerciais (Rock in Rio, Tim Festival, etc.)
    - Eventos esportivos (corridas, pedaladas, maratonas)
    - Artistas mainstream específicos: Ivete Sangalo, Thiaguinho, Alexandre Pires, Ludmilla
    - Palavras: "turnê nacional", "mega show", "arena"

    ⚠️ EVENTOS RECORRENTES:
    - ✅ Feira Praça XV: Todos os sábados e domingos (usar eh_recorrente: true)
    - ✅ Feira Rio Antigo: Primeiro sábado do mês (verificar se está no período)
    - ✅ Eventos semanais confirmados em parques

    ⚠️ VALIDAÇÃO:
    ✓ Data é SÁBADO ou DOMINGO entre {start_date_str} e {end_date_str}
    ✓ Evento é CULTURAL (não comercial/esportivo)
    ✓ Tem artista/tema/feira ESPECÍFICO (não genérico "evento no parque")
    ✓ Link de ingresso ou confirmação oficial (site, Instagram oficial)

    💡 DICA: Buscar "eventos fim de semana Rio {month_str}" SEM data específica
    → Deixar validação filtrar depois para o período correto
```

### Impacto
- **+3-5 eventos outdoor** por execução
- **Redução de taxa de falha** de 66% para ~20%

---

## 🟡 **2.2 - Otimizar Prompts de Comédia**

### Objetivo
Aumentar volume de eventos encontrados de 3 para 6-8.

**Arquivo:** `prompts/search_prompts.yaml` - seção `comedia`

```yaml
comedia:
  nome: Comédia
  tipo_busca: categoria
  descricao: Stand-up e peças de comédia no Rio (exceto infantil)

  tipos_evento:
    - Stand-up comedy
    - Shows de humor e comédia
    - Peças de comédia (teatro adulto)
    - Espetáculos cômicos
    - Noites de comédia em bares

  palavras_chave:
    # Gerais:
    - "stand-up Rio Janeiro {month_range_str}"
    - "comédia Rio {month_range_str}"
    - "show humor Rio {month_range_str}"
    - "stand up Rio entre {start_date_str} e {end_date_str}"
    - "teatro comédia Rio {month_range_str}"

    # Comediantes específicos (TOP 20 Rio):
    - "Rafael Portugal Rio {month_str}"
    - "Afonso Padilha Rio {month_str}"
    - "Thiago Ventura Rio {month_str}"
    - "Clarice Falcão Rio {month_str}"
    - "Fábio Porchat Rio {month_str}"
    - "Marcelo Adnet Rio {month_str}"
    - "Gregório Duvivier Rio {month_str}"
    - "Tatá Werneck Rio {month_str}"
    - "Dani Calabresa Rio {month_str}"
    - "Rodrigo Sant'Anna Rio {month_str}"

    # Venues específicos:
    - "stand-up Theatro Net Rio {month_str}"
    - "comédia Teatro Leblon {month_str}"
    - "humor Teatro Rival {month_str}"
    - "stand-up Teatro Riachuelo Rio {month_str}"
    - "comédia Casa da Matriz {month_str}"

  venues_sugeridos:
    # Teatros comerciais:
    - Theatro Net Rio (Copacabana)
    - Teatro Riachuelo (Centro)
    - Teatro do Leblon
    - Teatro Rival Petrobras (Cinelândia)

    # Teatros alternativos:
    - Teatro Clara Nunes (Penha)
    - Teatro dos Quatro (Jardim Botânico)
    - Teatro Municipal Café Pequeno (Copacabana)

    # Bares e casas de show:
    - Comedy Club Rio
    - The Pub Rio
    - Miranda Bar (Flamengo)
    - Casa da Matriz (Botafogo)
    - Belmonte (várias unidades)

  fontes_prioritarias:
    # Plataformas estruturadas (PRIORIDADE 1):
    - "site:sympla.com.br stand-up rio {month_str}"
    - "site:eventbrite.com.br comédia rio {month_str}"
    - "site:uhuu.com stand-up rio {month_str}"
    - "site:ingresso.com comédia rio {month_str}"
    - "site:ticketoffice.com.br rio stand-up {month_str}"

    # Portais culturais (PRIORIDADE 2):
    - "site:timeout.com/rio-de-janeiro comedy"
    - "site:vejario.abril.com.br comédia"
    - "site:oglobo.com.br cultura comédia"

    # Sites de teatros (PRIORIDADE 3):
    - "site:theatronetrio.com.br em-cartaz"
    - "site:teatroleblon.com.br programacao"
    - "site:teatroriachuelo.com.br rio"

    # Redes sociais (ÚLTIMA OPÇÃO):
    - Instagram @theatronetrio, @teatroleblon
    - Instagram dos comediantes específicos

  instrucoes_especiais: |
    🎯 ESTRATÉGIA DE BUSCA TRIPLA:

    1. BUSCAR POR COMEDIANTES CONHECIDOS:
       - Lista prioritária: Rafael Portugal, Afonso Padilha, Thiago Ventura, etc.
       - Buscar: "{comediante} Rio {month_str}"
       - Fontes: Sympla, Eventbrite, Uhuu, Ingresso.com

    2. BUSCAR POR VENUES ESPECÍFICOS:
       - Theatro Net Rio, Teatro Leblon, Teatro Rival
       - Buscar: "comédia {venue} {month_str}"
       - Fontes: Sites oficiais dos teatros, plataformas de ingresso

    3. BUSCA GERAL:
       - "stand-up Rio {month_str}"
       - Fontes: Sympla (categoria Comédia), TimeOut Rio

    ⚠️ FILTROS CRÍTICOS REVISADOS:

    ✅ INCLUIR:
    - Comédia adulta (stand-up, peças cômicas)
    - Shows de humor mainstream e alternativos
    - Comediantes conhecidos de qualquer temática/orientação
    - Noites de comédia em bares (se tiver nome do comediante)

    ❌ EXCLUIR:
    - Eventos infantis ou "para toda família"
    - Circo (a menos que seja circo adulto de comédia)
    - Palestras motivacionais (não é comédia)

    ⚠️ NOTA sobre filtro LGBTQIA+:
    O filtro anterior foi REMOVIDO. Incluir shows de comédia de qualquer
    temática desde que sejam relevantes e tenham comediante conhecido.

    ⚠️ VALIDAÇÃO:
    ✓ Comediante com NOME ESPECÍFICO (não "diversos comediantes")
    ✓ Venue com nome e endereço completos
    ✓ Link de venda ativo (Sympla, Eventbrite, Uhuu preferencial)
    ✓ Preço definido ou "Consultar" (não vago)
    ✓ Confirmar que NÃO é infantil/família

    ⚠️ FORMATO JSON OBRIGATÓRIO:
    [especificação JSON padrão conforme seção 1.3]
```

### Impacto
- **+3-5 eventos extras** de comédia (além dos 3 que serão recuperados com fix validação)
- **Total projetado:** 6-8 eventos de comédia por execução

---

## 🟡 **2.3 - Otimizar Prompts de Feira Gastronômica**

### Objetivo
Aumentar volume de 3 para 6-8 eventos.

**Arquivo:** `prompts/search_prompts.yaml` - seção `feira_gastronomica`

```yaml
feira_gastronomica:
  nome: Feira Gastronômica
  tipo_busca: categoria
  descricao: Feiras gastronômicas, food festivals e eventos de food trucks em fim de semana

  tipos_evento:
    - Feiras gastronômicas
    - Food festivals
    - Eventos de food trucks
    - Mercados gastronômicos
    - Mercados de rua
    - Eventos de gastronomia
    - Festivais de comida de rua
    - Rodadas gastronômicas
    - Feiras de produtores orgânicos (com área gastronômica)

  palavras_chave:
    # Feiras tradicionais:
    - "feira gastronômica Rio {month_str}"
    - "food festival Rio {month_year_str}"
    - "mercado gastronômico Rio fim de semana {month_str}"
    - "feira comida Rio sábado domingo {month_str}"

    # Food trucks:
    - "food truck Rio fim de semana {month_str}"
    - "festival food truck Rio {month_str}"
    - "food trucks Aterro Flamengo {month_str}"
    - "food trucks Lagoa Rio {month_str}"
    - "food trucks Marina da Glória {month_str}"

    # Mercados específicos:
    - "Mercado Jockey Rio {month_str}"
    - "Rota Gastronômica Rio fim de semana {month_str}"
    - "feira produtores Rio sábado {month_str}"
    - "mercado orgânico Rio fim de semana {month_str}"

    # Eventos híbridos:
    - "festival cerveja artesanal Rio {month_str}"
    - "festa gastronomia Rio fim de semana {month_str}"
    - "evento gastronômico parque Rio {month_str}"

  venues_sugeridos:
    # Locais outdoor tradicionais:
    - Aterro do Flamengo
    - Lagoa Rodrigo de Freitas
    - Marina da Glória
    - Parque Madureira
    - Quinta da Boa Vista

    # Locais com área outdoor/indoor:
    - Jockey Club (Mercado Jockey)
    - Cidade das Artes (área externa)
    - Centro Cultural Light
    - Galpões culturais (Lapa, Centro)

    # Praças e largos:
    - Praça XV
    - Praça Mauá
    - Boulevard Olímpico
    - Largo da Carioca

  fontes_prioritarias:
    # Plataformas (PRIORIDADE 1):
    - "site:sympla.com.br feira gastronômica rio {month_str}"
    - "site:sympla.com.br food truck rio {month_str}"
    - "site:eventbrite.com.br gastronomia rio {month_str}"
    - "site:fever.com.br rio gastronomia {month_str}"

    # Portais especializados (PRIORIDADE 2):
    - "site:timeout.com/rio-de-janeiro food"
    - "site:vejario.abril.com.br gastronomia"
    - "site:oglobo.com.br gastronomia eventos"
    - "site:bafafa.com.br rio-de-janeiro feira"

    # Sites oficiais (PRIORIDADE 3):
    - "site:visit.rio gastronomia"
    - "site:jockeyclubbrasileiro.com.br mercado"

    # Redes sociais (ÚLTIMA OPÇÃO):
    - Instagram @foodtrucksrio, @riofoodies
    - Instagram @jockeyclubrio, @marinadagloria

  instrucoes_especiais: |
    🎯 ESTRATÉGIA DE BUSCA QUÁDRUPLA:

    1. FEIRAS GASTRONÔMICAS FIXAS:
       - Mercado Jockey (sábados/domingos regulares)
       - Feiras de produtores orgânicos
       - Mercados de rua gastronômicos

    2. FOOD TRUCKS:
       - Eventos de food trucks em parques
       - Festivais de food trucks
       - Rodadas de food trucks (Aterro, Lagoa, Marina)

    3. FESTIVAIS DE GASTRONOMIA:
       - Food festivals temáticos
       - Festivais de cerveja + gastronomia
       - Eventos de comida de rua

    4. EVENTOS HÍBRIDOS:
       - Feiras com área gastronômica significativa
       - Shows + food trucks
       - Eventos culturais com feira gastronômica

    ⚠️ CRITÉRIOS DE INCLUSÃO:

    ✅ INCLUIR SE:
    - Evento tem GASTRONOMIA como componente principal ou significativo
    - Feira de produtores COM área gastronômica (degustação, refeições)
    - Festival de cerveja artesanal COM food trucks/gastronomia
    - Mínimo 5 food trucks ou 10 expositores gastronômicos

    ❌ EXCLUIR SE:
    - Apenas "área de alimentação" de evento não-gastronômico
    - Show/evento onde comida é apenas complementar
    - Bares/restaurantes normais (não é feira/festival)

    ⚠️ EVENTOS RECORRENTES:
    - Mercado Jockey: Sábados e domingos (usar eh_recorrente: true)
    - Food trucks Lagoa: Domingos regulares (confirmar se está ativo)

    ⚠️ VALIDAÇÃO:
    ✓ Data é SÁBADO ou DOMINGO entre {start_date_str} e {end_date_str}
    ✓ Evento tem componente gastronômico SIGNIFICATIVO
    ✓ Local específico com endereço (não vago "Rio de Janeiro")
    ✓ Link de informação/ingresso (Sympla, Eventbrite, site oficial)

    ⚠️ FORMATO JSON OBRIGATÓRIO:
    [especificação JSON padrão conforme seção 1.3]
```

### Impacto
- **+3-5 eventos extras** de feira gastronômica (além dos 3 recuperados com fix)
- **Total projetado:** 6-8 eventos de feira gastronômica por execução

---

# FASE 3: Melhorias Estruturais 🏗️

## 🟢 **3.1 - Priorizar Fontes Estruturadas sobre Redes Sociais**

### Problema
Dependência excessiva de Instagram/Facebook que não têm dados estruturados.

### Solução
Reordenar prioridade de fontes em TODOS os prompts.

**Padrão a aplicar:**

```yaml
fontes_prioritarias:
  # NÍVEL 1 - Plataformas estruturadas (dados completos):
  - "site:sympla.com.br {categoria} rio {month_str}"
  - "site:eventbrite.com.br {categoria} rio"
  - "site:feverup.com rio {categoria}"
  - "site:ingresso.com {venue/categoria}"
  - Site oficial do venue (se tiver sistema de ingressos)

  # NÍVEL 2 - Portais culturais curados:
  - "site:timeout.com/rio-de-janeiro {categoria}"
  - "site:vejario.abril.com.br {categoria}"
  - "site:oglobo.com.br cultura {categoria}"
  - "site:visit.rio {categoria}"

  # NÍVEL 3 - Sites oficiais de venues:
  - Site oficial do venue/categoria

  # NÍVEL 4 - Redes sociais (ÚLTIMO RECURSO):
  - Instagram @{handle} (APENAS se tiver datas explícitas em posts)
  - Facebook (APENAS eventos cadastrados na aba "Eventos")

instrucoes_especiais: |
  ⚠️ HIERARQUIA DE FONTES:

  1. PRIORIZAR: Sympla, Eventbrite, Fever, Ingresso.com
     → Dados estruturados: data, horário, local, link permanente

  2. USAR: TimeOut, Veja Rio, portais culturais
     → Curadoria profissional, informações completas

  3. COMPLEMENTAR: Sites oficiais
     → Validar informações das outras fontes

  4. EVITAR (usar só se necessário): Instagram/Facebook
     → APENAS se post tiver data/horário EXPLÍCITO
     → SEMPRE buscar link alternativo (Sympla/Eventbrite)
     → NÃO aceitar: "toda semana", "em breve", "a confirmar"
```

**Aplicar em:**
- Maze Jazz Club
- Clube do Jazz / Teatro Rival
- Parque Lage
- Todos os venues pequenos

### Impacto
- **+2-3 eventos** com dados de melhor qualidade
- **Redução de 70% em eventos com informações incompletas**

---

## 🟢 **3.2 - Implementar Critérios de Qualidade de Eventos**

### Problema
Sistema aceita eventos vagos e genéricos que não são úteis.

### Solução
Adicionar critérios de qualidade em todos os prompts.

**Adicionar em TODOS os prompts:**

```yaml
instrucoes_especiais: |
  ⚠️ CRITÉRIOS DE QUALIDADE OBRIGATÓRIOS:

  ✅ EVENTO BOM (incluir):
  - Título ESPECÍFICO com nome do artista/grupo/evento
    ✅ Bom: "Quarteto Fantástico - Jazz Noturno"
    ❌ Ruim: "Show de Jazz"

  - Artista/grupo com NOME PRÓPRIO
    ✅ Bom: "Maria Silva Trio", "Orquestra Sinfônica do Rio"
    ❌ Ruim: "Músicos da casa", "Diversos artistas", "A confirmar"

  - Local com NOME ESPECÍFICO e ENDEREÇO COMPLETO
    ✅ Bom: "Maze Jazz Club - Rua Barão de Iguatemi, 388, Praça da Bandeira"
    ❌ Ruim: "Bar na Lapa", "Teatro no Centro"

  - Link ATIVO e ESPECÍFICO
    ✅ Bom: sympla.com.br/evento/quarteto-fantastico-12345
    ❌ Ruim: instagram.com/venue (página genérica)
    ✅ Aceito: null (se não encontrar link, mas evento confirmado)

  - Descrição INFORMATIVA (40+ caracteres)
    ✅ Bom: "Quarteto de jazz instrumental apresenta repertório de bebop clássico"
    ❌ Ruim: "Show ao vivo", "Evento cultural"

  - Preço DEFINIDO ou "Consultar"
    ✅ Bom: "R$ 50,00", "R$ 30,00 / R$ 15,00 (meia)", "Gratuito", "Consultar"
    ❌ Ruim: "A definir", vazio

  ⚠️ SE EVENTO NÃO TEM QUALIDADE MÍNIMA:
  - Buscar MAIS INFORMAÇÕES antes de incluir
  - Se não encontrar info completa: EXCLUIR
  - NÃO incluir eventos vagos/genéricos
```

### Impacto
- **Melhoria de 80% na qualidade dos eventos**
- **Redução de eventos inúteis** para o usuário
- **+1-2 eventos úteis** (substituindo eventos vagos)

---

## 🟢 **3.3 - Melhorar Instruções sobre Eventos Recorrentes**

### Problema
Uso inconsistente de `eh_recorrente: true`, causando duplicatas ou rejeições.

### Solução
Especificar claramente QUANDO e COMO usar eventos recorrentes.

**Adicionar em TODOS os prompts:**

```yaml
instrucoes_especiais: |
  ⚠️ EVENTOS RECORRENTES (eh_recorrente: true):

  QUANDO USAR:

  1. MÚLTIPLAS SESSÕES do MESMO EVENTO:
     Exemplo: Filme exibido 5 vezes na semana
     → Cadastrar 1 vez com eh_recorrente: true
     → data: primeira sessão no período
     → descricao: "Sessões: 14/11 às 18h, 15/11 às 20h, 16/11 às 18h..."

  2. EVENTOS SEMANAIS CONFIRMADOS:
     Exemplo: "Jam Session toda quarta de novembro"
     → Cadastrar 1 vez com eh_recorrente: true
     → data: primeira quarta no período
     → titulo: "Jam Session (Todas as Quartas)"
     → descricao: "Evento semanal todas as quartas-feiras de {month_str}"

  3. FEIRAS FIXAS MENSAIS:
     Exemplo: "Feira Rio Antigo todo 1º sábado"
     → Verificar SE o 1º sábado está no período {start_date_str} a {end_date_str}
     → Cadastrar 1 vez com eh_recorrente: true (se aplicável)
     → descricao: "Feira fixa no primeiro sábado de cada mês"

  QUANDO NÃO USAR:

  ❌ Evento genérico "acontece às vezes" SEM confirmação específica
  ❌ "Programação regular" SEM datas confirmadas
  ❌ "A confirmar", "Em breve", "Volta em {mês}"
  ❌ Eventos passados que "podem voltar"

  FORMATO PARA RECORRENTES:

  {
    "titulo": "Nome do Evento (Múltiplas Sessões)" ou "(Todas as Quartas)",
    "data": "DD/MM/YYYY",  # Primeira ocorrência no período
    "horario": "HH:MM",     # Horário da primeira ou padrão
    "eh_recorrente": true,
    "descricao": "Detalhes da recorrência: datas/horários específicos ou padrão"
  }
```

### Impacto
- **Redução de 90% em duplicatas**
- **+1-2 eventos** que eram rejeitados por mal uso de recorrente

---

## 🟢 **3.4 - Monitoramento e Alertas**

### Objetivo
Detectar proativamente quando categorias não atingem metas.

### Solução
Adicionar sistema de alertas no orquestrador.

**Arquivo:** `main.py` ou `agents/retry_agent.py`

```python
from typing import Final
import logging

logger = logging.getLogger(__name__)

# Adicionar constantes:
MIN_EVENTS_ALERT_THRESHOLD: Final[dict[str, int]] = {
    "Jazz": 4,
    "Música Clássica": 2,
    "Comédia": 3,  # Novo: alertar se < 3
    "Outdoor/Parques": 2,  # Novo: alertar se < 2
}


def check_category_thresholds(verified_events: list[dict]) -> dict[str, dict]:
    """
    Verifica se categorias atingiram metas mínimas.

    Returns:
        Dict com alertas por categoria: {
            "categoria": {
                "found": int,
                "minimum": int,
                "status": "ok" | "warning" | "critical"
            }
        }
    """
    stats = {}

    # Contar eventos por categoria
    category_counts = {}
    for event in verified_events:
        cat = event.get('categoria', 'Geral')
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Verificar metas
    for category, minimum in MIN_EVENTS_ALERT_THRESHOLD.items():
        found = category_counts.get(category, 0)

        if found >= minimum:
            status = "ok"
        elif found >= minimum * 0.7:  # 70% da meta
            status = "warning"
        else:
            status = "critical"

        stats[category] = {
            "found": found,
            "minimum": minimum,
            "status": status
        }

        # Logar alertas
        if status == "critical":
            logger.error(f"🚨 CRÍTICO: {category} tem apenas {found}/{minimum} eventos!")
        elif status == "warning":
            logger.warning(f"⚠️  ATENÇÃO: {category} tem {found}/{minimum} eventos (abaixo da meta)")
        else:
            logger.info(f"✅ {category}: {found}/{minimum} eventos (meta atingida)")

    return stats


# Integrar no orquestrador após verificação:
def run_orchestration(self):
    # ... código existente ...

    verified_events = self.verify_agent.verify_events(all_events)

    # ADICIONAR: Check de thresholds com alertas
    threshold_stats = check_category_thresholds(verified_events)

    # Salvar stats em arquivo JSON para monitoramento externo
    with open('data/threshold_alerts.json', 'w', encoding='utf-8') as f:
        json.dump(threshold_stats, f, ensure_ascii=False, indent=2)

    # ... resto do código ...
```

### Impacto
- **Detecção proativa** de categorias com problemas
- **Visibilidade** para ajustes futuros
- **Base para alertas** automáticos (email, Slack, etc.)

---

# 📊 Impacto Total Esperado

## Antes (Atual - Produção)
```
Total: 31 eventos

Por categoria:
- Jazz: 5 eventos ✅ (meta: 4)
- Música Clássica: 5 eventos ✅ (meta: 2)
- Cinema: 5 eventos
- Feira de Artesanato: 2 eventos
- Comédia: 0 eventos ❌
- Feira Gastronômica: 0 eventos ❌
- Outdoor/Parques: 0 eventos ❌
- Geral: 13 eventos
```

## Depois (Projeção - Todas as Fases)

### Fase 1 (Fixes Críticos): 31 → 40 eventos
```
+6 eventos: Fix validação horário (Comédia + Feira Gastronômica)
+2 eventos: Validação links e eventos futuros
+1 evento: Formato JSON consistente
= +9 eventos IMEDIATOS
```

### Fase 2 (Otimizações): 40 → 52 eventos
```
+4 eventos: Outdoor/Parques melhorado
+4 eventos: Comédia otimizada (além dos 3 recuperados)
+4 eventos: Feira Gastronômica otimizada (além dos 3 recuperados)
= +12 eventos MÉDIO PRAZO
```

### Fase 3 (Melhorias Estruturais): 52 → 56 eventos
```
+2 eventos: Priorização de fontes estruturadas
+1 evento: Critérios de qualidade
+1 evento: Eventos recorrentes bem especificados
= +4 eventos LONGO PRAZO
```

## Total Final Projetado: **56 eventos** (+81%)

```
Por categoria (projeção):
- Jazz: 5 eventos ✅ (meta: 4) [sem mudança]
- Música Clássica: 5 eventos ✅ (meta: 2) [sem mudança]
- Cinema: 5 eventos [sem mudança]
- Feira de Artesanato: 2 eventos [sem mudança]
- Comédia: 7 eventos ✅ (meta proposta: 5) [+7]
- Feira Gastronômica: 7 eventos ✅ (meta proposta: 5) [+7]
- Outdoor/Parques: 4 eventos ✅ (meta proposta: 2) [+4]
- Geral: 21 eventos [+8]
```

---

# 🚀 Ordem de Implementação Recomendada

## Semana 1: Fase 1 - Fixes Críticos

**Dia 1-2:**
- [ ] 1.1 - Implementar `normalize_time_format()` em `utils/date_helpers.py`
- [ ] Integrar normalização em `agents/verify_agent.py`
- [ ] Testes unitários para normalização
- [ ] **Deploy e validação** → **+6 eventos imediatos**

**Dia 3:**
- [ ] 1.2 - Implementar validação de links e eventos futuros
- [ ] Testes de validação
- [ ] **Deploy** → **+2 eventos**

**Dia 4-5:**
- [ ] 1.3 - Atualizar TODOS os prompts com especificação JSON
- [ ] Validar formato em todas as categorias
- [ ] **Deploy** → **+1 evento**

**Resultado Semana 1: 31 → 40 eventos (+29%)**

---

## Semana 2: Fase 2 - Otimizações

**Dia 1-2:**
- [ ] 2.1 - Reescrever prompt `outdoor` completo
- [ ] Testar em ambiente de staging
- [ ] **Deploy** → **+4 eventos outdoor**

**Dia 3:**
- [ ] 2.2 - Otimizar prompt `comedia`
- [ ] Adicionar comediantes específicos
- [ ] **Deploy** → **+4 eventos comédia**

**Dia 4-5:**
- [ ] 2.3 - Otimizar prompt `feira_gastronomica`
- [ ] Adicionar food trucks e eventos híbridos
- [ ] **Deploy** → **+4 eventos feira gastronômica**

**Resultado Semana 2: 40 → 52 eventos (+68% vs. inicial)**

---

## Semana 3-4: Fase 3 - Melhorias Estruturais

**Semana 3:**
- [ ] 3.1 - Revisar fontes_prioritarias em TODOS os prompts
- [ ] Reordenar: Sympla/Eventbrite > Portais > Redes sociais
- [ ] **Deploy** → **+2 eventos**

- [ ] 3.2 - Adicionar critérios de qualidade em todos os prompts
- [ ] **Deploy** → **+1 evento**

**Semana 4:**
- [ ] 3.3 - Melhorar instruções sobre eventos recorrentes
- [ ] **Deploy** → **+1 evento**

- [ ] 3.4 - Implementar sistema de monitoramento e alertas
- [ ] Dashboard de thresholds

**Resultado Final: 52 → 56 eventos (+81% vs. inicial)**

---

# ✅ Checklist de Implementação

## Fase 1: Fixes Críticos ⚡
- [ ] `utils/date_helpers.py`: Criar com `normalize_time_format()` e `validate_time_format()`
- [ ] `agents/verify_agent.py`: Integrar normalização de horário
- [ ] `agents/verify_agent.py`: Adicionar `validate_event_date_and_link()`
- [ ] `tests/test_date_helpers.py`: Testes unitários completos
- [ ] `prompts/search_prompts.yaml`: Adicionar especificação JSON em:
  - [ ] `comedia`
  - [ ] `outdoor`
  - [ ] `feira_gastronomica`
  - [ ] `feira_artesanato`
  - [ ] Todos os venues sem especificação clara

## Fase 2: Otimizações 🔧
- [ ] `prompts/search_prompts.yaml` - seção `outdoor`:
  - [ ] Reescrever palavras_chave (adicionar Jockey, Marina, etc.)
  - [ ] Atualizar venues_sugeridos (indoor/outdoor)
  - [ ] Relaxar filtros de exclusão
  - [ ] Ampliar janela de busca
  - [ ] Adicionar instruções sobre eventos híbridos

- [ ] `prompts/search_prompts.yaml` - seção `comedia`:
  - [ ] Adicionar comediantes específicos (20 nomes)
  - [ ] Adicionar venues alternativos (Teatro Clara Nunes, etc.)
  - [ ] Remover/revisar filtro LGBTQIA+
  - [ ] Adicionar fontes estruturadas (Uhuu, TicketOffice)

- [ ] `prompts/search_prompts.yaml` - seção `feira_gastronomica`:
  - [ ] Adicionar palavras-chave de food trucks
  - [ ] Incluir eventos híbridos (cerveja + gastronomia)
  - [ ] Adicionar venues (Jockey, Marina, Lagoa)
  - [ ] Critérios claros de inclusão

## Fase 3: Melhorias Estruturais 🏗️
- [ ] `prompts/search_prompts.yaml` - TODOS os prompts:
  - [ ] Reordenar `fontes_prioritarias` (Sympla/Eventbrite first)
  - [ ] Adicionar critérios de qualidade
  - [ ] Melhorar instruções sobre eventos recorrentes

- [ ] `main.py` ou `agents/retry_agent.py`:
  - [ ] Implementar `check_category_thresholds()`
  - [ ] Adicionar logging de alertas
  - [ ] Salvar stats em JSON

- [ ] Testes e validação:
  - [ ] Teste de regressão completo
  - [ ] Validar thresholds funcionando
  - [ ] Monitorar logs de produção

---

# 📈 Métricas de Sucesso

## KPIs Principais

**Meta Final:** 50+ eventos por execução (vs. 31 atual)

### Por Fase:
- **Fase 1:** 40 eventos (+29%) ✅
- **Fase 2:** 52 eventos (+68%) ✅
- **Fase 3:** 56 eventos (+81%) ✅

### Por Categoria:
- **Comédia:** 0 → 7 eventos
- **Feira Gastronômica:** 0 → 7 eventos
- **Outdoor/Parques:** 0 → 4 eventos (reduzir taxa de falha de 66% para 20%)

### Qualidade:
- **Taxa de rejeição na validação:** < 20% (atual: ~30%)
- **Eventos com links válidos:** > 80%
- **Eventos com informações completas:** > 90%

---

# 🎯 Conclusão

Este roadmap fornece um caminho claro e incremental para aumentar o volume de eventos de **31 para 56+ por execução** (+81%), focando em:

1. **Fixes rápidos e críticos** (Fase 1) que resolvem problemas técnicos imediatos
2. **Otimizações de prompts** (Fase 2) que ampliam a cobertura de eventos
3. **Melhorias estruturais** (Fase 3) que garantem qualidade e sustentabilidade

**Próximo passo recomendado:** Iniciar Fase 1 com implementação de `normalize_time_format()` para ganho imediato de +6 eventos.

---

**Documento criado:** 11/11/2025
**Autor:** Claude Code
**Baseado em:** ANALISE_PROMPTS_PRODUCAO.md, RECOMENDACOES_MELHORIA_BUSCAS.md, logs de produção Railway
