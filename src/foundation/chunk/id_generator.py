"""
Chunk ID Generator

Generates unique chunk IDs with collision resolution.

ID format: chunk:{repo_id}:{kind}:{fqn}[:{hash_suffix}]
"""

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

    Usage:
        gen = ChunkIdGenerator()
        ctx = ChunkIdContext(repo_id="myrepo", kind="function", fqn="main.foo")
        chunk_id = gen.generate(ctx)  # "chunk:myrepo:function:main.foo"

    If collision occurs, appends content_hash suffix:
        "chunk:myrepo:function:main.foo:a1b2c3d4"
    """

    def __init__(self):
        self._seen: set[str] = set()

    def generate(self, ctx: ChunkIdContext) -> str:
        """
        Generate a unique chunk ID from context.

        Args:
            ctx: Chunk ID context

        Returns:
            Unique chunk ID
        """
        base = f"chunk:{ctx.repo_id}:{ctx.kind}:{ctx.fqn}"

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
        """Clear the seen set (for testing or incremental updates)."""
        self._seen.clear()
