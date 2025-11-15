"""
CategoryRegistry - Single source of truth for event categories

This utility provides a centralized API for all category operations,
loading from prompts/search_prompts.yaml as the primary source.

All category configurations, display names, keywords, and validation rules
are managed through this registry to avoid hardcoded duplications.
"""

import logging
from typing import Dict, List, Optional, Any
from functools import lru_cache
from utils.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)


class CategoryRegistry:
    """
    Centralized registry for event categories.

    Loads from prompts/search_prompts.yaml and provides type-safe API
    for category operations across all components.
    """

    _instance = None
    _loader: Optional[PromptLoader] = None
    _categories: Dict[str, Dict[str, Any]] = {}
    _keyword_map: Dict[str, str] = {}  # keyword -> category_id mapping

    def __new__(cls):
        """Singleton pattern to ensure single YAML load"""
        if cls._instance is None:
            cls._instance = super(CategoryRegistry, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Load categories from YAML and build keyword maps"""
        try:
            self._loader = PromptLoader()
            # Access internal _data dict to get categories section
            self._categories = self._loader._data.get("categorias", {})

            # Build keyword map for normalization
            self._build_keyword_map()

            logger.info(f"CategoryRegistry initialized with {len(self._categories)} categories")

        except Exception as e:
            logger.error(f"Failed to initialize CategoryRegistry: {e}")
            # Fallback to empty dict - methods will handle gracefully
            self._categories = {}
            self._keyword_map = {}

    def _build_keyword_map(self):
        """Build mapping from keywords/aliases to category IDs for normalization"""
        self._keyword_map = {}

        for cat_id, cat_data in self._categories.items():
            # Map display name to ID
            display_name = cat_data.get("nome", cat_id.title()).lower()
            self._keyword_map[display_name] = cat_id

            # Map category ID itself (normalized)
            self._keyword_map[cat_id.lower()] = cat_id
            self._keyword_map[cat_id.replace("_", " ").lower()] = cat_id

            # Map keywords from cache_keywords field
            cache_keywords = cat_data.get("cache_keywords", [])
            for keyword in cache_keywords:
                self._keyword_map[keyword.lower()] = cat_id

            # Map keywords from palavras_chave field
            palavras_chave = cat_data.get("palavras_chave", [])
            for keyword in palavras_chave:
                self._keyword_map[keyword.lower()] = cat_id

    @staticmethod
    @lru_cache(maxsize=1)
    def get_instance():
        """Get singleton instance (cached)"""
        return CategoryRegistry()

    @staticmethod
    def get_all_category_ids() -> List[str]:
        """
        Get list of all valid category IDs.

        Returns:
            List of category IDs in snake_case (e.g., ['jazz', 'atividades_ar_livre', ...])
        """
        instance = CategoryRegistry.get_instance()
        return list(instance._categories.keys())

    @staticmethod
    def get_category_display_name(category_id: str) -> str:
        """
        Get display name for a category ID.

        Args:
            category_id: Category ID in snake_case (e.g., 'jazz', 'atividades_ar_livre')

        Returns:
            Display name from YAML 'nome' field (e.g., 'Jazz', 'Atividades ao Ar Livre')
            Falls back to titlecased ID if not found.
        """
        instance = CategoryRegistry.get_instance()
        cat_data = instance._categories.get(category_id, {})
        return cat_data.get("nome", category_id.replace("_", " ").title())

    @staticmethod
    def get_category_data(category_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full category configuration data.

        Args:
            category_id: Category ID in snake_case

        Returns:
            Complete category dict from YAML, or None if not found
        """
        instance = CategoryRegistry.get_instance()
        return instance._categories.get(category_id)

    @staticmethod
    def normalize_category(raw_category: str) -> Optional[Dict[str, str]]:
        """
        Normalize any category string to standardized format.

        Handles variations like:
        - "Outdoor" → {'id': 'outdoor', 'nome': 'Outdoor/Parques'}
        - "feira gastronômica" → {'id': 'feira_gastronomica', 'nome': 'Feira Gastronômica'}
        - "outdoor_parques" → {'id': 'outdoor', 'nome': 'Outdoor/Parques'}

        Args:
            raw_category: Category string in any format (from LLM, user input, etc.)

        Returns:
            Dict with {'id': str, 'nome': str} or None if no match found
        """
        if not raw_category:
            return None

        instance = CategoryRegistry.get_instance()
        raw_lower = raw_category.strip().lower()

        # Direct keyword map lookup
        if raw_lower in instance._keyword_map:
            cat_id = instance._keyword_map[raw_lower]
            return {
                'id': cat_id,
                'nome': CategoryRegistry.get_category_display_name(cat_id)
            }

        # Fuzzy matching - check if raw_category is substring of any keyword
        for keyword, cat_id in instance._keyword_map.items():
            if raw_lower in keyword or keyword in raw_lower:
                return {
                    'id': cat_id,
                    'nome': CategoryRegistry.get_category_display_name(cat_id)
                }

        # No match found
        logger.warning(f"Could not normalize category: '{raw_category}'")
        return None

    @staticmethod
    def get_validation_rules(category_id: str) -> Dict[str, Any]:
        """
        Get validation rules for a category.

        Extracts rules like:
        - Allowed days of week
        - Time constraints
        - Required/excluded keywords
        - Special instructions

        Args:
            category_id: Category ID in snake_case

        Returns:
            Dict with validation rules, empty dict if category not found
        """
        instance = CategoryRegistry.get_instance()
        cat_data = instance._categories.get(category_id, {})

        # Extract validation-relevant fields
        return {
            'category_id': category_id,
            'nome': cat_data.get('nome', category_id.title()),
            'descricao': cat_data.get('descricao', ''),
            'tipos_evento': cat_data.get('tipos_evento', []),
            'palavras_chave': cat_data.get('palavras_chave', []),
            'palavras_excluir': cat_data.get('palavras_excluir', []),
            'instrucoes_especiais': cat_data.get('instrucoes_especiais', ''),
            'min_events': cat_data.get('min_events', 0),
            'venues_sugeridos': cat_data.get('venues_sugeridos', []),
        }

    @staticmethod
    def get_search_keywords(category_id: str) -> List[str]:
        """
        Get search keywords for a category.

        Args:
            category_id: Category ID in snake_case

        Returns:
            List of keywords for search queries
        """
        instance = CategoryRegistry.get_instance()
        cat_data = instance._categories.get(category_id, {})
        return cat_data.get('palavras_chave', [])

    @staticmethod
    def get_cache_keywords(category_id: str) -> List[str]:
        """
        Get cache filtering keywords for a category.

        Args:
            category_id: Category ID in snake_case

        Returns:
            List of keywords for cache filtering
        """
        instance = CategoryRegistry.get_instance()
        cat_data = instance._categories.get(category_id, {})
        return cat_data.get('cache_keywords', [])

    @staticmethod
    def is_valid_category(category_id: str) -> bool:
        """
        Check if a category ID is valid.

        Args:
            category_id: Category ID to check

        Returns:
            True if category exists in registry
        """
        instance = CategoryRegistry.get_instance()
        return category_id in instance._categories

    @staticmethod
    def get_all_display_names() -> List[str]:
        """
        Get list of all category display names.

        Returns:
            List of display names (e.g., ['Jazz', 'Atividades ao Ar Livre', ...])
            Used for Pydantic Literal generation.
        """
        instance = CategoryRegistry.get_instance()
        return [
            cat_data.get("nome", cat_id.title())
            for cat_id, cat_data in instance._categories.items()
        ]

    @staticmethod
    def reload():
        """
        Force reload of categories from YAML.

        Useful after YAML changes during development.
        Clears singleton and LRU cache.
        """
        CategoryRegistry._instance = None
        CategoryRegistry.get_instance.cache_clear()
        return CategoryRegistry.get_instance()


# Convenience functions for backward compatibility
def get_all_category_ids() -> List[str]:
    """Get all valid category IDs"""
    return CategoryRegistry.get_all_category_ids()


def get_category_display_name(category_id: str) -> str:
    """Get display name for category ID"""
    return CategoryRegistry.get_category_display_name(category_id)


def normalize_category(raw_category: str) -> Optional[Dict[str, str]]:
    """Normalize category string to {id, nome}"""
    return CategoryRegistry.normalize_category(raw_category)


if __name__ == "__main__":
    # Test CategoryRegistry
    import json

    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

    print("\n" + "="*80)
    print("CATEGORY REGISTRY TEST")
    print("="*80)

    # Test 1: Get all categories
    categories = CategoryRegistry.get_all_category_ids()
    print(f"\n1. All Categories ({len(categories)}):")
    for cat_id in categories:
        display = CategoryRegistry.get_category_display_name(cat_id)
        print(f"   {cat_id:25} -> {display}")

    # Test 2: Normalize various inputs
    test_inputs = [
        "Outdoor",
        "outdoor",
        "outdoor_parques",
        "Outdoor/Parques",
        "parque",
        "Jazz",
        "feira gastronômica",
        "Feira Gastronômica",
        "feira_gastronomica",
        "Unknown Category"
    ]

    print(f"\n2. Normalization Tests:")
    for test in test_inputs:
        result = CategoryRegistry.normalize_category(test)
        if result:
            print(f"   '{test:30}' -> {result}")
        else:
            print(f"   '{test:30}' -> NOT FOUND")

    # Test 3: Get validation rules
    print(f"\n3. Validation Rules for 'outdoor':")
    rules = CategoryRegistry.get_validation_rules('outdoor')
    print(json.dumps(rules, indent=2, ensure_ascii=False))

    # Test 4: Display names for Pydantic
    print(f"\n4. All Display Names (for Pydantic Literal):")
    display_names = CategoryRegistry.get_all_display_names()
    print(f"   {display_names}")

    print("\n" + "="*80)
