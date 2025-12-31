"""
Event Bus (Infrastructure Layer)

Simple event distribution for ShadowFS plugins.

Thread-Safety: asyncio-safe
Error Isolation: Plugin failures don't affect others
Performance: Parallel execution via asyncio.gather

References:
    - Observer Pattern (GoF)
    - RFC-018 Section 18
"""

import asyncio
import logging
from typing import Protocol

from ...domain.shadowfs.events import ShadowFSEvent

logger = logging.getLogger(__name__)


class ShadowFSPlugin(Protocol):
    """
    ShadowFS Plugin Interface

    Plugins react to ShadowFS events without mutating Core state.

    Thread-Safety:
        - on_event() called outside Core lock
        - Internal synchronization is plugin's responsibility

    Error Handling:
        - Regular exceptions: logged and isolated
        - ValidationError: propagated (blocks commit)

    Examples:
        >>> class MyPlugin:
        ...     async def on_event(self, event: ShadowFSEvent) -> None:
        ...         print(f"Event: {event.type}")
    """

    async def on_event(self, event: ShadowFSEvent) -> None:
        """
        Handle ShadowFS event

        Args:
            event: ShadowFSEvent

        Side Effects:
            Plugin-specific (e.g., IR caching, indexing)

        Raises:
            ValidationError: Critical error (propagated to caller)
            Exception: Non-critical error (logged and isolated)
        """
        ...


class EventBus:
    """
    Event Distribution Bus

    Responsibilities:
        - Plugin registration
        - Event emission (async, parallel)
        - Error isolation

    Performance:
        - Non-blocking (plugins run concurrently)
        - O(n) where n = number of plugins

    Thread-Safety:
        - Thread-safe (asyncio)
        - Registration not thread-safe (call before emit)

    Examples:
        >>> bus = EventBus()
        >>> bus.register(MyPlugin())
        >>> await bus.emit(ShadowFSEvent(...))
    """

    def __init__(self):
        """Initialize empty event bus"""
        self._plugins: list[ShadowFSPlugin] = []

    def register(self, plugin: ShadowFSPlugin) -> None:
        """
        Register plugin

        Args:
            plugin: ShadowFSPlugin instance

        Thread-Safety:
            NOT thread-safe (register before emit)

        Examples:
            >>> bus.register(IRSyncPlugin())
        """
        if not hasattr(plugin, "on_event"):
            raise TypeError(f"Plugin must implement on_event, got {type(plugin)}")

        self._plugins.append(plugin)

        logger.info(f"Plugin registered: {type(plugin).__name__}")

    async def emit(self, event: ShadowFSEvent) -> None:
        """
        Emit event to all plugins

        Execution:
            - Parallel (asyncio.gather)
            - Error isolation (one failure doesn't affect others)
            - ValidationError propagated (blocks commit)

        Args:
            event: ShadowFSEvent

        Raises:
            ValidationError: From plugin (propagated)

        Performance:
            O(n) where n = number of plugins (parallel)

        Examples:
            >>> await bus.emit(ShadowFSEvent(
            ...     type="write",
            ...     path="main.py",
            ...     txn_id="txn-123",
            ...     old_content=None,
            ...     new_content="code",
            ...     timestamp=time.time(),
            ... ))
        """
        if not self._plugins:
            return

        # Create tasks
        tasks = [self._call_plugin(plugin, event) for plugin in self._plugins]

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for ValidationError (must propagate)
        for result in results:
            if isinstance(result, Exception):
                # Check if it's a validation error
                if type(result).__name__ == "ValidationError":
                    raise result

    async def _call_plugin(
        self,
        plugin: ShadowFSPlugin,
        event: ShadowFSEvent,
    ) -> None:
        """
        Call plugin with error isolation

        Args:
            plugin: Plugin instance
            event: Event to process

        Raises:
            ValidationError: Propagated
            Exception: Logged and suppressed
        """
        try:
            await plugin.on_event(event)

        except Exception as e:
            # ValidationError → propagate
            if type(e).__name__ == "ValidationError":
                raise

            # Other errors → log and isolate
            logger.error(
                f"Plugin {type(plugin).__name__} failed on {event.type}: {e}",
                exc_info=True,
                extra={
                    "plugin": type(plugin).__name__,
                    "event_type": event.type,
                    "event_path": event.path,
                    "event_txn_id": event.txn_id,
                },
            )

            # Don't raise (error isolation)
