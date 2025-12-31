"""
Retriever Registry

Plugin-based registration system for retriever implementations.
Allows adding new retrievers without modifying core factory code.

Usage:
    # In retriever module (e.g., basic.py):
    from codegraph_search.infrastructure.registry import retriever_registry

    @retriever_registry.register("basic")
    class BasicRetriever:
        ...

    # Or manual registration:
    retriever_registry.register("basic", BasicRetriever)

    # In factory:
    retriever = retriever_registry.create("basic", container, config)
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_search.infrastructure.factory import RetrieverConfig

logger = get_logger(__name__)


@runtime_checkable
class RetrieverProtocol(Protocol):
    """Protocol for retriever implementations."""

    async def retrieve(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        **kwargs: Any,
    ) -> Any:
        """Execute retrieval."""
        ...


@dataclass
class RetrieverMeta:
    """Metadata for registered retriever."""

    name: str
    description: str
    features: list[str] = field(default_factory=list)
    factory_fn: Callable[..., RetrieverProtocol] | None = None
    wrapper_class: type | None = None


T = TypeVar("T")


class RetrieverRegistry:
    """
    Central registry for retriever implementations.

    Supports two registration patterns:
    1. Decorator-based: @retriever_registry.register("name")
    2. Factory function: retriever_registry.register_factory("name", factory_fn)
    """

    def __init__(self) -> None:
        self._retrievers: dict[str, RetrieverMeta] = {}
        self._initialized: set[str] = set()

    def register(
        self,
        name: str,
        description: str = "",
        features: list[str] | None = None,
    ) -> Callable[[type[T]], type[T]]:
        """
        Decorator to register a retriever wrapper class.

        Usage:
            @retriever_registry.register("basic", "Basic multi-index fusion")
            class BasicRetrieverWrapper:
                def __init__(self, container, config): ...
                async def retrieve(self, ...): ...
        """

        def decorator(cls: type[T]) -> type[T]:
            self._retrievers[name] = RetrieverMeta(
                name=name,
                description=description or cls.__doc__ or "",
                features=features or [],
                wrapper_class=cls,
            )
            logger.debug("retriever_registered", name=name, class_name=cls.__name__)
            return cls

        return decorator

    def register_factory(
        self,
        name: str,
        factory_fn: Callable[..., RetrieverProtocol],
        description: str = "",
        features: list[str] | None = None,
    ) -> None:
        """
        Register a factory function for creating retrievers.

        Usage:
            def create_basic_retriever(container, config):
                return BasicRetrieverWrapper(container, config)

            retriever_registry.register_factory("basic", create_basic_retriever)
        """
        self._retrievers[name] = RetrieverMeta(
            name=name,
            description=description,
            features=features or [],
            factory_fn=factory_fn,
        )
        logger.debug("retriever_factory_registered", name=name)

    def create(
        self,
        name: str,
        container: Any,
        config: "RetrieverConfig",
    ) -> RetrieverProtocol:
        """
        Create a retriever instance by name.

        Args:
            name: Registered retriever name
            container: DI container with dependencies
            config: Retriever configuration

        Returns:
            Retriever instance

        Raises:
            KeyError: If retriever name not registered
        """
        if name not in self._retrievers:
            available = ", ".join(self._retrievers.keys())
            raise KeyError(f"Unknown retriever: {name}. Available: {available}")

        meta = self._retrievers[name]

        if meta.factory_fn:
            return meta.factory_fn(container, config)
        elif meta.wrapper_class:
            return meta.wrapper_class(container, config)
        else:
            raise ValueError(f"Retriever {name} has no factory or wrapper class")

    def get(self, name: str) -> RetrieverMeta | None:
        """Get retriever metadata by name."""
        return self._retrievers.get(name)

    def list_available(self) -> list[dict[str, Any]]:
        """List all registered retrievers with metadata."""
        return [
            {
                "type": meta.name,
                "description": meta.description,
                "features": meta.features,
            }
            for meta in self._retrievers.values()
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._retrievers

    def __len__(self) -> int:
        return len(self._retrievers)


# Global registry singleton
retriever_registry = RetrieverRegistry()


def ensure_retrievers_registered() -> None:
    """
    Ensure all built-in retrievers are registered.

    Call this before using the registry to trigger lazy imports
    of all retriever modules that self-register.
    """
    # Import modules to trigger @register decorators
    # Each module registers itself on import
    from codegraph_search.infrastructure import _builtin_retrievers  # noqa: F401
