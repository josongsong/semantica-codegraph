"""
Dependency Graph Builder

Constructs dependency graphs from IR documents by:
1. Extracting import nodes from IR
2. Resolving import paths to actual modules
3. Creating dependency nodes and edges
4. Building complete dependency graph
"""

from pathlib import Path

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.dependency.models import (
    DependencyEdge,
    DependencyEdgeKind,
    DependencyGraph,
    DependencyKind,
    ImportLocation,
)
from codegraph_engine.code_foundation.infrastructure.dependency.python_resolver import PythonResolver
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument, Node, NodeKind

logger = get_logger(__name__)


class DependencyGraphBuilder:
    """
    Builds dependency graphs from IR documents.

    Example:
        ```python
        builder = DependencyGraphBuilder(
            repo_id="my-repo",
            snapshot_id="abc123",
            repo_root=Path("/path/to/repo")
        )

        # Build graph from IR documents
        graph = builder.build_from_ir(ir_documents)

        # Access graph
        print(f"Nodes: {len(graph.nodes)}")
        print(f"Edges: {len(graph.edges)}")
        ```
    """

    def __init__(
        self,
        repo_id: str,
        snapshot_id: str,
        repo_root: Path,
    ):
        """
        Initialize builder.

        Args:
            repo_id: Repository identifier
            snapshot_id: Commit hash or snapshot ID
            repo_root: Absolute path to repository root
        """
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.repo_root = Path(repo_root).resolve()
        self.resolver = PythonResolver(repo_root=self.repo_root)

        logger.info(
            "dependency_graph_builder_initialized",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            repo_root=str(self.repo_root),
        )

    def build_from_ir(self, ir_documents: list[IRDocument]) -> DependencyGraph:
        """
        Build dependency graph from IR documents.

        Args:
            ir_documents: List of IR documents from parsing

        Returns:
            Complete dependency graph
        """
        logger.info(
            "building_dependency_graph",
            document_count=len(ir_documents),
        )

        # Initialize graph
        graph = DependencyGraph(
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
        )

        # Process each document
        for doc in ir_documents:
            self._process_document(doc, graph)

        logger.info(
            "dependency_graph_built",
            total_nodes=len(graph.nodes),
            total_edges=len(graph.edges),
            internal_nodes=len(graph.get_internal_nodes()),
            external_nodes=len(graph.get_external_nodes()),
            unresolved_nodes=len(graph.get_unresolved_nodes()),
        )

        return graph

    def _process_document(self, doc: IRDocument, graph: DependencyGraph) -> None:
        """
        Process a single IR document.

        Args:
            doc: IR document
            graph: Graph to populate
        """
        # Get module node for this document
        module_node = self._find_module_node(doc)
        if not module_node:
            logger.warning(
                "no_module_node_found",
                file_path=doc.meta.get("file_path"),
            )
            return

        module_path = module_node.fqn
        file_path = doc.meta.get("file_path", "")

        # Ensure source module exists in graph
        graph.get_or_create_node(
            module_path=module_path,
            kind=DependencyKind.INTERNAL,
            file_path=file_path,
        )

        # Extract and process imports
        import_nodes = self._extract_import_nodes(doc)

        logger.debug(
            "processing_document",
            module_path=module_path,
            file_path=file_path,
            import_count=len(import_nodes),
        )

        for import_node in import_nodes:
            self._process_import_node(import_node, module_path, file_path, graph)

    def _find_module_node(self, doc: IRDocument) -> Node | None:
        """
        Find the module node in an IR document.

        Args:
            doc: IR document

        Returns:
            Module node, or None if not found
        """
        for node in doc.nodes:
            if node.kind == NodeKind.MODULE:
                return node
        return None

    def _extract_import_nodes(self, doc: IRDocument) -> list[Node]:
        """
        Extract all import nodes from a document.

        Args:
            doc: IR document

        Returns:
            List of import nodes
        """
        import_nodes = []
        for node in doc.nodes:
            if node.kind == NodeKind.IMPORT:
                import_nodes.append(node)
        return import_nodes

    def _process_import_node(
        self,
        import_node: Node,
        current_module: str,
        current_file: str,
        graph: DependencyGraph,
    ) -> None:
        """
        Process a single import node.

        Args:
            import_node: Import node from IR
            current_module: Module path of importing file
            current_file: File path of importing file
            graph: Graph to populate
        """
        # Get import details from attributes
        attrs = import_node.attrs or {}
        full_symbol = attrs.get("full_symbol", import_node.name)
        alias = attrs.get("alias", full_symbol)
        is_wildcard = attrs.get("is_wildcard", False)

        # Extract imported symbols
        imported_symbols = []
        if is_wildcard:
            imported_symbols = ["*"]
        elif alias and alias != full_symbol:
            # This is "from X import Y" style
            imported_symbols = [alias]

        # Parse import to get module path
        # full_symbol format: "module.path" or "module.path.symbol"
        import_path, symbols = self._parse_import(full_symbol, imported_symbols)

        # Resolve import
        kind, resolved_path = self.resolver.resolve_import(
            import_path=import_path,
            current_file=current_file,
            current_module=current_module,
        )

        # Create import location
        import_location = ImportLocation(
            file_path=current_file,
            line=import_node.span.start_line if import_node.span else 0,
            import_statement=self._reconstruct_import_statement(import_path, symbols, is_wildcard),
            symbols=symbols,
        )

        # Get or create target node
        target_node = graph.get_or_create_node(
            module_path=resolved_path,
            kind=kind,
            file_path=self.resolver.get_module_file_path(resolved_path) if kind == DependencyKind.INTERNAL else None,
            package_name=self.resolver.extract_package_name(resolved_path) if kind != DependencyKind.INTERNAL else None,
        )

        # Add imported symbols to target node
        for symbol in symbols:
            target_node.add_imported_symbol(symbol)

        # Add import location to target node
        target_node.add_import_location(import_location)

        # Determine edge kind
        if is_wildcard:
            edge_kind = DependencyEdgeKind.IMPORT_WILDCARD
        elif symbols:
            edge_kind = DependencyEdgeKind.IMPORT_FROM
        else:
            edge_kind = DependencyEdgeKind.IMPORT_MODULE

        # Check if edge already exists
        existing_edges = graph.get_edges_between(current_module, resolved_path)

        if existing_edges:
            # Update existing edge
            edge = existing_edges[0]
            for symbol in symbols:
                edge.add_symbol(symbol)
            edge.add_location(import_location)
        else:
            # Create new edge
            edge = DependencyEdge(
                source=current_module,
                target=resolved_path,
                kind=edge_kind,
                symbols=set(symbols),
                is_wildcard=is_wildcard,
                import_locations=[import_location],
            )
            graph.add_edge(edge)

        logger.debug(
            "processed_import",
            source=current_module,
            target=resolved_path,
            kind=kind.value,
            edge_kind=edge_kind.value,
            symbols=symbols,
        )

    def _parse_import(self, full_symbol: str, imported_symbols: list[str]) -> tuple[str, list[str]]:
        """
        Parse import to extract module path and symbols.

        Args:
            full_symbol: Full import symbol (e.g., "src.foundation.ir.models")
            imported_symbols: List of imported symbols (for "from X import Y")

        Returns:
            Tuple of (module_path, symbols)
        """
        # If there are imported symbols, full_symbol is the module
        if imported_symbols and imported_symbols != ["*"]:
            return (full_symbol, imported_symbols)

        # If wildcard, full_symbol is the module
        if imported_symbols == ["*"]:
            return (full_symbol, ["*"])

        # Otherwise, it's a module import
        return (full_symbol, [])

    def _reconstruct_import_statement(self, import_path: str, symbols: list[str], is_wildcard: bool) -> str:
        """
        Reconstruct import statement for display.

        Args:
            import_path: Module path
            symbols: Imported symbols
            is_wildcard: Whether this is a wildcard import

        Returns:
            Import statement string
        """
        if is_wildcard:
            return f"from {import_path} import *"
        elif symbols:
            return f"from {import_path} import {', '.join(symbols)}"
        else:
            return f"import {import_path}"


def build_dependency_graph(
    ir_documents: list[IRDocument],
    repo_id: str,
    snapshot_id: str,
    repo_root: Path,
) -> DependencyGraph:
    """
    Convenience function to build a dependency graph.

    Args:
        ir_documents: List of IR documents
        repo_id: Repository identifier
        snapshot_id: Commit hash or snapshot ID
        repo_root: Absolute path to repository root

    Returns:
        Complete dependency graph
    """
    builder = DependencyGraphBuilder(
        repo_id=repo_id,
        snapshot_id=snapshot_id,
        repo_root=repo_root,
    )
    return builder.build_from_ir(ir_documents)


def _example_usage():
    """Example demonstrating dependency graph building."""
    from codegraph_engine.code_foundation.infrastructure.parsing import parse_file

    # Parse some files
    repo_root = Path.cwd()
    files_to_parse = [
        repo_root / "src" / "foundation" / "ir" / "models" / "core.py",
        repo_root / "src" / "foundation" / "graph" / "builder.py",
    ]

    ir_documents = []
    for file_path in files_to_parse:
        if file_path.exists():
            doc = parse_file(str(file_path), language="python")
            if doc:
                ir_documents.append(doc)

    if not ir_documents:
        print("No files parsed")
        return

    # Build dependency graph
    graph = build_dependency_graph(
        ir_documents=ir_documents,
        repo_id="semantica-v2",
        snapshot_id="HEAD",
        repo_root=repo_root,
    )

    # Print statistics
    print("\n=== Dependency Graph ===")
    print(graph)
    print("\n=== Statistics ===")
    stats = graph.get_statistics()
    for key, value in stats.items():
        print(f"{key}: {value}")

    # Print some nodes
    print("\n=== Internal Nodes ===")
    for node in graph.get_internal_nodes()[:5]:
        print(f"- {node.module_path}")
        if node.imported_symbols:
            print(f"  Imported symbols: {', '.join(list(node.imported_symbols)[:3])}")

    print("\n=== External Nodes ===")
    for node in graph.get_external_nodes()[:5]:
        print(f"- {node.module_path} ({node.kind.value})")


if __name__ == "__main__":
    _example_usage()
