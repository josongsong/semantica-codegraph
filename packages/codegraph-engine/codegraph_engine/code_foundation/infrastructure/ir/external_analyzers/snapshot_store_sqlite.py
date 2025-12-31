"""
Semantic Snapshot Store - SQLite Implementation (RFC-052 Compatible)

RFC-052: MCP Service Layer Architecture
SQLite-based snapshot store for local/test environments.

Differences from PostgreSQL version:
- No JSONB type (use TEXT with JSON)
- No TIMESTAMPTZ (use TEXT with ISO format)
- Simplified schema
"""

import gzip
import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.snapshot import (
    PyrightSemanticSnapshot,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class SemanticSnapshotStoreSQLite:
    """
    SQLite-based semantic snapshot store.

    Compatible with RFC-052 snapshot stickiness.
    """

    # Schema (SQLite-compatible)
    _CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS pyright_semantic_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            data_compressed BLOB
        );
        
        CREATE INDEX IF NOT EXISTS idx_pyright_snapshots_project_timestamp
        ON pyright_semantic_snapshots (project_id, timestamp DESC);
    """

    def __init__(self, db_path: Path | str):
        """
        Initialize snapshot store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._cache: dict[str, PyrightSemanticSnapshot] = {}

        # Initialize schema
        self._init_schema()

        logger.info("semantic_snapshot_store_sqlite_initialized", db_path=str(self.db_path))

    def _init_schema(self) -> None:
        """Create tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self._CREATE_TABLE_SQL)
            conn.commit()

    async def save_snapshot(self, snapshot: PyrightSemanticSnapshot) -> None:
        """
        Save snapshot.

        Args:
            snapshot: PyrightSemanticSnapshot
        """
        data_dict = snapshot.to_dict()
        data_json = json.dumps(data_dict)
        data_compressed = gzip.compress(data_json.encode("utf-8"), compresslevel=6)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pyright_semantic_snapshots
                (snapshot_id, project_id, data_compressed)
                VALUES (?, ?, ?)
                """,
                (snapshot.snapshot_id, snapshot.project_id, data_compressed),
            )
            conn.commit()

        # Update cache
        cache_key = f"{snapshot.project_id}:latest"
        self._cache[cache_key] = snapshot
        self._cache[snapshot.snapshot_id] = snapshot

    async def load_latest_snapshot(self, project_id: str) -> PyrightSemanticSnapshot | None:
        """Load latest snapshot"""
        # Check cache
        cache_key = f"{project_id}:latest"
        if cache_key in self._cache:
            return self._cache[cache_key]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT snapshot_id, project_id, data_compressed
                FROM pyright_semantic_snapshots
                WHERE project_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (project_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        # Decompress
        data_compressed = row["data_compressed"]
        decompressed_json = gzip.decompress(data_compressed).decode("utf-8")
        data = json.loads(decompressed_json)

        snapshot = PyrightSemanticSnapshot.from_dict(data)

        # Update cache
        self._cache[cache_key] = snapshot
        self._cache[snapshot.snapshot_id] = snapshot

        return snapshot

    async def load_snapshot_by_id(self, snapshot_id: str) -> PyrightSemanticSnapshot | None:
        """Load specific snapshot"""
        # Check cache
        if snapshot_id in self._cache:
            return self._cache[snapshot_id]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT snapshot_id, project_id, data_compressed
                FROM pyright_semantic_snapshots
                WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        # Decompress
        data_compressed = row["data_compressed"]
        decompressed_json = gzip.decompress(data_compressed).decode("utf-8")
        data = json.loads(decompressed_json)

        snapshot = PyrightSemanticSnapshot.from_dict(data)

        # Update cache
        self._cache[snapshot_id] = snapshot

        return snapshot
