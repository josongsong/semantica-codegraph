"""
Base Mode Handler

Provides abstract base class for mode implementations with common utilities.
Also provides ModeRegistry for decoupled mode registration.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, TypeVar

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)
T = TypeVar("T", bound="BaseModeHandler")


class ModeRegistry:
    """
    Registry for mode handlers.

    Provides decoupled mode registration via decorator or explicit register() call.
    Supports lazy instantiation with factory functions.

    Usage:
        # Via decorator
        @mode_registry.register(AgentMode.IMPLEMENTATION)
        class ImplementationMode(BaseModeHandler):
            ...

        # Via factory (for modes requiring dependencies)
        mode_registry.register_factory(
            AgentMode.DEBUG,
            lambda deps: DebugMode(llm_client=deps.get("llm"))
        )

        # Retrieval
        handler_cls = mode_registry.get(AgentMode.IMPLEMENTATION)
        handler = handler_cls()  # or handler_cls(deps)
    """

    _instance: "ModeRegistry | None" = None
    _handlers: dict[AgentMode, type["BaseModeHandler"]]
    _factories: dict[AgentMode, Callable[..., "BaseModeHandler"]]
    _simple_variants: dict[AgentMode, type["BaseModeHandler"]]

    def __new__(cls) -> "ModeRegistry":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers = {}
            cls._instance._factories = {}
            cls._instance._simple_variants = {}
        return cls._instance

    def register(
        self,
        mode: AgentMode,
        *,
        simple: bool = False,
    ) -> Callable[[type[T]], type[T]]:
        """
        Decorator to register a mode handler class.

        Args:
            mode: The AgentMode this handler implements
            simple: If True, register as simple/fallback variant

        Returns:
            Decorator function

        Example:
            @mode_registry.register(AgentMode.IMPLEMENTATION)
            class ImplementationMode(BaseModeHandler):
                ...

            @mode_registry.register(AgentMode.IMPLEMENTATION, simple=True)
            class ImplementationModeSimple(BaseModeHandler):
                ...
        """

        def decorator(cls: type[T]) -> type[T]:
            if simple:
                self._simple_variants[mode] = cls
                logger.debug(f"Registered simple mode handler: {mode.value} -> {cls.__name__}")
            else:
                self._handlers[mode] = cls
                logger.debug(f"Registered mode handler: {mode.value} -> {cls.__name__}")
            return cls

        return decorator

    def register_factory(
        self,
        mode: AgentMode,
        factory: Callable[..., "BaseModeHandler"],
    ) -> None:
        """
        Register a factory function for creating mode handlers.

        Useful for modes that require dependency injection.

        Args:
            mode: The AgentMode this factory creates
            factory: Factory function that accepts dependencies dict
        """
        self._factories[mode] = factory
        logger.debug(f"Registered mode factory: {mode.value}")

    def get(self, mode: AgentMode) -> type["BaseModeHandler"] | None:
        """
        Get handler class for a mode.

        Args:
            mode: The AgentMode to look up

        Returns:
            Handler class or None if not registered
        """
        return self._handlers.get(mode)

    def get_simple(self, mode: AgentMode) -> type["BaseModeHandler"] | None:
        """
        Get simple/fallback handler class for a mode.

        Args:
            mode: The AgentMode to look up

        Returns:
            Simple handler class or None if not registered
        """
        return self._simple_variants.get(mode)

    def get_factory(self, mode: AgentMode) -> Callable[..., "BaseModeHandler"] | None:
        """
        Get factory function for a mode.

        Args:
            mode: The AgentMode to look up

        Returns:
            Factory function or None if not registered
        """
        return self._factories.get(mode)

    def create(
        self,
        mode: AgentMode,
        deps: dict[str, Any] | None = None,
        *,
        simple: bool = False,
    ) -> "BaseModeHandler | None":
        """
        Create a mode handler instance.

        Tries factory first, then falls back to class instantiation.

        Args:
            mode: The AgentMode to create
            deps: Dependencies dict for factory/constructor
            simple: If True, create simple variant

        Returns:
            Handler instance or None if mode not registered
        """
        deps = deps or {}

        # Try factory first
        if not simple and (factory := self._factories.get(mode)):
            return factory(deps)

        # Fall back to class instantiation
        handler_cls = self._simple_variants.get(mode) if simple else self._handlers.get(mode)
        if handler_cls:
            # Try to instantiate with deps, fall back to no-args
            # Note: Subclasses have varying __init__ signatures, so we catch TypeError
            try:
                return handler_cls(**deps)  # type: ignore[call-arg]
            except TypeError:
                return handler_cls()  # type: ignore[call-arg]

        return None

    def list_modes(self) -> list[AgentMode]:
        """List all registered modes."""
        return list(self._handlers.keys())

    def list_simple_modes(self) -> list[AgentMode]:
        """List modes with simple variants."""
        return list(self._simple_variants.keys())

    def is_registered(self, mode: AgentMode) -> bool:
        """Check if a mode is registered."""
        return mode in self._handlers or mode in self._factories

    def clear(self) -> None:
        """Clear all registrations. Mainly for testing."""
        self._handlers.clear()
        self._factories.clear()
        self._simple_variants.clear()


# Global registry instance
mode_registry = ModeRegistry()


class BaseModeHandler(ABC):
    """
    Abstract base class for mode handlers.

    Provides common utilities and enforces the mode handler interface.
    """

    def __init__(self, mode: AgentMode):
        """
        Initialize base mode handler.

        Args:
            mode: The mode this handler implements
        """
        self.mode = mode
        self.logger = logging.getLogger(f"{__name__}.{mode.value}")

    async def enter(self, context: ModeContext) -> None:
        """
        Called when entering this mode.

        Default implementation logs entry. Override for custom behavior.

        Args:
            context: Shared mode context
        """
        self.logger.info(f"Entering {self.mode.value} mode")
        self.logger.debug(f"Context: {len(context.current_files)} files, {len(context.current_symbols)} symbols")

    @abstractmethod
    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute mode logic.

        Must be implemented by subclasses.

        Args:
            task: Task to execute
            context: Shared mode context

        Returns:
            Result of execution
        """
        raise NotImplementedError

    async def exit(self, context: ModeContext) -> None:
        """
        Called when exiting this mode.

        Default implementation logs exit. Override for custom cleanup.

        Args:
            context: Shared mode context
        """
        self.logger.info(f"Exiting {self.mode.value} mode")

    def _create_result(
        self,
        data: Any,
        trigger: str | None = None,
        explanation: str = "",
        requires_approval: bool = False,
        **metadata,
    ) -> Result:
        """
        Helper to create Result objects.

        Args:
            data: Result data
            trigger: Optional trigger for next mode
            explanation: Human-readable explanation
            requires_approval: Whether approval is needed
            **metadata: Additional metadata

        Returns:
            Result object
        """
        return Result(
            mode=self.mode,
            data=data,
            trigger=trigger,
            explanation=explanation,
            requires_approval=requires_approval,
            metadata=metadata,
        )
