"""
PostgreSQL Adapter for SymbolGraph Storage

Implements SymbolGraphPort using PostgreSQL tables.
"""

import json
from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.infrastructure.symbol_graph.models import (
    Relation,
    RelationIndex,
    RelationKind,
    Symbol,
    SymbolGraph,
    SymbolKind,
)

if TYPE_CHECKING:
    from codegraph_shared.infra.storage.postgres import PostgresStore


class PostgreSQLSymbolGraphAdapter:
    """
    PostgreSQL implementation of SymbolGraphPort.

    Schema:
        symbols: Stores Symbol entities
        relations: Stores Relation entities
    """

    def __init__(self, postgres: "PostgresStore"):
        """
        Initialize adapter.

        Args:
            postgres: PostgreSQL store instance
        """
        self.postgres = postgres

    def save(self, graph: SymbolGraph) -> None:
        """
        Save SymbolGraph to PostgreSQL.

        Uses bulk insert for performance.
        """
        conn = self.postgres.get_connection()
        cur = conn.cursor()

        try:
            # Clear existing data for this snapshot
            cur.execute(
                """
                DELETE FROM symbols
                WHERE repo_id = %s AND snapshot_id = %s
                """,
                (graph.repo_id, graph.snapshot_id),
            )
            cur.execute(
                """
                DELETE FROM relations
                WHERE repo_id = %s AND snapshot_id = %s
                """,
                (graph.repo_id, graph.snapshot_id),
            )

            # Bulk insert symbols
            if graph.symbols:
                symbol_records = [
                    (
                        symbol.id,
                        graph.repo_id,
                        graph.snapshot_id,
                        symbol.kind.value,
                        symbol.fqn,
                        symbol.name,
                        json.dumps(
                            {
                                "start_line": symbol.span.start_line,
                                "end_line": symbol.span.end_line,
                                "start_col": symbol.span.start_col,
                                "end_col": symbol.span.end_col,
                            }
                        )
                        if symbol.span
                        else None,
                        symbol.parent_id,
                        symbol.signature_id,
                        symbol.type_id,
                    )
                    for symbol in graph.symbols.values()
                ]

                cur.executemany(
                    """
                    INSERT INTO symbols (
                        id, repo_id, snapshot_id, kind, fqn, name,
                        span_json, parent_id, signature_id, type_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    symbol_records,
                )

            # Bulk insert relations
            if graph.relations:
                relation_records = [
                    (
                        relation.id,
                        graph.repo_id,
                        graph.snapshot_id,
                        relation.kind.value,
                        relation.source_id,
                        relation.target_id,
                        json.dumps(
                            {
                                "start_line": relation.span.start_line,
                                "end_line": relation.span.end_line,
                                "start_col": relation.span.start_col,
                                "end_col": relation.span.end_col,
                            }
                        )
                        if relation.span
                        else None,
                    )
                    for relation in graph.relations
                ]

                cur.executemany(
                    """
                    INSERT INTO relations (
                        id, repo_id, snapshot_id, kind,
                        source_id, target_id, span_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    relation_records,
                )

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Failed to save SymbolGraph: {e}") from e

        finally:
            cur.close()

    def load(self, repo_id: str, snapshot_id: str) -> SymbolGraph:
        """
        Load SymbolGraph from PostgreSQL.

        Rebuilds indexes after loading.
        """
        conn = self.postgres.get_connection()
        cur = conn.cursor()

        try:
            # Load symbols
            cur.execute(
                """
                SELECT id, kind, fqn, name, span_json,
                       parent_id, signature_id, type_id
                FROM symbols
                WHERE repo_id = %s AND snapshot_id = %s
                """,
                (repo_id, snapshot_id),
            )

            symbols: dict[str, Symbol] = {}
            for row in cur.fetchall():
                symbol_id, kind, fqn, name, span_json, parent_id, signature_id, type_id = row

                span = None
                if span_json:
                    span_data = json.loads(span_json)
                    from codegraph_engine.code_foundation.infrastructure.ir.models import Span

                    span = Span(
                        start_line=span_data["start_line"],
                        end_line=span_data["end_line"],
                        start_col=span_data["start_col"],
                        end_col=span_data["end_col"],
                    )

                symbol = Symbol(
                    id=symbol_id,
                    kind=SymbolKind(kind),
                    fqn=fqn,
                    name=name,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    span=span,
                    parent_id=parent_id,
                    signature_id=signature_id,
                    type_id=type_id,
                )
                symbols[symbol_id] = symbol

            # Load relations
            cur.execute(
                """
                SELECT id, kind, source_id, target_id, span_json
                FROM relations
                WHERE repo_id = %s AND snapshot_id = %s
                """,
                (repo_id, snapshot_id),
            )

            relations: list[Relation] = []
            for row in cur.fetchall():
                relation_id, kind, source_id, target_id, span_json = row

                span = None
                if span_json:
                    span_data = json.loads(span_json)
                    from codegraph_engine.code_foundation.infrastructure.ir.models import Span

                    span = Span(
                        start_line=span_data["start_line"],
                        end_line=span_data["end_line"],
                        start_col=span_data["start_col"],
                        end_col=span_data["end_col"],
                    )

                relation = Relation(
                    id=relation_id,
                    kind=RelationKind(kind),
                    source_id=source_id,
                    target_id=target_id,
                    span=span,
                )
                relations.append(relation)

            # Build SymbolGraph
            graph = SymbolGraph(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                symbols=symbols,
                relations=relations,
            )

            # Rebuild indexes
            self._build_indexes(graph)

            return graph

        except Exception as e:
            raise RuntimeError(f"Failed to load SymbolGraph: {e}") from e

        finally:
            cur.close()

    def delete(self, repo_id: str, snapshot_id: str) -> None:
        """Delete SymbolGraph from PostgreSQL."""
        conn = self.postgres.get_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                """
                DELETE FROM symbols
                WHERE repo_id = %s AND snapshot_id = %s
                """,
                (repo_id, snapshot_id),
            )
            cur.execute(
                """
                DELETE FROM relations
                WHERE repo_id = %s AND snapshot_id = %s
                """,
                (repo_id, snapshot_id),
            )
            conn.commit()

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Failed to delete SymbolGraph: {e}") from e

        finally:
            cur.close()

    def exists(self, repo_id: str, snapshot_id: str) -> bool:
        """Check if SymbolGraph exists in PostgreSQL."""
        conn = self.postgres.get_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                """
                SELECT 1 FROM symbols
                WHERE repo_id = %s AND snapshot_id = %s
                LIMIT 1
                """,
                (repo_id, snapshot_id),
            )
            return cur.fetchone() is not None

        finally:
            cur.close()

    def _build_indexes(self, graph: SymbolGraph) -> None:
        """
        Build RelationIndex from relations.

        Called after loading graph from storage.
        """
        from collections import defaultdict

        # Initialize indexes
        called_by: dict[str, list[str]] = defaultdict(list)
        imported_by: dict[str, list[str]] = defaultdict(list)
        parent_to_children: dict[str, list[str]] = defaultdict(list)
        type_users: dict[str, list[str]] = defaultdict(list)
        reads_by: dict[str, list[str]] = defaultdict(list)
        writes_by: dict[str, list[str]] = defaultdict(list)
        outgoing: dict[str, list[str]] = defaultdict(list)
        incoming: dict[str, list[str]] = defaultdict(list)

        # Build indexes from relations
        for relation in graph.relations:
            # Adjacency
            outgoing[relation.source_id].append(relation.id)
            incoming[relation.target_id].append(relation.id)

            # Reverse indexes
            if relation.kind == RelationKind.CALLS:
                called_by[relation.target_id].append(relation.source_id)
            elif relation.kind == RelationKind.IMPORTS:
                imported_by[relation.target_id].append(relation.source_id)
            elif relation.kind == RelationKind.CONTAINS:
                parent_to_children[relation.source_id].append(relation.target_id)
            elif relation.kind == RelationKind.REFERENCES_TYPE:
                type_users[relation.target_id].append(relation.source_id)
            elif relation.kind == RelationKind.READS:
                reads_by[relation.target_id].append(relation.source_id)
            elif relation.kind == RelationKind.WRITES:
                writes_by[relation.target_id].append(relation.source_id)

        # Update graph indexes
        graph.indexes = RelationIndex(
            called_by=called_by,
            imported_by=imported_by,
            parent_to_children=parent_to_children,
            type_users=type_users,
            reads_by=reads_by,
            writes_by=writes_by,
            outgoing=outgoing,
            incoming=incoming,
        )
