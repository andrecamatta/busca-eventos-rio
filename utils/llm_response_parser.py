"""Utilitários para parsing e validação de respostas LLM."""

import logging
from typing import Any

from utils.json_helpers import safe_json_parse

logger = logging.getLogger(__name__)


class LLMResponseParser:
    """Classe utilitária para parsing e validação de respostas LLM."""

    @staticmethod
    def parse_json_response(
        content: str,
        default: dict | list | None = None,
        required_fields: list[str] | None = None,
        field_defaults: dict[str, Any] | None = None,
    ) -> dict | list:
        """Parse JSON de resposta LLM com validação de campos.

        Args:
            content: Conteúdo da resposta LLM (pode conter markdown)
            default: Valor padrão se parsing falhar
            required_fields: Lista de campos obrigatórios (apenas para dict)
            field_defaults: Valores padrão para campos específicos

        Returns:
            Objeto parseado (dict ou list) com campos validados

        Example:
            >>> parser = LLMResponseParser()
            >>> result = parser.parse_json_response(
            ...     response.content,
            ...     default={"approved": False},
            ...     required_fields=["approved", "reason"],
            ...     field_defaults={"confidence": 50}
            ... )
        """
        # Parse usando safe_json_parse existente
        parsed = safe_json_parse(content, default=default)

        # Se não for dict, retornar direto (não tem como validar campos)
        if not isinstance(parsed, dict):
            return parsed

        # Aplicar defaults de campos
        if field_defaults:
            for field, default_value in field_defaults.items():
                if field not in parsed:
                    parsed[field] = default_value

        # Validar campos obrigatórios
        if required_fields:
            missing = LLMResponseParser.get_missing_fields(parsed, required_fields)
            if missing:
                logger.warning(
                    f"Campos obrigatórios faltando na resposta LLM: {missing}. "
                    f"Usando defaults quando disponível."
                )

        return parsed

    @staticmethod
    def get_missing_fields(data: dict, required: list[str]) -> list[str]:
        """Retorna lista de campos obrigatórios ausentes.

        Args:
            data: Dicionário a validar
            required: Lista de campos obrigatórios

        Returns:
            Lista de campos faltando
        """
        return [field for field in required if field not in data]

    @staticmethod
    def validate_response_fields(
        data: dict,
        required: list[str]
    ) -> tuple[bool, list[str]]:
        """Valida se campos obrigatórios estão presentes.

        Args:
            data: Dicionário a validar
            required: Lista de campos obrigatórios

        Returns:
            Tupla (is_valid, missing_fields)
        """
        missing = LLMResponseParser.get_missing_fields(data, required)
        return (len(missing) == 0, missing)

    @staticmethod
    def parse_validation_response(
        content: str,
        default_approved: bool = False,
        default_confidence: int = 50,
    ) -> dict:
        """Parse resposta de validação (padrão comum nos agents).

        Args:
            content: Conteúdo da resposta LLM
            default_approved: Valor padrão para 'approved' se ausente
            default_confidence: Valor padrão para 'confidence' se ausente

        Returns:
            Dict com campos: approved, reason, confidence, warnings
        """
        return LLMResponseParser.parse_json_response(
            content,
            default={
                "approved": default_approved,
                "reason": "Erro ao processar resposta",
                "confidence": default_confidence,
            },
            required_fields=["approved", "reason"],
            field_defaults={
                "confidence": default_confidence,
                "warnings": [],
            },
        )

    @staticmethod
    def parse_event_list_response(
        content: str,
        default: list | None = None,
    ) -> list[dict]:
        """Parse resposta com lista de eventos.

        Args:
            content: Conteúdo da resposta LLM
            default: Lista padrão se parsing falhar

        Returns:
            Lista de eventos (dicts)
        """
        parsed = safe_json_parse(
            content,
            default=default if default is not None else []
        )

        # Garantir que é uma lista
        if not isinstance(parsed, list):
            logger.warning(
                f"Esperava lista de eventos mas recebeu {type(parsed)}. "
                f"Retornando lista vazia."
            )
            return default if default is not None else []

        # Garantir que todos os elementos são dicts
        events = []
        for item in parsed:
            if isinstance(item, dict):
                events.append(item)
            else:
                logger.warning(f"Item na lista não é dict: {type(item)}. Ignorando.")

        return events

    @staticmethod
    def parse_boolean_response(
        content: str,
        field_name: str = "result",
        default: bool = False,
    ) -> bool:
        """Parse resposta booleana simples.

        Args:
            content: Conteúdo da resposta LLM
            field_name: Nome do campo booleano esperado
            default: Valor padrão se parsing falhar

        Returns:
            Valor booleano
        """
        parsed = safe_json_parse(
            content,
            default={field_name: default}
        )

        if isinstance(parsed, dict):
            return bool(parsed.get(field_name, default))
        elif isinstance(parsed, bool):
            return parsed
        else:
            logger.warning(
                f"Resposta não é booleana nem dict: {type(parsed)}. "
                f"Usando default={default}"
            )
            return default
