"""Classe base para todos os agents do sistema."""

import logging
from typing import Optional

from utils.agent_factory import AgentFactory

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Classe base para agents com funcionalidade comum.

    Centraliza:
    - Criação padronizada de agents via AgentFactory
    - Logging consistente com prefixo emoji
    - Error handling básico
    """

    def __init__(
        self,
        agent_name: str,
        log_emoji: str = "🤖",
        model_type: str = "important",
        description: str = "",
        instructions: Optional[list[str]] = None,
        **kwargs
    ):
        """
        Inicializa agent base.

        Args:
            agent_name: Nome do agent (ex: "EnrichmentAgent")
            log_emoji: Emoji para prefixo de log (ex: "💎")
            model_type: Tipo de modelo ("light", "important", "search", "judge")
            description: Descrição do agent
            instructions: Lista de instruções para o agent
            **kwargs: Argumentos adicionais (ex: markdown=True)
        """
        self.agent_name = agent_name
        self.log_prefix = f"[{agent_name}] {log_emoji}"

        # Criar agent via factory
        self.agent = AgentFactory.create_agent(
            name=f"{agent_name} Agent",
            model_type=model_type,
            description=description or f"{agent_name} specialized agent",
            instructions=instructions or [],
            markdown=kwargs.get("markdown", True),
        )

        # Hook para inicialização adicional (sobrescrito por subclasses)
        self._initialize_dependencies(**kwargs)

    def _initialize_dependencies(self, **kwargs):
        """
        Hook para inicializar dependências específicas do agent.

        Subclasses podem sobrescrever para adicionar:
        - HttpClientWrapper
        - DateValidator
        - PromptLoader
        - Agents adicionais
        """
        pass

    def log_info(self, message: str):
        """Logging padronizado de informações."""
        logger.info(f"{self.log_prefix} {message}")

    def log_warning(self, message: str):
        """Logging padronizado de avisos."""
        logger.warning(f"{self.log_prefix} {message}")

    def log_error(self, message: str):
        """Logging padronizado de erros."""
        logger.error(f"{self.log_prefix} {message}")

    def safe_run(self, prompt: str, **kwargs):
        """
        Executa agent com error handling padronizado.

        Args:
            prompt: Prompt para executar
            **kwargs: Argumentos adicionais para agent.run()

        Returns:
            Response do agent

        Raises:
            Exception: Se houver erro na execução
        """
        try:
            response = self.agent.run(prompt, **kwargs)
            return response
        except Exception as e:
            self.log_error(f"Error running agent: {e}")
            raise
