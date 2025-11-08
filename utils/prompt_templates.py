"""
Sistema de construção de prompts com Template Method Pattern.

Centraliza lógica de formatação de prompts duplicada entre agentes,
melhorando testabilidade e manutenibilidade.
"""

import json
from typing import Any, Dict, List, Optional


class PromptBuilder:
    """
    Builder para construção estruturada de prompts para LLMs.

    Fornece métodos para adicionar seções comuns de prompts de forma padronizada,
    eliminando duplicação de lógica de formatação entre agentes.

    Example:
        >>> builder = PromptBuilder()
        >>> builder.add_header("MISSÃO", "Encontrar eventos culturais")
        >>> builder.add_section("EVENTOS", eventos_texto)
        >>> builder.add_criteria({"ACEITE": ["Link específico"], "REJEITE": ["Homepage"]})
        >>> prompt = builder.build()
    """

    def __init__(self):
        """Inicializa builder vazio."""
        self.sections: List[str] = []

    def add_header(self, title: str, description: str) -> "PromptBuilder":
        """
        Adiciona cabeçalho/missão principal do prompt.

        Args:
            title: Título do cabeçalho (ex: "MISSÃO", "TAREFA")
            description: Descrição da missão/tarefa

        Returns:
            Self para method chaining
        """
        header = f"{title}: {description}"
        self.sections.append(header)
        return self

    def add_section(self, title: str, content: str, separator: str = "\n") -> "PromptBuilder":
        """
        Adiciona seção com título e conteúdo.

        Args:
            title: Título da seção (ex: "EVENTOS", "REGRAS")
            content: Conteúdo da seção (pode ser multiline)
            separator: Separador entre título e conteúdo (default: newline)

        Returns:
            Self para method chaining
        """
        section = f"{title}:{separator}{content}"
        self.sections.append(section)
        return self

    def add_numbered_list(
        self,
        title: str,
        items: List[str],
        emoji_prefix: bool = False
    ) -> "PromptBuilder":
        """
        Adiciona lista numerada com título.

        Args:
            title: Título da lista
            items: Items da lista
            emoji_prefix: Se True, usa emojis (1️⃣, 2️⃣) em vez de números

        Returns:
            Self para method chaining
        """
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        formatted_items = []
        for i, item in enumerate(items, 1):
            if emoji_prefix and i <= len(emojis):
                prefix = emojis[i - 1]
            else:
                prefix = f"{i}."
            formatted_items.append(f"{prefix} {item}")

        content = "\n".join(formatted_items)
        return self.add_section(title, content)

    def add_bulleted_list(
        self,
        title: str,
        items: List[str],
        bullet: str = "-"
    ) -> "PromptBuilder":
        """
        Adiciona lista com bullets.

        Args:
            title: Título da lista
            items: Items da lista
            bullet: Caractere de bullet (default: "-")

        Returns:
            Self para method chaining
        """
        formatted_items = [f"{bullet} {item}" for item in items]
        content = "\n".join(formatted_items)
        return self.add_section(title, content)

    def add_criteria(
        self,
        criteria: Dict[str, List[str]],
        title: str = "CRITÉRIOS"
    ) -> "PromptBuilder":
        """
        Adiciona critérios de aceitação/rejeição.

        Args:
            criteria: Dict com chaves como "ACEITE", "REJEITE" e valores como listas
            title: Título da seção de critérios

        Returns:
            Self para method chaining

        Example:
            >>> builder.add_criteria({
            ...     "ACEITE": ["Links específicos", "IDs únicos"],
            ...     "REJEITE": ["Homepages", "Links genéricos"]
            ... })
        """
        lines = [title + ":"]

        for category, items in criteria.items():
            # Determinar emoji baseado na categoria
            if "aceit" in category.lower() or "aprova" in category.lower():
                emoji = "✅"
            elif "rejeit" in category.lower() or "bloqu" in category.lower():
                emoji = "❌"
            elif "atenção" in category.lower() or "aviso" in category.lower():
                emoji = "⚠️"
            else:
                emoji = "•"

            lines.append(f"\n{emoji} {category.upper()}:")
            for item in items:
                lines.append(f"   - {item}")

        self.sections.append("\n".join(lines))
        return self

    def add_json_example(
        self,
        example: Dict[str, Any],
        title: str = "FORMATO DE RESPOSTA"
    ) -> "PromptBuilder":
        """
        Adiciona exemplo de JSON esperado na resposta.

        Args:
            example: Dicionário com estrutura de exemplo
            title: Título da seção

        Returns:
            Self para method chaining
        """
        json_str = json.dumps(example, indent=2, ensure_ascii=False)
        content = f"```json\n{json_str}\n```"
        return self.add_section(title, content)

    def add_task(
        self,
        task: str,
        title: str = "TAREFA"
    ) -> "PromptBuilder":
        """
        Adiciona task/instruções finais.

        Args:
            task: Descrição da tarefa
            title: Título da seção de task

        Returns:
            Self para method chaining
        """
        return self.add_section(title, task)

    def add_instructions(
        self,
        instructions: List[str],
        title: str = "INSTRUÇÕES"
    ) -> "PromptBuilder":
        """
        Adiciona instruções importantes.

        Args:
            instructions: Lista de instruções
            title: Título da seção

        Returns:
            Self para method chaining
        """
        return self.add_bulleted_list(title, instructions)

    def add_raw(self, content: str) -> "PromptBuilder":
        """
        Adiciona conteúdo raw sem formatação.

        Args:
            content: Conteúdo bruto a adicionar

        Returns:
            Self para method chaining
        """
        self.sections.append(content)
        return self

    def build(self, section_separator: str = "\n\n") -> str:
        """
        Constrói prompt final juntando todas as seções.

        Args:
            section_separator: Separador entre seções (default: double newline)

        Returns:
            Prompt completo formatado
        """
        return section_separator.join(self.sections)

    def clear(self) -> "PromptBuilder":
        """
        Limpa todas as seções para reutilizar builder.

        Returns:
            Self para method chaining
        """
        self.sections = []
        return self


# Factory functions para prompts comuns

def build_event_list_text(events: List[Dict[str, Any]], max_desc_length: int = 100) -> str:
    """
    Formata lista de eventos para prompt.

    Args:
        events: Lista de eventos (dicts)
        max_desc_length: Comprimento máximo da descrição

    Returns:
        String formatada com eventos
    """
    event_texts = []
    for i, event in enumerate(events, 1):
        titulo = event.get("titulo", "Sem título")
        data = event.get("data", "Data não informada")
        horario = event.get("horario", "Horário não informado")
        local = event.get("local", "Local não informado")
        descricao = event.get("descricao", "")

        # Truncar descrição se muito longa
        if descricao and len(descricao) > max_desc_length:
            descricao = descricao[:max_desc_length] + "..."

        event_text = f"""Evento {i}:
- Título: {titulo}
- Data: {data}
- Horário: {horario}
- Local: {local}"""

        if descricao:
            event_text += f"\n- Descrição: {descricao}"

        event_texts.append(event_text)

    return "\n\n".join(event_texts)


def build_date_range_text(start_date, end_date) -> str:
    """
    Formata range de datas para prompt.

    Args:
        start_date: Data de início (datetime ou string)
        end_date: Data de fim (datetime ou string)

    Returns:
        String formatada: "DD/MM/YYYY a DD/MM/YYYY"
    """
    if hasattr(start_date, 'strftime'):
        start_str = start_date.strftime('%d/%m/%Y')
    else:
        start_str = str(start_date)

    if hasattr(end_date, 'strftime'):
        end_str = end_date.strftime('%d/%m/%Y')
    else:
        end_str = str(end_date)

    return f"{start_str} a {end_str}"
