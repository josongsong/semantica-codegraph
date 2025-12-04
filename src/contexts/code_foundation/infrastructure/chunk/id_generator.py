"""
Chunk ID Generator

Generates unique chunk IDs with collision resolution.

ID format: chunk:{repo_id}:{kind}:{fqn}[:{hash_suffix}]

Thread Safety (GAP G1):
    ChunkIdGenerator uses threading.Lock for thread-safe ID generation.
    This is critical when multiple workers process files concurrently.
"""

import threading
from dataclasses import dataclass


@dataclass
class ChunkIdContext:
    """
    Context for generating a chunk ID.

    Attributes:
        repo_id: Repository identifier
        kind: Chunk kind (repo/project/module/file/class/function)
        fqn: Fully qualified name (dotted notation)
        content_hash: Optional content hash for collision resolution
    """

    repo_id: str
    kind: str  # "repo" | "project" | "module" | "file" | "class" | "function"
    fqn: str
    content_hash: str | None = None


class ChunkIdGenerator:
    """
    Generates unique chunk IDs with collision resolution.

    Thread Safety (GAP G1):
        All public methods are thread-safe using threading.Lock.
        Safe for concurrent use from multiple threads/workers.

    Usage:
        gen = ChunkIdGenerator()
        ctx = ChunkIdContext(repo_id="myrepo", kind="function", fqn="main.foo")
        chunk_id = gen.generate(ctx)  # "chunk:myrepo:function:main.foo"

    If collision occurs, appends content_hash suffix:
        "chunk:myrepo:function:main.foo:a1b2c3d4"
    """

    def __init__(self):
        self._seen: set[str] = set()
        self._lock = threading.Lock()  # GAP G1: Thread safety

    def generate(self, ctx: ChunkIdContext) -> str:
        """
        Generate a unique chunk ID from context.

        Thread-safe: Uses lock to prevent race conditions.

        Args:
            ctx: Chunk ID context

        Returns:
            Unique chunk ID
        """
        base = f"chunk:{ctx.repo_id}:{ctx.kind}:{ctx.fqn}"

        with self._lock:
            # No collision - return base ID
            if base not in self._seen:
                self._seen.add(base)
                return base

            # Collision - append hash suffix
            suffix = (ctx.content_hash or "")[:8]
            candidate = f"{base}:{suffix}"
            self._seen.add(candidate)
            return candidate

    def reset(self):
        """Clear the seen set (for testing or incremental updates).

        Thread-safe: Uses lock for safe concurrent access.
        """
        with self._lock:
            self._seen.clear()

    def contains(self, chunk_id: str) -> bool:
        """Check if a chunk ID has already been generated.

        Thread-safe: Uses lock for safe concurrent access.

        Args:
            chunk_id: Chunk ID to check

        Returns:
            True if chunk ID exists in seen set
        """
        with self._lock:
            return chunk_id in self._seen
