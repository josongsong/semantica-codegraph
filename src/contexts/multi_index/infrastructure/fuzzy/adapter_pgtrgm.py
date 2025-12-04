"""
PostgreSQL pg_trgm-based Fuzzy Index Adapter

Implements FuzzyIndexPort using PostgreSQL trigram similarity for fuzzy identifier matching.

Architecture:
    IndexDocument → PostgreSQL (pg_trgm) → Fuzzy Search → SearchHit

Features:
    - Typo-tolerant identifier search
    - Partial name matching
    - Trigram similarity scoring
    - Fast GIN index-based lookups

Schema:
    Table: fuzzy_identifiers
        - id (primary key)
        - repo_id
        - snapshot_id
        - chunk_id
        - file_path
        - symbol_id
        - identifier (indexed with GIN trgm_ops)
        - kind (function, class, variable, etc.)
        - metadata (JSON)

Example Queries:
    - "HybridRetr" → matches "HybridRetriever"
    - "idx_repo" → matches "index_repository"
    - "get_usr" → matches "get_user_by_id"
"""

from typing import Any

from src.common.observability import get_logger
from src.contexts.multi_index.infrastructure.common.documents import IndexDocument, SearchHit

logger = get_logger(__name__)


class PostgresFuzzyIndex:
    """
    Fuzzy search implementation using PostgreSQL pg_trgm extension.

    Uses trigram similarity for typo-tolerant identifier matching.

    Usage:
        fuzzy = PostgresFuzzyIndex(postgres_store=postgres)
        await fuzzy.index(repo_id, snapshot_id, index_docs)
        hits = await fuzzy.search(repo_id, snapshot_id, "get_usr", limit=10)
    """

    def __init__(self, postgres_store: Any):
        """
        Initialize PostgreSQL fuzzy index.

        Args:
            postgres_store: PostgresStore instance with async connection pool
        """
        self.postgres = postgres_store
        self._table_name = "fuzzy_identifiers"
        self._initialized = False

    # ============================================================
    # FuzzyIndexPort Implementation
    # ============================================================

    async def index(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """
        Full index creation for fuzzy search.

        Extracts identifiers from IndexDocuments and stores them with trigram indexes.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances
        """
        await self._ensure_schema()

        # Clear existing data for this repo+snapshot
        await self._clear_snapshot(repo_id, snapshot_id)

        # Extract identifiers from documents
        import json

        identifier_records = []
        for doc in docs:
            identifiers = self._extract_identifiers(doc)
            # Get fqn and node_type with fallbacks for IndexDocument compatibility
            fqn = getattr(doc, "fqn", None) or getattr(doc, "symbol_id", None) or ""
            tags = getattr(doc, "tags", {}) or {}
            node_type = getattr(doc, "node_type", None) or tags.get("kind", "unknown")
            for identifier, kind in identifiers:
                identifier_records.append(
                    {
                        "repo_id": repo_id,
                        "snapshot_id": snapshot_id,
                        "chunk_id": doc.chunk_id,
                        "file_path": doc.file_path,
                        "symbol_id": doc.symbol_id,
                        "identifier": identifier,
                        "kind": kind,
                        "metadata": json.dumps(
                            {
                                "fqn": fqn,
                                "node_type": node_type,
                            }
                        ),
                    }
                )

        if identifier_records:
            await self._bulk_insert(identifier_records)
            logger.info(f"Fuzzy index created {len(identifier_records)} identifiers for {repo_id}:{snapshot_id}")
        else:
            logger.warning(f"No identifiers extracted for fuzzy indexing: {repo_id}:{snapshot_id}")

    async def upsert(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """
        Incremental upsert for fuzzy search.

        Deletes existing identifiers for updated chunks and inserts new ones.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances to upsert
        """
        await self._ensure_schema()

        # Delete existing identifiers for these chunks
        chunk_ids = [doc.chunk_id for doc in docs]
        await self._delete_chunks(repo_id, snapshot_id, chunk_ids)

        # Extract and insert new identifiers
        import json

        identifier_records = []
        for doc in docs:
            identifiers = self._extract_identifiers(doc)
            # Get fqn and node_type with fallbacks for IndexDocument compatibility
            fqn = getattr(doc, "fqn", None) or getattr(doc, "symbol_id", None) or ""
            tags = getattr(doc, "tags", {}) or {}
            node_type = getattr(doc, "node_type", None) or tags.get("kind", "unknown")
            for identifier, kind in identifiers:
                identifier_records.append(
                    {
                        "repo_id": repo_id,
                        "snapshot_id": snapshot_id,
                        "chunk_id": doc.chunk_id,
                        "file_path": doc.file_path,
                        "symbol_id": doc.symbol_id,
                        "identifier": identifier,
                        "kind": kind,
                        "metadata": json.dumps(
                            {
                                "fqn": fqn,
                                "node_type": node_type,
                            }
                        ),
                    }
                )

        if identifier_records:
            await self._bulk_insert(identifier_records)
            logger.info(f"Fuzzy index upserted {len(identifier_records)} identifiers for {repo_id}:{snapshot_id}")

    async def delete(self, repo_id: str, snapshot_id: str, doc_ids: list[str]) -> None:
        """
        Delete identifiers by chunk IDs.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            doc_ids: List of chunk_ids to delete
        """
        await self._ensure_schema()
        await self._delete_chunks(repo_id, snapshot_id, doc_ids)
        logger.info(f"Fuzzy index deleted {len(doc_ids)} chunks for {repo_id}:{snapshot_id}")

    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Fuzzy search for identifiers using trigram similarity.

        Uses pg_trgm similarity operator (%) and similarity() function.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Partial or misspelled identifier
            limit: Maximum results

        Returns:
            List of SearchHit with source="fuzzy", scored by similarity
        """
        await self._ensure_schema()

        # Normalize query (lowercase for case-insensitive matching)
        normalized_query = query.strip().lower()

        if not normalized_query:
            return []

        # PostgreSQL query using pg_trgm similarity
        sql = f"""
        SELECT
            chunk_id,
            file_path,
            symbol_id,
            identifier,
            kind,
            metadata,
            similarity(LOWER(identifier), $1) AS score
        FROM {self._table_name}
        WHERE repo_id = $2
          AND snapshot_id = $3
          AND LOWER(identifier) % $1  -- Trigram similarity operator
        ORDER BY score DESC, identifier ASC
        LIMIT $4
        """

        try:
            async with self.postgres.pool.acquire() as conn:
                rows = await conn.fetch(
                    sql,
                    normalized_query,
                    repo_id,
                    snapshot_id,
                    limit,
                )

            hits = []
            for row in rows:
                hit = SearchHit(
                    chunk_id=row["chunk_id"],
                    file_path=row["file_path"],
                    symbol_id=row["symbol_id"],
                    score=float(row["score"]),
                    source="fuzzy",
                    metadata={
                        "identifier": row["identifier"],
                        "kind": row["kind"],
                        "match_type": "trigram",
                        **(row["metadata"] or {}),
                    },
                )
                hits.append(hit)

            logger.info(f"Fuzzy search returned {len(hits)} results for query: {query}")
            return hits

        except Exception as e:
            logger.error(f"Fuzzy search failed for repo {repo_id}: {e}", exc_info=True)
            return []

    # ============================================================
    # Private Helpers - Schema Management
    # ============================================================

    async def _ensure_schema(self) -> None:
        """
        Ensure fuzzy_identifiers table and indexes exist.

        Creates:
        - pg_trgm extension (if not exists)
        - fuzzy_identifiers table
        - GIN index on identifier using trgm_ops
        """
        if self._initialized:
            return

        # Ensure PostgreSQL pool is initialized
        await self.postgres._ensure_pool()

        async with self.postgres.pool.acquire() as conn:
            # Create pg_trgm extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

            # Create table
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table_name} (
                    id SERIAL PRIMARY KEY,
                    repo_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    file_path TEXT,
                    symbol_id TEXT,
                    identifier TEXT NOT NULL,
                    kind TEXT,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """
            )

            # Create indexes
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_fuzzy_repo_snapshot
                ON {self._table_name}(repo_id, snapshot_id)
            """
            )

            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_fuzzy_chunk
                ON {self._table_name}(chunk_id)
            """
            )

            # Create GIN trigram index for fuzzy matching
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_fuzzy_identifier_trgm
                ON {self._table_name}
                USING GIN (identifier gin_trgm_ops)
            """
            )

            logger.info("Fuzzy index schema initialized")
            self._initialized = True

    async def _clear_snapshot(self, repo_id: str, snapshot_id: str) -> None:
        """Delete all identifiers for a repo+snapshot."""
        async with self.postgres.pool.acquire() as conn:
            _ = await conn.execute(
                f"DELETE FROM {self._table_name} WHERE repo_id = $1 AND snapshot_id = $2",
                repo_id,
                snapshot_id,
            )
            logger.debug(f"Cleared fuzzy index for {repo_id}:{snapshot_id}")

    async def _delete_chunks(self, repo_id: str, snapshot_id: str, chunk_ids: list[str]) -> None:
        """Delete identifiers for specific chunks."""
        if not chunk_ids:
            return

        async with self.postgres.pool.acquire() as conn:
            await conn.execute(
                f"""
                DELETE FROM {self._table_name}
                WHERE repo_id = $1 AND snapshot_id = $2 AND chunk_id = ANY($3)
                """,
                repo_id,
                snapshot_id,
                chunk_ids,
            )

    async def _bulk_insert(self, records: list[dict[str, Any]]) -> None:
        """Bulk insert identifier records."""
        if not records:
            return

        # Prepare values for executemany
        values = [
            (
                r["repo_id"],
                r["snapshot_id"],
                r["chunk_id"],
                r["file_path"],
                r["symbol_id"],
                r["identifier"],
                r["kind"],
                r["metadata"],
            )
            for r in records
        ]

        async with self.postgres.pool.acquire() as conn:
            await conn.executemany(
                f"""
                INSERT INTO {self._table_name}
                (repo_id, snapshot_id, chunk_id, file_path, symbol_id, identifier, kind, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                values,
            )

    # ============================================================
    # Private Helpers - Identifier Extraction
    # ============================================================

    def _extract_identifiers(self, doc: IndexDocument) -> list[tuple[str, str]]:
        """
        Extract searchable identifiers from IndexDocument.

        Returns:
            List of (identifier, kind) tuples

        Extraction strategy:
        1. Primary: symbol_name (from metadata)
        2. FQN parts (e.g., "mymodule.MyClass.my_method" → ["MyClass", "my_method"])
        3. Class names, function names from node_type
        """
        identifiers = []

        # Extract from symbol_name (highest priority)
        # Check doc.symbol_name first, then fall back to tags/attrs
        symbol_name = getattr(doc, "symbol_name", None)
        if not symbol_name:
            # Fallback to tags or attrs for backward compatibility
            tags = getattr(doc, "tags", {}) or {}
            attrs = getattr(doc, "attrs", {}) or {}
            symbol_name = tags.get("symbol_name") or attrs.get("symbol_name")
        if symbol_name:
            node_type = getattr(doc, "node_type", None) or "unknown"
            identifiers.append((symbol_name, node_type))

        # Extract from FQN parts (symbol_id can be FQN-like)
        fqn = getattr(doc, "fqn", None) or getattr(doc, "symbol_id", None) or ""
        if fqn:
            parts = fqn.split(".")
            for part in parts:
                if part and part not in [p[0] for p in identifiers]:
                    identifiers.append((part, "fqn_part"))

        # Extract from chunk content (if contains def/class keywords)
        # This is a simple heuristic - can be enhanced
        if doc.content:
            # Simple pattern matching for Python identifiers
            import re

            patterns = [
                r"def\s+(\w+)",  # function names
                r"class\s+(\w+)",  # class names
                r"(\w+)\s*=",  # variable assignments
            ]
            for pattern in patterns:
                matches = re.findall(pattern, doc.content)
                for match in matches:
                    if match and len(match) > 2 and match not in [p[0] for p in identifiers]:
                        identifiers.append((match, "extracted"))

        # Deduplicate while preserving order
        seen = set()
        unique_identifiers = []
        for ident, kind in identifiers:
            if ident.lower() not in seen:
                seen.add(ident.lower())
                unique_identifiers.append((ident, kind))

        return unique_identifiers[:10]  # Limit to top 10 identifiers per document


# ============================================================
# Convenience Factory
# ============================================================


def create_postgres_fuzzy_index(postgres_store: Any) -> PostgresFuzzyIndex:
    """
    Factory function for PostgresFuzzyIndex.

    Args:
        postgres_store: PostgresStore instance

    Returns:
        Configured PostgresFuzzyIndex instance
    """
    return PostgresFuzzyIndex(postgres_store=postgres_store)
