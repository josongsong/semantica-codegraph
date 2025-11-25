"""
Kuzu-based Symbol Index Adapter

Implements SymbolIndexPort using Kuzu embedded graph database.

Architecture:
    GraphDocument (nodes + edges) → Kuzu Graph → Symbol Search/Navigation

Features:
    - Symbol search by name/FQN
    - Go-to-definition
    - Find references (callers/callees)
    - Call graph queries
    - Type hierarchy queries
"""

import logging
from pathlib import Path
from typing import Any

import kuzu

from src.foundation.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphNode,
)
from src.index.common.documents import SearchHit

logger = logging.getLogger(__name__)


class KuzuSymbolIndex:
    """
    Symbol index implementation using Kuzu graph database.

    Schema:
        Node tables: Symbol (unified table for all node kinds)
        Edge tables: Relationship (unified table for all edge kinds)

    Indexes:
        - Symbol.fqn (unique)
        - Symbol.name (for name-based search)
        - Symbol.kind (for kind filtering)

    Usage:
        index = KuzuSymbolIndex(db_path="./kuzu_db")
        index.index_graph(repo_id, snapshot_id, graph_doc)
        results = await index.search(repo_id, snapshot_id, "MyClass")
    """

    def __init__(self, db_path: str = "./kuzu_db"):
        """
        Initialize Kuzu symbol index.

        Args:
            db_path: Path to Kuzu database directory
        """
        self.db_path = Path(db_path)
        # Ensure parent directory exists, but let Kuzu create the database directory
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = None
        self._conn = None

    def _get_db(self) -> kuzu.Database:
        """Get or create Kuzu database instance"""
        if self._db is None:
            self._db = kuzu.Database(str(self.db_path))
        return self._db

    def _get_conn(self) -> kuzu.Connection:
        """Get or create Kuzu connection"""
        if self._conn is None:
            db = self._get_db()
            self._conn = kuzu.Connection(db)
        return self._conn

    def close(self):
        """Close database connections"""
        if self._conn:
            self._conn = None
        if self._db:
            self._db.close()
            self._db = None

    # ============================================================
    # SymbolIndexPort Implementation
    # ============================================================

    async def index_graph(self, repo_id: str, snapshot_id: str, graph_doc: GraphDocument) -> None:
        """
        Index graph document into Kuzu.

        Creates/updates Symbol and Relationship tables.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            graph_doc: GraphDocument with nodes and edges
        """
        conn = self._get_conn()

        # 1. Ensure schema exists
        self._ensure_schema(conn)

        # 2. Clear existing data for this repo+snapshot
        self._clear_snapshot(conn, repo_id, snapshot_id)

        # 3. Insert nodes
        logger.info(f"Indexing {len(graph_doc.graph_nodes)} nodes for {repo_id}:{snapshot_id}")
        for node in graph_doc.graph_nodes.values():
            self._insert_node(conn, node, override_snapshot_id=snapshot_id)

        # 4. Insert edges
        logger.info(f"Indexing {len(graph_doc.graph_edges)} edges for {repo_id}:{snapshot_id}")
        for edge in graph_doc.graph_edges:
            self._insert_edge(conn, edge)

        logger.info(f"Symbol index completed for {repo_id}:{snapshot_id}")

    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Symbol search by name or FQN.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Symbol name or pattern (supports partial match)
            limit: Maximum results

        Returns:
            List of SearchHit with source="symbol"
        """
        conn = self._get_conn()

        # Search by name (case-insensitive partial match) or FQN
        cypher = """
        MATCH (s:Symbol)
        WHERE s.repo_id = $repo_id
          AND s.snapshot_id = $snapshot_id
          AND (LOWER(s.name) CONTAINS LOWER($query) OR LOWER(s.fqn) CONTAINS LOWER($query))
        RETURN s.id AS id,
               s.kind AS kind,
               s.fqn AS fqn,
               s.name AS name,
               s.path AS path,
               s.start_line AS start_line,
               s.end_line AS end_line
        ORDER BY s.name ASC
        LIMIT $limit
        """

        try:
            result = conn.execute(
                cypher,
                {
                    "repo_id": repo_id,
                    "snapshot_id": snapshot_id,
                    "query": query,
                    "limit": limit,
                },
            )

            hits = []
            while result.has_next():
                row = result.get_next()
                hit = self._row_to_search_hit(row, score=1.0)
                hits.append(hit)

            logger.info(f"Symbol search returned {len(hits)} results for query: {query}")
            return hits

        except Exception as e:
            logger.error(f"Symbol search failed: {e}", exc_info=True)
            return []

    async def get_callers(self, symbol_id: str) -> list[dict[str, Any]]:
        """
        Get symbols that call this symbol.

        Args:
            symbol_id: Symbol node ID

        Returns:
            List of caller symbols (as dicts)
        """
        conn = self._get_conn()

        cypher = """
        MATCH (caller:Symbol)-[r:Relationship]->(callee:Symbol)
        WHERE callee.id = $symbol_id
          AND r.kind = 'CALLS'
        RETURN caller.id AS id,
               caller.kind AS kind,
               caller.fqn AS fqn,
               caller.name AS name,
               caller.path AS path,
               caller.start_line AS start_line,
               caller.end_line AS end_line
        """

        try:
            result = conn.execute(cypher, {"symbol_id": symbol_id})

            callers = []
            while result.has_next():
                row = result.get_next()
                callers.append(self._row_to_dict(row))

            logger.debug(f"Found {len(callers)} callers for {symbol_id}")
            return callers

        except Exception as e:
            logger.error(f"get_callers failed: {e}", exc_info=True)
            return []

    async def get_callees(self, symbol_id: str) -> list[dict[str, Any]]:
        """
        Get symbols called by this symbol.

        Args:
            symbol_id: Symbol node ID

        Returns:
            List of callee symbols (as dicts)
        """
        conn = self._get_conn()

        cypher = """
        MATCH (caller:Symbol)-[r:Relationship]->(callee:Symbol)
        WHERE caller.id = $symbol_id
          AND r.kind = 'CALLS'
        RETURN callee.id AS id,
               callee.kind AS kind,
               callee.fqn AS fqn,
               callee.name AS name,
               callee.path AS path,
               callee.start_line AS start_line,
               callee.end_line AS end_line
        """

        try:
            result = conn.execute(cypher, {"symbol_id": symbol_id})

            callees = []
            while result.has_next():
                row = result.get_next()
                callees.append(self._row_to_dict(row))

            logger.debug(f"Found {len(callees)} callees for {symbol_id}")
            return callees

        except Exception as e:
            logger.error(f"get_callees failed: {e}", exc_info=True)
            return []

    # ============================================================
    # Private Helpers - Schema
    # ============================================================

    def _ensure_schema(self, conn: kuzu.Connection) -> None:
        """
        Create Kuzu schema if not exists.

        Schema:
            Symbol (NODE):
                - id: STRING (PRIMARY KEY)
                - repo_id: STRING
                - snapshot_id: STRING
                - kind: STRING
                - fqn: STRING
                - name: STRING
                - path: STRING
                - start_line: INT64
                - end_line: INT64
                - attrs: STRING (JSON)

            Relationship (REL):
                - FROM Symbol TO Symbol
                - kind: STRING
                - attrs: STRING (JSON)
        """
        # Check if Symbol table exists
        try:
            conn.execute("MATCH (s:Symbol) RETURN s LIMIT 1")
            logger.debug("Symbol table already exists")
            return  # Schema exists
        except Exception as e:
            logger.debug(f"Schema check failed (expected if first run): {e}")
            # Schema doesn't exist, create it

        logger.info("Creating Kuzu schema")

        # Create Symbol node table
        conn.execute(
            """
            CREATE NODE TABLE Symbol(
                id STRING,
                repo_id STRING,
                snapshot_id STRING,
                kind STRING,
                fqn STRING,
                name STRING,
                path STRING,
                start_line INT64,
                end_line INT64,
                attrs STRING,
                PRIMARY KEY (id)
            )
        """
        )

        # Create Relationship edge table
        conn.execute(
            """
            CREATE REL TABLE Relationship(
                FROM Symbol TO Symbol,
                kind STRING,
                attrs STRING
            )
        """
        )

        logger.info("Kuzu schema created")

    def _clear_snapshot(self, conn: kuzu.Connection, repo_id: str, snapshot_id: str) -> None:
        """
        Clear existing data for a repo+snapshot.

        Deletes both nodes and edges.
        """
        try:
            # Delete edges first (relationships)
            conn.execute(
                """
                MATCH (s1:Symbol)-[r:Relationship]->(s2:Symbol)
                WHERE s1.repo_id = $repo_id AND s1.snapshot_id = $snapshot_id
                DELETE r
            """,
                {"repo_id": repo_id, "snapshot_id": snapshot_id},
            )

            # Delete nodes
            conn.execute(
                """
                MATCH (s:Symbol)
                WHERE s.repo_id = $repo_id AND s.snapshot_id = $snapshot_id
                DELETE s
            """,
                {"repo_id": repo_id, "snapshot_id": snapshot_id},
            )

            logger.debug(f"Cleared existing data for {repo_id}:{snapshot_id}")
        except Exception as e:
            logger.warning(f"Clear snapshot failed (may be first index): {e}")

    # ============================================================
    # Private Helpers - Data Insertion
    # ============================================================

    def _insert_node(self, conn: kuzu.Connection, node: GraphNode, override_snapshot_id: str | None = None) -> None:
        """Insert a graph node into Kuzu

        Args:
            conn: Kuzu connection
            node: GraphNode to insert
            override_snapshot_id: Optional snapshot_id to override node's snapshot_id
        """
        import json

        cypher = """
        CREATE (s:Symbol {
            id: $id,
            repo_id: $repo_id,
            snapshot_id: $snapshot_id,
            kind: $kind,
            fqn: $fqn,
            name: $name,
            path: $path,
            start_line: $start_line,
            end_line: $end_line,
            attrs: $attrs
        })
        """

        params = {
            "id": node.id,
            "repo_id": node.repo_id,
            "snapshot_id": override_snapshot_id or node.snapshot_id or "",
            "kind": node.kind.value,
            "fqn": node.fqn,
            "name": node.name,
            "path": node.path or "",
            "start_line": node.span.start_line if node.span else 0,
            "end_line": node.span.end_line if node.span else 0,
            "attrs": json.dumps(node.attrs),
        }

        try:
            conn.execute(cypher, params)
        except Exception as e:
            logger.error(f"Failed to insert node {node.id}: {e}")

    def _insert_edge(self, conn: kuzu.Connection, edge: GraphEdge) -> None:
        """Insert a graph edge into Kuzu"""
        import json

        cypher = """
        MATCH (s1:Symbol {id: $source_id}), (s2:Symbol {id: $target_id})
        CREATE (s1)-[r:Relationship {kind: $kind, attrs: $attrs}]->(s2)
        """

        params = {
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "kind": edge.kind.value,
            "attrs": json.dumps(edge.attrs),
        }

        try:
            conn.execute(cypher, params)
        except Exception as e:
            logger.debug(f"Failed to insert edge {edge.id} (nodes may not exist): {e}")

    # ============================================================
    # Private Helpers - Result Conversion
    # ============================================================

    def _row_to_search_hit(self, row: list, score: float = 1.0) -> SearchHit:
        """
        Convert Kuzu query result row to SearchHit.

        Args:
            row: Query result row [id, kind, fqn, name, path, start_line, end_line]
            score: Search score

        Returns:
            SearchHit with source="symbol"
        """
        # Kuzu returns results as list
        id_val = row[0]
        kind = row[1]
        fqn = row[2]
        name = row[3]
        path = row[4]
        start_line = row[5]
        end_line = row[6]

        # Generate chunk_id from symbol_id for consistency
        chunk_id = f"symbol:{id_val}"

        return SearchHit(
            chunk_id=chunk_id,
            file_path=path if path else None,
            symbol_id=id_val,
            score=score,
            source="symbol",
            metadata={
                "kind": kind,
                "fqn": fqn,
                "name": name,
                "start_line": start_line,
                "end_line": end_line,
            },
        )

    def _row_to_dict(self, row: list) -> dict[str, Any]:
        """
        Convert Kuzu query result row to dict.

        Args:
            row: Query result row [id, kind, fqn, name, path, start_line, end_line]

        Returns:
            Dict representation of symbol
        """
        return {
            "id": row[0],
            "kind": row[1],
            "fqn": row[2],
            "name": row[3],
            "path": row[4],
            "start_line": row[5],
            "end_line": row[6],
        }


# ============================================================
# Convenience Factory
# ============================================================


def create_kuzu_symbol_index(db_path: str = "./kuzu_db") -> KuzuSymbolIndex:
    """
    Factory function for KuzuSymbolIndex.

    Args:
        db_path: Path to Kuzu database directory

    Returns:
        Configured KuzuSymbolIndex instance
    """
    return KuzuSymbolIndex(db_path=db_path)
