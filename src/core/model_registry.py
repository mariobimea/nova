"""
Model Registry - Factory for Model Providers

Centralized registry for creating model provider instances.
Supports aliases for user-friendly model names.
"""

import logging
from typing import Dict, Type, Optional

from .providers.model_provider import ModelProvider
from .providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Factory for creating model provider instances.

    This registry:
    1. Maps model names/aliases to provider classes
    2. Creates provider instances on demand
    3. Validates model names before execution
    4. Supports user-friendly aliases (e.g., "mini" → "gpt-4o-mini")

    Example:
        >>> provider = ModelRegistry.get_provider("gpt-4o-mini")
        >>> isinstance(provider, OpenAIProvider)
        True

        >>> provider = ModelRegistry.get_provider("mini")  # alias
        >>> provider.get_model_name()
        "gpt-4o-mini"
    """

    # Registry: model_name → (Provider class, internal model name)
    _REGISTRY: Dict[str, tuple[Type[ModelProvider], str]] = {
        # OpenAI models (full names)
        "gpt-4o-mini": (OpenAIProvider, "gpt-4o-mini"),
        "gpt-5-mini": (OpenAIProvider, "gpt-5-mini"),
        "gpt-5-codex": (OpenAIProvider, "gpt-5-codex"),
        "gpt-5": (OpenAIProvider, "gpt-5"),

        # OpenAI aliases (user-friendly)
        "mini": (OpenAIProvider, "gpt-4o-mini"),
        "codex": (OpenAIProvider, "gpt-5-codex"),

        # Future: Anthropic models
        # "claude-haiku-4-5": (AnthropicProvider, "claude-haiku-4-5"),
        # "haiku": (AnthropicProvider, "claude-haiku-4-5"),
        # "claude-sonnet-4-5": (AnthropicProvider, "claude-sonnet-4-5"),
        # "sonnet": (AnthropicProvider, "claude-sonnet-4-5"),
    }

    # Cache for provider instances (avoid recreating)
    _CACHE: Dict[str, ModelProvider] = {}

    @classmethod
    def get_provider(cls, model_name: str, api_key: Optional[str] = None) -> ModelProvider:
        """
        Get provider instance for a model.

        Creates provider instance if not cached. Returns cached instance if available.

        Args:
            model_name: Model name or alias (e.g., "gpt-4o-mini", "mini")
            api_key: Optional API key (or use environment variable)

        Returns:
            Provider instance

        Raises:
            ValueError: If model name is not registered

        Example:
            >>> provider = ModelRegistry.get_provider("gpt-4o-mini")
            >>> code, metadata = await provider.generate_code_with_tools(...)
        """
        if not model_name:
            raise ValueError("Model name cannot be empty")

        # Check cache first
        cache_key = f"{model_name}:{api_key or 'default'}"
        if cache_key in cls._CACHE:
            logger.debug(f"Using cached provider for model: {model_name}")
            return cls._CACHE[cache_key]

        # Validate model name
        if model_name not in cls._REGISTRY:
            available_models = cls.list_models()
            raise ValueError(
                f"Unknown model: '{model_name}'. "
                f"Available models: {', '.join(available_models)}"
            )

        # Create provider
        provider_class, internal_model_name = cls._REGISTRY[model_name]

        logger.info(f"Creating provider for model: {model_name} → {internal_model_name}")

        try:
            provider = provider_class(internal_model_name, api_key=api_key)

            # Cache the instance
            cls._CACHE[cache_key] = provider

            return provider

        except Exception as e:
            logger.error(f"Failed to create provider for model '{model_name}': {e}")
            raise ValueError(
                f"Failed to initialize provider for model '{model_name}': {e}"
            )

    @classmethod
    def list_models(cls) -> list[str]:
        """
        List all available models (including aliases).

        Returns:
            List of model names/aliases

        Example:
            >>> ModelRegistry.list_models()
            ['gpt-4o-mini', 'gpt-5-mini', 'gpt-5-codex', 'gpt-5', 'mini', 'codex']
        """
        return sorted(cls._REGISTRY.keys())

    @classmethod
    def list_models_by_provider(cls) -> Dict[str, list[str]]:
        """
        List models grouped by provider.

        Returns:
            Dictionary mapping provider names to model lists

        Example:
            >>> ModelRegistry.list_models_by_provider()
            {
                'OpenAI': ['gpt-4o-mini', 'gpt-5-mini', 'gpt-5-codex', 'gpt-5'],
                'Anthropic': []  # future
            }
        """
        providers: Dict[str, list[str]] = {}

        for model_name, (provider_class, internal_name) in cls._REGISTRY.items():
            # Skip aliases (they have different internal names)
            if model_name != internal_name:
                continue

            provider_name = provider_class.__name__.replace("Provider", "")

            if provider_name not in providers:
                providers[provider_name] = []

            providers[provider_name].append(model_name)

        return providers

    @classmethod
    def is_valid_model(cls, model_name: str) -> bool:
        """
        Check if a model name is valid.

        Args:
            model_name: Model name to validate

        Returns:
            True if model exists, False otherwise

        Example:
            >>> ModelRegistry.is_valid_model("gpt-4o-mini")
            True
            >>> ModelRegistry.is_valid_model("invalid-model")
            False
        """
        return model_name in cls._REGISTRY

    @classmethod
    def get_model_info(cls, model_name: str) -> Dict[str, any]:
        """
        Get detailed information about a model.

        Args:
            model_name: Model name or alias

        Returns:
            Dictionary with model information:
            {
                "model_name": "gpt-4o-mini",
                "provider": "OpenAI",
                "is_alias": False,
                "canonical_name": "gpt-4o-mini",
                "pricing": {"input": 0.15, "output": 0.60}
            }

        Raises:
            ValueError: If model not found

        Example:
            >>> info = ModelRegistry.get_model_info("mini")
            >>> info["canonical_name"]
            "gpt-4o-mini"
        """
        if model_name not in cls._REGISTRY:
            raise ValueError(f"Unknown model: '{model_name}'")

        provider_class, internal_name = cls._REGISTRY[model_name]
        provider_name = provider_class.__name__.replace("Provider", "")

        # Check if this is an alias
        is_alias = (model_name != internal_name)

        # Get pricing from a temp provider instance
        try:
            temp_provider = cls.get_provider(model_name)
            pricing = temp_provider.get_pricing()
        except Exception as e:
            logger.warning(f"Could not get pricing for {model_name}: {e}")
            pricing = {}

        return {
            "model_name": model_name,
            "provider": provider_name,
            "is_alias": is_alias,
            "canonical_name": internal_name,
            "pricing": pricing
        }

    @classmethod
    def clear_cache(cls):
        """
        Clear provider instance cache.

        Useful for testing or when API keys change.

        Example:
            >>> ModelRegistry.clear_cache()
            >>> # Next get_provider() call will create fresh instances
        """
        cls._CACHE.clear()
        logger.info("Provider cache cleared")
