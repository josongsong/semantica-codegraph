"""
Chunk ↔ IR/Graph Mapping

Maps chunks to IR nodes and Graph nodes with filtering.

Mapping Strategy:
1. Chunk → IRNode: Line-based containment (IR nodes within chunk span)
2. Chunk → GraphNode: Symbol-based + aggregation + filtering
   - Leaf (function): Direct symbol mapping (1:1)
   - Class: Class symbol + public method symbols
   - File/Module/Project: Aggregated from children + filtering
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..graph.models import GraphDocument, GraphNode
    from ..ir.models import IRDocument
    from .models import Chunk, ChunkToGraph, ChunkToIR

logger = logging.getLogger(__name__)


class ChunkMapper:
    """
    Maps chunks to IR nodes based on line containment.

    Usage:
        mapper = ChunkMapper()
        chunk_to_ir = mapper.map_ir(chunks, ir_doc)
    """

    def map_ir(self, chunks: list["Chunk"], ir_doc: "IRDocument") -> "ChunkToIR":
        """
        Map chunks to IR nodes.

        Strategy: IR node is mapped to chunk if its line range is fully
        contained within the chunk's line range.

        Args:
            chunks: List of chunks
            ir_doc: IR document

        Returns:
            Mapping from chunk ID to set of IR node IDs
        """
        from .models import ChunkToIR

        mapping: ChunkToIR = {c.chunk_id: set() for c in chunks}

        for ir_node in ir_doc.nodes:
            # Skip nodes without line information
            if ir_node.span.start_line is None or ir_node.span.end_line is None:
                continue

            # Find containing chunks
            for chunk in chunks:
                if chunk.start_line is None or chunk.end_line is None:
                    continue

                # Check if IR node is fully contained in chunk
                if (
                    ir_node.span.start_line >= chunk.start_line
                    and ir_node.span.end_line <= chunk.end_line
                    and ir_node.file_path == chunk.file_path
                ):
                    mapping[chunk.chunk_id].add(ir_node.id)

        # Log mapping statistics
        total_mappings = sum(len(ir_ids) for ir_ids in mapping.values())
        logger.debug(
            f"Mapped {total_mappings} IR nodes to {len(chunks)} chunks "
            f"({total_mappings / len(chunks):.1f} IR nodes per chunk)"
        )

        return mapping


class GraphNodeFilter:
    """
    Filters graph nodes for chunk mapping.

    Inclusion policy:
    - Include: Functions, classes, methods, imports, types, etc.
    - Exclude: Variables, fields (noise for RAG)

    Note: GraphNodeKind enum values are capitalized (e.g., "Function", "Class")

    Usage:
        filter = GraphNodeFilter()
        if filter.include(node):
            # Include in chunk mapping
    """

    def __init__(
        self,
        include_kinds: set[str] | None = None,
        exclude_kinds: set[str] | None = None,
    ):
        """
        Initialize graph node filter.

        Args:
            include_kinds: Set of node kinds to include (if None, use defaults)
            exclude_kinds: Set of node kinds to exclude (if None, use defaults)
        """
        # Default inclusion: Important symbols (match GraphNodeKind enum values)
        self.include_kinds = include_kinds or {
            "Function",  # Top-level functions
            "Method",  # Class methods
            "Class",  # Classes
            "Type",  # Type definitions
            "Signature",  # Function signatures
            "Module",  # Modules
            "File",  # Files
            # Phase 3: Extended node types
            "Route",  # API routes
            "Service",  # Service layer
            "Repository",  # Data access layer
            "Config",  # Configuration
            "Job",  # Background jobs
            "Middleware",  # Middleware components
        }

        # Default exclusion: Noise symbols
        self.exclude_kinds = exclude_kinds or {
            "Variable",  # Variables (too noisy for RAG)
            "Field",  # Class fields (too noisy for RAG)
            "CfgBlock",  # CFG blocks (internal)
        }

    def include(self, node: "GraphNode") -> bool:
        """
        Check if graph node should be included in chunk mapping.

        Args:
            node: Graph node to check

        Returns:
            True if node should be included
        """
        # Get kind as string (GraphNodeKind is str Enum)
        kind_str = node.kind.value if hasattr(node.kind, "value") else str(node.kind)

        # Check exclusion first (higher priority)
        if kind_str in self.exclude_kinds:
            return False

        # Check inclusion
        if kind_str in self.include_kinds:
            return True

        # Default: include unknown kinds (safe for now)
        # We can change this to exclude later if needed
        logger.debug(f"Unknown node kind '{kind_str}' - including in mapping")
        return True


class ChunkGraphMapper:
    """
    Maps chunks to graph nodes with aggregation and filtering.

    Strategy:
    1. Leaf chunks (function): Direct symbol mapping (1:1)
    2. Class chunks: Class symbol + public method symbols
    3. Structural chunks (file/module/project/repo): Aggregate from children + filter

    Usage:
        mapper = ChunkGraphMapper(node_filter=GraphNodeFilter())
        chunk_to_graph = mapper.map_graph(chunks, graph_doc)
    """

    def __init__(self, node_filter: GraphNodeFilter | None = None):
        """
        Initialize chunk-graph mapper.

        Args:
            node_filter: Graph node filter (defaults to GraphNodeFilter())
        """
        self.node_filter = node_filter or GraphNodeFilter()

    def map_graph(self, chunks: list["Chunk"], graph_doc: "GraphDocument") -> "ChunkToGraph":
        """
        Map chunks to graph nodes.

        Args:
            chunks: List of chunks
            graph_doc: Graph document

        Returns:
            Mapping from chunk ID to set of graph node IDs
        """
        from .models import ChunkToGraph

        mapping: ChunkToGraph = {c.chunk_id: set() for c in chunks}

        # Build chunk lookup and hierarchy
        chunk_by_id = {c.chunk_id: c for c in chunks}

        # Phase 1: Direct mapping for leaf chunks (function/method)
        for chunk in chunks:
            if chunk.kind == "function" and chunk.symbol_id is not None:
                # Direct symbol mapping
                mapping[chunk.chunk_id].add(chunk.symbol_id)

        # Phase 2: Class/Extended chunks - include symbol + public methods
        # Extended kinds (Phase 3): service, repository, config, job, middleware, route
        class_like_kinds = {
            "class",
            # Phase 3 extended types
            "service",
            "repository",
            "config",
            "job",
            "middleware",
            "route",
        }

        for chunk in chunks:
            if chunk.kind in class_like_kinds and chunk.symbol_id is not None:
                mapping[chunk.chunk_id].add(chunk.symbol_id)

                # Add public method symbols from children
                for child_id in chunk.children:
                    child = chunk_by_id.get(child_id)
                    if child and child.kind == "function" and child.symbol_id:
                        # TODO: Filter by visibility (public only)
                        mapping[chunk.chunk_id].add(child.symbol_id)

        # Phase 3: Structural chunks - aggregate from children with filtering
        structural_kinds = {"file", "module", "project", "repo"}
        for chunk in chunks:
            if chunk.kind not in structural_kinds:
                continue

            # Aggregate symbols from all descendants
            descendant_symbols = self._collect_descendant_symbols(chunk, chunk_by_id, mapping)

            # Filter symbols
            for symbol_id in descendant_symbols:
                # Find graph node
                graph_node = self._find_graph_node(symbol_id, graph_doc)
                if graph_node and self.node_filter.include(graph_node):
                    mapping[chunk.chunk_id].add(symbol_id)

        # Log mapping statistics
        total_mappings = sum(len(graph_ids) for graph_ids in mapping.values())
        logger.debug(
            f"Mapped {total_mappings} graph nodes to {len(chunks)} chunks "
            f"({total_mappings / len(chunks):.1f} graph nodes per chunk)"
        )

        return mapping

    def _collect_descendant_symbols(
        self,
        chunk: "Chunk",
        chunk_by_id: dict[str, "Chunk"],
        mapping: "ChunkToGraph",
    ) -> set[str]:
        """
        Recursively collect all symbols from descendant chunks.

        Args:
            chunk: Parent chunk
            chunk_by_id: Chunk lookup by ID
            mapping: Current chunk-to-graph mapping

        Returns:
            Set of descendant symbol IDs
        """
        symbols = set()

        # Add direct children symbols
        for child_id in chunk.children:
            child = chunk_by_id.get(child_id)
            if not child:
                continue

            # Add child's symbols
            symbols.update(mapping.get(child_id, set()))

            # Recursively collect grandchildren
            symbols.update(self._collect_descendant_symbols(child, chunk_by_id, mapping))

        return symbols

    def _find_graph_node(self, symbol_id: str, graph_doc: "GraphDocument") -> "GraphNode | None":
        """
        Find graph node by symbol ID.

        Args:
            symbol_id: Symbol ID to find
            graph_doc: Graph document

        Returns:
            Graph node if found, None otherwise
        """
        return graph_doc.get_node(symbol_id)
