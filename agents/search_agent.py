"""Agente de busca de eventos."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from pydantic import ValidationError

from config import MODELS, OPENROUTER_API_KEY, OPENROUTER_BASE_URL, SEARCH_CONFIG
from models.event_models import ResultadoBuscaCategoria

logger = logging.getLogger(__name__)


class SearchAgent:
    """Agente responsável por buscar eventos em múltiplas fontes."""

    def __init__(self):

        # Agente de busca com Perplexity Sonar Pro (busca web em tempo real)
        self.search_agent = Agent(
            name="Event Search Agent",
            model=OpenAIChat(
                id=MODELS["search"],  # perplexity/sonar-pro
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
            description="Agente com busca web em tempo real para encontrar eventos culturais no Rio de Janeiro",
            instructions=[
                f"Você tem acesso à busca web em tempo real. Use para encontrar eventos no Rio de Janeiro "
                f"entre {SEARCH_CONFIG['start_date'].strftime('%d/%m/%Y')} "
                f"e {SEARCH_CONFIG['end_date'].strftime('%d/%m/%Y')}",
                "Busque nas seguintes categorias:",
                "1. Shows de jazz no Rio (próximas 3 semanas)",
                "2. Teatro comédia/stand-up no Rio (EXCETO eventos infantis)",
                "3. Eventos na Casa do Choro, Sala Cecília Meireles e Teatro Municipal",
                "4. Eventos ao ar livre em fim de semana no Rio",
                "Para cada evento, extrair: título, data completa, horário, local, valor/preço, link para compra de ingressos",
                "Buscar em sites como: Sympla, Eventbrite, Fever, TimeOut Rio, sites oficiais dos locais",
                "Retorne no formato JSON estruturado",
            ],
            markdown=True,
        )

        # Agente otimizador de queries (usa modelo rápido para melhorar prompts)
        self.query_optimizer = Agent(
            name="Query Optimizer Agent",
            model=OpenAIChat(
                id=MODELS["verify"],  # gpt-5-mini (rápido e barato)
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
            description="Agente especializado em otimizar e refinar queries de busca",
            instructions=[
                "Você é um especialista em criar queries de busca otimizadas",
                "Analise o contexto fornecido e gere prompts de busca específicos e eficazes",
                "Use técnicas de: especificidade geográfica, temporal, e por venue",
                "Sugira palavras-chave alternativas e sinônimos relevantes",
                "Identifique gaps e áreas que precisam de busca mais direcionada",
            ],
            markdown=True,
        )

    async def _run_micro_search(self, prompt: str, search_name: str) -> str:
        """Executa uma micro-search focada de forma assíncrona."""
        logger.info(f"   🔍 Iniciando busca: {search_name}")

        def sync_search():
            try:
                response = self.search_agent.run(prompt)
                return response.content
            except Exception as e:
                logger.error(f"Erro na busca {search_name}: {e}")
                return "{}"

        result = await asyncio.to_thread(sync_search)
        logger.info(f"   ✓ Busca concluída: {search_name}")
        return result

    def _build_focused_prompt(
        self,
        categoria: str,
        tipo_busca: str,  # "categoria" ou "venue"
        descricao: str,
        tipos_evento: list[str],
        palavras_chave: list[str],
        venues_sugeridos: list[str],
        instrucoes_especiais: str = "",
        start_date_str: str = "",
        end_date_str: str = "",
        month_year_str: str = "",
        month_str: str = "",
    ) -> str:
        """Constrói prompt focado para uma única categoria ou venue (DRY)."""

        # Template comum para todos os prompts
        common_header = f"""Execute uma busca FOCADA e DETALHADA exclusivamente para: {categoria}

PERÍODO: {start_date_str} a {end_date_str}

🎯 FOCO EXCLUSIVO: {descricao}

ESTRATÉGIA DE BUSCA:
"""

        # Seção de tipos de evento
        tipos_section = "TIPOS DE EVENTO:\n"
        for tipo in tipos_evento:
            tipos_section += f"- {tipo}\n"

        # Seção de palavras-chave
        keywords_section = "\nPALAVRAS-CHAVE PARA BUSCA:\n"
        for keyword in palavras_chave:
            keywords_section += f'- "{keyword}"\n'

        # Seção de venues
        venues_section = "\nVENUES/LOCAIS PRIORITÁRIOS:\n"
        for venue in venues_sugeridos:
            venues_section += f"- {venue}\n"

        # Fontes (comum para todos)
        sources_section = """
FONTES PARA BUSCAR:
- Sympla (sympla.com.br), Eventbrite (eventbrite.com.br), Fever (fever.com.br)
- Portais culturais: TimeOut Rio, Veja Rio, O Globo Cultura
- Sites oficiais dos venues e suas redes sociais (Instagram/Facebook)
- Bilheterias online oficiais dos locais
"""

        # Campos obrigatórios (comum para todos)
        required_fields = """
INFORMAÇÕES OBRIGATÓRIAS PARA CADA EVENTO:
- Nome completo do evento
- Data exata (formato DD/MM/YYYY)
- ⚠️ Horário de início (HH:MM) - CRÍTICO: SEMPRE inclua o horário preciso
- Nome completo do local/venue + endereço
- Preço (incluir meia-entrada se disponível)
- Link para compra de ingressos (se disponível)
- Descrição detalhada: artistas, duração, público-alvo

ATENÇÃO ESPECIAL AO HORÁRIO:
- O horário é OBRIGATÓRIO (não opcional)
- Formato: "19:00", "20:30", "21:00" (HH:MM)
- Se o site não mostrar horário, busque em Instagram, Facebook, Sympla, Eventbrite
- NUNCA deixe horário em branco
"""

        # Formato de retorno (diferente para categoria vs venue)
        if tipo_busca == "categoria":
            return_format = f"""
FORMATO DE RETORNO:
{{
  "eventos": [
    {{
      "categoria": "{categoria}",
      "titulo": "Nome do evento",
      "data": "DD/MM/YYYY",
      "horario": "HH:MM",
      "local": "Nome completo + Endereço",
      "preco": "Valor completo",
      "link_ingresso": "URL específica ou null",
      "descricao": "Descrição detalhada"
    }}
  ]
}}

IMPORTANTE:
- Busque o MÁXIMO de eventos possível (objetivo: pelo menos 3 eventos)
- INCLUA TODOS os eventos que encontrar com data, horário, local e descrição

REGRAS CRÍTICAS PARA LINKS:
- Links devem ser ESPECÍFICOS do evento (não páginas de busca/categoria/listagem)
- ✅ LINKS VÁLIDOS (com ID/nome único do evento):
  * sympla.com.br/evento/nome-do-evento/123456
  * eventbrite.com.br/e/nome-do-evento-tickets-123456
  * ingresso.com/evento/nome-do-evento-123456
  * bluenote.com.br/evento/nome-do-show/
- ❌ LINKS INVÁLIDOS (genéricos - NÃO USAR):
  * ingresso.com/eventos/stand-up?city=rio-de-janeiro (página de categoria)
  * sympla.com.br/eventos/rio-de-janeiro (página de busca)
  * eventbrite.com.br/d/brazil--rio-de-janeiro/events/ (listagem)
  * Qualquer URL com query params de cidade/categoria (?city=, &partnership=)
- Se não encontrar link ESPECÍFICO, use null (busca complementar preencherá depois)
"""
        else:  # venue
            return_format = f"""
ENCODING E CARACTERES ESPECIAIS:
- Usar UTF-8 encoding para TODOS os campos
- Caracteres acentuados são PERMITIDOS e DEVEM ser escritos normalmente (ex: "Cecília", "música", "sábado")
- NÃO usar escapes unicode (ex: \\u00ed) - escrever os caracteres acentuados diretamente
- A chave do JSON DEVE ser EXATAMENTE: "{categoria}" (preservar acentuação se houver)

FORMATO DE RETORNO (use exatamente estes nomes de campos):
{{
  "{categoria}": [
    {{
      "titulo": "Nome do evento",
      "data": "DD/MM/YYYY",
      "horario": "HH:MM",
      "local": "{categoria} - Endereço completo",
      "preco": "Valor completo",
      "link_ingresso": "URL específica ou null",
      "descricao": "Descrição detalhada"
    }}
  ]
}}

IMPORTANTE - NOMES DE CAMPOS:
- Use "horario" (não "hora")
- Use "preco" (não "preço")
- Use "link_ingresso" (não "link")
- Use "descricao" (não "descrição")

REGRAS CRÍTICAS PARA JSON:
1. Comece DIRETAMENTE com {{ (sem markdown, sem textos, sem cabeçalhos antes)
2. Se usar markdown, use APENAS ```json no início e ``` no final
3. Feche COMPLETAMENTE o JSON antes de qualquer texto explicativo
4. NÃO adicione nada DEPOIS do último }}
5. Caracteres especiais devem ser escritos normalmente (ex: "à", "ã", "ç", "é", "í", "ó", "ô", "õ", "ü")

OBJETIVO:
- Busque o MÁXIMO de eventos possível (objetivo: pelo menos 1 evento)
- INCLUA TODOS os eventos que encontrar com data, horário, local e descrição

REGRAS CRÍTICAS PARA LINKS:
- Links devem ser ESPECÍFICOS do evento (não páginas de busca/categoria/listagem)
- ✅ LINKS VÁLIDOS (com ID/nome único do evento):
  * sympla.com.br/evento/nome-do-evento/123456
  * eventbrite.com.br/e/nome-do-evento-tickets-123456
  * ingresso.com/evento/nome-do-evento-123456
  * bluenote.com.br/evento/nome-do-show/
- ❌ LINKS INVÁLIDOS (genéricos - NÃO USAR):
  * ingresso.com/eventos/stand-up?city=rio-de-janeiro (página de categoria)
  * sympla.com.br/eventos/rio-de-janeiro (página de busca)
  * eventbrite.com.br/d/brazil--rio-de-janeiro/events/ (listagem)
  * Qualquer URL com query params de cidade/categoria (?city=, &partnership=)
- Se não encontrar link ESPECÍFICO, use null (busca complementar preencherá depois)
"""

        # Montar prompt completo
        return (
            common_header
            + tipos_section
            + keywords_section
            + venues_section
            + sources_section
            + instrucoes_especiais
            + required_fields
            + return_format
        )

    def optimize_search_prompt(self, base_prompt: str, search_type: str) -> str:
        """Otimiza prompt de busca usando LLM antes de passar para Perplexity."""
        logger.info(f"Otimizando prompt de busca ({search_type})...")

        optimization_prompt = f"""
Você é um especialista em otimização de queries de busca para eventos culturais.

Analise o prompt de busca abaixo e MELHORE-O para maximizar os resultados no Perplexity Sonar Pro.

PROMPT ORIGINAL:
{base_prompt}

TAREFAS DE OTIMIZAÇÃO:

1. **Adicionar palavras-chave alternativas e sinônimos**:
   - Para "jazz": incluir "música instrumental", "jazz fusion", "bossa nova instrumental"
   - Para "comédia": incluir "humor adulto", "stand-up comedy", "improv"
   - Para "ao ar livre": incluir "outdoor", "open air", "a céu aberto"

2. **Refinar especificidade geográfica**:
   - Adicionar bairros específicos além dos já mencionados
   - Incluir landmarks e referências geográficas conhecidas
   - Sugerir áreas alternativas relevantes

3. **Ampliar fontes de busca**:
   - Além das já listadas, sugerir: blogs culturais, Instagram de venues, páginas Facebook oficiais
   - Sites de turismo: Visit Rio, Rio+
   - Agendas culturais: Guia da Semana, Catraca Livre

4. **Adicionar instruções de verificação**:
   - Confirmar datas dentro do período
   - Verificar se links são específicos (não apenas homepage)
   - Priorizar eventos com informações completas

5. **Técnicas de busca avançada**:
   - Sugerir usar aspas para termos exatos
   - Operadores de busca quando apropriado
   - Datas específicas em queries

RETORNE:
Apenas o prompt OTIMIZADO, pronto para ser usado diretamente no Perplexity.
Não adicione comentários ou explicações, apenas o prompt melhorado.
"""

        try:
            response = self.query_optimizer.run(optimization_prompt)
            optimized = response.content.strip()

            logger.info(f"✓ Prompt otimizado ({len(optimized)} caracteres)")
            return optimized

        except Exception as e:
            logger.warning(f"Erro ao otimizar prompt: {e}. Usando prompt original.")
            return base_prompt

    async def search_all_sources(self) -> dict[str, Any]:
        """Busca eventos usando Perplexity Sonar Pro com 6 micro-searches focadas."""
        logger.info("Iniciando busca de eventos com Perplexity Sonar Pro...")

        # Gerar strings de data dinâmicas
        start_date_str = SEARCH_CONFIG['start_date'].strftime('%d/%m/%Y')
        end_date_str = SEARCH_CONFIG['end_date'].strftime('%d/%m/%Y')
        month_year_str = SEARCH_CONFIG['start_date'].strftime('%B %Y')  # ex: "novembro 2025"
        month_str = SEARCH_CONFIG['start_date'].strftime('%B').lower()  # ex: "novembro"

        # ═══════════════════════════════════════════════════════════
        # ESTRATÉGIA: 6 MICRO-SEARCHES FOCADAS (DRY + Paralelas)
        # ═══════════════════════════════════════════════════════════
        logger.info("🎯 Criando 6 prompts micro-focados...")

        # MICRO-SEARCH 1: Jazz
        prompt_jazz = self._build_focused_prompt(
            categoria="Jazz",
            tipo_busca="categoria",
            descricao="Shows de jazz no Rio de Janeiro (jazz tradicional, bebop, fusion, bossa nova)",
            tipos_evento=[
                "Shows de jazz ao vivo",
                "Jazz tradicional, bebop, fusion",
                "Bossa nova, jazz contemporâneo",
                "Jazz em bares, casas de jazz especializadas"
            ],
            palavras_chave=[
                f"jazz Rio Janeiro {month_year_str}",
                f"shows jazz {month_str}",
                "jazz ao vivo Rio de Janeiro",
                "Blue Note Rio",
                "Maze Jazz Club"
            ],
            venues_sugeridos=[
                "Blue Note Rio",
                "Maze Jazz Club",
                "Clube do Jazz",
                "Jazz nos Fundos",
                "Bares e hotéis com jazz ao vivo"
            ],
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 2: Teatro-Comédia
        prompt_comedia = self._build_focused_prompt(
            categoria="Teatro-Comédia",
            tipo_busca="categoria",
            descricao="Teatro de comédia e stand-up ADULTO no Rio de Janeiro (EXCLUIR eventos infantis)",
            tipos_evento=[
                "Peças teatrais de comédia (adulto)",
                "Stand-up comedy",
                "Humor adulto, espetáculos cômicos",
                "Improv, teatro de improvisação"
            ],
            palavras_chave=[
                f"stand-up Rio {month_str}",
                "teatro comédia adulto Rio de Janeiro",
                "humor adulto Rio",
                "espetáculo cômico Rio"
            ],
            venues_sugeridos=[
                "Estação Net Rio",
                "Teatro Riachuelo",
                "Teatro Clara Nunes",
                "Teatros de comédia especializados"
            ],
            instrucoes_especiais="""
ATENÇÃO - EXCLUSÕES CRÍTICAS:
- NÃO incluir: eventos infantis, teatro para crianças
- NÃO incluir eventos com tags: "kids", "família", "infantil"
- APENAS comédia para público adulto
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 3: Outdoor-FimDeSemana
        prompt_outdoor = self._build_focused_prompt(
            categoria="Outdoor-FimDeSemana",
            tipo_busca="categoria",
            descricao="Eventos ao ar livre APENAS em sábados e domingos no Rio de Janeiro",
            tipos_evento=[
                "Festivais ao ar livre (sábado/domingo)",
                "Shows outdoor em fim de semana",
                "Feiras culturais (sábado/domingo)",
                "Eventos em parques (fim de semana)"
            ],
            palavras_chave=[
                f"festival Rio fim de semana {month_str}",
                "evento ao ar livre sábado domingo Rio",
                "show outdoor Rio fim de semana",
                "parque Rio evento sábado"
            ],
            venues_sugeridos=[
                "Aterro do Flamengo",
                "Jockey Club Brasileiro",
                "Marina da Glória",
                "Parque Lage",
                "Pista Cláudio Coutinho"
            ],
            instrucoes_especiais="""
ATENÇÃO - DIAS ESPECÍFICOS:
- APENAS sábados e domingos
- NÃO incluir eventos de segunda a sexta
- Verificar dia da semana da data do evento
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 4: Casa do Choro
        prompt_casa_choro = self._build_focused_prompt(
            categoria="Casa do Choro",
            tipo_busca="venue",
            descricao="Eventos na Casa do Choro (Rua da Carioca, 38 - Centro, Rio de Janeiro)",
            tipos_evento=[
                "Shows de choro e música brasileira",
                "Apresentações ao vivo",
                "Eventos culturais no venue"
            ],
            palavras_chave=[
                f"Casa do Choro {month_year_str}",
                "Casa do Choro agenda",
                "eventos Casa do Choro Rio",
                "shows Casa do Choro"
            ],
            venues_sugeridos=[
                "Casa do Choro - Rua da Carioca, 38, Centro"
            ],
            instrucoes_especiais="""
ESTRATÉGIA DE BUSCA MULTI-STEP:
1. Site oficial: casadochoro.com.br
2. Instagram: @casadochororj
3. Facebook: Casa do Choro oficial
4. Sympla/Eventbrite: "Casa do Choro"
5. Portais culturais: agenda Casa do Choro
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 5: Sala Cecília Meireles
        prompt_sala_cecilia = self._build_focused_prompt(
            categoria="Sala Cecília Meireles",
            tipo_busca="venue",
            descricao="Eventos na Sala Cecília Meireles (Lapa, Rio de Janeiro - música clássica e erudita)",
            tipos_evento=[
                "Concertos de música clássica",
                "Música erudita, orquestras",
                "Recitais e apresentações",
                "Eventos de música de câmara"
            ],
            palavras_chave=[
                f"Sala Cecília Meireles {month_year_str}",
                "Sala Cecília Meireles agenda",
                "concerto Sala Cecília Meireles",
                "música clássica Sala Cecília"
            ],
            venues_sugeridos=[
                "Sala Cecília Meireles - Lapa"
            ],
            instrucoes_especiais="""
ESTRATÉGIA DE BUSCA MULTI-STEP:
1. Site oficial do venue
2. Sympla/Eventbrite: "Sala Cecília Meireles"
3. TimeOut Rio, Veja Rio: programação sala Cecília
4. Site da Prefeitura: agenda cultural Lapa
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 6: Teatro Municipal
        prompt_teatro_municipal = self._build_focused_prompt(
            categoria="Teatro Municipal do Rio de Janeiro",
            tipo_busca="venue",
            descricao="Eventos no Teatro Municipal do Rio de Janeiro (Centro - óperas, balés, concertos)",
            tipos_evento=[
                "Óperas e apresentações líricas",
                "Balés clássicos e contemporâneos",
                "Concertos da Orquestra Sinfônica",
                "Eventos culturais especiais"
            ],
            palavras_chave=[
                f"Teatro Municipal Rio {month_year_str}",
                "Teatro Municipal agenda",
                "ópera Teatro Municipal",
                "balé Teatro Municipal Rio"
            ],
            venues_sugeridos=[
                "Teatro Municipal do Rio de Janeiro - Centro"
            ],
            instrucoes_especiais="""
ESTRATÉGIA DE BUSCA MULTI-STEP:
1. Site oficial: theatromunicipal.rj.gov.br
2. Sympla/Eventbrite: "Teatro Municipal Rio"
3. Portais culturais: programação Teatro Municipal
4. Redes sociais oficiais do Teatro
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        # MICRO-SEARCH 7: Artemis - Torrefação Artesanal e Cafeteria
        prompt_artemis = self._build_focused_prompt(
            categoria="Artemis - Torrefação Artesanal e Cafeteria",
            tipo_busca="venue",
            descricao="Cursos, workshops e eventos sobre café na Artemis (cursos de barista, degustações, talks sobre café)",
            tipos_evento=[
                "Cursos de barista e métodos de preparo",
                "Workshops de degustação e cupping",
                "Talks e palestras sobre café especial",
                "Eventos de lançamento de cafés",
                "Cursos de torra artesanal"
            ],
            palavras_chave=[
                f"Artemis café {month_year_str}",
                "Artemis curso barista Rio",
                "workshop café Artemis",
                "degustação café Artemis",
                "cupping Artemis Rio",
                "curso café especial Rio"
            ],
            venues_sugeridos=[
                "Artemis Torrefação Artesanal e Cafeteria"
            ],
            instrucoes_especiais="""
ESTRATÉGIA DE BUSCA MULTI-STEP:
1. Site oficial e redes sociais do Artemis (@artemiscafe, Instagram/Facebook)
2. Sympla/Eventbrite: "Artemis café", "curso barista"
3. Portais de gastronomia: cursos de café Rio
4. Busca por: "workshop café especialidade Rio"
""",
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            month_year_str=month_year_str,
            month_str=month_str
        )

        logger.info("✓ 7 prompts criados com sucesso")

        try:
            # ═══════════════════════════════════════════════════════════
            # OTIMIZAÇÃO PARALELA DOS 7 PROMPTS
            # ═══════════════════════════════════════════════════════════
            logger.info("🧠 Otimizando 7 prompts em paralelo com LLM especialista...")

            # Otimizar todos os prompts em paralelo
            prompts_otimizados = await asyncio.gather(
                asyncio.to_thread(self.optimize_search_prompt, prompt_jazz, "categoria"),
                asyncio.to_thread(self.optimize_search_prompt, prompt_comedia, "categoria"),
                asyncio.to_thread(self.optimize_search_prompt, prompt_outdoor, "categoria"),
                asyncio.to_thread(self.optimize_search_prompt, prompt_casa_choro, "venue"),
                asyncio.to_thread(self.optimize_search_prompt, prompt_sala_cecilia, "venue"),
                asyncio.to_thread(self.optimize_search_prompt, prompt_teatro_municipal, "venue"),
                asyncio.to_thread(self.optimize_search_prompt, prompt_artemis, "venue"),
            )

            # Desempacotar prompts otimizados
            (
                prompt_jazz_opt,
                prompt_comedia_opt,
                prompt_outdoor_opt,
                prompt_casa_choro_opt,
                prompt_sala_cecilia_opt,
                prompt_teatro_municipal_opt,
                prompt_artemis_opt,
            ) = prompts_otimizados

            logger.info("✓ Todos os 7 prompts otimizados")

            # ═══════════════════════════════════════════════════════════
            # EXECUÇÃO PARALELA DAS 7 MICRO-SEARCHES COM PROMPTS OTIMIZADOS
            # ═══════════════════════════════════════════════════════════
            logger.info("🚀 Executando 7 micro-searches em paralelo...")

            # Executar as 7 buscas em paralelo com prompts otimizados
            results = await asyncio.gather(
                self._run_micro_search(prompt_jazz_opt, "Jazz"),
                self._run_micro_search(prompt_comedia_opt, "Teatro-Comédia"),
                self._run_micro_search(prompt_outdoor_opt, "Outdoor-FimDeSemana"),
                self._run_micro_search(prompt_casa_choro_opt, "Casa do Choro"),
                self._run_micro_search(prompt_sala_cecilia_opt, "Sala Cecília Meireles"),
                self._run_micro_search(prompt_teatro_municipal_opt, "Teatro Municipal"),
                self._run_micro_search(prompt_artemis_opt, "Artemis"),
            )

            # Desempacotar resultados
            (
                result_jazz,
                result_comedia,
                result_outdoor,
                result_casa_choro,
                result_sala_cecilia,
                result_teatro_municipal,
                result_artemis,
            ) = results

            logger.info("✓ Todas as 7 micro-searches concluídas")

            # ═══════════════════════════════════════════════════════════
            # MERGE INTELIGENTE DOS RESULTADOS COM PYDANTIC
            # ═══════════════════════════════════════════════════════════
            logger.info("🔗 Fazendo merge dos resultados...")

            # Helper function: Clean markdown from JSON
            def clean_json_from_markdown(text: str) -> str:
                """Remove markdown code blocks and extra text from JSON responses.

                Handles cases like:
                - # Eventos na Sala Cecília Meireles\n\nCom base na busca...\n\n```json\n{...}\n```
                - Plain JSON with preamble text
                - Multiple markdown blocks (uses last one)
                """
                if not text or text.strip() == "":
                    return ""

                import re

                # Remove leading/trailing whitespace
                text = text.strip()

                # STEP 1: Try to find JSON within markdown code blocks
                # Pattern: ```json ... ``` or ``` ... ```
                code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
                matches = re.findall(code_block_pattern, text)
                if matches:
                    # Use the last match (usually the complete JSON)
                    text = matches[-1].strip()

                # STEP 2: Remove ANYTHING before the first { or [
                # This handles preamble text like headers, explanations, etc.
                json_start_brace = text.find('{')
                json_start_bracket = text.find('[')

                # Find the earliest valid JSON start
                valid_starts = [pos for pos in [json_start_brace, json_start_bracket] if pos != -1]
                if valid_starts:
                    json_start = min(valid_starts)
                    text = text[json_start:]

                # STEP 3: Remove ANYTHING after the last } or ]
                # Find matching closing bracket
                if text.startswith('{'):
                    # Find the last } that matches the structure
                    depth = 0
                    for i, char in enumerate(text):
                        if char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                text = text[:i+1]
                                break
                elif text.startswith('['):
                    # Find the last ] that matches the structure
                    depth = 0
                    for i, char in enumerate(text):
                        if char == '[':
                            depth += 1
                        elif char == ']':
                            depth -= 1
                            if depth == 0:
                                text = text[:i+1]
                                break

                return text.strip()

            # Helper function: Parse categoria com Pydantic
            def safe_parse_categoria(result_str: str, search_name: str) -> list[dict]:
                """Parse categoria usando Pydantic validation."""
                try:
                    if not result_str or result_str.strip() == "":
                        logger.warning(f"⚠️  Busca {search_name} retornou vazio")
                        return []
                    # Limpar markdown antes de parsear
                    clean_json = clean_json_from_markdown(result_str)
                    if not clean_json:
                        logger.warning(f"⚠️  Busca {search_name} retornou JSON vazio após limpeza")
                        return []
                    # Use Pydantic para validar e parsear
                    resultado = ResultadoBuscaCategoria.model_validate_json(clean_json)
                    logger.info(f"✓ Busca {search_name}: {len(resultado.eventos)} eventos validados")
                    # Converter Pydantic models para dicts
                    return [evento.model_dump() for evento in resultado.eventos]
                except ValidationError as e:
                    logger.error(f"❌ Schema inválido na busca {search_name}:")
                    for error in e.errors():
                        logger.error(f"   • {error['loc']}: {error['msg']}")
                    logger.error(f"   Conteúdo (primeiros 200 chars): {result_str[:200]}")
                    return []
                except Exception as e:
                    logger.error(f"❌ Erro inesperado na busca {search_name}: {e}")
                    return []

            # Helper function: Parse venue (formato diferente, mantém dict)
            def safe_parse_venue(result_str: str, venue_name: str) -> list[dict]:
                """Parse venue usando JSON simples (formato: {venue_name: [eventos]}).

                Inclui fallback com normalização unicode para lidar com acentuação.
                """
                try:
                    import unicodedata

                    if not result_str or result_str.strip() == "":
                        logger.warning(f"⚠️  Busca {venue_name} retornou vazio")
                        return []
                    # Limpar markdown antes de parsear
                    clean_json = clean_json_from_markdown(result_str)
                    if not clean_json:
                        logger.warning(f"⚠️  Busca {venue_name} retornou JSON vazio após limpeza")
                        return []
                    data = json.loads(clean_json)

                    # STEP 1: Tentar match exato primeiro
                    eventos = data.get(venue_name, [])

                    # STEP 2: Se não encontrou, tentar com normalização unicode (fallback)
                    if not eventos and venue_name:
                        # Normalizar nome do venue esperado (NFD = decompor acentos)
                        normalized_expected = unicodedata.normalize('NFD', venue_name)

                        # Tentar encontrar chave com normalização
                        for key in data.keys():
                            normalized_key = unicodedata.normalize('NFD', key)
                            if normalized_key == normalized_expected:
                                eventos = data.get(key, [])
                                logger.info(
                                    f"⚙️  Fallback unicode: '{key}' → '{venue_name}' "
                                    f"({len(eventos)} eventos)"
                                )
                                break

                    if eventos:
                        logger.info(f"✓ Busca {venue_name}: {len(eventos)} eventos encontrados")
                    else:
                        logger.warning(f"⚠️  Nenhum evento encontrado para {venue_name} (chaves disponíveis: {list(data.keys())})")

                    return eventos
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON inválido na busca {venue_name}: {e}")
                    logger.error(f"   Conteúdo (primeiros 200 chars): {result_str[:200]}")
                    return []

            # Parse categorias com Pydantic validation
            logger.info("🔍 DEBUG: Iniciando parse de categorias...")
            eventos_jazz = safe_parse_categoria(result_jazz, "Jazz")
            logger.info(f"🔍 DEBUG: Jazz parsed - {len(eventos_jazz)} eventos")

            eventos_comedia = safe_parse_categoria(result_comedia, "Teatro-Comédia")
            logger.info(f"🔍 DEBUG: Teatro-Comédia parsed - {len(eventos_comedia)} eventos")

            eventos_outdoor = safe_parse_categoria(result_outdoor, "Outdoor-FimDeSemana")
            logger.info(f"🔍 DEBUG: Outdoor parsed - {len(eventos_outdoor)} eventos")

            # Merge eventos gerais (categorias)
            logger.info("🔍 DEBUG: Fazendo merge de eventos gerais...")
            todos_eventos_gerais = eventos_jazz + eventos_comedia + eventos_outdoor
            logger.info(f"🔍 DEBUG: Merge gerais OK - {len(todos_eventos_gerais)} eventos total")

            # Criar estrutura de eventos gerais
            eventos_gerais_merged = {"eventos": todos_eventos_gerais}
            logger.info(f"🔍 DEBUG: Estrutura eventos_gerais_merged criada - type: {type(eventos_gerais_merged)}")

            # Parse eventos de venues
            logger.info("🔍 DEBUG: Iniciando parse de venues...")
            eventos_casa_choro = safe_parse_venue(result_casa_choro, "Casa do Choro")
            logger.info(f"🔍 DEBUG: Casa do Choro parsed - {len(eventos_casa_choro)} eventos")

            eventos_sala_cecilia = safe_parse_venue(result_sala_cecilia, "Sala Cecília Meireles")
            logger.info(f"🔍 DEBUG: Sala Cecília Meireles parsed - {len(eventos_sala_cecilia)} eventos")

            eventos_teatro_municipal = safe_parse_venue(result_teatro_municipal, "Teatro Municipal do Rio de Janeiro")
            logger.info(f"🔍 DEBUG: Teatro Municipal parsed - {len(eventos_teatro_municipal)} eventos")

            eventos_artemis = safe_parse_venue(result_artemis, "Artemis - Torrefação Artesanal e Cafeteria")
            logger.info(f"🔍 DEBUG: Artemis parsed - {len(eventos_artemis)} eventos")

            # Criar estrutura de eventos de venues
            logger.info("🔍 DEBUG: Criando estrutura eventos_locais_merged...")
            eventos_locais_merged = {
                "Casa do Choro": eventos_casa_choro,
                "Sala Cecília Meireles": eventos_sala_cecilia,
                "Teatro Municipal do Rio de Janeiro": eventos_teatro_municipal,
                "Artemis - Torrefação Artesanal e Cafeteria": eventos_artemis,
            }
            logger.info(f"🔍 DEBUG: Estrutura eventos_locais_merged criada - type: {type(eventos_locais_merged)}")

            total_venues = len(eventos_casa_choro) + len(eventos_sala_cecilia) + len(eventos_teatro_municipal) + len(eventos_artemis)
            logger.info(
                f"✓ Merge concluído: {len(todos_eventos_gerais)} eventos gerais, "
                f"{total_venues} eventos de venues"
            )

            # Retornar no formato compatível com o resto do sistema
            logger.info("🔍 DEBUG: Serializando para JSON...")
            try:
                json_geral = json.dumps(eventos_gerais_merged, ensure_ascii=False)
                logger.info(f"🔍 DEBUG: JSON geral OK - {len(json_geral)} bytes")

                json_especial = json.dumps(eventos_locais_merged, ensure_ascii=False)
                logger.info(f"🔍 DEBUG: JSON especial OK - {len(json_especial)} bytes")

                result = {
                    "perplexity_geral": json_geral,
                    "perplexity_especial": json_especial,
                    "search_timestamp": datetime.now().isoformat(),
                }
                logger.info("🔍 DEBUG: Return dict criado com sucesso")
                return result
            except Exception as json_error:
                logger.error(f"❌ Erro na serialização JSON: {json_error}")
                import traceback
                traceback.print_exc()
                raise

        except Exception as e:
            logger.error(f"❌ ERRO CRÍTICO nas micro-searches: {type(e).__name__}: {e}")
            logger.error("📍 Local do erro:")
            import traceback
            import sys
            exc_type, exc_value, exc_traceback = sys.exc_info()

            # Logar o traceback completo
            logger.error("=== TRACEBACK COMPLETO ===")
            traceback.print_exc()
            logger.error("=========================")

            # Logar informações sobre onde o erro ocorreu
            if exc_traceback:
                frame = exc_traceback.tb_frame
                lineno = exc_traceback.tb_lineno
                filename = frame.f_code.co_filename
                logger.error(f"Arquivo: {filename}, Linha: {lineno}")
                logger.error(f"Função: {frame.f_code.co_name}")

            # Retornar JSONs vazios como fallback (para não quebrar o pipeline)
            logger.warning("⚠️  Retornando JSONs vazios como fallback")
            return {
                "perplexity_geral": "{}",
                "perplexity_especial": "{}",
                "search_timestamp": datetime.now().isoformat(),
            }

    def _find_event_ticket_link_batch(self, events_batch: list[dict]) -> dict[str, str]:
        """Busca links de múltiplos eventos em uma única chamada (batch)."""
        if not events_batch:
            return {}

        # Construir prompt com lista de eventos
        eventos_texto = []
        for i, event in enumerate(events_batch, 1):
            titulo = event.get("titulo", "")
            data = event.get("data", "")
            local = event.get("local", "")
            eventos_texto.append(f"{i}. {titulo} - {data} - {local}")

        prompt = f"""Encontre os links de compra/informações para estes {len(events_batch)} eventos no Rio de Janeiro:

{chr(10).join(eventos_texto)}

Para CADA evento, busque o link específico em:
- Sympla (sympla.com.br)
- Eventbrite (eventbrite.com.br)
- Site oficial do venue (Blue Note, Dolores Club, Casa do Choro, etc)
- Instagram oficial (se tiver link de venda)

Retorne no formato JSON:
{{
  "1": "URL completo ou null",
  "2": "URL completo ou null",
  ...
}}

IMPORTANTE:
- Use null (sem aspas) se não encontrar link confiável
- NÃO retorne links genéricos de homepage
- Links devem começar com http:// ou https://
"""

        try:
            response = self.search_agent.run(prompt)
            content = response.content.strip()

            # Limpar markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # Parse JSON
            links_map = json.loads(content)

            # Converter chaves para int se necessário
            result = {}
            for key, value in links_map.items():
                result[str(key)] = value if value and value != "null" else None

            return result

        except Exception as e:
            logger.error(f"Erro na busca batch de links: {e}")
            return {}

    def _search_missing_links(self, events: list[dict]) -> list[dict]:
        """Busca links para eventos que não têm link, processando em batches."""
        # Identificar eventos sem link
        events_without_links = []
        events_indices = []

        for i, event in enumerate(events):
            if not event.get("link_ingresso"):
                events_without_links.append(event)
                events_indices.append(i)

        if not events_without_links:
            logger.info("Todos os eventos já possuem links")
            return events

        logger.info(f"🔗 Buscando links para {len(events_without_links)} eventos sem link...")

        # Processar em batches de 5
        batch_size = 5
        total_found = 0

        for batch_start in range(0, len(events_without_links), batch_size):
            batch_end = min(batch_start + batch_size, len(events_without_links))
            batch = events_without_links[batch_start:batch_end]

            logger.info(f"   Processando batch {batch_start//batch_size + 1} ({len(batch)} eventos)...")

            # Buscar links para este batch
            links_map = self._find_event_ticket_link_batch(batch)

            # Atribuir links encontrados
            for local_idx, event in enumerate(batch):
                batch_key = str(local_idx + 1)
                if batch_key in links_map and links_map[batch_key]:
                    event["link_ingresso"] = links_map[batch_key]
                    event["link_source"] = "busca_complementar_batch"
                    total_found += 1
                    logger.info(f"   ✓ Link encontrado para: {event.get('titulo')}")

        logger.info(f"✓ Busca complementar concluída: {total_found}/{len(events_without_links)} links encontrados")
        return events

    def process_with_llm(self, raw_events: dict[str, Any]) -> str:
        """Combina e limpa resultados das duas buscas Perplexity."""
        logger.info("Combinando dados das 2 buscas Perplexity...")

        # Extrair dados das duas buscas
        data_geral = raw_events.get("perplexity_geral", "{}")
        data_especial = raw_events.get("perplexity_especial", "{}")

        # Limpar markdown code blocks e comentários
        def clean_json(data):
            # Remover markdown code blocks
            if "```json" in data:
                data = data.split("```json")[1].split("```")[0].strip()
            elif "```" in data:
                data = data.split("```")[1].split("```")[0].strip()

            # Remover comentários JavaScript (// comentários) linha por linha
            lines = data.split("\n")
            cleaned_lines = []
            for line in lines:
                # Se a linha contém //, remover tudo a partir daí (exceto se estiver dentro de string)
                if "//" in line:
                    # Verificar se está dentro de string
                    in_string = False
                    quote_char = None
                    result = []
                    i = 0
                    while i < len(line):
                        char = line[i]
                        if char in ['"', "'"]:
                            if not in_string:
                                in_string = True
                                quote_char = char
                            elif char == quote_char and (i == 0 or line[i - 1] != "\\"):
                                in_string = False
                                quote_char = None
                            result.append(char)
                        elif char == "/" and i + 1 < len(line) and line[i + 1] == "/" and not in_string:
                            # Comentário encontrado fora de string, parar aqui
                            break
                        else:
                            result.append(char)
                        i += 1
                    line = "".join(result).rstrip()
                cleaned_lines.append(line)

            # Remover linhas vazias
            cleaned_lines = [line for line in cleaned_lines if line.strip()]

            return "\n".join(cleaned_lines)

        data_geral_clean = clean_json(data_geral)
        data_especial_clean = clean_json(data_especial)

        # Combinar em um único JSON
        combined = f'{{"eventos_gerais": {data_geral_clean}, "eventos_locais_especiais": {data_especial_clean}}}'

        logger.info("Dados combinados das 2 buscas")

        # Parsear para aplicar busca complementar de links
        try:
            combined_data = json.loads(combined)

            # Extrair todos os eventos para busca complementar
            all_events = []

            # Eventos gerais
            if "eventos_gerais" in combined_data and "eventos" in combined_data["eventos_gerais"]:
                all_events.extend(combined_data["eventos_gerais"]["eventos"])

            # Eventos de locais especiais
            if "eventos_locais_especiais" in combined_data:
                for local_name, local_events in combined_data["eventos_locais_especiais"].items():
                    if isinstance(local_events, list):
                        all_events.extend([e for e in local_events if isinstance(e, dict)])

            # Aplicar busca complementar de links
            if all_events:
                self._search_missing_links(all_events)

            # Retornar JSON atualizado
            return json.dumps(combined_data, ensure_ascii=False, indent=2)

        except json.JSONDecodeError as e:
            logger.error(f"Erro ao parsear JSON combinado: {e}")
            return combined
