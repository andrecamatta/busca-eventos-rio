"""Utilitário centralizado para carregar configurações de YAML."""

import yaml
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Classe utilitária para carregar e cachear configurações de YAML."""

    _validation_config_cache: dict[str, Any] | None = None
    _min_events_cache: dict[str, int] | None = None

    @staticmethod
    def load_validation_config() -> dict[str, Any]:
        """Carrega configurações de validação do YAML com cache.

        Returns:
            Dicionário com configurações de validação do search_prompts.yaml
        """
        if ConfigLoader._validation_config_cache is None:
            yaml_path = Path(__file__).parent.parent / "prompts" / "search_prompts.yaml"

            try:
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    ConfigLoader._validation_config_cache = config.get('validation', {})
            except Exception as e:
                logger.error(f"Erro ao carregar validation config do YAML: {e}")
                ConfigLoader._validation_config_cache = {}

        return ConfigLoader._validation_config_cache

    @staticmethod
    def format_updated_info(validation_config: dict) -> str:
        """Formata informações atualizadas de eventos recorrentes.

        Args:
            validation_config: Dicionário de configuração de validação

        Returns:
            String formatada com informações de feiras recorrentes
        """
        info_list = []

        feiras = validation_config.get('informacoes_eventos_atualizadas', {}).get('feiras_recorrentes', [])

        for feira in feiras:
            nome = feira.get('nome', '')
            frequencia = feira.get('frequencia', '')
            local = feira.get('local', '')
            obs = feira.get('observacao', '')

            info_list.append(f"- {nome}: {frequencia}")
            if local:
                info_list.append(f"  Local: {local}")
            if obs:
                info_list.append(f"  ⚠️ {obs}")

        return "\n".join(info_list) if info_list else ""

    @staticmethod
    def load_min_events_thresholds() -> dict[str, int]:
        """Carrega valores de min_events do search_prompts.yaml com cache.

        Returns:
            Dicionário mapeando categoria/venue -> min_events
        """
        if ConfigLoader._min_events_cache is None:
            yaml_path = Path(__file__).parent.parent / "prompts" / "search_prompts.yaml"
            thresholds = {}

            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                # Extrair min_events de categorias
                if "categorias" in data:
                    for cat_key, cat_data in data["categorias"].items():
                        if "min_events" in cat_data:
                            thresholds[cat_key] = cat_data["min_events"]

                # Extrair min_events de venues
                if "venues" in data:
                    for venue_key, venue_data in data["venues"].items():
                        if "min_events" in venue_data:
                            thresholds[venue_key] = venue_data["min_events"]

                logger.info(f"✓ Thresholds carregados do YAML: {len(thresholds)} categorias/venues")
                ConfigLoader._min_events_cache = thresholds

            except Exception as e:
                logger.warning(f"⚠️  Erro ao carregar thresholds do YAML: {e}. Usando valores padrão.")
                # Valores padrão (fallback) caso YAML falhe
                ConfigLoader._min_events_cache = {
                    "jazz": 2,
                    "comedia": 2,
                    "atividades_ar_livre": 2,
                    "musica_classica": 2,
                    "casa_choro": 2,
                    "sala_cecilia": 1,
                    "teatro_municipal": 1,
                }

        return ConfigLoader._min_events_cache

    @staticmethod
    def clear_cache():
        """Limpa o cache de configurações. Útil para testes."""
        ConfigLoader._validation_config_cache = None
        ConfigLoader._min_events_cache = None
