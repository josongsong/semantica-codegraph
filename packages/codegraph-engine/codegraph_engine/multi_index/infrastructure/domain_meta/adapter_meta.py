"""
Domain Metadata Index Adapter

Implements DomainMetaIndexPort for searching documentation and architectural artifacts.

Architecture:
    IndexDocument (docs) → PostgreSQL (full-text) → Domain Search → SearchHit

Features:
    - README, CHANGELOG, LICENSE search
    - Architecture Decision Records (ADR) search
    - API documentation search
    - Full-text search with ranking
    - Document type filtering

Schema:
    Table: domain_documents
        - id (primary key)
        - repo_id
        - snapshot_id
        - chunk_id
        - file_path
        - symbol_id
        - doc_type (readme, adr, api_spec, changelog, etc.)
        - title
        - content
        - content_vector (tsvector for full-text search)
        - metadata (JSON)

Example Queries:
    - "authentication flow" → matches ADR on auth architecture
    - "API endpoints" → matches API documentation
    - "installation guide" → matches README sections
"""

from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument, SearchHit

logger = get_logger(__name__)


class DomainMetaIndex:
    """
    Domain metadata search implementation using PostgreSQL full-text search.

    Specialized for documentation, ADRs, and architectural artifacts.

    Usage:
        domain = DomainMetaIndex(postgres_store=postgres)
        await domain.index(repo_id, snapshot_id, domain_docs)
        hits = await domain.search(repo_id, snapshot_id, "authentication", limit=10)
    """

    def __init__(self, postgres_store: Any):
        """
        Initialize PostgreSQL domain metadata index.

        Args:
            postgres_store: PostgresStore instance with async connection pool
        """
        self.postgres = postgres_store
        self._table_name = "domain_documents"
        self._initialized = False

    # ============================================================
    # DomainMetaIndexPort Implementation
    # ============================================================

    async def index(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """
        Full index creation for domain documents.

        Only indexes documents identified as domain/documentation.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances (should be pre-filtered for domain docs)
        """
        await self._ensure_schema()

        # Clear existing data for this repo+snapshot
        await self._clear_snapshot(repo_id, snapshot_id)

        # Convert IndexDocuments to domain records
        domain_records = []
        for doc in docs:
            doc_type = self._infer_doc_type(doc)
            title = self._extract_title(doc)

            # Extract metadata safely from IndexDocument (no fqn/node_type/importance_score)
            tags = doc.tags or {}
            domain_records.append(
                {
                    "repo_id": repo_id,
                    "snapshot_id": snapshot_id,
                    "chunk_id": doc.chunk_id,
                    "file_path": doc.file_path,
                    "symbol_id": doc.symbol_id,
                    "doc_type": doc_type,
                    "title": title,
                    "content": doc.content or "",
                    "metadata": {
                        "symbol_name": doc.symbol_name,
                        "kind": tags.get("kind", "unknown"),
                        "repomap_score": tags.get("repomap_score", "0.0"),
                        "language": doc.language,
                    },
                }
            )

        if domain_records:
            await self._bulk_insert(domain_records)
            logger.info(f"Domain index created {len(domain_records)} documents for {repo_id}:{snapshot_id}")
        else:
            logger.warning(f"No domain documents to index for {repo_id}:{snapshot_id}")

    async def upsert(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """
        Incremental upsert for domain documents.

        Deletes existing documents for updated chunks and inserts new ones.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances to upsert
        """
        await self._ensure_schema()

        # Delete existing documents for these chunks
        chunk_ids = [doc.chunk_id for doc in docs]
        await self._delete_chunks(repo_id, snapshot_id, chunk_ids)

        # Convert and insert new documents
        domain_records = []
        for doc in docs:
            doc_type = self._infer_doc_type(doc)
            title = self._extract_title(doc)

            # Extract metadata safely from IndexDocument (no fqn/node_type/importance_score)
            tags = doc.tags or {}
            domain_records.append(
                {
                    "repo_id": repo_id,
                    "snapshot_id": snapshot_id,
                    "chunk_id": doc.chunk_id,
                    "file_path": doc.file_path,
                    "symbol_id": doc.symbol_id,
                    "doc_type": doc_type,
                    "title": title,
                    "content": doc.content or "",
                    "metadata": {
                        "symbol_name": doc.symbol_name,
                        "kind": tags.get("kind", "unknown"),
                        "repomap_score": tags.get("repomap_score", "0.0"),
                        "language": doc.language,
                    },
                }
            )

        if domain_records:
            await self._bulk_insert(domain_records)
            logger.info(f"Domain index upserted {len(domain_records)} documents for {repo_id}:{snapshot_id}")

    async def delete(self, repo_id: str, snapshot_id: str, doc_ids: list[str]) -> None:
        """
        Delete domain documents by chunk IDs.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            doc_ids: List of chunk_ids to delete
        """
        await self._ensure_schema()
        await self._delete_chunks(repo_id, snapshot_id, doc_ids)
        logger.info(f"Domain index deleted {len(doc_ids)} documents for {repo_id}:{snapshot_id}")

    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Full-text search for domain documents.

        Uses PostgreSQL ts_rank for relevance scoring.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Natural language query
            limit: Maximum results

        Returns:
            List of SearchHit with source="domain", ranked by relevance
        """
        await self._ensure_schema()

        if not query.strip():
            return []

        # Convert query to tsquery (simple English full-text search)
        # Use plainto_tsquery for simple tokenization
        sql = f"""
        SELECT
            chunk_id,
            file_path,
            symbol_id,
            doc_type,
            title,
            content,
            metadata,
            ts_rank(content_vector, plainto_tsquery('english', $1)) AS score
        FROM {self._table_name}
        WHERE repo_id = $2
          AND snapshot_id = $3
          AND content_vector @@ plainto_tsquery('english', $1)
        ORDER BY score DESC, title ASC
        LIMIT $4
        """

        try:
            async with self.postgres.pool.acquire() as conn:
                rows = await conn.fetch(
                    sql,
                    query,
                    repo_id,
                    snapshot_id,
                    limit,
                )

            hits = []
            for row in rows:
                # Truncate content for preview (first 200 chars)
                content_preview = row["content"][:200] + "..." if len(row["content"]) > 200 else row["content"]

                hit = SearchHit(
                    chunk_id=row["chunk_id"],
                    file_path=row["file_path"],
                    symbol_id=row["symbol_id"],
                    score=float(row["score"]),
                    source="domain",
                    metadata={
                        "doc_type": row["doc_type"],
                        "title": row["title"],
                        "preview": content_preview,
                        "match_type": "full_text",
                        **(row["metadata"] or {}),
                    },
                )
                hits.append(hit)

            logger.info(f"Domain search returned {len(hits)} results for query: {query}")
            return hits

        except Exception as e:
            logger.error(f"Domain search failed for repo {repo_id}: {e}", exc_info=True)
            return []

    # ============================================================
    # Private Helpers - Schema Management
    # ============================================================

    async def _ensure_schema(self) -> None:
        """
        Ensure domain_documents table and indexes exist.

        Creates:
        - domain_documents table
        - GIN index on content_vector for full-text search
        - Indexes on repo_id, snapshot_id, doc_type
        """
        if self._initialized:
            return

        # Ensure PostgreSQL pool is initialized
        await self.postgres._ensure_pool()

        async with self.postgres.pool.acquire() as conn:
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
                    doc_type TEXT NOT NULL,
                    title TEXT,
                    content TEXT NOT NULL,
                    content_vector TSVECTOR,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """
            )

            # Create indexes
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_domain_repo_snapshot
                ON {self._table_name}(repo_id, snapshot_id)
            """
            )

            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_domain_chunk
                ON {self._table_name}(chunk_id)
            """
            )

            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_domain_type
                ON {self._table_name}(doc_type)
            """
            )

            # Create GIN index for full-text search
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_domain_content_fts
                ON {self._table_name}
                USING GIN (content_vector)
            """
            )

            logger.info("Domain index schema initialized")
            self._initialized = True

    async def _clear_snapshot(self, repo_id: str, snapshot_id: str) -> None:
        """Delete all domain documents for a repo+snapshot."""
        async with self.postgres.pool.acquire() as conn:
            _ = await conn.execute(
                f"DELETE FROM {self._table_name} WHERE repo_id = $1 AND snapshot_id = $2",
                repo_id,
                snapshot_id,
            )
            logger.debug(f"Cleared domain index for {repo_id}:{snapshot_id}")

    async def _delete_chunks(self, repo_id: str, snapshot_id: str, chunk_ids: list[str]) -> None:
        """Delete domain documents for specific chunks."""
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
        """
        Bulk insert domain document records.

        Automatically generates tsvector from title + content.
        """
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
                r["doc_type"],
                r["title"],
                r["content"],
                r["metadata"],
            )
            for r in records
        ]

        async with self.postgres.pool.acquire() as conn:
            await conn.executemany(
                f"""
                INSERT INTO {self._table_name}
                (
                    repo_id, snapshot_id, chunk_id, file_path,
                    symbol_id, doc_type, title, content,
                    content_vector, metadata
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    to_tsvector('english', COALESCE($7, '') || ' ' || COALESCE($8, '')),
                    $9
                )
                """,
                values,
            )

    # ============================================================
    # Private Helpers - Document Classification
    # ============================================================

    def _infer_doc_type(self, doc: IndexDocument) -> str:
        """
        Infer document type from file path and content.

        Returns:
            Document type: readme, adr, api_spec, changelog, license, contributing, other
        """
        if not doc.file_path:
            return "other"

        path_lower = doc.file_path.lower()

        # Check filename patterns
        if "readme" in path_lower:
            return "readme"
        elif "changelog" in path_lower or "history" in path_lower:
            return "changelog"
        elif "license" in path_lower:
            return "license"
        elif "contributing" in path_lower or "code_of_conduct" in path_lower:
            return "contributing"
        elif "adr" in path_lower or "decision" in path_lower:
            return "adr"
        elif "api" in path_lower or "openapi" in path_lower or "swagger" in path_lower:
            return "api_spec"
        elif path_lower.endswith(".md"):
            return "markdown_doc"
        elif path_lower.endswith(".rst"):
            return "rst_doc"
        elif path_lower.endswith(".adoc"):
            return "asciidoc"
        else:
            return "other"

    def _extract_title(self, doc: IndexDocument) -> str:
        """
        Extract document title from content or file path.

        Strategy:
        1. Look for markdown H1 header (# Title)
        2. Use first line if it looks like a title
        3. Fallback to file name
        """
        if not doc.content:
            return doc.file_path or "Untitled"

        lines = doc.content.split("\n")

        # Look for markdown H1
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()

        # Use first non-empty line as title
        for line in lines[:5]:
            line = line.strip()
            if line and len(line) < 100:  # Reasonable title length
                return line

        # Fallback to file name
        if doc.file_path:
            from pathlib import Path

            return Path(doc.file_path).stem

        return "Untitled"


# ============================================================
# Convenience Factory
# ============================================================


def create_domain_meta_index(postgres_store: Any) -> DomainMetaIndex:
    """
    Factory function for DomainMetaIndex.

    Args:
        postgres_store: PostgresStore instance

    Returns:
        Configured DomainMetaIndex instance
    """
    return DomainMetaIndex(postgres_store=postgres_store)
