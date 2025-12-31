"""
ShadowFS Plugin Port (Application Layer)

Defines Plugin interface for ShadowFS extension.

Architecture:
    - Application Layer (Port)
    - Infrastructure Layer implements this port

References:
    - RFC-018 Section 18 (Extension Points)
"""

from typing import Protocol

from ...domain.shadowfs.events import ShadowFSEvent


class ShadowFSPlugin(Protocol):
    """
    ShadowFS Plugin Interface (Port)

    Plugins extend ShadowFS behavior without modifying Core.

    Responsibilities:
        - React to ShadowFS events
        - NO Core state mutation (Core handles that)
        - Error isolation (plugin failure doesn't affect Core)

    Thread-Safety:
        - on_event() called outside Core lock
        - Internal synchronization is plugin's responsibility

    Error Handling:
        - Regular exceptions: logged and isolated
        - ValidationError: propagated (can block commit)

    Examples:
        >>> class MyPlugin:
        ...     async def on_event(self, event: ShadowFSEvent) -> None:
        ...         print(f"Event: {event.type} at {event.path}")

        >>> bus.register(MyPlugin())
    """

    async def on_event(self, event: ShadowFSEvent) -> None:
        """
        Handle ShadowFS event

        Args:
            event: ShadowFSEvent (write/delete/commit/rollback)

        Side Effects:
            Plugin-specific (e.g., IR caching, indexing)

        Raises:
            ValidationError: Critical error (propagated, blocks commit)
            Exception: Non-critical error (logged, isolated)

        Performance:
            Should be fast (<100ms per event)
            Blocking operations should be avoided

        Examples:
            >>> await plugin.on_event(ShadowFSEvent(
            ...     type="write",
            ...     path="main.py",
            ...     txn_id="txn-123",
            ...     old_content=None,
            ...     new_content="def func(): pass",
            ...     timestamp=time.time(),
            ... ))
        """
        ...
