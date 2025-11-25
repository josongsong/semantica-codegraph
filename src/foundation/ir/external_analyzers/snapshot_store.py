"""
Semantic Snapshot Store

RFC-023 M1: PostgreSQL storage for Pyright semantic snapshots

Provides:
- Save/load snapshots to/from PostgreSQL
- Query latest snapshot by project
- Simple caching
"""


from src.infra.storage.postgres import PostgresStore

from .snapshot import PyrightSemanticSnapshot


class SemanticSnapshotStore:
    """
    RFC-023 M1: Semantic Snapshot Storage

    Stores Pyright semantic snapshots in PostgreSQL as JSONB.

    Usage:
        store = SemanticSnapshotStore(postgres_store)
        await store.save_snapshot(snapshot)
        latest = await store.load_latest_snapshot("my-project")
    """

    def __init__(self, postgres_store: PostgresStore):
        """
        Initialize semantic snapshot store.

        Args:
            postgres_store: PostgresStore instance
        """
        self.postgres = postgres_store
        self._cache: dict[str, PyrightSemanticSnapshot] = {}

    async def save_snapshot(self, snapshot: PyrightSemanticSnapshot) -> None:
        """
        Save snapshot to PostgreSQL.

        Args:
            snapshot: PyrightSemanticSnapshot to save

        Table: pyright_semantic_snapshots
        Columns: snapshot_id, project_id, timestamp, data (JSONB)
        """
        # Serialize to JSON string (asyncpg expects string for JSONB)
        import json
        data_dict = snapshot.to_dict()
        data_json = json.dumps(data_dict)

        # Insert into database
        query = """
            INSERT INTO pyright_semantic_snapshots (snapshot_id, project_id, timestamp, data)
            VALUES ($1, $2, NOW(), $3::jsonb)
            ON CONFLICT (snapshot_id) DO UPDATE
            SET data = EXCLUDED.data, timestamp = EXCLUDED.timestamp
        """

        async with self.postgres.pool.acquire() as conn:
            await conn.execute(
                query,
                snapshot.snapshot_id,
                snapshot.project_id,
                data_json,
            )

        # Update cache
        cache_key = f"{snapshot.project_id}:latest"
        self._cache[cache_key] = snapshot
        self._cache[snapshot.snapshot_id] = snapshot

    async def load_latest_snapshot(
        self, project_id: str
    ) -> PyrightSemanticSnapshot | None:
        """
        Load latest snapshot for a project.

        Args:
            project_id: Project identifier

        Returns:
            Latest PyrightSemanticSnapshot or None if not found
        """
        # Check cache
        cache_key = f"{project_id}:latest"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Query database
        query = """
            SELECT snapshot_id, project_id, data
            FROM pyright_semantic_snapshots
            WHERE project_id = $1
            ORDER BY timestamp DESC
            LIMIT 1
        """

        async with self.postgres.pool.acquire() as conn:
            row = await conn.fetchrow(query, project_id)

        if not row:
            return None

        # Deserialize (data is already a dict from JSONB, but may be string)
        import json
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)

        snapshot = PyrightSemanticSnapshot.from_dict(data)

        # Update cache
        self._cache[cache_key] = snapshot
        self._cache[snapshot.snapshot_id] = snapshot

        return snapshot

    async def load_snapshot_by_id(
        self, snapshot_id: str
    ) -> PyrightSemanticSnapshot | None:
        """
        Load specific snapshot by ID.

        Args:
            snapshot_id: Snapshot identifier

        Returns:
            PyrightSemanticSnapshot or None if not found
        """
        # Check cache
        if snapshot_id in self._cache:
            return self._cache[snapshot_id]

        # Query database
        query = """
            SELECT snapshot_id, project_id, data
            FROM pyright_semantic_snapshots
            WHERE snapshot_id = $1
        """

        async with self.postgres.pool.acquire() as conn:
            row = await conn.fetchrow(query, snapshot_id)

        if not row:
            return None

        # Deserialize (data is already a dict from JSONB, but may be string)
        import json
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)

        snapshot = PyrightSemanticSnapshot.from_dict(data)

        # Update cache
        self._cache[snapshot_id] = snapshot

        return snapshot

    async def list_snapshots(
        self, project_id: str, limit: int = 10
    ) -> list[dict[str, str]]:
        """
        List snapshots for a project (most recent first).

        Args:
            project_id: Project identifier
            limit: Maximum number of snapshots to return

        Returns:
            List of dicts with snapshot_id, project_id, timestamp
        """
        query = """
            SELECT snapshot_id, project_id, timestamp, created_at
            FROM pyright_semantic_snapshots
            WHERE project_id = $1
            ORDER BY timestamp DESC
            LIMIT $2
        """

        async with self.postgres.pool.acquire() as conn:
            rows = await conn.fetch(query, project_id, limit)

        return [
            {
                "snapshot_id": row["snapshot_id"],
                "project_id": row["project_id"],
                "timestamp": row["timestamp"].isoformat(),
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]

    async def delete_old_snapshots(
        self, project_id: str, keep_count: int = 5
    ) -> int:
        """
        Delete old snapshots, keeping only the most recent N.

        Args:
            project_id: Project identifier
            keep_count: Number of snapshots to keep

        Returns:
            Number of snapshots deleted
        """
        query = """
            DELETE FROM pyright_semantic_snapshots
            WHERE snapshot_id IN (
                SELECT snapshot_id
                FROM pyright_semantic_snapshots
                WHERE project_id = $1
                ORDER BY timestamp DESC
                OFFSET $2
            )
        """

        async with self.postgres.pool.acquire() as conn:
            result = await conn.execute(query, project_id, keep_count)

        # Parse result (e.g., "DELETE 3")
        deleted_count = int(result.split()[-1]) if result else 0

        # Clear cache for this project
        cache_key = f"{project_id}:latest"
        if cache_key in self._cache:
            del self._cache[cache_key]

        return deleted_count

    def clear_cache(self):
        """Clear in-memory cache"""
        self._cache.clear()
