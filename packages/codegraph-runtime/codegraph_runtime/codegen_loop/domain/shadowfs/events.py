"""
ShadowFS Events (Domain Layer)

Immutable events for file system operations.

References:
    - Event Sourcing (Fowler, 2005)
    - Domain Events (Vernon, 2013)
    - RFC-018 Section 18
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ShadowFSEvent:
    """
    ShadowFS Event (Immutable)

    Emitted by ShadowFSCore on file operations.

    Event Types:
        - write: File written to overlay
        - delete: File deleted (tombstone)
        - commit: Transaction committed
        - rollback: Transaction rolled back

    Attributes:
        type: Event type
        path: File path (relative to workspace)
        txn_id: Transaction ID
        old_content: Previous content (None if new file)
        new_content: New content (None if deleted)
        timestamp: Unix timestamp (time.time())

    Invariants:
        - type must be valid
        - txn_id must not be empty
        - timestamp > 0

    Examples:
        >>> event = ShadowFSEvent(
        ...     type="write",
        ...     path="main.py",
        ...     txn_id="txn-123",
        ...     old_content=None,
        ...     new_content="def func(): pass",
        ...     timestamp=1234567890.0,
        ... )
        >>> event.type
        'write'
    """

    type: Literal["write", "delete", "commit", "rollback"]
    path: str
    txn_id: str
    old_content: str | None
    new_content: str | None
    timestamp: float

    def __post_init__(self):
        """
        Validate invariants

        Raises:
            ValueError: Invariant violation
        """
        if not self.txn_id:
            raise ValueError("txn_id must not be empty")

        if self.timestamp <= 0:
            raise ValueError(f"timestamp must be positive, got {self.timestamp}")

        # Type-specific validation
        if self.type == "write":
            if self.new_content is None:
                raise ValueError("write event must have new_content")

        elif self.type == "delete":
            if self.new_content is not None:
                raise ValueError("delete event must have new_content=None")

        elif self.type in ("commit", "rollback"):
            # path is not used for commit/rollback
            pass


class ConflictError(Exception):
    """
    Transaction Conflict Error

    Raised when optimistic concurrency conflict is detected.

    Attributes:
        message: Error message
        conflicts: List of conflicting paths
        txn_id: Transaction ID
    """

    def __init__(
        self,
        message: str,
        conflicts: list[str],
        txn_id: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.conflicts = conflicts
        self.txn_id = txn_id

    def __str__(self) -> str:
        return f"{self.message}: {', '.join(self.conflicts)}"


class CommitError(Exception):
    """
    Commit Error

    Raised when commit fails.

    Attributes:
        message: Error message
        recoverable: Whether error is recoverable
        cause: Original exception
    """

    def __init__(
        self,
        message: str,
        recoverable: bool,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.recoverable = recoverable
        self.cause = cause

    def __str__(self) -> str:
        return self.message
