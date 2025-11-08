"""Agente de formatação de eventos para WhatsApp."""

import json
import logging
from datetime import datetime
from typing import Any

from config import MAX_DESCRIPTION_LENGTH
from utils.agent_factory import AgentFactory
from utils.date_helpers import DateParser

logger = logging.getLogger(__name__)

# Prefixo para logs deste agente
LOG_PREFIX = "[FormatAgent] 📝"


class FormatAgent:
    """Agente responsável por formatar eventos para compartilhamento no WhatsApp."""

    def __init__(self):
        self.log_prefix = "[FormatAgent] 📝"

        self.agent = AgentFactory.create_agent(
            name="Event Format Agent",
            model_type="light",  # GPT-5 mini - tarefa leve (formatação WhatsApp)
            description="Agente especializado em formatar eventos para compartilhamento no WhatsApp",
            instructions=[
                "Organizar eventos em ordem crescente por data",
                f"Criar resumo de até {MAX_DESCRIPTION_LENGTH} palavras para cada evento",
                "Formatar para WhatsApp com emojis apropriados",
                "Incluir: título, data, horário, local, valor, link",
                "Usar formatação clara e fácil de ler",
                "Agrupar eventos por data quando possível",
                "Adicionar emojis contextuais (🎺 jazz, 😂 comédia, 🌳 ar livre, etc)",
            ],
            markdown=True,
        )

    def format_for_whatsapp(self, verified_events: dict[str, Any]) -> str:
        """Formata eventos verificados para compartilhamento no WhatsApp.

        Inclui consolidação automática de eventos recorrentes antes da formatação.
        """
        logger.info(f"{self.log_prefix} Formatando eventos para WhatsApp...")

        # Extrair lista de eventos
        if isinstance(verified_events, dict):
            events_list = verified_events.get("verified_events", [])
        else:
            events_list = verified_events

        if not events_list:
            logger.warning("Nenhum evento para formatar")
            return "Nenhum evento encontrado para o período especificado."

        # Consolidar eventos recorrentes ANTES de formatar
        logger.info(f"{self.log_prefix} Consolidando eventos recorrentes...")
        from utils.event_consolidator import EventConsolidator

        consolidator = EventConsolidator()
        eventos_antes = len(events_list)
        events_list = consolidator.consolidate_recurring_events(events_list)
        eventos_depois = len(events_list)

        logger.info(
            f"{self.log_prefix} ✓ Eventos consolidados: {eventos_antes} → {eventos_depois} "
            f"({eventos_antes - eventos_depois} eventos mesclados)"
        )

        # Gerar timestamp atual
        current_timestamp = datetime.now().strftime('%d/%m/%Y às %H:%M')

        prompt = f"""
Você é um especialista em criar mensagens atraentes para WhatsApp.

EVENTOS VERIFICADOS:
{json.dumps(events_list, indent=2, ensure_ascii=False)}

TAREFA:
Crie uma mensagem formatada para WhatsApp seguindo este modelo:

```
🎭 EVENTOS RIO - Próximas 3 Semanas
Atualizado em: {current_timestamp}

📅 **[Data] - [Dia da semana]**
[Emoji da categoria] **[Título do Evento]**
⏰ [Horário] | 💰 [Valor]
📍 [Local]
🎫 [Link para ingressos]
📝 [Resumo de até {MAX_DESCRIPTION_LENGTH} palavras]

[Repetir para cada evento]

---
Total: [X] eventos encontrados
```

REGRAS:
1. Ordenar eventos por data crescente
2. Usar emojis apropriados:
   - 🎺 para jazz
   - 😂 para comédia/stand-up
   - 🎭 para teatro
   - 🌳 🏞️ para eventos ao ar livre
   - 🏛️ para locais culturais especiais
3. Se não tiver horário, omitir a linha
4. Se não tiver valor, colocar "Consultar"
5. Resumo deve ser atrativo e informativo
6. Incluir quebras de linha para facilitar leitura
7. Data em formato brasileiro (DD/MM/YYYY - Dia da semana)
8. Agrupar eventos do mesmo dia quando possível
9. **EVENTOS RECORRENTES**: Se o evento tiver campo "eh_recorrente": true:
   - Usar formato: "📅 Múltiplas datas: [primeira], [segunda] (+X datas)"
   - Listar até 3 datas explícitas, depois "+X datas" se houver mais
   - Ao final do evento, incluir seção com todas as datas:
     "   📆 Todas as datas disponíveis:\n   • [data] às [hora]\n   • [data] às [hora]..."

Retorne APENAS a mensagem formatada, pronta para Ctrl+C + Ctrl+V.
Não inclua explicações adicionais.
"""

        try:
            response = self.agent.run(prompt)
            formatted_message = response.content

            # Limpar markdown code blocks se existirem
            if "```" in formatted_message:
                formatted_message = formatted_message.split("```")[1]
                if formatted_message.startswith("text") or formatted_message.startswith("plaintext"):
                    formatted_message = formatted_message.split("\n", 1)[1]

            logger.info(f"{self.log_prefix} ✅ Formatação concluída com sucesso")
            return formatted_message.strip()

        except Exception as e:
            logger.error(f"Erro ao formatar eventos: {e}")
            return self._format_fallback(events_list)

    def _format_fallback(self, events_list: list[dict[str, Any]]) -> str:
        """Formatação de fallback caso LLM falhe."""
        logger.info("Usando formatação de fallback...")

        # Ordenar por data
        events_sorted = sorted(
            events_list,
            key=lambda x: self._parse_date(x.get("date", "")),
        )

        lines = [
            "🎭 EVENTOS RIO - Próximas 3 Semanas",
            f"Atualizado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}",
            "",
        ]

        for event in events_sorted:
            emoji = self._get_emoji(event.get("category", ""))
            title = event.get("title", "Sem título")
            date = event.get("date", "Data a confirmar")
            time = event.get("time") or event.get("horario")
            venue = event.get("venue") or event.get("local", "Local a confirmar")
            price = event.get("price") or event.get("valor", "Consultar")
            link = event.get("link") or event.get("ticket_link", "Link indisponível")
            description = event.get("description", "")[:500]  # limitar caracteres

            lines.append(f"📅 **{date}**")
            lines.append(f"{emoji} **{title}**")
            if time:
                lines.append(f"⏰ {time} | 💰 {price}")
            else:
                lines.append(f"💰 {price}")
            lines.append(f"📍 {venue}")
            lines.append(f"🎫 {link}")
            if description:
                lines.append(f"📝 {description}")
            lines.append("")

        lines.append("---")
        lines.append(f"Total: {len(events_sorted)} eventos encontrados")

        return "\n".join(lines)

    def _get_emoji(self, category: str) -> str:
        """Retorna emoji apropriado para a categoria."""
        category_lower = category.lower()
        emojis = {
            "jazz": "🎺",
            "comedia": "😂",
            "teatro": "🎭",
            "outdoor": "🌳",
            "venue_especial": "🏛️",
        }
        return emojis.get(category_lower, "🎉")

    def _parse_date(self, date_str: str) -> datetime:
        """Parseia string de data para ordenação."""
        if not date_str:
            return datetime.max

        # Remove horário se presente
        date_only = date_str.split()[0] if " " in date_str else date_str
        parsed = DateParser.parse_date(date_only)
        return parsed if parsed else datetime.max
