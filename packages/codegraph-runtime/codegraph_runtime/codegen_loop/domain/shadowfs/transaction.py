"""
Transaction Domain Models (SOTA-Level Fixed)

TransactionState: Per-transaction isolated state
FileSnapshot: File state at transaction start

THREAD-SAFETY: RLock for all mutations
TYPE-SAFETY: Protocol-based typing
VALIDATION: Strict invariants + duck typing checks
"""

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    # Avoid circular import at runtime
    pass


class IRDocumentProtocol(Protocol):
    """
    Protocol for IRDocument duck typing

    Allows type checking without hard dependency on IR module.
    Any object with these attributes is acceptable.
    """

    @property
    def nodes(self) -> list: ...

    @property
    def edges(self) -> list: ...

    @property
    def file_path(self) -> str: ...


@dataclass(frozen=True)
class FileSnapshot:
    """
    File snapshot (immutable value object)

    Captures file state at transaction start for drift detection.

    Attributes:
        path: Relative file path
        mtime: Modification time (Unix timestamp)
        size: File size in bytes
        content_hash: SHA-256 hash of content (lowercase hex)

    Invariants:
        - path is non-empty
        - mtime > 0
        - size >= 0
        - content_hash is 64 lowercase hex characters (SHA-256)

    Security:
        - Hash must be canonical form (lowercase)
        - Strict hex validation

    Thread-Safety: Immutable (frozen=True)

    Examples:
        >>> snapshot = FileSnapshot(
        ...     path="src/main.py",
        ...     mtime=1704067200.0,
        ...     size=1024,
        ...     content_hash="abc123" + "0" * 58
        ... )
    """

    path: str
    mtime: float
    size: int
    content_hash: str

    def __post_init__(self):
        """
        Validate invariants (SOTA-Level Strict)

        Raises:
            ValueError: For any invariant violation
        """
        # Invariant 1: Non-empty path
        if not self.path:
            raise ValueError("path must be non-empty")

        # Invariant 2: Positive mtime
        if self.mtime <= 0:
            raise ValueError(f"mtime must be > 0, got {self.mtime}")

        # Invariant 3: Non-negative size
        if self.size < 0:
            raise ValueError(f"size must be >= 0, got {self.size}")

        # Invariant 4: SHA-256 length (CRITICAL FIX)
        if len(self.content_hash) != 64:
            raise ValueError(f"content_hash must be 64 hex chars (SHA-256), got {len(self.content_hash)}")

        # SECURITY: Strict hex validation (CRITICAL FIX)
        try:
            int(self.content_hash, 16)
        except ValueError as e:
            raise ValueError(f"content_hash must be hex string: {e}")

        # SECURITY: Canonical form (lowercase) (CRITICAL FIX)
        if self.content_hash != self.content_hash.lower():
            raise ValueError(
                f"content_hash must be lowercase hex (canonical form). "
                f"Got: {self.content_hash}, expected: {self.content_hash.lower()}"
            )

    @classmethod
    def from_content(cls, path: str, mtime: float, size: int, content: str) -> "FileSnapshot":
        """
        Create snapshot from file content

        Args:
            path: File path
            mtime: Modification time
            size: File size
            content: File content

        Returns:
            FileSnapshot with computed hash
        """
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return cls(path=path, mtime=mtime, size=size, content_hash=content_hash)


@dataclass
class TransactionState:
    """
    Transaction state (mutable aggregate root)

    Per-transaction isolated state for MVCC.

    Attributes:
        txn_id: Unique transaction ID
        ir_cache: Cached IRDocument objects
        file_snapshots: File snapshots for drift detection
        created_at: Transaction creation timestamp
        _symbol_cache: Lazy-built symbol table (FQN → file_path)
        _cache_built: Flag indicating if symbol cache is built
        _lock: Thread lock for mutations

    Invariants:
        - txn_id is valid UUID
        - created_at > 0
        - ir_cache values have 'nodes' attribute (duck typing)

    Business Rules:
        - Symbol cache is built lazily on first access
        - Symbol cache is invalidated when IR cache changes
        - Transaction is isolated (no shared state)

    Thread-Safety: RLock protects all mutations (CRITICAL FIX)

    References:
        - MVCC (Bernstein & Goodman, 1983)
        - Software Transactional Memory (Herlihy & Moss, 1993)

    Examples:
        >>> txn = TransactionState()
        >>> txn.txn_id
        'a1b2c3d4-...'
        >>> txn.add_ir("main.py", ir_document)
        >>> txn.invalidate_symbol_cache()
    """

    txn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ir_cache: dict[str, IRDocumentProtocol] = field(default_factory=dict)
    file_snapshots: dict[str, FileSnapshot] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    _symbol_cache: dict[str, str] | None = field(default=None, init=False, repr=False)
    _cache_built: bool = field(default=False, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self):
        """
        Validate invariants

        Raises:
            ValueError: For any invariant violation
        """
        # Validate UUID format
        try:
            uuid.UUID(self.txn_id)
        except ValueError as e:
            raise ValueError(f"txn_id must be valid UUID: {e}")

        if self.created_at <= 0:
            raise ValueError(f"created_at must be > 0, got {self.created_at}")

    def add_ir(self, file_path: str, ir_document: IRDocumentProtocol) -> None:
        """
        Add parsed IR to cache (Thread-Safe)

        Args:
            file_path: File path
            ir_document: IRDocument instance

        Side Effects:
            - Invalidates symbol cache

        Raises:
            ValueError: If file_path is empty or ir_document is None
            TypeError: If ir_document doesn't conform to protocol

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            if not file_path:
                raise ValueError("file_path must be non-empty")

            if ir_document is None:
                raise ValueError("ir_document must not be None")

            # TYPE-SAFETY: Duck typing validation (CRITICAL FIX)
            if not hasattr(ir_document, "nodes"):
                raise TypeError(
                    f"ir_document must have 'nodes' attribute (IRDocumentProtocol), got {type(ir_document)}"
                )

            if not hasattr(ir_document, "edges"):
                raise TypeError(
                    f"ir_document must have 'edges' attribute (IRDocumentProtocol), got {type(ir_document)}"
                )

            self.ir_cache[file_path] = ir_document
            self._invalidate_symbol_cache_unsafe()

    def remove_ir(self, file_path: str) -> None:
        """
        Remove IR from cache (Thread-Safe)

        Args:
            file_path: File path

        Side Effects:
            - Invalidates symbol cache

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            if file_path in self.ir_cache:
                del self.ir_cache[file_path]
                self._invalidate_symbol_cache_unsafe()

    def get_ir(self, file_path: str) -> IRDocumentProtocol | None:
        """
        Get cached IR (Thread-Safe Read-Only)

        Args:
            file_path: File path

        Returns:
            IRDocument or None

        Warning:
            Returns reference to internal cache.
            Caller MUST NOT modify the returned object.

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            return self.ir_cache.get(file_path)

    def has_ir(self, file_path: str) -> bool:
        """
        Check if IR is cached (Thread-Safe)

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            return file_path in self.ir_cache

    def invalidate_symbol_cache(self) -> None:
        """
        Invalidate symbol table cache (Thread-Safe Public API)

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            self._invalidate_symbol_cache_unsafe()

    def _invalidate_symbol_cache_unsafe(self) -> None:
        """
        Invalidate symbol table cache (Unsafe - must hold lock)

        Thread-Safety: Caller must hold self._lock
        """
        self._symbol_cache = None
        self._cache_built = False

    def get_symbol_cache(self) -> dict[str, str] | None:
        """
        Get symbol cache if built (Thread-Safe)

        Returns:
            Dict[FQN, file_path] or None

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            return self._symbol_cache.copy() if self._symbol_cache else None

    def set_symbol_cache(self, cache: dict[str, str]) -> None:
        """
        Set symbol cache (Thread-Safe)

        Args:
            cache: Symbol table dict

        Raises:
            ValueError: If cache is not dict

        Thread-Safety: Protected by RLock (CRITICAL FIX)
        """
        with self._lock:
            if not isinstance(cache, dict):
                raise ValueError(f"cache must be dict, got {type(cache)}")

            self._symbol_cache = cache.copy()  # Defensive copy
            self._cache_built = True

    def is_symbol_cache_built(self) -> bool:
        """
        Check if symbol cache is built (Thread-Safe)

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            return self._cache_built

    def add_snapshot(self, snapshot: FileSnapshot) -> None:
        """
        Add file snapshot (Thread-Safe)

        Args:
            snapshot: FileSnapshot instance

        Raises:
            TypeError: If snapshot is not FileSnapshot

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            if not isinstance(snapshot, FileSnapshot):
                raise TypeError(f"snapshot must be FileSnapshot instance, got {type(snapshot)}")

            self.file_snapshots[snapshot.path] = snapshot

    def get_snapshot(self, file_path: str) -> FileSnapshot | None:
        """
        Get file snapshot (Thread-Safe)

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            return self.file_snapshots.get(file_path)

    def has_snapshot(self, file_path: str) -> bool:
        """
        Check if snapshot exists (Thread-Safe)

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            return file_path in self.file_snapshots

    def clear(self) -> None:
        """
        Clear all state (Thread-Safe)

        Used for rollback and cleanup.

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            self.ir_cache.clear()
            self.file_snapshots.clear()
            self._invalidate_symbol_cache_unsafe()

    @property
    def age_seconds(self) -> float:
        """
        Transaction age in seconds (Thread-Safe)

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            return time.time() - self.created_at

    @property
    def num_cached_files(self) -> int:
        """
        Number of cached IR files (Thread-Safe)

        Thread-Safety: Protected by RLock
        """
        with self._lock:
            return len(self.ir_cache)
