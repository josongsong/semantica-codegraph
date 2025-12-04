"""
Edge Builder for Python IR

Utility class for creating edges between IR nodes.
"""

from src.contexts.code_foundation.infrastructure.ir.id_strategy import generate_edge_id
from src.contexts.code_foundation.infrastructure.ir.models import Edge, EdgeKind, Span


class EdgeBuilder:
    """
    Utility for creating edges between IR nodes.

    Responsibilities:
    - Create CONTAINS edges (structural hierarchy)
    - Create CALLS edges (function call relationships)
    - Create IMPORTS edges (import relationships)

    This class provides a clean interface for edge generation,
    extracted from PythonIRGenerator to improve modularity.

    Example:
        >>> edges = []
        >>> builder = EdgeBuilder(edges)
        >>> builder.add_contains_edge(file_id, class_id, span)
        >>> assert len(edges) == 1
        >>> assert edges[0].kind == EdgeKind.CONTAINS
    """

    def __init__(self, edges: list[Edge]):
        """
        Initialize edge builder.

        Args:
            edges: Shared edge collection (will be mutated)
        """
        self._edges = edges

    def add_contains_edge(self, parent_id: str, child_id: str, span: Span):
        """
        Add CONTAINS edge from parent to child.

        CONTAINS edges represent structural hierarchy:
        - FILE contains CLASS
        - CLASS contains METHOD
        - FUNCTION contains PARAMETER
        - etc.

        Args:
            parent_id: Parent node ID
            child_id: Child node ID
            span: Edge location (typically same as child node span)

        Example:
            >>> # File contains class
            >>> builder.add_contains_edge("file:main", "class:Foo", span)
            >>> # Class contains method
            >>> builder.add_contains_edge("class:Foo", "method:bar", span)
        """
        edge_id = generate_edge_id("contains", parent_id, child_id, 0)

        edge = Edge(
            id=edge_id,
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=child_id,
            span=span,
        )

        self._edges.append(edge)

    def add_calls_edge(self, caller_id: str, callee_id: str, callee_name: str, span: Span):
        """
        Add CALLS edge from caller to callee.

        CALLS edges represent function call relationships.
        Multiple calls from same caller to same callee are tracked
        by occurrence count (0, 1, 2, ...).

        Args:
            caller_id: Caller function/method node ID
            callee_id: Callee function/method node ID
            callee_name: Callee name (stored as attribute for debugging)
            span: Call location (span of the call expression)

        Example:
            >>> # Function foo calls bar
            >>> builder.add_calls_edge("func:foo", "func:bar", "bar", span1)
            >>> # foo calls bar again (occurrence = 1)
            >>> builder.add_calls_edge("func:foo", "func:bar", "bar", span2)
        """
        # Count existing calls from this caller to same callee
        # This creates unique edge IDs for multiple calls: calls:foo:bar:0, calls:foo:bar:1, ...
        occurrence = sum(
            1 for e in self._edges if e.kind == EdgeKind.CALLS and e.source_id == caller_id and e.target_id == callee_id
        )

        edge_id = generate_edge_id("calls", caller_id, callee_id, occurrence)

        edge = Edge(
            id=edge_id,
            kind=EdgeKind.CALLS,
            source_id=caller_id,
            target_id=callee_id,
            span=span,
            attrs={"callee_name": callee_name},
        )

        self._edges.append(edge)

    def add_imports_edge(self, importer_id: str, import_id: str, span: Span):
        """
        Add IMPORTS edge from importer to import.

        IMPORTS edges represent import relationships:
        - FILE imports MODULE
        - FILE imports SYMBOL

        Args:
            importer_id: Importer node ID (typically FILE)
            import_id: Import node ID
            span: Import statement location

        Example:
            >>> # File imports os module
            >>> builder.add_imports_edge("file:main", "import:os", span)
        """
        edge_id = generate_edge_id("imports", importer_id, import_id, 0)

        edge = Edge(
            id=edge_id,
            kind=EdgeKind.IMPORTS,
            source_id=importer_id,
            target_id=import_id,
            span=span,
        )

        self._edges.append(edge)
