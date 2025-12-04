"""
Retriever Factory

Unified factory for creating and selecting retriever implementations.
Uses plugin-based registry for extensibility.

Usage:
    factory = RetrieverFactory(container)

    # Get default retriever (V3)
    retriever = factory.create()

    # Get specific type
    retriever = factory.create(RetrieverType.OPTIMIZED)

    # With config
    config = RetrieverConfig(token_budget=8000)
    retriever = factory.create(RetrieverType.V3, config)

External plugins can register new retrievers:
    from src.contexts.retrieval_search.infrastructure.registry import retriever_registry

    @retriever_registry.register("custom", "My custom retriever")
    class CustomRetriever:
        def __init__(self, container, config): ...
        async def retrieve(self, ...): ...
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.contexts.retrieval_search.infrastructure.registry import (
    RetrieverProtocol,
    ensure_retrievers_registered,
    retriever_registry,
)
from src.infra.observability import get_logger

logger = get_logger(__name__)


class RetrieverType(Enum):
    """Available retriever implementations."""

    BASIC = "basic"
    OPTIMIZED = "optimized"
    V3 = "v3"
    MULTI_HOP = "multi_hop"
    REASONING = "reasoning"


class OptimizationLevel(Enum):
    """Optimization levels for OptimizedRetriever."""

    MINIMAL = "minimal"
    MODERATE = "moderate"
    FULL = "full"


@dataclass
class RetrieverConfig:
    """Unified configuration for all retriever types."""

    # Common settings
    timeout_seconds: float = 30.0
    token_budget: int = 4000
    max_results: int = 50

    # Caching
    enable_cache: bool = True
    cache_ttl: int = 300

    # Optimized retriever settings
    optimization_level: OptimizationLevel = OptimizationLevel.MODERATE

    # V3 specific settings
    enable_query_expansion: bool = True
    enable_consensus: bool = True

    # Multi-hop settings
    max_hops: int = 3

    # Reasoning settings
    enable_self_verification: bool = True
    reasoning_budget: int = 3

    # Additional kwargs
    extra: dict = field(default_factory=dict)


# Re-export UnifiedRetrievalResult from _builtin_retrievers for backward compatibility
from src.contexts.retrieval_search.infrastructure._builtin_retrievers import UnifiedRetrievalResult  # noqa: E402


class RetrieverFactory:
    """
    Factory for creating retriever instances.

    Uses plugin-based registry internally. New retrievers can be added
    without modifying this class - just register with retriever_registry.
    """

    def __init__(self, container: Any):
        """
        Initialize factory with DI container.

        Args:
            container: Dependency injection container with index clients
        """
        self.container = container
        self._instances: dict[str, RetrieverProtocol] = {}

        # Ensure built-in retrievers are registered
        ensure_retrievers_registered()

    def create(
        self,
        retriever_type: RetrieverType | str = RetrieverType.V3,
        config: RetrieverConfig | None = None,
    ) -> RetrieverProtocol:
        """
        Create or get cached retriever instance.

        Args:
            retriever_type: Type of retriever (enum or string name)
            config: Optional configuration

        Returns:
            Retriever instance implementing RetrieverProtocol
        """
        config = config or RetrieverConfig()

        # Normalize type to string
        type_name = retriever_type.value if isinstance(retriever_type, RetrieverType) else retriever_type

        # Check cache (only for default config)
        if config == RetrieverConfig() and type_name in self._instances:
            return self._instances[type_name]

        logger.info(
            "creating_retriever",
            retriever_type=type_name,
            optimization_level=config.optimization_level.value if type_name == "optimized" else None,
        )

        # Delegate to registry
        retriever = retriever_registry.create(type_name, self.container, config)

        # Cache default instances
        if config == RetrieverConfig():
            self._instances[type_name] = retriever

        return retriever

    def list_available(self) -> list[dict[str, Any]]:
        """List available retriever types with descriptions."""
        return retriever_registry.list_available()

    def register_custom(
        self,
        name: str,
        wrapper_class: type,
        description: str = "",
        features: list[str] | None = None,
    ) -> None:
        """
        Register a custom retriever at runtime.

        Args:
            name: Unique name for the retriever
            wrapper_class: Class with __init__(container, config) and retrieve() method
            description: Human-readable description
            features: List of feature names
        """
        retriever_registry.register(name, description, features)(wrapper_class)


__all__ = [
    "RetrieverType",
    "OptimizationLevel",
    "RetrieverConfig",
    "RetrieverProtocol",
    "RetrieverFactory",
    "UnifiedRetrievalResult",
    "retriever_registry",
]
