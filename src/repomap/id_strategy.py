"""
RepoMap ID Strategy

Stable ID generation for RepoMap nodes.

ID format: repomap:{repo_id}:{snapshot_id}:{kind}:{identifier}
"""

import hashlib
from dataclasses import dataclass


@dataclass
class RepoMapIdContext:
    """Context for RepoMap ID generation."""

    repo_id: str
    snapshot_id: str
    kind: str  # repo, project, module, dir, file, class, function, symbol
    identifier: str  # path or FQN


class RepoMapIdGenerator:
    """
    Generate stable IDs for RepoMap nodes.

    IDs are deterministic and based on:
    - repo_id
    - snapshot_id (commit, branch, or workspace)
    - kind (node type)
    - identifier (path or FQN)

    Examples:
        repomap:myrepo:main:repo:root
        repomap:myrepo:main:dir:src/indexing
        repomap:myrepo:main:file:src/indexing/builder.py
        repomap:myrepo:main:function:src.indexing.builder.build_index
    """

    @staticmethod
    def generate(ctx: RepoMapIdContext) -> str:
        """
        Generate RepoMap node ID.

        Args:
            ctx: ID generation context

        Returns:
            Stable node ID
        """
        # Sanitize identifier (replace / with . for consistency)
        identifier = ctx.identifier.replace("/", ".").replace("\\", ".")

        # For very long identifiers, use hash suffix
        if len(identifier) > 200:
            hash_suffix = hashlib.sha1(identifier.encode()).hexdigest()[:8]
            identifier = identifier[:180] + "..." + hash_suffix

        return f"repomap:{ctx.repo_id}:{ctx.snapshot_id}:{ctx.kind}:{identifier}"

    @staticmethod
    def generate_repo_root(repo_id: str, snapshot_id: str) -> str:
        """Generate ID for repo root node."""
        return RepoMapIdGenerator.generate(
            RepoMapIdContext(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                kind="repo",
                identifier="root",
            )
        )

    @staticmethod
    def generate_dir(repo_id: str, snapshot_id: str, dir_path: str) -> str:
        """Generate ID for directory node."""
        return RepoMapIdGenerator.generate(
            RepoMapIdContext(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                kind="dir",
                identifier=dir_path,
            )
        )

    @staticmethod
    def generate_file(repo_id: str, snapshot_id: str, file_path: str) -> str:
        """Generate ID for file node."""
        return RepoMapIdGenerator.generate(
            RepoMapIdContext(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                kind="file",
                identifier=file_path,
            )
        )

    @staticmethod
    def generate_symbol(repo_id: str, snapshot_id: str, fqn: str, kind: str = "symbol") -> str:
        """Generate ID for symbol node (class/function)."""
        return RepoMapIdGenerator.generate(
            RepoMapIdContext(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                kind=kind,
                identifier=fqn,
            )
        )
