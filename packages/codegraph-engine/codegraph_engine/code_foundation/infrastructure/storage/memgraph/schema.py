"""
Memgraph Schema Definition

Defines constraints and indexes for GraphDocument storage.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import Driver


class MemgraphSchema:
    """
    Memgraph database schema for GraphDocument.

    Schema design:
    - Node label: GraphNode
    - Relationship types: CONTAINS, CALLS, IMPORTS, etc.
    - Constraints and indexes for performance
    """

    @classmethod
    def initialize(cls, driver: "Driver", include_framework_rels: bool = False):
        """
        Initialize Memgraph database with schema.

        Args:
            driver: Neo4j driver instance
            include_framework_rels: Whether to create framework-specific indexes
        """
        with driver.session() as session:
            # Create uniqueness constraint on node_id
            session.run("CREATE CONSTRAINT ON (n:GraphNode) ASSERT n.node_id IS UNIQUE")

            # Create indexes for common queries
            session.run("CREATE INDEX ON :GraphNode(repo_id)")
            session.run("CREATE INDEX ON :GraphNode(snapshot_id)")
            session.run("CREATE INDEX ON :GraphNode(kind)")
            session.run("CREATE INDEX ON :GraphNode(fqn)")
            session.run("CREATE INDEX ON :GraphNode(path)")

    @classmethod
    def clear_all(cls, driver: "Driver"):
        """Clear all data from database."""
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
