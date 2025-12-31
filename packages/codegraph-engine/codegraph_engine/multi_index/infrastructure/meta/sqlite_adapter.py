"""
SQLite Meta Adapter (RFC-020 Phase 6)

Replaces PostgreSQL for metadata storage.

Features:
- Embedded database (no server)
- Write queue for concurrency
- Lightweight for local development
"""

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.infrastructure.meta.write_queue import SQLiteWriteQueue

logger = get_logger(__name__)


class SQLiteMetaAdapter:
    """
    SQLite-based metadata storage (RFC-020)

    Replaces: PostgreSQL metadata tables

    Architecture:
    - Uses SQLiteWriteQueue for concurrency
    - Implements same interface as PostgresAdapter
    """

    def __init__(self, db_path: str):
        """
        Initialize SQLite meta adapter

        Args:
            db_path: SQLite database file path
        """
        self.write_queue = SQLiteWriteQueue(db_path)
        self._init_schema()

    def _init_schema(self):
        """
        Initialize database schema (RFC-020 Phase 6)

        Tables:
        1. metadata: repo-level key-value store
        2. correlation: chunk-chunk correlation scores

        Schema matches PostgreSQL tables for compatibility
        """
        db = self.write_queue.db

        # Table 1: metadata (repo-level key-value)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(repo_id, key)
            )
            """
        )

        # Index for fast lookup
        db.execute("CREATE INDEX IF NOT EXISTS idx_metadata_repo_key ON metadata(repo_id, key)")

        # Table 2: correlation (chunk-chunk similarity)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS chunk_correlation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id_1 TEXT NOT NULL,
                chunk_id_2 TEXT NOT NULL,
                score REAL NOT NULL,
                correlation_type TEXT DEFAULT 'semantic',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chunk_id_1, chunk_id_2, correlation_type)
            )
            """
        )

        # Index for fast correlation lookup
        db.execute("CREATE INDEX IF NOT EXISTS idx_correlation_chunk1 ON chunk_correlation(chunk_id_1)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_correlation_chunk2 ON chunk_correlation(chunk_id_2)")

        db.commit()

        logger.info("SQLite meta schema initialized")

    async def upsert_metadata(self, repo_id: str, key: str, value: str):
        """
        Upsert metadata

        Args:
            repo_id: Repository ID
            key: Metadata key
            value: Metadata value
        """
        query = """
        INSERT INTO metadata (repo_id, key, value, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT (repo_id, key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """
        await self.write_queue.execute(query, (repo_id, key, value))

    async def get_metadata(self, repo_id: str, key: str) -> str | None:
        """
        Get metadata value

        Args:
            repo_id: Repository ID
            key: Metadata key

        Returns:
            Value or None if not found
        """
        # Read queries don't need write queue
        cursor = self.write_queue.db.execute("SELECT value FROM metadata WHERE repo_id = ? AND key = ?", (repo_id, key))
        row = cursor.fetchone()
        return row[0] if row else None

    async def upsert_correlation(
        self, chunk_id_1: str, chunk_id_2: str, score: float, correlation_type: str = "semantic"
    ):
        """
        Upsert chunk correlation

        Args:
            chunk_id_1: First chunk ID
            chunk_id_2: Second chunk ID
            score: Correlation score (0.0-1.0)
            correlation_type: Type of correlation (semantic, structural, etc)
        """
        query = """
        INSERT INTO chunk_correlation (chunk_id_1, chunk_id_2, score, correlation_type, created_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT (chunk_id_1, chunk_id_2, correlation_type) DO UPDATE SET
            score = excluded.score,
            created_at = CURRENT_TIMESTAMP
        """
        await self.write_queue.execute(query, (chunk_id_1, chunk_id_2, score, correlation_type))

    async def get_correlations(self, chunk_id: str, min_score: float = 0.7, limit: int = 10) -> list[tuple[str, float]]:
        """
        Get correlated chunks

        Args:
            chunk_id: Source chunk ID
            min_score: Minimum correlation score
            limit: Maximum results

        Returns:
            List of (chunk_id, score) tuples
        """
        cursor = self.write_queue.db.execute(
            """
            SELECT chunk_id_2, score FROM chunk_correlation
            WHERE chunk_id_1 = ? AND score >= ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (chunk_id, min_score, limit),
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]
