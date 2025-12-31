"""
IR Document Store v2 - Storage Only (SOLID S)

Refactored from GOD class (534 lines) to focused store (150 lines).

책임:
- IR Document 저장/조회 (DB operations)
- Migration

NOT responsible for:
- Serialization (IRSerializer)
- Validation (IRSerializer)
"""

import json
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

from .ir_serializer import IRSerializer

if TYPE_CHECKING:
    from codegraph_shared.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


class IRDocumentStore:
    """
    IR Document PostgreSQL Store (Single Responsibility).

    SOLID:
    - S: Storage만 담당
    - O: 확장 가능 (새 backend)
    - L: 교체 가능
    - I: 최소 인터페이스 (save, load)
    - D: IRSerializer에 의존 (abstraction)
    """

    _CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS ir_documents (
            repo_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            node_count INTEGER DEFAULT 0,
            edge_count INTEGER DEFAULT 0,
            data JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (repo_id, snapshot_id)
        );

        CREATE INDEX IF NOT EXISTS idx_ir_documents_repo_id
        ON ir_documents (repo_id);

        CREATE INDEX IF NOT EXISTS idx_ir_documents_created_at
        ON ir_documents (created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_ir_documents_data_gin
        ON ir_documents USING GIN (data);
    """

    def __init__(self, postgres_store: "PostgresStore", auto_migrate: bool = True):
        """
        Initialize with dependencies.

        Args:
            postgres_store: PostgresStore instance
            auto_migrate: Auto-create table
        """
        self.postgres_store = postgres_store
        self._serializer = IRSerializer()  # DI

        if auto_migrate:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._migrate())
                else:
                    loop.run_until_complete(self._migrate())
            except Exception as e:
                logger.error("migration_failed", error=str(e))

    async def _migrate(self) -> None:
        """Create table if not exists (supports SQLite and PostgreSQL)"""
        try:
            # Check if using SQLiteStore or PostgresStore
            if hasattr(self.postgres_store, "pool"):
                # PostgreSQL with connection pool
                async with self.postgres_store.pool.acquire() as conn:
                    await conn.execute(self._CREATE_TABLE_SQL)
            else:
                # SQLite (direct execution)
                # Convert PostgreSQL DDL to SQLite compatible
                sqlite_ddl = self._CREATE_TABLE_SQL.replace("JSONB", "TEXT")
                sqlite_ddl = sqlite_ddl.replace("TIMESTAMPTZ", "TEXT")
                await self.postgres_store.execute(sqlite_ddl)

            logger.info("ir_document_store_migrated")
        except Exception as e:
            logger.error("migration_error", error=str(e), exc_info=True)

    async def save(self, ir_doc: IRDocument) -> bool:
        """
        Save IR Document (supports SQLite and PostgreSQL).

        Delegation: IRSerializer.serialize_ir_document()

        Args:
            ir_doc: IRDocument

        Returns:
            True if success
        """
        try:
            # Delegate serialization (SOLID S + D)
            data = self._serialize_complete(ir_doc)

            # Check backend type
            if hasattr(self.postgres_store, "pool"):
                # PostgreSQL with connection pool
                async with self.postgres_store.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO ir_documents (repo_id, snapshot_id, schema_version, node_count, edge_count, data)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (repo_id, snapshot_id)
                        DO UPDATE SET
                            schema_version = EXCLUDED.schema_version,
                            node_count = EXCLUDED.node_count,
                            edge_count = EXCLUDED.edge_count,
                            data = EXCLUDED.data,
                            updated_at = NOW()
                        """,
                        ir_doc.repo_id,
                        ir_doc.snapshot_id,
                        ir_doc.schema_version,
                        len(ir_doc.nodes),
                        len(ir_doc.edges),
                        json.dumps(data),
                    )
            else:
                # SQLite (direct execution)
                await self.postgres_store.execute(
                    """
                    INSERT INTO ir_documents (repo_id, snapshot_id, schema_version, node_count, edge_count, data)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (repo_id, snapshot_id)
                    DO UPDATE SET
                        schema_version = excluded.schema_version,
                        node_count = excluded.node_count,
                        edge_count = excluded.edge_count,
                        data = excluded.data,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    ir_doc.repo_id,
                    ir_doc.snapshot_id,
                    ir_doc.schema_version,
                    len(ir_doc.nodes),
                    len(ir_doc.edges),
                    json.dumps(data),
                )

            logger.info(
                "ir_document_saved",
                repo_id=ir_doc.repo_id,
                snapshot_id=ir_doc.snapshot_id,
                nodes=len(ir_doc.nodes),
                edges=len(ir_doc.edges),
            )
            return True

        except Exception as e:
            logger.error("save_failed", repo_id=ir_doc.repo_id, error=str(e), exc_info=True)
            return False

    async def load(self, repo_id: str, snapshot_id: str) -> IRDocument | None:
        """
        Load IR Document (supports SQLite and PostgreSQL).

        Delegation: IRSerializer.deserialize_ir_document()

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            IRDocument or None
        """
        try:
            # Check backend type
            if hasattr(self.postgres_store, "pool"):
                # PostgreSQL with connection pool
                async with self.postgres_store.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        SELECT data, schema_version
                        FROM ir_documents
                        WHERE repo_id = $1 AND snapshot_id = $2
                        """,
                        repo_id,
                        snapshot_id,
                    )
            else:
                # SQLite (direct execution)
                row = await self.postgres_store.fetchrow(
                    """
                    SELECT data, schema_version
                    FROM ir_documents
                    WHERE repo_id = ? AND snapshot_id = ?
                    """,
                    repo_id,
                    snapshot_id,
                )

            if not row:
                logger.debug("not_found", repo_id=repo_id, snapshot_id=snapshot_id)
                return None

            # Deserialize (delegated)
            data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]

            # Validate schema (delegated)
            is_valid, errors = self._serializer.validate_schema(data)
            if not is_valid:
                logger.error("schema_invalid", repo_id=repo_id, errors=errors)
                return None

            # Deserialize complete (delegated)
            ir_doc = self._deserialize_complete(data)

            logger.debug("loaded", repo_id=repo_id, nodes=len(ir_doc.nodes))
            return ir_doc

        except Exception as e:
            logger.error("load_failed", repo_id=repo_id, error=str(e), exc_info=True)
            return None

    def _serialize_complete(self, ir_doc: IRDocument) -> dict:
        """Serialize complete IRDocument (30 fields)"""
        return {
            # Identity
            "repo_id": ir_doc.repo_id,
            "snapshot_id": ir_doc.snapshot_id,
            "schema_version": ir_doc.schema_version,
            # Structural IR (delegated to serializer)
            "nodes": [self._serializer.serialize_node(n) for n in ir_doc.nodes],
            "edges": [self._serializer.serialize_edge(e) for e in ir_doc.edges],
            # Semantic IR
            "types": [self._serializer.serialize_type(t) for t in ir_doc.types] if ir_doc.types else [],
            "signatures": [self._serializer.serialize_signature(s) for s in ir_doc.signatures]
            if ir_doc.signatures
            else [],
            "cfgs": len(ir_doc.cfgs),
            # v2.1 Extended
            "cfg_blocks_count": len(ir_doc.cfg_blocks),
            "cfg_edges_count": len(ir_doc.cfg_edges),
            "bfg_graphs_count": len(ir_doc.bfg_graphs),
            "bfg_blocks_count": len(ir_doc.bfg_blocks),
            "dfg_snapshot": self._serializer.serialize_dfg_snapshot(ir_doc.dfg_snapshot)
            if ir_doc.dfg_snapshot
            else None,
            "expressions_count": len(ir_doc.expressions),
            "interprocedural_edges_count": len(ir_doc.interprocedural_edges),
            # SCIP
            "occurrences_count": len(ir_doc.occurrences),
            "diagnostics_count": len(ir_doc.diagnostics),
            "packages_count": len(ir_doc.packages),
            "unified_symbols_count": len(ir_doc.unified_symbols),
            # Analysis
            "pdg_nodes_count": len(ir_doc.pdg_nodes),
            "pdg_edges_count": len(ir_doc.pdg_edges),
            "taint_findings": [self._serializer.serialize_taint_finding(f) for f in ir_doc.taint_findings]
            if ir_doc.taint_findings
            else [],
            # Metadata
            "meta": ir_doc.meta,
        }

    def _deserialize_complete(self, data: dict) -> IRDocument:
        """Deserialize complete IRDocument"""
        return IRDocument(
            repo_id=data["repo_id"],
            snapshot_id=data["snapshot_id"],
            schema_version=data.get("schema_version", "2.1"),
            nodes=[self._serializer.deserialize_node(n) for n in data.get("nodes", [])],
            edges=[self._serializer.deserialize_edge(e) for e in data.get("edges", [])],
        )
