"""
Kuzu Schema Definition

Defines NODE and REL tables for GraphDocument storage.

Based on: _command_doc/04.Graph/디비.md
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import kuzu


class KuzuSchema:
    """
    Kuzu database schema for GraphDocument.

    Schema design:
    - Single NODE TABLE: graph_node
    - Multiple REL TABLES for different edge types
    - Indexes for common queries
    """

    # Core schema DDL statements
    NODE_TABLE_DDL = """
    CREATE NODE TABLE IF NOT EXISTS graph_node (
        node_id       STRING,
        repo_id       STRING,
        lang          STRING,
        kind          STRING,
        fqn           STRING,
        name          STRING,
        path          STRING,
        snapshot_id   STRING,

        span_start_line INT64,
        span_end_line   INT64,

        attrs         STRING,

        PRIMARY KEY (node_id)
    )
    """

    # Relationship table DDLs
    REL_TABLES_DDL = [
        # Structural
        """
        CREATE REL TABLE IF NOT EXISTS CONTAINS (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS IMPORTS (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS CALLS (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS INHERITS (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS IMPLEMENTS (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        # Type/Symbol references
        """
        CREATE REL TABLE IF NOT EXISTS REFERENCES_TYPE (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS REFERENCES_SYMBOL (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        # Data flow
        """
        CREATE REL TABLE IF NOT EXISTS READS (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS WRITES (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        # Control flow
        """
        CREATE REL TABLE IF NOT EXISTS CFG_NEXT (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS CFG_BRANCH (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS CFG_LOOP (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS CFG_HANDLER (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
    ]

    # Optional: Framework/Architecture relationships
    FRAMEWORK_REL_TABLES_DDL = [
        """
        CREATE REL TABLE IF NOT EXISTS ROUTE_HANDLER (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS HANDLES_REQUEST (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS USES_REPOSITORY (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS MIDDLEWARE_NEXT (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS INSTANTIATES (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS DECORATES (
            FROM graph_node TO graph_node,
            attrs STRING
        )
        """,
    ]

    @classmethod
    def initialize(cls, db: "kuzu.Database", include_framework_rels: bool = False):
        """
        Initialize Kuzu database with schema.

        Args:
            db: Kuzu database instance
            include_framework_rels: Whether to create framework-specific REL tables
        """
        import kuzu

        conn = kuzu.Connection(db)

        # Create NODE table
        conn.execute(cls.NODE_TABLE_DDL)

        # Create core REL tables
        for ddl in cls.REL_TABLES_DDL:
            conn.execute(ddl)

        # Optionally create framework REL tables
        if include_framework_rels:
            for ddl in cls.FRAMEWORK_REL_TABLES_DDL:
                conn.execute(ddl)

    @classmethod
    def create_indexes(cls, db: "kuzu.Database"):
        """
        Create indexes for common queries.

        Note: Kuzu auto-indexes PRIMARY KEY, so this is optional for now.
        """
        # Kuzu automatically creates indexes on PRIMARY KEY
        # Additional indexes can be added here if needed
        pass
