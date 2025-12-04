"""
PostgreSQL-backed RepoMapStore Implementation

[DEPRECATED] This storage backend is deprecated in favor of JsonFileRepoMapStore.

Uses asyncpg for async database operations with sync wrapper.

Migration Guide:
    Replace PostgresRepoMapStore with JsonFileRepoMapStore for simpler
    deployment without database dependencies.

    Before:
        store = PostgresRepoMapStore(connection_string="postgresql://...")

    After:
        from src.contexts.repo_structure.infrastructure.storage_json import JsonFileRepoMapStore
        store = JsonFileRepoMapStore(base_dir="./data/repomap")
"""

import asyncio
import json
import warnings
from datetime import datetime, timezone

try:
    import asyncpg
except ImportError:
    asyncpg = None

from src.contexts.repo_structure.infrastructure.models import RepoMapNode, RepoMapSnapshot


class PostgresRepoMapStore:
    """
    [DEPRECATED] PostgreSQL-backed RepoMapStore implementation.

    This class is deprecated. Use JsonFileRepoMapStore instead for:
    - Simpler deployment (no database required)
    - Faster development setup
    - Built-in in-memory caching

    Tables:
    - repomap_snapshots: snapshot metadata
    - repomap_nodes: node data (JSONB for flexibility)

    Requires asyncpg: pip install asyncpg
    """

    def __init__(self, connection_string: str):
        """
        Initialize PostgreSQL store.

        [DEPRECATED] Use JsonFileRepoMapStore instead.

        Args:
            connection_string: PostgreSQL connection string
                Format: postgresql://user:password@host:port/database
        """
        warnings.warn(
            "PostgresRepoMapStore is deprecated and will be removed in a future version. "
            "Use JsonFileRepoMapStore instead for simpler deployment without database dependencies.",
            DeprecationWarning,
            stacklevel=2,
        )

        if asyncpg is None:
            raise ImportError("asyncpg is required for PostgresRepoMapStore. Install with: pip install asyncpg")

        self.connection_string = connection_string
        self._pool: asyncpg.Pool | None = None
        self._loop = asyncio.new_event_loop()

    def __del__(self):
        """Cleanup connection pool on deletion."""
        if self._pool:
            self._loop.run_until_complete(self._pool.close())
        self._loop.close()

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
        return self._pool

    def _run_async(self, coro):
        """Run async coroutine in sync context."""
        return self._loop.run_until_complete(coro)

    # ========================================================================
    # Public API (sync wrappers)
    # ========================================================================

    def save_snapshot(self, snapshot: RepoMapSnapshot) -> None:
        """Save a complete RepoMap snapshot."""
        self._run_async(self._save_snapshot_async(snapshot))

    def get_snapshot(self, repo_id: str, snapshot_id: str) -> RepoMapSnapshot | None:
        """Get a snapshot by repo_id and snapshot_id."""
        return self._run_async(self._get_snapshot_async(repo_id, snapshot_id))

    def list_snapshots(self, repo_id: str) -> list[str]:
        """List all snapshot IDs for a repo."""
        return self._run_async(self._list_snapshots_async(repo_id))

    def delete_snapshot(self, repo_id: str, snapshot_id: str) -> None:
        """Delete a snapshot."""
        self._run_async(self._delete_snapshot_async(repo_id, snapshot_id))

    def get_node(self, node_id: str) -> RepoMapNode | None:
        """Get a single node by ID."""
        return self._run_async(self._get_node_async(node_id))

    def get_nodes_by_path(self, repo_id: str, snapshot_id: str, path: str) -> list[RepoMapNode]:
        """Get all nodes matching a path."""
        return self._run_async(self._get_nodes_by_path_async(repo_id, snapshot_id, path))

    def get_nodes_by_fqn(self, repo_id: str, snapshot_id: str, fqn: str) -> list[RepoMapNode]:
        """Get all nodes matching an FQN."""
        return self._run_async(self._get_nodes_by_fqn_async(repo_id, snapshot_id, fqn))

    def get_subtree(self, node_id: str) -> list[RepoMapNode]:
        """
        Get node and all descendants.

        Args:
            node_id: RepoMap node ID (format: repomap:{repo_id}:{snapshot_id}:{kind}:{path})

        Returns:
            List of RepoMapNode (root + all children recursively)
        """
        return self._run_async(self._get_subtree_async(node_id))

    def get_topk_by_importance(self, repo_id: str, snapshot_id: str, k: int = 100) -> list[RepoMapNode]:
        """Get top K nodes sorted by importance score."""
        return self._run_async(self._get_topk_by_importance_async(repo_id, snapshot_id, k))

    # ========================================================================
    # Async implementations
    # ========================================================================

    async def _save_snapshot_async(self, snapshot: RepoMapSnapshot) -> None:
        """Save snapshot to database."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            async with conn.transaction():
                # 1. Upsert snapshot metadata
                await conn.execute(
                    """
                    INSERT INTO repomap_snapshots (repo_id, snapshot_id, root_node_id, created_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (repo_id, snapshot_id)
                    DO UPDATE SET
                        root_node_id = EXCLUDED.root_node_id,
                        created_at = EXCLUDED.created_at
                    """,
                    snapshot.repo_id,
                    snapshot.snapshot_id,
                    snapshot.root_node_id,
                    datetime.now(timezone.utc),
                )

                # 2. Delete old nodes for this snapshot
                await conn.execute(
                    "DELETE FROM repomap_nodes WHERE repo_id = $1 AND snapshot_id = $2",
                    snapshot.repo_id,
                    snapshot.snapshot_id,
                )

                # 3. Bulk insert nodes
                if snapshot.nodes:
                    await conn.executemany(
                        """
                        INSERT INTO repomap_nodes (
                            id, repo_id, snapshot_id,
                            kind, name, path, fqn,
                            parent_id, children_ids, depth,
                            chunk_ids, graph_node_ids,
                            metrics, summary, attrs,
                            language, is_entrypoint, is_test
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                        """,
                        [self._node_to_row(node) for node in snapshot.nodes],
                    )

    async def _get_snapshot_async(self, repo_id: str, snapshot_id: str) -> RepoMapSnapshot | None:
        """Get snapshot from database."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            # 1. Get snapshot metadata
            meta = await conn.fetchrow(
                "SELECT * FROM repomap_snapshots WHERE repo_id = $1 AND snapshot_id = $2",
                repo_id,
                snapshot_id,
            )

            if not meta:
                return None

            # 2. Get all nodes
            rows = await conn.fetch(
                "SELECT * FROM repomap_nodes WHERE repo_id = $1 AND snapshot_id = $2",
                repo_id,
                snapshot_id,
            )

            nodes = [self._row_to_node(row) for row in rows]

            return RepoMapSnapshot(
                repo_id=meta["repo_id"],
                snapshot_id=meta["snapshot_id"],
                root_node_id=meta["root_node_id"],
                nodes=nodes,
                schema_version=meta["schema_version"],
                created_at=meta["created_at"].isoformat() if meta["created_at"] else None,
            )

    async def _list_snapshots_async(self, repo_id: str) -> list[str]:
        """List snapshot IDs for a repo."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT snapshot_id FROM repomap_snapshots WHERE repo_id = $1 ORDER BY created_at DESC",
                repo_id,
            )
            return [row["snapshot_id"] for row in rows]

    async def _delete_snapshot_async(self, repo_id: str, snapshot_id: str) -> None:
        """Delete snapshot (CASCADE will delete nodes automatically)."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM repomap_snapshots WHERE repo_id = $1 AND snapshot_id = $2",
                repo_id,
                snapshot_id,
            )

    async def _get_node_async(self, node_id: str) -> RepoMapNode | None:
        """Get single node by ID."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM repomap_nodes WHERE id = $1", node_id)
            return self._row_to_node(row) if row else None

    async def _get_nodes_by_path_async(self, repo_id: str, snapshot_id: str, path: str) -> list[RepoMapNode]:
        """Get nodes by path."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM repomap_nodes WHERE repo_id = $1 AND snapshot_id = $2 AND path = $3",
                repo_id,
                snapshot_id,
                path,
            )
            return [self._row_to_node(row) for row in rows]

    async def _get_nodes_by_fqn_async(self, repo_id: str, snapshot_id: str, fqn: str) -> list[RepoMapNode]:
        """Get nodes by FQN."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM repomap_nodes WHERE repo_id = $1 AND snapshot_id = $2 AND fqn = $3",
                repo_id,
                snapshot_id,
                fqn,
            )
            return [self._row_to_node(row) for row in rows]

    async def _get_subtree_async(self, node_id: str) -> list[RepoMapNode]:
        """Get node and all descendants using recursive CTE."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH RECURSIVE subtree AS (
                    -- Base case: root node
                    SELECT * FROM repomap_nodes WHERE id = $1

                    UNION ALL

                    -- Recursive case: children
                    SELECT n.*
                    FROM repomap_nodes n
                    INNER JOIN subtree s ON n.parent_id = s.id
                )
                SELECT * FROM subtree
                """,
                node_id,
            )
            return [self._row_to_node(row) for row in rows]

    async def _get_topk_by_importance_async(self, repo_id: str, snapshot_id: str, k: int = 100) -> list[RepoMapNode]:
        """Get top K nodes sorted by importance score (descending)."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM repomap_nodes
                WHERE repo_id = $1
                  AND snapshot_id = $2
                  AND (metrics->>'importance') IS NOT NULL
                ORDER BY (metrics->>'importance')::double precision DESC NULLS LAST
                LIMIT $3
                """,
                repo_id,
                snapshot_id,
                k,
            )
            return [self._row_to_node(row) for row in rows]

    # ========================================================================
    # Helper methods for serialization
    # ========================================================================

    def _node_to_row(self, node: RepoMapNode) -> tuple:
        """Convert RepoMapNode to database row tuple."""
        # asyncpg requires JSON strings for JSONB columns
        return (
            node.id,
            node.repo_id,
            node.snapshot_id,
            node.kind,
            node.name,
            node.path,
            node.fqn,
            node.parent_id,
            node.children_ids,
            node.depth,
            node.chunk_ids,
            node.graph_node_ids,
            json.dumps(node.metrics.model_dump()),  # Convert to JSON string
            json.dumps(
                {
                    "summary_title": node.summary_title,
                    "summary_body": node.summary_body,
                    "summary_tags": node.summary_tags,
                    "summary_text": node.summary_text,
                }
            ),
            json.dumps(node.attrs),  # Convert to JSON string
            node.language,
            node.is_entrypoint,
            node.is_test,
        )

    def _row_to_node(self, row: asyncpg.Record) -> RepoMapNode:
        """Convert database row to RepoMapNode."""
        from src.contexts.repo_structure.infrastructure.models import RepoMapMetrics

        # Parse JSONB fields - asyncpg returns them as strings
        metrics_dict = json.loads(row["metrics"]) if isinstance(row["metrics"], str) else row["metrics"]
        summary_dict = json.loads(row["summary"]) if isinstance(row["summary"], str) else row["summary"]
        attrs_dict = json.loads(row["attrs"]) if isinstance(row["attrs"], str) else row["attrs"]

        return RepoMapNode(
            id=row["id"],
            repo_id=row["repo_id"],
            snapshot_id=row["snapshot_id"],
            kind=row["kind"],
            name=row["name"],
            path=row["path"],
            fqn=row["fqn"],
            parent_id=row["parent_id"],
            children_ids=list(row["children_ids"]),
            depth=row["depth"],
            chunk_ids=list(row["chunk_ids"]),
            graph_node_ids=list(row["graph_node_ids"]),
            metrics=RepoMapMetrics(**metrics_dict),
            summary_title=summary_dict.get("summary_title"),
            summary_body=summary_dict.get("summary_body"),
            summary_tags=summary_dict.get("summary_tags", []),
            summary_text=summary_dict.get("summary_text"),
            language=row["language"],
            is_entrypoint=row["is_entrypoint"],
            is_test=row["is_test"],
            attrs=attrs_dict,
        )
