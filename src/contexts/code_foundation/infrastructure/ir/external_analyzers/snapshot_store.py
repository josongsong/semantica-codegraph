"""
Semantic Snapshot Store

RFC-023 M1: PostgreSQL storage for Pyright semantic snapshots

Provides:
- Save/load snapshots to/from PostgreSQL
- Query latest snapshot by project
- Simple caching
- Compression support (Migration 009) - dual-write/dual-read strategy
"""

import gzip
import json
from typing import TYPE_CHECKING

from src.contexts.code_foundation.infrastructure.ir.external_analyzers.snapshot import PyrightSemanticSnapshot

if TYPE_CHECKING:
    from src.infra.storage.postgres import PostgresStore
from src.common.observability import get_logger

logger = get_logger(__name__)


class SemanticSnapshotStore:
    """
    RFC-023 M1: Semantic Snapshot Storage

    Stores Pyright semantic snapshots in PostgreSQL as JSONB.

    Usage:
        store = SemanticSnapshotStore(postgres_store)
        await store.save_snapshot(snapshot)
        latest = await store.load_latest_snapshot("my-project")
    """

    # SQL for auto-migration (table creation)
    _CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS pyright_semantic_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            data JSONB,
            data_compressed BYTEA
        );

        -- Index for project queries
        CREATE INDEX IF NOT EXISTS idx_pyright_snapshots_project_timestamp
        ON pyright_semantic_snapshots (project_id, timestamp DESC);

        -- Index for cleanup queries
        CREATE INDEX IF NOT EXISTS idx_pyright_snapshots_project_id
        ON pyright_semantic_snapshots (project_id);
    """

    def __init__(self, postgres_store: "PostgresStore", auto_migrate: bool = True):
        """
        Initialize semantic snapshot store.

        Args:
            postgres_store: PostgresStore instance
            auto_migrate: If True, auto-create tables on first operation (default: True)
        """
        self.postgres = postgres_store
        self._cache: dict[str, PyrightSemanticSnapshot] = {}
        self._auto_migrate = auto_migrate
        self._migrated = False

    async def _ensure_tables(self) -> None:
        """
        Ensure required tables exist (auto-migration).

        Called before first database operation if auto_migrate=True.
        Uses CREATE TABLE IF NOT EXISTS for idempotency.
        """
        if not self._auto_migrate or self._migrated:
            return

        try:
            async with self.postgres.pool.acquire() as conn:
                await conn.execute(self._CREATE_TABLE_SQL)
            self._migrated = True
            logger.info("SemanticSnapshotStore: tables created/verified")
        except Exception as e:
            logger.warning(f"SemanticSnapshotStore: auto-migration failed: {e}")
            # Don't raise - let the actual operation fail with a better error
            self._migrated = True  # Avoid repeated attempts

    async def save_snapshot(self, snapshot: PyrightSemanticSnapshot) -> None:
        """
        Save snapshot to PostgreSQL with compression.

        Args:
            snapshot: PyrightSemanticSnapshot to save

        Table: pyright_semantic_snapshots
        Columns: snapshot_id, project_id, timestamp, data (JSONB), data_compressed (BYTEA)

        Migration 009: Dual-write strategy
        - Writes both 'data' (JSONB) and 'data_compressed' (BYTEA)
        - Ensures zero-downtime migration
        - Future migration will remove 'data' column after full transition
        """
        await self._ensure_tables()

        data_dict = snapshot.to_dict()
        data_json = json.dumps(data_dict)

        # Compress data (gzip level 6 = good balance of speed/compression)
        data_compressed = gzip.compress(data_json.encode("utf-8"), compresslevel=6)

        # Insert into database (dual-write)
        query = """
            INSERT INTO pyright_semantic_snapshots
            (snapshot_id, project_id, timestamp, data, data_compressed)
            VALUES ($1, $2, NOW(), $3::jsonb, $4)
            ON CONFLICT (snapshot_id) DO UPDATE
            SET data = EXCLUDED.data,
                data_compressed = EXCLUDED.data_compressed,
                timestamp = EXCLUDED.timestamp
        """

        async with self.postgres.pool.acquire() as conn:
            await conn.execute(
                query,
                snapshot.snapshot_id,
                snapshot.project_id,
                data_json,
                data_compressed,
            )

        # Update cache
        cache_key = f"{snapshot.project_id}:latest"
        self._cache[cache_key] = snapshot
        self._cache[snapshot.snapshot_id] = snapshot

    async def load_latest_snapshot(self, project_id: str) -> PyrightSemanticSnapshot | None:
        """
        Load latest snapshot for a project.

        Args:
            project_id: Project identifier

        Returns:
            Latest PyrightSemanticSnapshot or None if not found

        Migration 009: Dual-read strategy
        - Prefers 'data_compressed' (BYTEA) if available
        - Falls back to 'data' (JSONB) for backward compatibility
        """
        # Check cache
        cache_key = f"{project_id}:latest"
        if cache_key in self._cache:
            return self._cache[cache_key]

        await self._ensure_tables()

        # Query database (fetch both columns)
        query = """
            SELECT snapshot_id, project_id, data, data_compressed
            FROM pyright_semantic_snapshots
            WHERE project_id = $1
            ORDER BY timestamp DESC
            LIMIT 1
        """

        async with self.postgres.pool.acquire() as conn:
            row = await conn.fetchrow(query, project_id)

        if not row:
            return None

        # Deserialize (prefer compressed)
        data = self._deserialize_snapshot_data(row)
        snapshot = PyrightSemanticSnapshot.from_dict(data)

        # Update cache
        self._cache[cache_key] = snapshot
        self._cache[snapshot.snapshot_id] = snapshot

        return snapshot

    async def load_snapshot_by_id(self, snapshot_id: str) -> PyrightSemanticSnapshot | None:
        """
        Load specific snapshot by ID.

        Args:
            snapshot_id: Snapshot identifier

        Returns:
            PyrightSemanticSnapshot or None if not found

        Migration 009: Dual-read strategy
        - Prefers 'data_compressed' (BYTEA) if available
        - Falls back to 'data' (JSONB) for backward compatibility
        """
        # Check cache
        if snapshot_id in self._cache:
            return self._cache[snapshot_id]

        await self._ensure_tables()

        # Query database (fetch both columns)
        query = """
            SELECT snapshot_id, project_id, data, data_compressed
            FROM pyright_semantic_snapshots
            WHERE snapshot_id = $1
        """

        async with self.postgres.pool.acquire() as conn:
            row = await conn.fetchrow(query, snapshot_id)

        if not row:
            return None

        # Deserialize (prefer compressed)
        data = self._deserialize_snapshot_data(row)
        snapshot = PyrightSemanticSnapshot.from_dict(data)

        # Update cache
        self._cache[snapshot_id] = snapshot

        return snapshot

    async def list_snapshots(self, project_id: str, limit: int = 10) -> list[dict[str, str]]:
        """
        List snapshots for a project (most recent first).

        Args:
            project_id: Project identifier
            limit: Maximum number of snapshots to return

        Returns:
            List of dicts with snapshot_id, project_id, timestamp

        Note: Migration 008 removes created_at column (redundant with timestamp)
        """
        await self._ensure_tables()

        query = """
            SELECT snapshot_id, project_id, timestamp
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
            }
            for row in rows
        ]

    async def delete_old_snapshots(self, project_id: str, keep_count: int = 5) -> int:
        """
        Delete old snapshots, keeping only the most recent N.

        Args:
            project_id: Project identifier
            keep_count: Number of snapshots to keep

        Returns:
            Number of snapshots deleted
        """
        await self._ensure_tables()

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

    def _deserialize_snapshot_data(self, row) -> dict:
        """
        Deserialize snapshot data from database row.

        Migration 009: Dual-read strategy
        - Prefers 'data_compressed' (BYTEA) if available
        - Falls back to 'data' (JSONB) for backward compatibility

        Args:
            row: Database row with 'data' and 'data_compressed' columns

        Returns:
            Deserialized snapshot data as dict
        """
        # Prefer compressed data (Migration 009)
        if row["data_compressed"] is not None:
            # Decompress BYTEA → JSON string → dict
            compressed_bytes = row["data_compressed"]
            decompressed_json = gzip.decompress(compressed_bytes).decode("utf-8")
            return json.loads(decompressed_json)

        # Fallback to JSONB (legacy or pre-migration data)
        data = row["data"]
        if isinstance(data, str):
            return json.loads(data)
        return data
