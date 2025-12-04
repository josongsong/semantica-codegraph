"""
Chunk ↔ IR/Graph Mapping

Maps chunks to IR nodes and Graph nodes with filtering.

Mapping Strategy:
1. Chunk → IRNode: Line-based containment (IR nodes within chunk span)
2. Chunk → GraphNode: Symbol-based + aggregation + filtering
   - Leaf (function): Direct symbol mapping (1:1)
   - Class: Class symbol + public method symbols
   - File/Module/Project: Aggregated from children + filtering

GAP Improvements (2024-11-29):
- GAP #1: Visibility filtering for class methods (public only)
- GAP #2: Structural chunk symbol aggregation with defined vs referenced distinction
- GAP #3: Bidirectional mapping validation
- GAP #4: IR node coverage for external nodes and boundary crossing
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.chunk.models import Chunk, ChunkToGraph, ChunkToIR
    from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument, GraphNode
    from src.contexts.code_foundation.infrastructure.ir.models import IRDocument
from src.common.observability import get_logger

logger = get_logger(__name__)
# ============================================================
# GAP #3: Mapping Validation Result
# ============================================================


@dataclass
class MappingValidationResult:
    """
    Result of bidirectional mapping validation.

    Tracks inconsistencies between chunk-to-graph mappings and actual graph nodes.
    """

    valid: bool = True
    missing_graph_nodes: list[tuple[str, str]] = field(default_factory=list)  # (chunk_id, symbol_id)
    orphaned_symbols: list[str] = field(default_factory=list)  # symbols in graph but not in any chunk
    invalid_mappings: list[tuple[str, str, str]] = field(default_factory=list)  # (chunk_id, symbol_id, reason)
    # GAP H1: Parent-child validation errors
    orphaned_children: list[tuple[str, str]] = field(default_factory=list)  # (chunk_id, missing_parent_id)
    invalid_parent_refs: list[tuple[str, str, str]] = field(default_factory=list)  # (chunk_id, parent_id, reason)

    def add_missing_node(self, chunk_id: str, symbol_id: str) -> None:
        """Add a missing graph node error."""
        self.missing_graph_nodes.append((chunk_id, symbol_id))
        self.valid = False

    def add_orphaned_symbol(self, symbol_id: str) -> None:
        """Add an orphaned symbol (in graph but not mapped to any chunk)."""
        self.orphaned_symbols.append(symbol_id)
        # Orphaned symbols don't invalidate the mapping, just a warning

    def add_invalid_mapping(self, chunk_id: str, symbol_id: str, reason: str) -> None:
        """Add an invalid mapping with reason."""
        self.invalid_mappings.append((chunk_id, symbol_id, reason))
        self.valid = False

    def add_orphaned_child(self, chunk_id: str, missing_parent_id: str) -> None:
        """Add an orphaned child error (GAP H1)."""
        self.orphaned_children.append((chunk_id, missing_parent_id))
        self.valid = False

    def add_invalid_parent_ref(self, chunk_id: str, parent_id: str, reason: str) -> None:
        """Add an invalid parent reference error (GAP H1)."""
        self.invalid_parent_refs.append((chunk_id, parent_id, reason))
        self.valid = False

    def summary(self) -> str:
        """Get summary of validation result."""
        if self.valid and not self.orphaned_symbols:
            return "All mappings valid"

        parts = []
        if self.missing_graph_nodes:
            parts.append(f"{len(self.missing_graph_nodes)} missing graph nodes")
        if self.orphaned_symbols:
            parts.append(f"{len(self.orphaned_symbols)} orphaned symbols (warning)")
        if self.invalid_mappings:
            parts.append(f"{len(self.invalid_mappings)} invalid mappings")
        # GAP H1: Include parent-child errors
        if self.orphaned_children:
            parts.append(f"{len(self.orphaned_children)} orphaned children")
        if self.invalid_parent_refs:
            parts.append(f"{len(self.invalid_parent_refs)} invalid parent refs")

        status = "INVALID" if not self.valid else "VALID with warnings"
        return f"{status}: {', '.join(parts)}"


# ============================================================
# GAP #2: Symbol Aggregation Context
# ============================================================


@dataclass
class SymbolAggregation:
    """
    Symbol aggregation context for structural chunks.

    Distinguishes between:
    - defined_symbols: Symbols defined directly in this chunk
    - direct_children_symbols: Symbols from direct children
    - transitive_symbols: Symbols from all descendants (transitive)
    - public_api_symbols: Only public symbols exposed as API
    """

    defined_symbols: set[str] = field(default_factory=set)
    direct_children_symbols: set[str] = field(default_factory=set)
    transitive_symbols: set[str] = field(default_factory=set)
    public_api_symbols: set[str] = field(default_factory=set)

    def all_symbols(self) -> set[str]:
        """Get all symbols (union of all sets)."""
        return self.defined_symbols | self.direct_children_symbols | self.transitive_symbols

    def api_surface(self) -> set[str]:
        """Get API surface symbols (public only)."""
        return self.public_api_symbols


class ChunkMapper:
    """
    Maps chunks to IR nodes based on line containment.

    GAP #4 Improvements:
    - Handle external IR nodes (no line ranges)
    - Handle IR nodes crossing chunk boundaries
    - Track unmapped IR nodes for debugging

    Usage:
        mapper = ChunkMapper()
        chunk_to_ir = mapper.map_ir(chunks, ir_doc)
    """

    def __init__(self, include_external_nodes: bool = False):
        """
        Initialize chunk mapper.

        Args:
            include_external_nodes: Whether to map external IR nodes (no line ranges)
                                   to structural chunks (file/module level)
        """
        self.include_external_nodes = include_external_nodes

    def map_ir(self, chunks: list["Chunk"], ir_doc: "IRDocument") -> "ChunkToIR":
        """
        Map chunks to IR nodes using IntervalTree for O(n log n) performance.

        OPTIMIZED: Changed from O(nodes × chunks) to O(n log n) using spatial indexing.

        GAP #4 Improvements:
        - External nodes (no line ranges) mapped to file/module chunks
        - Boundary-crossing nodes mapped to smallest containing chunk
        - Tracks unmapped nodes for debugging

        Strategy: IR node is mapped to chunk if its line range is fully
        contained within the chunk's line range.

        Args:
            chunks: List of chunks
            ir_doc: IR document

        Returns:
            Mapping from chunk ID to set of IR node IDs
        """
        from src.contexts.code_foundation.infrastructure.chunk.models import ChunkToIR

        mapping: ChunkToIR = {c.chunk_id: set() for c in chunks}
        unmapped_nodes: list[str] = []

        # OPTIMIZATION: Build IntervalTree per file for O(n log n) lookup
        # Instead of O(nodes × chunks) nested loop
        try:
            from intervaltree import IntervalTree

            use_interval_tree = True
        except ImportError:
            logger.warning("intervaltree not installed - using O(n²) fallback. Install: pip install intervaltree")
            use_interval_tree = False

        # GAP #4: Build file chunk index for external nodes
        file_chunks: dict[str, str] = {}  # file_path -> file chunk_id
        module_chunks: dict[str, str] = {}  # module_path -> module chunk_id
        for chunk in chunks:
            if chunk.kind == "file" and chunk.file_path:
                file_chunks[chunk.file_path] = chunk.chunk_id
            elif chunk.kind == "module" and chunk.module_path:
                module_chunks[chunk.module_path] = chunk.chunk_id

        if use_interval_tree:
            # Build interval trees per file (O(chunks log chunks))
            trees_by_file: dict[str, IntervalTree] = {}

            for chunk in chunks:
                if chunk.start_line is None or chunk.end_line is None or not chunk.file_path:
                    continue

                if chunk.file_path not in trees_by_file:
                    trees_by_file[chunk.file_path] = IntervalTree()

                # IntervalTree uses half-open intervals [start, end)
                # So we add 1 to end_line to make it inclusive
                trees_by_file[chunk.file_path].addi(chunk.start_line, chunk.end_line + 1, chunk.chunk_id)

            # Map IR nodes to chunks (O(nodes log chunks))
            for ir_node in ir_doc.nodes:
                mapped = False

                # GAP #4: Handle external nodes (no line ranges)
                if ir_node.span.start_line is None or ir_node.span.end_line is None:
                    if self.include_external_nodes:
                        # Map to file chunk if available
                        file_chunk_id = file_chunks.get(ir_node.file_path)
                        if file_chunk_id:
                            mapping[file_chunk_id].add(ir_node.id)
                            mapped = True
                    if not mapped:
                        unmapped_nodes.append(ir_node.id)
                    continue

                tree = trees_by_file.get(ir_node.file_path)
                if not tree:
                    # GAP #4: Node in file with no chunks - map to file chunk
                    file_chunk_id = file_chunks.get(ir_node.file_path)
                    if file_chunk_id:
                        mapping[file_chunk_id].add(ir_node.id)
                        mapped = True
                    if not mapped:
                        unmapped_nodes.append(ir_node.id)
                    continue

                # Find all chunks that contain this IR node
                # Query with half-open interval
                overlaps = tree.overlap(ir_node.span.start_line, ir_node.span.end_line + 1)

                for interval in overlaps:
                    chunk_id = interval.data
                    # Double-check full containment (interval.overlap is inclusive)
                    chunk_start = interval.begin
                    chunk_end = interval.end - 1  # Convert back to inclusive

                    if ir_node.span.start_line >= chunk_start and ir_node.span.end_line <= chunk_end:
                        mapping[chunk_id].add(ir_node.id)
                        mapped = True

                # GAP #4: Handle boundary-crossing nodes
                if not mapped and overlaps:
                    # Node crosses chunk boundaries - map to smallest overlapping chunk
                    smallest_interval = min(overlaps, key=lambda iv: iv.end - iv.begin)
                    mapping[smallest_interval.data].add(ir_node.id)
                    mapped = True
                    logger.debug(
                        f"IR node {ir_node.id} crosses chunk boundaries, "
                        f"mapped to smallest overlapping chunk {smallest_interval.data}"
                    )

                if not mapped:
                    unmapped_nodes.append(ir_node.id)

        else:
            # Fallback: O(n²) nested loop (old implementation)
            for ir_node in ir_doc.nodes:
                mapped = False

                # GAP #4: Handle external nodes
                if ir_node.span.start_line is None or ir_node.span.end_line is None:
                    if self.include_external_nodes:
                        file_chunk_id = file_chunks.get(ir_node.file_path)
                        if file_chunk_id:
                            mapping[file_chunk_id].add(ir_node.id)
                            mapped = True
                    if not mapped:
                        unmapped_nodes.append(ir_node.id)
                    continue

                best_chunk: tuple[str, int] | None = None  # (chunk_id, span_size)

                for chunk in chunks:
                    if chunk.start_line is None or chunk.end_line is None:
                        continue

                    if (
                        ir_node.span.start_line >= chunk.start_line
                        and ir_node.span.end_line <= chunk.end_line
                        and ir_node.file_path == chunk.file_path
                    ):
                        mapping[chunk.chunk_id].add(ir_node.id)
                        mapped = True

                    # GAP #4: Track best overlapping chunk for boundary crossing
                    elif (
                        ir_node.file_path == chunk.file_path
                        and ir_node.span.start_line <= chunk.end_line
                        and ir_node.span.end_line >= chunk.start_line
                    ):
                        span_size = chunk.end_line - chunk.start_line
                        if best_chunk is None or span_size < best_chunk[1]:
                            best_chunk = (chunk.chunk_id, span_size)

                # GAP #4: Handle boundary-crossing
                if not mapped and best_chunk:
                    mapping[best_chunk[0]].add(ir_node.id)
                    mapped = True

                if not mapped:
                    unmapped_nodes.append(ir_node.id)

        # Log mapping statistics
        total_mappings = sum(len(ir_ids) for ir_ids in mapping.values())
        chunks_with_mappings = len(chunks) if len(chunks) > 0 else 1
        logger.debug(
            f"Mapped {total_mappings} IR nodes to {len(chunks)} chunks "
            f"({total_mappings / chunks_with_mappings:.1f} IR nodes per chunk)"
        )

        if unmapped_nodes:
            logger.debug(f"GAP #4: {len(unmapped_nodes)} IR nodes could not be mapped to any chunk")

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

    GAP Improvements:
    - GAP #1: Visibility filtering for class methods (public only)
    - GAP #2: Symbol aggregation with defined vs referenced distinction
    - GAP #3: Bidirectional mapping validation

    Strategy:
    1. Leaf chunks (function): Direct symbol mapping (1:1)
    2. Class chunks: Class symbol + public method symbols (GAP #1: visibility filter)
    3. Structural chunks (file/module/project/repo): Aggregate from children + filter

    Usage:
        mapper = ChunkGraphMapper(node_filter=GraphNodeFilter())
        chunk_to_graph = mapper.map_graph(chunks, graph_doc)

        # GAP #3: Validate mappings
        validation = mapper.validate_mappings(chunk_to_graph, graph_doc)
        if not validation.valid:
            logger.warning(f"Mapping issues: {validation.summary()}")
    """

    def __init__(
        self,
        node_filter: GraphNodeFilter | None = None,
        visibility_filter: bool = True,  # GAP #1: Enable visibility filtering
        public_only_for_classes: bool = True,  # GAP #1: Only public methods for class chunks
    ):
        """
        Initialize chunk-graph mapper.

        Args:
            node_filter: Graph node filter (defaults to GraphNodeFilter())
            visibility_filter: Enable visibility-based filtering (GAP #1)
            public_only_for_classes: Only include public methods in class mappings (GAP #1)
        """
        self.node_filter = node_filter or GraphNodeFilter()
        self.visibility_filter = visibility_filter
        self.public_only_for_classes = public_only_for_classes

    def map_graph(self, chunks: list["Chunk"], graph_doc: "GraphDocument") -> "ChunkToGraph":
        """
        Map chunks to graph nodes.

        GAP #1: Now filters class methods by visibility (public only by default)
        GAP #2: Tracks symbol aggregation context

        Args:
            chunks: List of chunks
            graph_doc: Graph document

        Returns:
            Mapping from chunk ID to set of graph node IDs
        """
        from src.contexts.code_foundation.infrastructure.chunk.models import ChunkToGraph

        mapping: ChunkToGraph = {c.chunk_id: set() for c in chunks}

        # GAP #2: Track aggregation context per chunk
        aggregations: dict[str, SymbolAggregation] = {c.chunk_id: SymbolAggregation() for c in chunks}

        # Build chunk lookup and hierarchy
        chunk_by_id = {c.chunk_id: c for c in chunks}

        # Phase 1: Direct mapping for leaf chunks (function/method)
        for chunk in chunks:
            if chunk.kind == "function" and chunk.symbol_id is not None:
                # Direct symbol mapping
                mapping[chunk.chunk_id].add(chunk.symbol_id)
                aggregations[chunk.chunk_id].defined_symbols.add(chunk.symbol_id)

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
                aggregations[chunk.chunk_id].defined_symbols.add(chunk.symbol_id)

                # Add method symbols from children
                for child_id in chunk.children:
                    child = chunk_by_id.get(child_id)
                    if child and child.kind == "function" and child.symbol_id:
                        # GAP #1: Filter by visibility (public only)
                        if self._should_include_method(child):
                            mapping[chunk.chunk_id].add(child.symbol_id)
                            aggregations[chunk.chunk_id].direct_children_symbols.add(child.symbol_id)

                            # GAP #2: Track public API symbols
                            if self._is_public_symbol(child):
                                aggregations[chunk.chunk_id].public_api_symbols.add(child.symbol_id)

        # Phase 3: Structural chunks - aggregate from children with filtering
        structural_kinds = {"file", "module", "project", "repo"}
        for chunk in chunks:
            if chunk.kind not in structural_kinds:
                continue

            # GAP #2: Aggregate symbols with context
            aggregation = self._collect_descendant_symbols_with_context(chunk, chunk_by_id, mapping, aggregations)
            aggregations[chunk.chunk_id] = aggregation

            # Filter symbols based on visibility and node type
            for symbol_id in aggregation.all_symbols():
                # Find graph node
                graph_node = self._find_graph_node(symbol_id, graph_doc)
                if graph_node and self.node_filter.include(graph_node):
                    mapping[chunk.chunk_id].add(symbol_id)

        # Log mapping statistics
        total_mappings = sum(len(graph_ids) for graph_ids in mapping.values())
        chunks_count = len(chunks) if len(chunks) > 0 else 1
        logger.debug(
            f"Mapped {total_mappings} graph nodes to {len(chunks)} chunks "
            f"({total_mappings / chunks_count:.1f} graph nodes per chunk)"
        )

        return mapping

    def map_graph_with_aggregation(
        self, chunks: list["Chunk"], graph_doc: "GraphDocument"
    ) -> tuple["ChunkToGraph", dict[str, SymbolAggregation]]:
        """
        Map chunks to graph nodes and return aggregation context.

        GAP #2: Returns both mapping and aggregation context for analysis.

        Args:
            chunks: List of chunks
            graph_doc: Graph document

        Returns:
            Tuple of (mapping, aggregations)
        """
        from src.contexts.code_foundation.infrastructure.chunk.models import ChunkToGraph

        mapping: ChunkToGraph = {c.chunk_id: set() for c in chunks}
        aggregations: dict[str, SymbolAggregation] = {c.chunk_id: SymbolAggregation() for c in chunks}

        chunk_by_id = {c.chunk_id: c for c in chunks}

        # Phase 1: Leaf chunks
        for chunk in chunks:
            if chunk.kind == "function" and chunk.symbol_id is not None:
                mapping[chunk.chunk_id].add(chunk.symbol_id)
                aggregations[chunk.chunk_id].defined_symbols.add(chunk.symbol_id)

        # Phase 2: Class-like chunks
        class_like_kinds = {"class", "service", "repository", "config", "job", "middleware", "route"}

        for chunk in chunks:
            if chunk.kind in class_like_kinds and chunk.symbol_id is not None:
                mapping[chunk.chunk_id].add(chunk.symbol_id)
                aggregations[chunk.chunk_id].defined_symbols.add(chunk.symbol_id)

                for child_id in chunk.children:
                    child = chunk_by_id.get(child_id)
                    if child and child.kind == "function" and child.symbol_id:
                        if self._should_include_method(child):
                            mapping[chunk.chunk_id].add(child.symbol_id)
                            aggregations[chunk.chunk_id].direct_children_symbols.add(child.symbol_id)
                            if self._is_public_symbol(child):
                                aggregations[chunk.chunk_id].public_api_symbols.add(child.symbol_id)

        # Phase 3: Structural chunks
        structural_kinds = {"file", "module", "project", "repo"}
        for chunk in chunks:
            if chunk.kind not in structural_kinds:
                continue

            aggregation = self._collect_descendant_symbols_with_context(chunk, chunk_by_id, mapping, aggregations)
            aggregations[chunk.chunk_id] = aggregation

            for symbol_id in aggregation.all_symbols():
                graph_node = self._find_graph_node(symbol_id, graph_doc)
                if graph_node and self.node_filter.include(graph_node):
                    mapping[chunk.chunk_id].add(symbol_id)

        return mapping, aggregations

    def validate_mappings(self, mapping: "ChunkToGraph", graph_doc: "GraphDocument") -> MappingValidationResult:
        """
        Validate chunk-to-graph mappings (GAP #3).

        Checks:
        1. All mapped symbols exist in the graph
        2. Detects orphaned symbols (in graph but not in any chunk)
        3. Validates mapping consistency

        Args:
            mapping: Chunk-to-graph mapping to validate
            graph_doc: Graph document

        Returns:
            MappingValidationResult with validation details
        """
        result = MappingValidationResult()

        # Collect all mapped symbols
        all_mapped_symbols: set[str] = set()
        for chunk_id, symbol_ids in mapping.items():
            for symbol_id in symbol_ids:
                all_mapped_symbols.add(symbol_id)

                # Check if symbol exists in graph
                graph_node = self._find_graph_node(symbol_id, graph_doc)
                if graph_node is None:
                    result.add_missing_node(chunk_id, symbol_id)

        # Check for orphaned symbols (in graph but not mapped)
        for node in graph_doc.graph_nodes.values():
            if node.id not in all_mapped_symbols:
                # Only check important node types
                if self.node_filter.include(node):
                    result.add_orphaned_symbol(node.id)

        if result.valid:
            logger.debug(f"GAP #3: Mapping validation passed - {len(all_mapped_symbols)} symbols verified")
        else:
            logger.warning(f"GAP #3: Mapping validation failed - {result.summary()}")

        return result

    def _should_include_method(self, chunk: "Chunk") -> bool:
        """
        Check if a method chunk should be included in class mapping.

        GAP #1: Implements visibility filtering for class methods.

        Args:
            chunk: Method chunk to check

        Returns:
            True if method should be included
        """
        if not self.visibility_filter:
            return True

        if not self.public_only_for_classes:
            return True

        return self._is_public_symbol(chunk)

    def _is_public_symbol(self, chunk: "Chunk") -> bool:
        """
        Check if chunk represents a public symbol.

        GAP #1: Uses symbol_visibility field for filtering.

        Args:
            chunk: Chunk to check

        Returns:
            True if symbol is public (or visibility unknown)
        """
        # If visibility is not set, assume public (conservative)
        if chunk.symbol_visibility is None:
            return True

        return chunk.symbol_visibility == "public"

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

    def _collect_descendant_symbols_with_context(
        self,
        chunk: "Chunk",
        chunk_by_id: dict[str, "Chunk"],
        mapping: "ChunkToGraph",
        aggregations: dict[str, SymbolAggregation],
    ) -> SymbolAggregation:
        """
        Collect descendant symbols with aggregation context (GAP #2).

        Distinguishes between:
        - Direct children symbols
        - Transitive (grandchildren+) symbols
        - Public API symbols

        Args:
            chunk: Parent chunk
            chunk_by_id: Chunk lookup by ID
            mapping: Current chunk-to-graph mapping
            aggregations: Aggregation context per chunk

        Returns:
            SymbolAggregation with context
        """
        result = SymbolAggregation()

        # Add own symbol if exists
        if chunk.symbol_id:
            result.defined_symbols.add(chunk.symbol_id)

        for child_id in chunk.children:
            child = chunk_by_id.get(child_id)
            if not child:
                continue

            child_agg = aggregations.get(child_id, SymbolAggregation())

            # Direct children symbols
            result.direct_children_symbols.update(mapping.get(child_id, set()))

            # Transitive symbols (grandchildren and beyond)
            result.transitive_symbols.update(child_agg.direct_children_symbols)
            result.transitive_symbols.update(child_agg.transitive_symbols)

            # Public API symbols
            result.public_api_symbols.update(child_agg.public_api_symbols)

            # Add child's defined symbols to public API if public
            if child.symbol_visibility == "public" and child.symbol_id:
                result.public_api_symbols.add(child.symbol_id)

        return result

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


# ============================================================
# GAP H1: Parent-Child Relationship Validation
# ============================================================


def validate_chunk_hierarchy(chunks: list["Chunk"]) -> MappingValidationResult:
    """
    Validate parent-child relationships in chunk hierarchy (GAP H1).

    Checks:
    1. All parent_id references point to existing chunks
    2. All children references point to existing chunks
    3. Bidirectional consistency (parent.children contains child, child.parent_id points to parent)
    4. No circular references
    5. Root chunks have parent_id=None

    Args:
        chunks: List of chunks to validate

    Returns:
        MappingValidationResult with validation details
    """
    result = MappingValidationResult()

    # Build chunk lookup for O(1) access
    chunk_by_id: dict[str, Chunk] = {c.chunk_id: c for c in chunks}

    # Track visited chunks for cycle detection
    visited: set[str] = set()
    in_path: set[str] = set()

    def detect_cycle(chunk_id: str) -> bool:
        """Detect cycles using DFS."""
        if chunk_id in in_path:
            return True  # Cycle detected
        if chunk_id in visited:
            return False  # Already validated

        chunk = chunk_by_id.get(chunk_id)
        if not chunk:
            return False

        in_path.add(chunk_id)
        visited.add(chunk_id)

        # Check parent reference
        if chunk.parent_id and detect_cycle(chunk.parent_id):
            return True

        in_path.remove(chunk_id)
        return False

    for chunk in chunks:
        # 1. Validate parent_id reference exists
        if chunk.parent_id is not None:
            if chunk.parent_id not in chunk_by_id:
                result.add_orphaned_child(chunk.chunk_id, chunk.parent_id)
                logger.warning(f"GAP H1: Chunk {chunk.chunk_id} has invalid parent_id: {chunk.parent_id}")
            else:
                # 3. Check bidirectional consistency: parent.children should contain this chunk
                parent = chunk_by_id[chunk.parent_id]
                if chunk.chunk_id not in parent.children:
                    result.add_invalid_parent_ref(
                        chunk.chunk_id,
                        chunk.parent_id,
                        f"Parent {chunk.parent_id} doesn't list {chunk.chunk_id} as child",
                    )

        # 2. Validate children references exist
        for child_id in chunk.children:
            if child_id not in chunk_by_id:
                result.add_invalid_parent_ref(
                    chunk.chunk_id,
                    child_id,
                    f"Child {child_id} doesn't exist",
                )
            else:
                # 3. Check bidirectional consistency: child.parent_id should point to this chunk
                child = chunk_by_id[child_id]
                if child.parent_id != chunk.chunk_id:
                    result.add_invalid_parent_ref(
                        chunk.chunk_id,
                        child_id,
                        f"Child {child_id} has parent_id={child.parent_id}, expected {chunk.chunk_id}",
                    )

        # 4. Check for cycles
        if detect_cycle(chunk.chunk_id):
            result.add_invalid_parent_ref(
                chunk.chunk_id,
                chunk.parent_id or "root",
                "Circular reference detected in hierarchy",
            )

    # 5. Validate root chunks
    root_chunks = [c for c in chunks if c.parent_id is None]
    if not root_chunks:
        logger.warning("GAP H1: No root chunk found (all chunks have parent_id)")
    elif len(root_chunks) > 1:
        # Multiple roots - might be intentional for multi-repo scenarios
        logger.debug(f"GAP H1: Found {len(root_chunks)} root chunks")

    if result.valid:
        logger.debug(f"GAP H1: Hierarchy validation passed - {len(chunks)} chunks verified")
    else:
        logger.warning(f"GAP H1: Hierarchy validation failed - {result.summary()}")

    return result


def validate_chunk_spans(chunks: list["Chunk"]) -> MappingValidationResult:
    """
    Validate chunk span containment (GAP H1 extension).

    For hierarchical chunks (parent contains children), validates that
    child spans are fully contained within parent spans.

    Args:
        chunks: List of chunks to validate

    Returns:
        MappingValidationResult with validation details
    """
    result = MappingValidationResult()

    # Build chunk lookup
    chunk_by_id: dict[str, Chunk] = {c.chunk_id: c for c in chunks}

    for chunk in chunks:
        if chunk.parent_id is None:
            continue

        parent = chunk_by_id.get(chunk.parent_id)
        if not parent:
            continue

        # Skip structural chunks without spans
        if chunk.start_line is None or chunk.end_line is None:
            continue
        if parent.start_line is None or parent.end_line is None:
            continue

        # Only validate if both are in same file
        if chunk.file_path != parent.file_path:
            continue

        # Check containment: child span should be within parent span
        if chunk.start_line < parent.start_line or chunk.end_line > parent.end_line:
            result.add_invalid_parent_ref(
                chunk.chunk_id,
                parent.chunk_id,
                f"Child span [{chunk.start_line}:{chunk.end_line}] "
                f"exceeds parent span [{parent.start_line}:{parent.end_line}]",
            )

    if result.valid:
        logger.debug("GAP H1: Span containment validation passed")
    else:
        logger.warning(f"GAP H1: Span containment validation failed - {result.summary()}")

    return result
