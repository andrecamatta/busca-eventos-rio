"""Utilitários para construção padronizada de prompts para LLM."""

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Classe utilitária para construir prompts padronizados."""

    @staticmethod
    def build_event_context(
        events: list[dict],
        include_fields: list[str] | None = None,
        format_type: str = "json"
    ) -> str:
        """Formata eventos para inclusão em prompts.

        Args:
            events: Lista de eventos a formatar
            include_fields: Lista de campos a incluir (None = todos)
            format_type: "json" ou "markdown"

        Returns:
            String formatada com os eventos
        """
        if not events:
            return "Nenhum evento disponível."

        # Filtrar campos se especificado
        if include_fields:
            filtered_events = []
            for event in events:
                filtered = {
                    k: v for k, v in event.items()
                    if k in include_fields
                }
                filtered_events.append(filtered)
        else:
            filtered_events = events

        if format_type == "json":
            return json.dumps(
                filtered_events,
                ensure_ascii=False,
                indent=2
            )
        elif format_type == "markdown":
            lines = []
            for i, event in enumerate(filtered_events, 1):
                lines.append(f"\n### Evento {i}")
                for key, value in event.items():
                    lines.append(f"- **{key}**: {value}")
            return "\n".join(lines)
        else:
            raise ValueError(f"Formato inválido: {format_type}")

    @staticmethod
    def build_date_range_context(
        start_date: datetime | None = None,
        end_date: datetime | None = None
    ) -> str:
        """Formata período de datas para prompts.

        Args:
            start_date: Data inicial (None = usa SEARCH_CONFIG)
            end_date: Data final (None = usa SEARCH_CONFIG)

        Returns:
            String formatada com o período
        """
        from config import SEARCH_CONFIG

        start = start_date or SEARCH_CONFIG["start_date"]
        end = end_date or SEARCH_CONFIG["end_date"]

        return (
            f"Período válido: {start.strftime('%d/%m/%Y')} "
            f"a {end.strftime('%d/%m/%Y')}"
        )

    @staticmethod
    def build_validation_rules_context() -> str:
        """Carrega e formata regras de validação do YAML.

        Returns:
            String formatada com as regras de validação
        """
        from utils.config_loader import ConfigLoader

        validation_config = ConfigLoader.load_validation_config()

        if not validation_config:
            return "Nenhuma regra de validação configurada."

        lines = ["## Regras de Validação\n"]

        # Adicionar informações atualizadas de eventos recorrentes
        updated_info = ConfigLoader.format_updated_info(validation_config)
        if updated_info:
            lines.append("### Eventos Recorrentes Atualizados")
            lines.append(updated_info)
            lines.append("")

        # Adicionar regras por categoria
        rules = validation_config.get('validation_rules', {})
        if rules:
            lines.append("### Regras por Categoria")
            for category, category_rules in rules.items():
                lines.append(f"\n**{category}**:")
                if isinstance(category_rules, dict):
                    for key, value in category_rules.items():
                        lines.append(f"- {key}: {value}")
                else:
                    lines.append(f"- {category_rules}")

        return "\n".join(lines)

    @staticmethod
    def build_category_list_context(
        enabled_only: bool = True
    ) -> str:
        """Formata lista de categorias para prompts.

        Args:
            enabled_only: Se True, apenas categorias habilitadas

        Returns:
            String formatada com categorias
        """
        from utils.category_registry import CategoryRegistry
        from config import ENABLED_CATEGORIES

        # Get all category IDs from CategoryRegistry
        all_category_ids = CategoryRegistry.get_all_category_ids()

        # Filter by enabled categories if requested
        if enabled_only:
            category_ids = [cat_id for cat_id in all_category_ids if cat_id in ENABLED_CATEGORIES]
        else:
            category_ids = all_category_ids

        if not category_ids:
            return "Nenhuma categoria configurada."

        lines = ["## Categorias Disponíveis\n"]
        for cat_id in category_ids:
            # Get category data from registry
            cat_data = CategoryRegistry.get_category_data(cat_id)
            display_name = CategoryRegistry.get_category_display_name(cat_id)
            description = cat_data.get('descricao', display_name) if cat_data else display_name
            keywords = CategoryRegistry.get_search_keywords(cat_id)

            lines.append(f"- **{display_name}**: {description}")
            if keywords:
                lines.append(f"  Keywords: {', '.join(keywords[:5])}")

        return "\n".join(lines)

    @staticmethod
    def build_venue_list_context(
        include_addresses: bool = False,
        enabled_only: bool = True
    ) -> str:
        """Formata lista de venues para prompts.

        Args:
            include_addresses: Se True, inclui endereços
            enabled_only: Se True, apenas venues habilitados

        Returns:
            String formatada com venues
        """
        from config import REQUIRED_VENUES, ENABLED_VENUES, VENUE_ADDRESSES

        if enabled_only:
            venues = {
                k: v for k, v in REQUIRED_VENUES.items()
                if k in ENABLED_VENUES
            }
        else:
            venues = REQUIRED_VENUES

        if not venues:
            return "Nenhum venue configurado."

        lines = ["## Venues Importantes\n"]
        for key, names in venues.items():
            lines.append(f"- **{names[0]}**")
            if len(names) > 1:
                lines.append(f"  Aliases: {', '.join(names[1:])}")

            if include_addresses and key in VENUE_ADDRESSES:
                addresses = VENUE_ADDRESSES[key]
                lines.append(f"  Endereços: {addresses[0]}")

        return "\n".join(lines)

    @staticmethod
    def build_json_schema_instruction(
        schema_example: dict,
        required_fields: list[str] | None = None
    ) -> str:
        """Gera instrução de formato JSON para o LLM.

        Args:
            schema_example: Exemplo do schema JSON esperado
            required_fields: Lista de campos obrigatórios

        Returns:
            String com instrução formatada
        """
        lines = ["## Formato de Resposta Esperado\n"]
        lines.append("Retorne APENAS JSON válido no seguinte formato:\n")
        lines.append("```json")
        lines.append(json.dumps(schema_example, ensure_ascii=False, indent=2))
        lines.append("```")

        if required_fields:
            lines.append("\n**Campos obrigatórios:**")
            for field in required_fields:
                lines.append(f"- `{field}`")

        return "\n".join(lines)

    @staticmethod
    def build_event_summary(events: list[dict]) -> str:
        """Gera resumo estatístico de eventos.

        Args:
            events: Lista de eventos

        Returns:
            String com resumo
        """
        if not events:
            return "Nenhum evento para resumir."

        from utils.event_counter import EventCounter

        total = len(events)
        by_category = EventCounter.count_by_category(events)
        by_venue = EventCounter.count_by_venue(events)

        lines = [
            f"**Total de eventos:** {total}\n",
            "**Por categoria:**"
        ]

        for cat, count in sorted(by_category.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"- {cat}: {count}")

        lines.append("\n**Top venues:**")
        for venue, count in sorted(by_venue.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"- {venue}: {count}")

        return "\n".join(lines)
