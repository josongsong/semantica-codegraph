"""
Dependency Resolution Data Models

Core data structures for representing module dependencies, import relationships,
and dependency graphs.
"""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class DependencyKind(str, Enum):
    """Classification of dependency types."""

    INTERNAL = "internal"  # Same repository
    EXTERNAL_STDLIB = "external_stdlib"  # Python standard library
    EXTERNAL_PACKAGE = "external_package"  # Third-party package
    UNRESOLVED = "unresolved"  # Could not be resolved


class DependencyEdgeKind(str, Enum):
    """Type of dependency relationship."""

    IMPORT_MODULE = "import_module"  # import module
    IMPORT_FROM = "import_from"  # from module import symbol
    IMPORT_WILDCARD = "import_wildcard"  # from module import *


@dataclass
class ImportLocation:
    """Location where an import statement appears."""

    file_path: str  # File containing the import
    line: int  # Line number
    import_statement: str  # Raw import statement
    symbols: list[str]  # Imported symbols (empty for module imports)

    def __hash__(self) -> int:
        """Make hashable for set operations."""
        return hash((self.file_path, self.line, self.import_statement))

    def __eq__(self, other) -> bool:
        """Equality based on location and statement."""
        if not isinstance(other, ImportLocation):
            return False
        return (
            self.file_path == other.file_path
            and self.line == other.line
            and self.import_statement == other.import_statement
        )


@dataclass
class DependencyNode:
    """
    Represents a module or package in the dependency graph.

    A node can be:
    - Internal module (in the same repository)
    - External stdlib module (Python standard library)
    - External package (third-party)
    - Unresolved (import could not be resolved)
    """

    module_path: str  # Dotted path: "src.foundation.ir.models"
    kind: DependencyKind  # Classification

    # Optional attributes
    file_path: str | None = None  # Absolute path for internal modules
    package_name: str | None = None  # Package name for external deps

    # Import tracking
    imported_symbols: set[str] = field(default_factory=set)  # Symbols imported from this
    import_locations: list[ImportLocation] = field(default_factory=list)  # Where it's imported

    # Resolution status
    is_resolved: bool = True
    resolution_error: str | None = None

    def __post_init__(self):
        """Validate and normalize data."""
        if self.kind == DependencyKind.UNRESOLVED:
            self.is_resolved = False

    def add_imported_symbol(self, symbol: str) -> None:
        """Add a symbol that's imported from this module."""
        self.imported_symbols.add(symbol)

    def add_import_location(self, location: ImportLocation) -> None:
        """Add a location where this module is imported."""
        if location not in self.import_locations:
            self.import_locations.append(location)

    def is_internal(self) -> bool:
        """Check if this is an internal (same-repo) dependency."""
        return self.kind == DependencyKind.INTERNAL

    def is_external(self) -> bool:
        """Check if this is an external dependency."""
        return self.kind in (
            DependencyKind.EXTERNAL_STDLIB,
            DependencyKind.EXTERNAL_PACKAGE,
        )

    def is_stdlib(self) -> bool:
        """Check if this is a standard library module."""
        return self.kind == DependencyKind.EXTERNAL_STDLIB


@dataclass
class DependencyEdge:
    """
    Represents a dependency relationship between two modules.

    Edge direction: source imports from target
    """

    source: str  # Source module path (importer)
    target: str  # Target module path (imported)
    kind: DependencyEdgeKind  # Type of import

    # Import details
    symbols: set[str] = field(default_factory=set)  # Specific symbols imported
    is_wildcard: bool = False  # True for "import *"
    import_locations: list[ImportLocation] = field(default_factory=list)  # Where imports occur

    def add_symbol(self, symbol: str) -> None:
        """Add an imported symbol."""
        self.symbols.add(symbol)

    def add_location(self, location: ImportLocation) -> None:
        """Add an import location."""
        if location not in self.import_locations:
            self.import_locations.append(location)

    def is_module_import(self) -> bool:
        """Check if this is a module-level import."""
        return self.kind == DependencyEdgeKind.IMPORT_MODULE

    def is_symbol_import(self) -> bool:
        """Check if this imports specific symbols."""
        return self.kind in (
            DependencyEdgeKind.IMPORT_FROM,
            DependencyEdgeKind.IMPORT_WILDCARD,
        )


@dataclass
class DependencyGraph:
    """
    Complete dependency graph for a repository or snapshot.

    Contains all modules (internal + external) and their dependency relationships.
    """

    repo_id: str  # Repository identifier
    snapshot_id: str  # Commit hash or snapshot ID

    # Graph data
    nodes: dict[str, DependencyNode] = field(default_factory=dict)  # module_path -> node
    edges: list[DependencyEdge] = field(default_factory=list)

    # Indexes for fast lookup
    imports_by_module: dict[str, set[str]] = field(default_factory=dict)  # module -> modules it imports
    imported_by: dict[str, set[str]] = field(default_factory=dict)  # module -> modules that import it

    # Analysis results (computed lazily)
    circular_dependencies: list[list[str]] = field(default_factory=list)  # List of cycles
    dependency_layers: list[set[str]] = field(default_factory=list)  # Topological layers

    def add_node(self, node: DependencyNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.module_path] = node

    def add_edge(self, edge: DependencyEdge) -> None:
        """
        Add an edge to the graph and update indexes.

        Args:
            edge: Dependency edge to add
        """
        self.edges.append(edge)

        # Update indexes
        if edge.source not in self.imports_by_module:
            self.imports_by_module[edge.source] = set()
        self.imports_by_module[edge.source].add(edge.target)

        if edge.target not in self.imported_by:
            self.imported_by[edge.target] = set()
        self.imported_by[edge.target].add(edge.source)

    def get_node(self, module_path: str) -> DependencyNode | None:
        """Get a node by module path."""
        return self.nodes.get(module_path)

    def get_or_create_node(self, module_path: str, kind: DependencyKind, **kwargs) -> DependencyNode:
        """
        Get existing node or create a new one.

        Args:
            module_path: Module path
            kind: Dependency kind
            **kwargs: Additional node attributes

        Returns:
            Existing or newly created node
        """
        if module_path in self.nodes:
            return self.nodes[module_path]

        node = DependencyNode(module_path=module_path, kind=kind, **kwargs)
        self.add_node(node)
        return node

    def get_dependencies(self, module_path: str) -> set[str]:
        """
        Get all modules that the given module imports.

        Args:
            module_path: Module to query

        Returns:
            Set of module paths this module depends on
        """
        return self.imports_by_module.get(module_path, set())

    def get_dependents(self, module_path: str) -> set[str]:
        """
        Get all modules that import the given module.

        Args:
            module_path: Module to query

        Returns:
            Set of module paths that depend on this module
        """
        return self.imported_by.get(module_path, set())

    def get_transitive_dependencies(self, module_path: str, max_depth: int | None = None) -> set[str]:
        """
        Get all transitive dependencies (dependencies of dependencies).

        Args:
            module_path: Starting module
            max_depth: Maximum depth to traverse (None = unlimited)

        Returns:
            Set of all reachable module paths
        """
        visited = set()
        queue = deque([(module_path, 0)])

        while queue:
            current, depth = queue.popleft()

            if current in visited:
                continue
            if max_depth is not None and depth > max_depth:
                continue

            visited.add(current)

            # Add dependencies to queue
            for dep in self.get_dependencies(current):
                if dep not in visited:
                    queue.append((dep, depth + 1))

        # Remove the starting module
        visited.discard(module_path)
        return visited

    def get_transitive_dependents(self, module_path: str, max_depth: int | None = None) -> set[str]:
        """
        Get all transitive dependents (dependents of dependents).

        Args:
            module_path: Starting module
            max_depth: Maximum depth to traverse (None = unlimited)

        Returns:
            Set of all modules that transitively depend on this
        """
        visited = set()
        queue = deque([(module_path, 0)])

        while queue:
            current, depth = queue.popleft()

            if current in visited:
                continue
            if max_depth is not None and depth > max_depth:
                continue

            visited.add(current)

            # Add dependents to queue
            for dep in self.get_dependents(current):
                if dep not in visited:
                    queue.append((dep, depth + 1))

        # Remove the starting module
        visited.discard(module_path)
        return visited

    def get_internal_nodes(self) -> list[DependencyNode]:
        """Get all internal (same-repo) dependency nodes."""
        return [node for node in self.nodes.values() if node.is_internal()]

    def get_external_nodes(self) -> list[DependencyNode]:
        """Get all external dependency nodes."""
        return [node for node in self.nodes.values() if node.is_external()]

    def get_unresolved_nodes(self) -> list[DependencyNode]:
        """Get all unresolved dependency nodes."""
        return [node for node in self.nodes.values() if not node.is_resolved]

    def get_edges_between(self, source: str, target: str) -> list[DependencyEdge]:
        """
        Get all edges from source to target.

        Args:
            source: Source module path
            target: Target module path

        Returns:
            List of edges between the two modules
        """
        return [edge for edge in self.edges if edge.source == source and edge.target == target]

    def has_edge(self, source: str, target: str) -> bool:
        """Check if an edge exists between two modules."""
        return target in self.imports_by_module.get(source, set())

    def get_module_count(self) -> dict[str, int]:
        """
        Get count of modules by kind.

        Returns:
            Dictionary mapping kind to count
        """
        counts = dict.fromkeys(DependencyKind, 0)
        for node in self.nodes.values():
            counts[node.kind] += 1
        return counts

    def get_statistics(self) -> dict[str, int | float]:
        """
        Get graph statistics.

        Returns:
            Dictionary with various statistics
        """
        internal_nodes = self.get_internal_nodes()
        external_nodes = self.get_external_nodes()

        # Count internal edges
        internal_edges = [
            edge
            for edge in self.edges
            if edge.source in self.nodes
            and edge.target in self.nodes
            and self.nodes[edge.source].is_internal()
            and self.nodes[edge.target].is_internal()
        ]

        # Average dependencies per internal module
        avg_deps = (
            sum(len(self.get_dependencies(n.module_path)) for n in internal_nodes) / len(internal_nodes)
            if internal_nodes
            else 0.0
        )

        return {
            "total_nodes": len(self.nodes),
            "internal_nodes": len(internal_nodes),
            "external_nodes": len(external_nodes),
            "unresolved_nodes": len(self.get_unresolved_nodes()),
            "total_edges": len(self.edges),
            "internal_edges": len(internal_edges),
            "circular_dependency_count": len(self.circular_dependencies),
            "avg_dependencies_per_module": avg_deps,
        }

    def __repr__(self) -> str:
        """String representation."""
        stats = self.get_statistics()
        return (
            f"DependencyGraph("
            f"repo={self.repo_id}, "
            f"nodes={stats['total_nodes']}, "
            f"edges={stats['total_edges']}, "
            f"cycles={stats['circular_dependency_count']})"
        )
