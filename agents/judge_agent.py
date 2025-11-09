"""Agente de julgamento de qualidade de eventos usando GPT-5."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from config import JUDGE_BATCH_SIZE, JUDGE_MAX_LINK_CHARS, JUDGE_TIMEOUT
from utils.agent_factory import AgentFactory
from utils.http_client import HttpClientWrapper
from utils.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)

# Prefixo para logs deste agente
LOG_PREFIX = "[QualityJudgeAgent] ⚖️"


class QualityJudgeAgent:
    """Agente especializado em avaliar qualidade de eventos extraídos.

    Avalia eventos usando GPT-5 com base em:
    1. Aderência ao prompt original (search_prompts.yaml)
    2. Correlação entre link do evento e dados extraídos
    3. Qualidade geral das informações (completude, corretude)
    """

    def __init__(self):
        self.log_prefix = LOG_PREFIX
        self.http_client = HttpClientWrapper()
        self.prompt_loader = PromptLoader()

        # Criar agent com GPT-5
        self.agent = AgentFactory.create_agent(
            name="Quality Judge Agent",
            model_type="judge",  # GPT-5 com high effort
            description="Agente especializado em avaliar qualidade de eventos culturais",
            instructions=[
                "Avaliar eventos de forma rigorosa mas justa",
                "Verificar aderência ao prompt de busca original",
                "Correlacionar dados extraídos com conteúdo do link",
                "Considerar completude e corretude das informações",
                "Retornar avaliação estruturada em JSON",
            ],
            markdown=True,
        )

    def _get_original_prompt(self, event: dict) -> str:
        """Recupera o prompt original usado na busca do evento.

        Args:
            event: Dicionário do evento (deve ter 'categoria' ou 'venue')

        Returns:
            Texto do prompt original ou mensagem de erro
        """
        try:
            # Tentar carregar por categoria
            categoria = event.get("categoria")
            if categoria:
                categoria_key = categoria.lower().replace(" ", "_").replace("/", "_")
                try:
                    prompt_data = self.prompt_loader.get_categoria(categoria_key)
                    if prompt_data:
                        return self._format_prompt_text(prompt_data)
                except KeyError:
                    logger.debug(f"{self.log_prefix} Categoria não encontrada: {categoria_key}")

            # Tentar carregar por venue
            venue = event.get("venue") or event.get("local", "")
            if venue:
                # Simplificar nome do venue para buscar no YAML
                venue_key = self._normalize_venue_name(venue)
                try:
                    prompt_data = self.prompt_loader.get_venue(venue_key)
                    if prompt_data:
                        return self._format_prompt_text(prompt_data)
                except KeyError:
                    logger.debug(f"{self.log_prefix} Venue não encontrado: {venue_key}")

            return "Prompt original não encontrado (sem categoria ou venue identificável)"

        except Exception as e:
            logger.warning(f"{self.log_prefix} Erro ao recuperar prompt: {e}")
            return f"Erro ao recuperar prompt: {e}"

    def _normalize_venue_name(self, venue: str) -> str:
        """Normaliza nome do venue para buscar no YAML.

        Args:
            venue: Nome do venue (pode incluir endereço)

        Returns:
            Chave normalizada (ex: "sala_cecilia", "ccbb")
        """
        venue_lower = venue.lower()

        # Mapeamento de nomes para chaves do YAML
        mappings = {
            "sala cecília meireles": "sala_cecilia",
            "sala cecilia meireles": "sala_cecilia",
            "teatro municipal": "teatro_municipal",
            "theatro municipal": "teatro_municipal",
            "ccbb": "ccbb",
            "centro cultural banco do brasil": "ccbb",
            "blue note": "blue_note",
            "casa do choro": "casa_choro",
            "artemis": "artemis",
            "oi futuro": "oi_futuro",
            "ims": "ims",
            "instituto moreira salles": "ims",
            "parque lage": "parque_lage",
            "ccjf": "ccjf",
            "mam cinema": "mam_cinema",
            "theatro net": "theatro_net",
            "maze jazz": "maze_jazz",
            "teatro leblon": "teatro_leblon",
            "teatro do leblon": "teatro_leblon",
            "clube do jazz": "clube_jazz_rival",
            "teatro rival": "clube_jazz_rival",
            "estação net": "estacao_net",
            "estacao net": "estacao_net",
            "istituto italiano": "istituto_italiano",
        }

        for key, value in mappings.items():
            if key in venue_lower:
                return value

        # Fallback: remover caracteres especiais e espaços
        return venue_lower.replace(" ", "_").replace("-", "_")

    def _format_prompt_text(self, prompt_data: dict) -> str:
        """Formata dados do prompt em texto legível.

        Args:
            prompt_data: Dicionário do prompt do YAML

        Returns:
            Texto formatado do prompt
        """
        parts = []

        # Cabeçalho
        if prompt_data.get("nome"):
            parts.append(f"CATEGORIA/VENUE: {prompt_data['nome']}")
        if prompt_data.get("descricao"):
            parts.append(f"DESCRIÇÃO: {prompt_data['descricao']}")

        # Tipos de evento
        if prompt_data.get("tipos_evento"):
            parts.append("\nTIPOS DE EVENTO ESPERADOS:")
            for tipo in prompt_data["tipos_evento"]:
                parts.append(f"  - {tipo}")

        # Palavras-chave
        if prompt_data.get("palavras_chave"):
            parts.append("\nPALAVRAS-CHAVE DE BUSCA:")
            for kw in prompt_data["palavras_chave"][:5]:  # Primeiras 5
                parts.append(f"  - {kw}")

        # Instruções especiais
        if prompt_data.get("instrucoes_especiais"):
            parts.append("\nINSTRUÇÕES ESPECIAIS:")
            parts.append(prompt_data["instrucoes_especiais"][:500])  # Primeiros 500 chars

        return "\n".join(parts)

    async def _fetch_link_content(self, url: str) -> str:
        """Acessa o link do evento e retorna conteúdo HTML simplificado.

        Args:
            url: URL do link do evento

        Returns:
            Texto extraído do HTML (primeiros JUDGE_MAX_LINK_CHARS caracteres)
        """
        if not url:
            return "[Sem link disponível]"

        try:
            logger.debug(f"{self.log_prefix} Acessando link: {url}")

            response = await self.http_client.get(url, timeout=10)

            if response.status_code != 200:
                return f"[Link inacessível - HTTP {response.status_code}]"

            # Parsear HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # Remover scripts e styles
            for element in soup(["script", "style", "nav", "footer"]):
                element.decompose()

            # Extrair texto
            text = soup.get_text(separator="\n", strip=True)

            # Limitar tamanho
            if len(text) > JUDGE_MAX_LINK_CHARS:
                text = text[:JUDGE_MAX_LINK_CHARS] + "..."

            logger.debug(f"{self.log_prefix} ✓ Link acessado ({len(text)} chars)")
            return text

        except Exception as e:
            logger.warning(f"{self.log_prefix} Erro ao acessar link {url}: {e}")
            return f"[Erro ao acessar link: {e}]"

    async def _fetch_links_batch(self, urls: list[str]) -> list[str]:
        """Acessa múltiplos links em paralelo e retorna seus conteúdos.

        Args:
            urls: Lista de URLs para acessar

        Returns:
            Lista de conteúdos (textos extraídos dos HTMLs)
        """
        logger.debug(f"{self.log_prefix} Acessando {len(urls)} links em paralelo...")

        # Executar fetches em paralelo
        tasks = [self._fetch_link_content(url) for url in urls]
        contents = await asyncio.gather(*tasks)

        logger.debug(f"{self.log_prefix} ✓ {len(contents)} links acessados")
        return contents

    def _build_judge_prompt(self, event: dict, prompt_original: str, link_content: str) -> str:
        """Constrói o prompt para o GPT-5 julgar o evento.

        Args:
            event: Dicionário do evento
            prompt_original: Texto do prompt original da busca
            link_content: Conteúdo extraído do link do evento

        Returns:
            Prompt formatado para o GPT-5
        """
        # Serializar evento para JSON legível
        event_json = json.dumps(event, ensure_ascii=False, indent=2)

        prompt = f"""Você é um avaliador de qualidade de dados de eventos culturais.

Sua tarefa é avaliar a qualidade de um evento extraído automaticamente, verificando:
1. Se o evento corresponde ao que foi solicitado no prompt original (aderência)
2. Se os dados extraídos (título, data, local, preço) condizem com o conteúdo do link (correlação)
3. Se as informações estão completas e corretas (qualidade geral)

═══════════════════════════════════════════════════════════════
PROMPT ORIGINAL DA BUSCA:
═══════════════════════════════════════════════════════════════

{prompt_original}

═══════════════════════════════════════════════════════════════
DADOS EXTRAÍDOS DO EVENTO:
═══════════════════════════════════════════════════════════════

{event_json}

═══════════════════════════════════════════════════════════════
CONTEÚDO DO LINK (primeiros {JUDGE_MAX_LINK_CHARS} caracteres):
═══════════════════════════════════════════════════════════════

{link_content}

═══════════════════════════════════════════════════════════════
CRITÉRIOS DE AVALIAÇÃO (nota 0-10 para cada):
═══════════════════════════════════════════════════════════════

1. **ADERÊNCIA AO PROMPT (peso 40%)**
   - O evento corresponde ao tipo solicitado no prompt?
   - Está dentro da categoria/venue esperado?
   - Palavras-chave batem com o prompt?

2. **CORRELAÇÃO LINK-DADOS (peso 40%)**
   - Título do evento bate com o conteúdo do link?
   - Data e horário estão corretos conforme o link?
   - Local/venue conferem?
   - Preço está correto (se disponível no link)?

3. **QUALIDADE GERAL (peso 20%)**
   - Campos obrigatórios estão preenchidos?
   - Informações são completas e claras?
   - Não há inconsistências óbvias?

═══════════════════════════════════════════════════════════════
RETORNE JSON NO FORMATO EXATO:
═══════════════════════════════════════════════════════════════

{{
  "prompt_adherence": 8.5,
  "link_match": 9.0,
  "completeness": 7.5,
  "quality_score": 8.3,
  "notes": "Evento condiz com busca de jazz. Link válido e dados corretos, mas preço genérico ('Consultar'). Descrição ausente."
}}

**IMPORTANTE:**
- `prompt_adherence`: nota de aderência ao prompt (0-10)
- `link_match`: nota de correlação link-dados (0-10). Se link inacessível, use 5.0
- `completeness`: nota de completude (0-10)
- `quality_score`: nota final ponderada automaticamente:
  quality_score = (prompt_adherence * 0.4) + (link_match * 0.4) + (completeness * 0.2)
- `notes`: observações em até 200 caracteres

Seja rigoroso mas justo. Eventos legítimos com pequenas falhas devem ter notas boas (7-8).
Eventos perfeitos: 9-10. Eventos muito ruins: 0-4.
"""

        return prompt

    def _build_batch_judge_prompt(
        self,
        events: list[dict],
        prompts_original: list[str],
        links_content: list[str]
    ) -> str:
        """Constrói um prompt único para julgar múltiplos eventos em batch.

        Args:
            events: Lista de eventos a julgar
            prompts_original: Lista de prompts originais (um por evento)
            links_content: Lista de conteúdos dos links (um por evento)

        Returns:
            Prompt formatado para o GPT-5 julgar todos os eventos
        """
        # Cabeçalho
        prompt = f"""Você é um avaliador de qualidade de dados de eventos culturais.

Sua tarefa é avaliar a qualidade de {len(events)} eventos extraídos automaticamente, verificando:
1. Se cada evento corresponde ao que foi solicitado no prompt original (aderência)
2. Se os dados extraídos condizem com o conteúdo do link (correlação)
3. Se as informações estão completas e corretas (qualidade geral)

═══════════════════════════════════════════════════════════════
EVENTOS PARA AVALIAR ({len(events)} eventos):
═══════════════════════════════════════════════════════════════

"""

        # Adicionar cada evento
        for idx, (event, prompt_orig, link_cont) in enumerate(zip(events, prompts_original, links_content), 1):
            event_json = json.dumps(event, ensure_ascii=False, indent=2)

            prompt += f"""
───────────────────────────────────────────────────────────────
EVENTO #{idx}
───────────────────────────────────────────────────────────────

📋 PROMPT ORIGINAL DA BUSCA:
{prompt_orig}

📊 DADOS EXTRAÍDOS:
{event_json}

🔗 CONTEÚDO DO LINK (primeiros {JUDGE_MAX_LINK_CHARS} chars):
{link_cont}

"""

        # Instruções de avaliação
        prompt += f"""
═══════════════════════════════════════════════════════════════
CRITÉRIOS DE AVALIAÇÃO (nota 0-10 para cada):
═══════════════════════════════════════════════════════════════

Para CADA um dos {len(events)} eventos, avalie:

1. **ADERÊNCIA AO PROMPT (peso 40%)**
   - O evento corresponde ao tipo solicitado no prompt?
   - Está dentro da categoria/venue esperado?
   - Palavras-chave batem com o prompt?

2. **CORRELAÇÃO LINK-DADOS (peso 40%)**
   - Título do evento bate com o conteúdo do link?
   - Data e horário estão corretos conforme o link?
   - Local/venue conferem?
   - Preço está correto (se disponível no link)?

3. **QUALIDADE GERAL (peso 20%)**
   - Campos obrigatórios estão preenchidos?
   - Informações são completas e claras?
   - Não há inconsistências óbvias?

═══════════════════════════════════════════════════════════════
RETORNE JSON ARRAY COM EXATAMENTE {len(events)} AVALIAÇÕES:
═══════════════════════════════════════════════════════════════

[
  {{
    "event_index": 1,
    "prompt_adherence": 8.5,
    "link_match": 9.0,
    "completeness": 7.5,
    "quality_score": 8.3,
    "notes": "Evento condiz com busca. Link válido e dados corretos, mas preço genérico."
  }},
  {{
    "event_index": 2,
    "prompt_adherence": 7.0,
    "link_match": 8.5,
    "completeness": 8.0,
    "quality_score": 7.7,
    "notes": "Boa correlação link-dados. Descrição ausente."
  }}
  // ... continue para todos os {len(events)} eventos
]

**IMPORTANTE:**
- Retorne EXATAMENTE {len(events)} avaliações (uma para cada evento)
- `event_index`: número do evento (1 a {len(events)})
- `prompt_adherence`: nota de aderência ao prompt (0-10)
- `link_match`: nota de correlação link-dados (0-10). Se link inacessível, use 5.0
- `completeness`: nota de completude (0-10)
- `quality_score`: nota final ponderada:
  quality_score = (prompt_adherence * 0.4) + (link_match * 0.4) + (completeness * 0.2)
- `notes`: observações em até 200 caracteres

Seja rigoroso mas justo. Eventos legítimos com pequenas falhas: 7-8. Perfeitos: 9-10. Ruins: 0-4.
"""

        return prompt

    async def judge_event(self, event: dict) -> dict[str, Any]:
        """Julga a qualidade de um evento individual.

        Args:
            event: Dicionário do evento a julgar

        Returns:
            Dict com avaliação: {prompt_adherence, link_match, completeness, quality_score, notes}
        """
        try:
            logger.info(f"{self.log_prefix} Julgando: {event.get('titulo', 'Sem título')}")

            # 1. Recuperar prompt original
            prompt_original = self._get_original_prompt(event)

            # 2. Acessar link do evento (assíncrono)
            link = event.get("link_ingresso")
            link_content = await self._fetch_link_content(link)

            # 3. Construir prompt de julgamento
            judge_prompt = self._build_judge_prompt(event, prompt_original, link_content)

            # 4. Chamar GPT-5
            logger.debug(f"{self.log_prefix} Chamando GPT-5...")
            response = self.agent.run(judge_prompt, stream=False)

            # 5. Parsear resposta JSON
            response_text = response.content if hasattr(response, "content") else str(response)

            # Extrair JSON (pode vir com markdown)
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

            if json_start == -1 or json_end == 0:
                raise ValueError(f"Resposta não contém JSON: {response_text[:200]}")

            json_str = response_text[json_start:json_end]
            result = json.loads(json_str)

            # Validar campos obrigatórios
            required_fields = ["prompt_adherence", "link_match", "completeness", "quality_score", "notes"]
            for field in required_fields:
                if field not in result:
                    raise ValueError(f"Campo obrigatório ausente: {field}")

            logger.info(
                f"{self.log_prefix} ✓ Julgamento concluído: "
                f"score={result['quality_score']:.1f}, "
                f"prompt={result['prompt_adherence']:.1f}, "
                f"link={result['link_match']:.1f}"
            )

            return result

        except Exception as e:
            logger.error(f"{self.log_prefix} Erro ao julgar evento: {e}")
            # Retornar avaliação de erro
            return {
                "prompt_adherence": 0.0,
                "link_match": 0.0,
                "completeness": 0.0,
                "quality_score": 0.0,
                "notes": f"Erro no julgamento: {str(e)[:100]}"
            }

    async def judge_events_batch(self, events: list[dict]) -> list[dict]:
        """Julga um batch de eventos com UMA ÚNICA chamada GPT-5.

        Args:
            events: Lista de eventos a julgar (máximo JUDGE_BATCH_SIZE)

        Returns:
            Lista de eventos com campos de qualidade preenchidos
        """
        if not events:
            return []

        batch_size = len(events)
        logger.info(f"{self.log_prefix} Julgando batch de {batch_size} eventos (1 chamada GPT-5)...")

        try:
            # 1. Recuperar prompts originais de todos os eventos
            prompts_original = [self._get_original_prompt(event) for event in events]

            # 2. Buscar conteúdos de todos os links em paralelo
            urls = [event.get("link_ingresso", "") for event in events]
            links_content = await self._fetch_links_batch(urls)

            # 3. Construir prompt único para todos os eventos do batch
            batch_prompt = self._build_batch_judge_prompt(events, prompts_original, links_content)

            # 4. Fazer UMA ÚNICA chamada ao GPT-5 para julgar todos os eventos
            logger.debug(f"{self.log_prefix} Chamando GPT-5 para julgar {batch_size} eventos...")
            response = self.agent.run(batch_prompt, stream=False)

            # 5. Parsear resposta JSON (array com avaliações)
            response_text = response.content if hasattr(response, "content") else str(response)

            # Extrair JSON array (pode vir com markdown)
            json_start = response_text.find("[")
            json_end = response_text.rfind("]") + 1

            if json_start == -1 or json_end == 0:
                raise ValueError(f"Resposta não contém JSON array: {response_text[:500]}")

            json_str = response_text[json_start:json_end]
            evaluations = json.loads(json_str)

            # Validar que temos o número correto de avaliações
            if len(evaluations) != batch_size:
                logger.warning(
                    f"{self.log_prefix} GPT-5 retornou {len(evaluations)} avaliações, "
                    f"esperado {batch_size}. Ajustando..."
                )

            # 6. Adicionar campos de qualidade aos eventos
            judged_events = []
            for idx, event in enumerate(events):
                event_judged = event.copy()

                # Buscar avaliação correspondente (por event_index ou por posição)
                evaluation = None
                for eval_item in evaluations:
                    if eval_item.get("event_index") == idx + 1:
                        evaluation = eval_item
                        break

                # Fallback: usar por posição se não encontrou por index
                if not evaluation and idx < len(evaluations):
                    evaluation = evaluations[idx]

                # Se ainda não tem avaliação, criar uma de erro
                if not evaluation:
                    logger.error(f"{self.log_prefix} Avaliação ausente para evento #{idx + 1}")
                    evaluation = {
                        "prompt_adherence": 0.0,
                        "link_match": 0.0,
                        "completeness": 0.0,
                        "quality_score": 0.0,
                        "notes": "Erro: avaliação ausente na resposta do GPT-5"
                    }

                # Adicionar campos ao evento
                event_judged["quality_score"] = evaluation.get("quality_score", 0.0)
                event_judged["prompt_adherence"] = evaluation.get("prompt_adherence", 0.0)
                event_judged["link_match"] = evaluation.get("link_match", 0.0)
                event_judged["completeness"] = evaluation.get("completeness", 0.0)
                event_judged["quality_notes"] = evaluation.get("notes", "")
                event_judged["judged_at"] = datetime.now().isoformat()

                judged_events.append(event_judged)

            # Log estatísticas
            avg_score = sum(e["quality_score"] for e in judged_events) / len(judged_events)
            logger.info(
                f"{self.log_prefix} ✓ Batch julgado com sucesso! "
                f"Nota média: {avg_score:.1f}/10"
            )

            return judged_events

        except Exception as e:
            logger.error(f"{self.log_prefix} Erro ao julgar batch: {e}")
            # Retornar eventos com avaliações de erro
            judged_events = []
            for event in events:
                event_judged = event.copy()
                event_judged["quality_score"] = 0.0
                event_judged["prompt_adherence"] = 0.0
                event_judged["link_match"] = 0.0
                event_judged["completeness"] = 0.0
                event_judged["quality_notes"] = f"Erro no batch: {str(e)[:100]}"
                event_judged["judged_at"] = datetime.now().isoformat()
                judged_events.append(event_judged)

            return judged_events

    async def judge_all_events(
        self,
        events: list[dict],
        progress_callback: callable = None,
        max_parallel_batches: int = 3
    ) -> list[dict]:
        """Julga todos os eventos dividindo em batches, processando múltiplos batches em paralelo.

        Args:
            events: Lista completa de eventos
            progress_callback: Função chamada a cada batch concluído (batch_num, total_batches)
            max_parallel_batches: Número máximo de batches processados simultaneamente (default: 3)

        Returns:
            Lista de todos os eventos julgados
        """
        total_events = len(events)
        batch_size = JUDGE_BATCH_SIZE
        total_batches = (total_events + batch_size - 1) // batch_size

        logger.info(
            f"{self.log_prefix} Iniciando julgamento de {total_events} eventos "
            f"em {total_batches} batches de {batch_size} "
            f"(até {max_parallel_batches} batches paralelos)"
        )

        # Dividir eventos em batches
        batches = []
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, total_events)
            batch = events[start_idx:end_idx]
            batches.append((batch_num, batch))

        # Processar batches em paralelo com semáforo
        semaphore = asyncio.Semaphore(max_parallel_batches)
        completed_count = 0

        async def process_batch_with_semaphore(batch_data):
            nonlocal completed_count
            batch_num, batch = batch_data

            async with semaphore:
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, total_events)

                logger.info(
                    f"{self.log_prefix} Processando batch {batch_num + 1}/{total_batches} "
                    f"(eventos {start_idx + 1}-{end_idx})"
                )

                # Julgar batch (UMA chamada GPT-5 por batch)
                judged_batch = await self.judge_events_batch(batch)

                # Atualizar contador e callback
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, total_batches)

                return judged_batch

        # Executar todos os batches em paralelo (respeitando semáforo)
        tasks = [process_batch_with_semaphore(batch_data) for batch_data in batches]
        judged_batches = await asyncio.gather(*tasks)

        # Concatenar todos os resultados
        all_judged = []
        for judged_batch in judged_batches:
            all_judged.extend(judged_batch)

        logger.info(f"{self.log_prefix} ✅ Todos os {total_events} eventos julgados com sucesso!")

        # Estatísticas finais
        avg_score = sum(e.get("quality_score", 0) for e in all_judged) / len(all_judged)
        high_quality = sum(1 for e in all_judged if e.get("quality_score", 0) >= 8)
        medium_quality = sum(1 for e in all_judged if 5 <= e.get("quality_score", 0) < 8)
        low_quality = sum(1 for e in all_judged if e.get("quality_score", 0) < 5)

        logger.info(f"{self.log_prefix} 📊 Estatísticas:")
        logger.info(f"{self.log_prefix}   Nota média: {avg_score:.2f}/10")
        logger.info(f"{self.log_prefix}   Alta qualidade (≥8): {high_quality} eventos")
        logger.info(f"{self.log_prefix}   Média qualidade (5-7.9): {medium_quality} eventos")
        logger.info(f"{self.log_prefix}   Baixa qualidade (<5): {low_quality} eventos")

        return all_judged
