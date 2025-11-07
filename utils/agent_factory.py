"""Factory para criação padronizada de Agents com LLMs."""

from agno.agent import Agent
from agno.models.openai import OpenAIChat

from config import MODELS, OPENROUTER_API_KEY, OPENROUTER_BASE_URL


class AgentFactory:
    """Factory para criar agents com configurações padronizadas.

    Elimina duplicação de código na criação de agents em múltiplos arquivos.
    Centraliza configuração de API keys, base URLs e modelos.
    """

    @staticmethod
    def create_agent(
        name: str,
        model_type: str,
        description: str,
        instructions: list[str],
        markdown: bool = True,
    ) -> Agent:
        """Cria um Agent configurado com OpenRouter.

        Args:
            name: Nome do agent
            model_type: Tipo de modelo ("search", "search_simple", "light", "important")
            description: Descrição do propósito do agent
            instructions: Lista de instruções específicas
            markdown: Se deve usar markdown (padrão: True)

        Returns:
            Agent configurado e pronto para uso

        Examples:
            >>> agent = AgentFactory.create_agent(
            ...     name="Event Search Agent",
            ...     model_type="search",
            ...     description="Busca eventos no Rio",
            ...     instructions=["Buscar eventos de jazz", "Retornar JSON"]
            ... )
        """
        return Agent(
            name=name,
            model=OpenAIChat(
                id=MODELS[model_type],
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            ),
            description=description,
            instructions=instructions,
            markdown=markdown,
        )
