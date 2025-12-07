"""
Graph Construction Layer - Models

Unified graph representation for code analysis.
Converts Structural IR + Semantic IR → GraphDocument.

GraphDocument:
  - GraphNode (13 kinds): File, Module, Class, Function, Variable, Type,
    Signature, CfgBlock, External...
  - GraphEdge (13 kinds): CONTAINS, CALLS, READS, WRITES, CFG edges, etc.
  - GraphIndex: Reverse indexes + adjacency for efficient queries
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.contexts.code_foundation.infrastructure.ir.models import Span

# ============================================================
# Graph Node
# ============================================================


class GraphNodeKind(str, Enum):
    """
    Graph node types.

    Represents all semantic entities in the codebase graph.
    """

    # Structural nodes (from IR)
    FILE = "File"
    MODULE = "Module"  # Auto-generated from file paths
    CLASS = "Class"
    INTERFACE = "Interface"  # TypeScript/Java interfaces
    FUNCTION = "Function"
    METHOD = "Method"
    VARIABLE = "Variable"
    FIELD = "Field"
    IMPORT = "Import"  # Import statement node

    # Semantic nodes (from Semantic IR)
    TYPE = "Type"  # Type entities
    SIGNATURE = "Signature"  # Function/method signatures
    CFG_BLOCK = "CfgBlock"  # Control flow graph blocks

    # External nodes (lazy created for unresolved references)
    EXTERNAL_MODULE = "ExternalModule"  # External package/module
    EXTERNAL_FUNCTION = "ExternalFunction"  # External function/method
    EXTERNAL_TYPE = "ExternalType"  # External type

    # Extended nodes (Phase 3: Framework/Architecture layer)
    ROUTE = "Route"  # API route endpoint
    SERVICE = "Service"  # Service layer component
    REPOSITORY = "Repository"  # Data access layer
    CONFIG = "Config"  # Configuration
    JOB = "Job"  # Background job/task
    MIDDLEWARE = "Middleware"  # Middleware component
    SUMMARY = "Summary"  # Code summary node

    # Documentation nodes
    DOCUMENT = "Document"  # Documentation file (Markdown, RST, etc.)


@dataclass
class GraphNode:
    """
    Graph node representing a code entity.

    Attributes:
        id: Unique identifier (FQN-based for stability)
        kind: Node type
        repo_id: Repository identifier
        snapshot_id: Snapshot identifier (None for external nodes)
        fqn: Fully qualified name
        name: Simple name
        path: File path (for FILE nodes) or module path
        span: Source location (None for external/generated nodes)
        attrs: Additional attributes (language-specific, metadata)
    """

    id: str
    kind: GraphNodeKind
    repo_id: str
    snapshot_id: str | None
    fqn: str
    name: str
    path: str | None = None
    span: Span | None = None
    attrs: dict[str, Any] = field(default_factory=dict)

    def is_external(self) -> bool:
        """Check if this is an external node"""
        return self.kind in (
            GraphNodeKind.EXTERNAL_MODULE,
            GraphNodeKind.EXTERNAL_FUNCTION,
            GraphNodeKind.EXTERNAL_TYPE,
        )

    def is_callable(self) -> bool:
        """Check if this node represents a callable entity"""
        return self.kind in (
            GraphNodeKind.FUNCTION,
            GraphNodeKind.METHOD,
            GraphNodeKind.EXTERNAL_FUNCTION,
        )

    def is_type(self) -> bool:
        """Check if this node represents a type entity"""
        return self.kind in (
            GraphNodeKind.TYPE,
            GraphNodeKind.CLASS,
            GraphNodeKind.EXTERNAL_TYPE,
        )


# ============================================================
# Graph Edge
# ============================================================


class GraphEdgeKind(str, Enum):
    """
    Graph edge types.

    Represents relationships between code entities.
    """

    # Structural edges (from IR)
    CONTAINS = "CONTAINS"  # Parent-child relationship (File contains Class, Class contains Method)
    IMPORTS = "IMPORTS"  # Import relationship
    INHERITS = "INHERITS"  # Class inheritance
    IMPLEMENTS = "IMPLEMENTS"  # Interface implementation

    # Call/Reference edges (from IR + Semantic IR)
    CALLS = "CALLS"  # Function/method calls
    # Type usage (variable declarations, parameters, return types)
    REFERENCES_TYPE = "REFERENCES_TYPE"
    REFERENCES_SYMBOL = "REFERENCES_SYMBOL"  # Symbol reference (variable usage)

    # Data flow edges (from DFG)
    READS = "READS"  # Variable read
    WRITES = "WRITES"  # Variable write

    # Control flow edges (from CFG)
    CFG_NEXT = "CFG_NEXT"  # Sequential execution
    CFG_BRANCH = "CFG_BRANCH"  # Conditional branch (true/false)
    CFG_LOOP = "CFG_LOOP"  # Loop back edge
    CFG_HANDLER = "CFG_HANDLER"  # Exception handler edge

    # Framework/Architecture edges (Phase 3)
    ROUTE_HANDLER = "ROUTE_HANDLER"  # Route → Handler Function/Method
    HANDLES_REQUEST = "HANDLES_REQUEST"  # Handler → Service
    USES_REPOSITORY = "USES_REPOSITORY"  # Service → Repository
    MIDDLEWARE_NEXT = "MIDDLEWARE_NEXT"  # Middleware chain

    # Object/Decorator edges (Phase 3)
    INSTANTIATES = "INSTANTIATES"  # Function/Block → Class (object creation)
    DECORATES = "DECORATES"  # Decorator → Decorated symbol

    # Documentation edges
    DOCUMENTS = "DOCUMENTS"  # File → Document (file has documentation)
    REFERENCES_CODE = "REFERENCES_CODE"  # Document → Code symbol (doc mentions code)
    DOCUMENTED_IN = "DOCUMENTED_IN"  # Code symbol → Document (code is documented in)


@dataclass
class GraphEdge:
    """
    Graph edge representing a relationship.

    Attributes:
        id: Unique edge identifier
        kind: Edge type
        source_id: Source node ID
        target_id: Target node ID
        attrs: Additional attributes (edge-specific metadata)
    """

    id: str
    kind: GraphEdgeKind
    source_id: str
    target_id: str
    attrs: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Graph Index
# ============================================================


@dataclass
class GraphIndex:
    """
    Graph indexes for efficient queries.

    Provides both reverse indexes (who uses/calls this?) and
    adjacency indexes (what does this use/call?).
    """

    # Core reverse indexes (target → sources)
    called_by: dict[str, list[str]] = field(default_factory=dict)  # Function → Callers
    imported_by: dict[str, list[str]] = field(default_factory=dict)  # Module → Importers
    contains_children: dict[str, list[str]] = field(default_factory=dict)  # Parent → Children
    type_users: dict[str, list[str]] = field(default_factory=dict)  # Type → Users
    reads_by: dict[str, list[str]] = field(default_factory=dict)  # Variable → Readers
    writes_by: dict[str, list[str]] = field(default_factory=dict)  # Variable → Writers

    # Adjacency indexes (for general graph queries)
    outgoing: dict[str, list[str]] = field(default_factory=dict)  # Node → Outgoing edge IDs
    incoming: dict[str, list[str]] = field(default_factory=dict)  # Node → Incoming edge IDs

    # Extended indexes (Phase 3: Framework/Architecture)
    routes_by_path: dict[str, list[str]] = field(default_factory=dict)  # Route path → Route node IDs
    services_by_domain: dict[str, list[str]] = field(default_factory=dict)  # Domain tag → Service node IDs
    request_flow_index: dict[str, dict[str, list[str]]] = field(
        default_factory=dict
    )  # Route ID → {handler, services, repositories}
    decorators_by_target: dict[str, list[str]] = field(default_factory=dict)  # Target node ID → Decorator node IDs

    def get_callers(self, function_id: str) -> list[str]:
        """Get all callers of a function"""
        return self.called_by.get(function_id, [])

    def get_importers(self, module_id: str) -> list[str]:
        """Get all modules that import this module"""
        return self.imported_by.get(module_id, [])

    def get_children(self, parent_id: str) -> list[str]:
        """Get all children of a parent node"""
        return self.contains_children.get(parent_id, [])

    def get_type_users(self, type_id: str) -> list[str]:
        """Get all nodes that use this type"""
        return self.type_users.get(type_id, [])

    def get_readers(self, variable_id: str) -> list[str]:
        """Get all nodes that read this variable"""
        return self.reads_by.get(variable_id, [])

    def get_writers(self, variable_id: str) -> list[str]:
        """Get all nodes that write to this variable"""
        return self.writes_by.get(variable_id, [])

    def get_outgoing_edges(self, node_id: str) -> list[str]:
        """Get all outgoing edge IDs from a node"""
        return self.outgoing.get(node_id, [])

    def get_incoming_edges(self, node_id: str) -> list[str]:
        """Get all incoming edge IDs to a node"""
        return self.incoming.get(node_id, [])

    # Extended index access methods (Phase 3)
    def get_routes_by_path(self, path: str) -> list[str]:
        """Get route nodes for a specific path"""
        return self.routes_by_path.get(path, [])

    def get_services_by_domain(self, domain: str) -> list[str]:
        """Get service nodes in a specific domain"""
        return self.services_by_domain.get(domain, [])

    def get_request_flow(self, route_id: str) -> dict[str, list[str]]:
        """Get the complete request flow for a route (handler, services, repositories)"""
        return self.request_flow_index.get(route_id, {})

    def get_decorators(self, target_id: str) -> list[str]:
        """Get all decorators applied to a target node"""
        return self.decorators_by_target.get(target_id, [])


# ============================================================
# Graph Document
# ============================================================


@dataclass
class GraphDocument:
    """
    Complete graph representation of a codebase snapshot.

    Combines:
    - Structural IR (Nodes, Edges)
    - Semantic IR (Types, Signatures, CFG, DFG)

    Into a unified graph with:
    - GraphNodes (all entities)
    - GraphEdges (all relationships)
    - GraphIndex (efficient queries)

    Attributes:
        repo_id: Repository identifier
        snapshot_id: Snapshot identifier
        graph_nodes: All graph nodes (indexed by ID)
        graph_edges: All graph edges
        indexes: Reverse + adjacency indexes
    """

    repo_id: str
    snapshot_id: str
    graph_nodes: dict[str, GraphNode] = field(default_factory=dict)
    graph_edges: list[GraphEdge] = field(default_factory=list)
    # FIX: HIGH #5 - Add edge index for O(1) lookup instead of O(E)
    edge_by_id: dict[str, GraphEdge] = field(default_factory=dict)
    indexes: GraphIndex = field(default_factory=GraphIndex)

    # 🔥 NEW: Performance optimization - path index for O(1) lookup
    _path_index: dict[str, set[str]] | None = field(default=None, init=False, repr=False)

    def build_path_index(self) -> None:
        """
        🔥 OPTIMIZATION: Build index for O(1) node lookup by file path.

        Before: O(N) scan - iterate all nodes
        After: O(1) lookup - hash table
        Performance: 100x faster for large graphs!
        """
        if self._path_index is not None:
            return  # Already built

        self._path_index = {}
        for node_id, node in self.graph_nodes.items():
            if hasattr(node, "path") and node.path:
                if node.path not in self._path_index:
                    self._path_index[node.path] = set()
                self._path_index[node.path].add(node_id)

    def get_node_ids_by_path(self, file_path: str) -> set[str]:
        """
        🔥 OPTIMIZATION: O(1) lookup instead of O(N) scan.

        Args:
            file_path: File path to lookup

        Returns:
            Set of node IDs in that file
        """
        if self._path_index is None:
            self.build_path_index()
        return self._path_index.get(file_path, set())

    def get_node_ids_by_paths(self, file_paths: list[str]) -> set[str]:
        """
        🔥 OPTIMIZATION: Batch lookup for multiple files.

        Before: O(N × M) where N=nodes, M=files
        After: O(M) - one lookup per file

        Args:
            file_paths: List of file paths

        Returns:
            Set of all node IDs in those files
        """
        if self._path_index is None:
            self.build_path_index()

        result = set()
        for file_path in file_paths:
            result.update(self._path_index.get(file_path, set()))
        return result

    def get_node(self, node_id: str) -> GraphNode | None:
        """Get node by ID"""
        return self.graph_nodes.get(node_id)

    def get_nodes_by_kind(self, kind: GraphNodeKind) -> list[GraphNode]:
        """Get all nodes of a specific kind"""
        return [node for node in self.graph_nodes.values() if node.kind == kind]

    def get_edges_by_kind(self, kind: GraphEdgeKind) -> list[GraphEdge]:
        """Get all edges of a specific kind"""
        return [edge for edge in self.graph_edges if edge.kind == kind]

    def get_edges_from(self, source_id: str) -> list[GraphEdge]:
        """Get all edges originating from a node (O(k) where k = outgoing edges)"""
        edge_ids = self.indexes.get_outgoing_edges(source_id)
        # FIX: HIGH #5 - Use O(1) edge_by_id lookup instead of O(E) list scan
        return [self.edge_by_id[eid] for eid in edge_ids if eid in self.edge_by_id]

    def get_edges_to(self, target_id: str) -> list[GraphEdge]:
        """Get all edges pointing to a node (O(k) where k = incoming edges)"""
        edge_ids = self.indexes.get_incoming_edges(target_id)
        # FIX: HIGH #5 - Use O(1) edge_by_id lookup instead of O(E) list scan
        return [self.edge_by_id[eid] for eid in edge_ids if eid in self.edge_by_id]

    @property
    def nodes(self) -> dict[str, GraphNode]:
        """Backward compatibility: alias for graph_nodes"""
        return self.graph_nodes

    @property
    def node_count(self) -> int:
        """Total number of nodes"""
        return len(self.graph_nodes)

    @property
    def edge_count(self) -> int:
        """Total number of edges"""
        return len(self.graph_edges)

    def stats(self) -> dict[str, Any]:
        """Get graph statistics"""
        node_counts: dict[str, int] = {}
        for node in self.graph_nodes.values():
            kind = node.kind.value
            node_counts[kind] = node_counts.get(kind, 0) + 1

        edge_counts: dict[str, int] = {}
        for edge in self.graph_edges:
            kind = edge.kind.value
            edge_counts[kind] = edge_counts.get(kind, 0) + 1

        return {
            "total_nodes": self.node_count,
            "total_edges": self.edge_count,
            "nodes_by_kind": node_counts,
            "edges_by_kind": edge_counts,
        }
