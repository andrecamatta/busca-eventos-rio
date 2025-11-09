"""
Carregador de prompts a partir de arquivos YAML.

Este módulo separa prompts (conteúdo) de código (lógica),
melhorando manutenibilidade e permitindo versionamento independente.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class PromptLoader:
    """
    Carrega e interpola prompts de arquivos YAML.

    Example:
        >>> loader = PromptLoader("prompts/search_prompts.yaml")
        >>> context = {
        ...     "start_date_str": "08/11/2025",
        ...     "end_date_str": "29/11/2025",
        ...     "month_str": "novembro",
        ...     "month_year_str": "novembro 2025"
        ... }
        >>> prompt_config = loader.get_categoria("jazz", context)
        >>> print(prompt_config["nome"])  # "Jazz"
    """

    def __init__(self, yaml_path: str | Path = None):
        """
        Inicializa loader com arquivo YAML.

        Args:
            yaml_path: Caminho para o arquivo YAML de prompts.
                       Se None, usa o padrão: prompts/search_prompts.yaml
        """
        if yaml_path is None:
            # Caminho relativo à raiz do projeto
            yaml_path = Path(__file__).parent.parent / "prompts" / "search_prompts.yaml"

        self.yaml_path = Path(yaml_path)
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Carrega arquivo YAML."""
        if not self.yaml_path.exists():
            raise FileNotFoundError(
                f"Arquivo de prompts não encontrado: {self.yaml_path}\n"
                f"Crie o arquivo ou especifique um caminho válido."
            )

        with open(self.yaml_path, 'r', encoding='utf-8') as f:
            self._data = yaml.safe_load(f)

    def _interpolate(self, value: Any, context: Dict[str, str]) -> Any:
        """
        Interpola variáveis {var} em strings recursivamente.

        Args:
            value: Valor a interpolar (str, list, dict)
            context: Dicionário com variáveis para interpolação

        Returns:
            Valor interpolado (mesmo tipo da entrada)
        """
        if isinstance(value, str):
            return value.format(**context)
        elif isinstance(value, list):
            return [self._interpolate(item, context) for item in value]
        elif isinstance(value, dict):
            return {k: self._interpolate(v, context) for k, v in value.items()}
        else:
            return value

    def get_template_base(self) -> Dict[str, Any]:
        """Retorna template base comum a todos os prompts."""
        return self._data.get("_template_base", {})

    def get_categoria(self, nome: str, context: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Retorna configuração de uma categoria com variáveis interpoladas.

        Args:
            nome: Nome da categoria (ex: "jazz", "comedia")
            context: Contexto com variáveis para interpolação
                     (start_date_str, end_date_str, month_str, etc)

        Returns:
            Dicionário com configuração da categoria

        Raises:
            KeyError: Se categoria não existe
        """
        if "categorias" not in self._data:
            raise ValueError(f"Seção 'categorias' não encontrada no YAML: {self.yaml_path}")

        if nome not in self._data["categorias"]:
            available = list(self._data["categorias"].keys())
            raise KeyError(
                f"Categoria '{nome}' não encontrada.\n"
                f"Categorias disponíveis: {', '.join(available)}"
            )

        config = self._data["categorias"][nome].copy()

        # Interpolar variáveis se contexto fornecido
        if context:
            config = self._interpolate(config, context)

        return config

    def get_venue(self, nome: str, context: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Retorna configuração de um venue com variáveis interpoladas.

        Args:
            nome: Nome do venue (ex: "casa_choro", "ccbb")
            context: Contexto com variáveis para interpolação

        Returns:
            Dicionário com configuração do venue

        Raises:
            KeyError: Se venue não existe
        """
        if "venues" not in self._data:
            raise ValueError(f"Seção 'venues' não encontrada no YAML: {self.yaml_path}")

        if nome not in self._data["venues"]:
            available = list(self._data["venues"].keys())
            raise KeyError(
                f"Venue '{nome}' não encontrado.\n"
                f"Venues disponíveis: {', '.join(available)}"
            )

        config = self._data["venues"][nome].copy()

        # Interpolar variáveis se contexto fornecido
        if context:
            config = self._interpolate(config, context)

        return config

    def get_all_categorias(self) -> list[str]:
        """Retorna lista de nomes de todas as categorias."""
        return list(self._data.get("categorias", {}).keys())

    def get_all_venues(self) -> list[str]:
        """Retorna lista de nomes de todos os venues."""
        return list(self._data.get("venues", {}).keys())

    def reload(self) -> None:
        """Recarrega arquivo YAML (útil para hot-reload em desenvolvimento)."""
        self._load()

    def build_context(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, str]:
        """
        Constrói contexto padrão para interpolação de datas.

        Args:
            start_date: Data de início
            end_date: Data de fim

        Returns:
            Dicionário com variáveis de data formatadas

        Example:
            >>> context = loader.build_context(
            ...     datetime(2025, 11, 8),
            ...     datetime(2025, 11, 29)
            ... )
            >>> context["start_date_str"]
            '08/11/2025'
        """
        # Mapeamento de meses em português
        meses = {
            1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
            5: "maio", 6: "junho", 7: "julho", 8: "agosto",
            9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
        }

        month_str = meses[start_date.month]
        month_year_str = f"{month_str} {start_date.year}"

        return {
            "start_date_str": start_date.strftime("%d/%m/%Y"),
            "end_date_str": end_date.strftime("%d/%m/%Y"),
            "month_str": month_str,
            "month_year_str": month_year_str,
        }


# Singleton global para reutilização
_loader_instance: Optional[PromptLoader] = None


def get_prompt_loader(yaml_path: Optional[str | Path] = None) -> PromptLoader:
    """
    Retorna instância singleton do PromptLoader.

    Args:
        yaml_path: Caminho opcional para YAML customizado

    Returns:
        Instância do PromptLoader
    """
    global _loader_instance

    if _loader_instance is None:
        _loader_instance = PromptLoader(yaml_path)

    return _loader_instance
