"""
Graph Builder

Converts Structural IR + Semantic IR → GraphDocument.

Phase 1: GraphNode conversion
Phase 2: GraphEdge conversion + External node creation
Phase 3: GraphIndex construction
"""

from contextlib import nullcontext
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.graph.models import (
    GraphDocument,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument, NodeKind
from codegraph_engine.code_foundation.infrastructure.semantic_ir.context import SemanticIrSnapshot

logger = get_logger(__name__)
if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.dfg.models import VariableEntity
    from codegraph_engine.code_foundation.infrastructure.profiling import Profiler
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import ControlFlowBlock as CFGBlock
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.signature.models import SignatureEntity
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.models import TypeEntity

# ============================================================
# GraphBuilder
# ============================================================


class GraphBuilder:
    """
    Builds GraphDocument from IR + Semantic IR.

    Conversion strategy:
    1. IR Nodes → GraphNodes (structural)
    2. TypeEntity → GraphNode(Type) (semantic)
    3. SignatureEntity → GraphNode(Signature) (semantic)
    4. CFGBlock → GraphNode(CfgBlock) (semantic)
    5. Auto-generate Module nodes from file paths
    6. Convert edges (IR + Semantic)
    7. Build indexes
    """

    def __init__(self, profiler: "Profiler | None" = None):
        self._module_cache: dict[str, GraphNode] = {}
        self._profiler = profiler

    def build_full(
        self,
        ir_doc: IRDocument,
        semantic_snapshot: SemanticIrSnapshot | None,
    ) -> GraphDocument:
        """
        Build complete graph from IR + Semantic IR.

        Args:
            ir_doc: Structural IR document
            semantic_snapshot: Semantic IR snapshot (optional - may be None if semantic IR failed)

        Returns:
            GraphDocument with all nodes, edges, and indexes
        """

        # Helper to use profiler or no-op context
        def _phase(name: str, **attrs):
            if self._profiler:
                return self._profiler.phase(name, **attrs)
            return nullcontext()

        with _phase("graph_build"):
            graph = GraphDocument(
                repo_id=ir_doc.repo_id,
                snapshot_id=ir_doc.snapshot_id,
            )

            # Phase 1: Convert IR nodes (always available)
            with _phase("convert_ir_nodes"):
                self._convert_ir_nodes(ir_doc, graph)

            if self._profiler:
                self._profiler.increment("graph_nodes_from_ir", len(graph.graph_nodes))

            # Phase 2: Convert semantic nodes (optional - graceful degradation)
            if semantic_snapshot:
                try:
                    with _phase("convert_semantic_nodes"):
                        self._convert_semantic_nodes(semantic_snapshot, graph, ir_doc)
                        logger.info("Semantic nodes converted successfully")

                    if self._profiler:
                        self._profiler.increment(
                            "graph_nodes_from_semantic", len(graph.graph_nodes) - len(ir_doc.nodes)
                        )
                except Exception as e:
                    logger.warning(f"Failed to convert semantic nodes: {e}", exc_info=True)
                    # Continue without semantic nodes (structural graph only)
            else:
                logger.warning("Semantic snapshot not available - building structural graph only")

            # Phase 3: Convert edges
            with _phase("convert_edges"):
                self._convert_edges(ir_doc, semantic_snapshot, graph)

            if self._profiler:
                self._profiler.increment("graph_edges_created", len(graph.graph_edges))

            # Phase 4: Build indexes
            with _phase("build_indexes"):
                self._build_indexes(graph)

            return graph

    # ============================================================
    # Phase 1: Node Conversion
    # ============================================================

    def _convert_ir_nodes(self, ir_doc: IRDocument, graph: GraphDocument):
        """
        Convert IR nodes to graph nodes.

        Handles: FILE, MODULE, CLASS, FUNCTION, METHOD, VARIABLE, FIELD, etc.
        Phase 3: Uses role field to create specialized nodes (Route, Service, Repository)
        """
        # logger already defined at module level

        total_ir_nodes = len(ir_doc.nodes)
        skipped_nodes = 0
        failed_nodes = 0
        success_nodes = 0

        for node in ir_doc.nodes:
            # Skip nodes that don't become graph nodes (IMPORT, CALL, etc.)
            try:
                # Phase 3: Pass role to mapper for specialized node type detection
                graph_kind = self._map_ir_kind_to_graph_kind(node.kind, node.role)
            except ValueError:
                # Expected - skip unsupported kinds (they become edges instead)
                skipped_nodes += 1
                continue
            except KeyError as e:
                # Missing required attribute
                logger.error(f"Missing attribute for node {node.id}: {e}")
                failed_nodes += 1
                continue
            except AttributeError as e:
                # Invalid node structure
                logger.error(f"Invalid node structure for {node.id}: {e}")
                failed_nodes += 1
                continue
            except Exception as e:
                # Unexpected error - log with full stack trace
                logger.error(f"Unexpected error mapping node {node.id}: {e}", exc_info=True)
                failed_nodes += 1
                # Re-raise if this looks critical (not a data issue)
                if isinstance(e, MemoryError | SystemError):
                    raise
                continue

            try:
                # Create graph node
                # Store file_path for all nodes (not just FILE) to enable path-based lookups
                graph_node = GraphNode(
                    id=node.id,
                    kind=graph_kind,
                    repo_id=ir_doc.repo_id,
                    snapshot_id=ir_doc.snapshot_id,
                    fqn=node.fqn,
                    name=node.name or "",
                    path=node.file_path,  # Store file_path for all nodes
                    span=node.span,
                    attrs={
                        "language": node.language,
                        "docstring": node.docstring,
                        "role": node.role,
                        "is_test_file": node.is_test_file,
                        "signature_id": node.signature_id,
                        "declared_type_id": node.declared_type_id,
                        "module_path": node.module_path,
                        **node.attrs,  # Include language-specific attrs
                    },
                )

                graph.graph_nodes[graph_node.id] = graph_node
                success_nodes += 1
            except Exception as e:
                logger.warning(f"Failed to create graph node for {node.id}: {e}")
                failed_nodes += 1
                continue

        if total_ir_nodes > 0:
            logger.info(
                f"IR node conversion: {success_nodes}/{total_ir_nodes} success, "
                f"{skipped_nodes} skipped (IMPORT/CALL), {failed_nodes} failed"
            )

        # Auto-generate module nodes from file paths
        self._generate_module_nodes(ir_doc, graph)

    def _generate_module_nodes(self, ir_doc: IRDocument, graph: GraphDocument):
        """
        Auto-generate MODULE nodes from file paths (optimized).

        Example: "src/data/processor.py" → ["src", "src.data"]

        Optimizations:
        - Use Path objects instead of string operations
        - Build paths incrementally with lists
        - Persist cache across builds
        """
        from pathlib import Path

        # Initialize cache if first time (don't clear - persist across builds)
        if not hasattr(self, "_module_cache"):
            self._module_cache = {}

        # Collect all file nodes
        file_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FILE]

        for file_node in file_nodes:
            file_path = Path(file_node.file_path)
            parts = file_path.parts[:-1]  # Exclude filename

            # Skip if no directory structure
            if not parts:
                continue

            # Build paths incrementally with lists (avoid repeated string concatenation)
            path_parts = []
            fqn_parts = []

            for part in parts:
                path_parts.append(part)
                fqn_parts.append(part)

                # Build identifiers
                current_path = "/".join(path_parts)
                current_fqn = ".".join(fqn_parts)
                module_id = f"module:{ir_doc.repo_id}::{current_fqn}"

                # Skip if already generated (cache is authoritative since we add to both simultaneously)
                if module_id in self._module_cache:
                    continue

                # Create module node
                module_node = GraphNode(
                    id=module_id,
                    kind=GraphNodeKind.MODULE,
                    repo_id=ir_doc.repo_id,
                    snapshot_id=ir_doc.snapshot_id,
                    fqn=current_fqn,
                    name=part,
                    path=current_path,
                    span=None,  # Auto-generated, no source location
                    attrs={
                        "language": file_node.language,
                        "auto_generated": True,
                    },
                )

                graph.graph_nodes[module_id] = module_node
                self._module_cache[module_id] = module_node

    def _convert_semantic_nodes(
        self,
        semantic_snapshot: SemanticIrSnapshot,
        graph: GraphDocument,
        ir_doc: IRDocument,
    ):
        """
        Convert semantic IR entities to graph nodes with safety checks.

        Handles: Type, Signature, CfgBlock, DFG Variables
        """
        # logger already defined at module level

        # Convert Type entities (with empty check)
        if semantic_snapshot.types:
            for type_entity in semantic_snapshot.types:
                try:
                    graph_node = self._convert_type_entity(type_entity, ir_doc)
                    graph.graph_nodes[graph_node.id] = graph_node
                except Exception as e:
                    logger.warning(f"Failed to convert type entity {type_entity.id}: {e}")

        # Convert Signature entities (with empty check)
        if semantic_snapshot.signatures:
            for signature_entity in semantic_snapshot.signatures:
                try:
                    graph_node = self._convert_signature_entity(signature_entity, ir_doc)
                    graph.graph_nodes[graph_node.id] = graph_node
                except Exception as e:
                    logger.warning(f"Failed to convert signature entity {signature_entity.id}: {e}")

        # Convert CFG blocks (with empty check)
        if semantic_snapshot.cfg_blocks:
            for cfg_block in semantic_snapshot.cfg_blocks:
                try:
                    graph_node = self._convert_cfg_block(cfg_block, ir_doc)
                    graph.graph_nodes[graph_node.id] = graph_node
                except Exception as e:
                    logger.warning(f"Failed to convert CFG block {cfg_block.id}: {e}")

        # Convert DFG variables (with null and empty checks)
        if semantic_snapshot.dfg_snapshot and semantic_snapshot.dfg_snapshot.variables:
            for variable in semantic_snapshot.dfg_snapshot.variables:
                try:
                    graph_node = self._convert_variable_entity(variable, ir_doc)
                    graph.graph_nodes[graph_node.id] = graph_node
                except Exception as e:
                    logger.warning(f"Failed to convert DFG variable {variable.id}: {e}")

    def _convert_type_entity(self, type_entity: "TypeEntity", ir_doc: IRDocument) -> GraphNode:
        """
        Convert TypeEntity to GraphNode(TYPE).

        Args:
            type_entity: Type entity from semantic IR

        Returns:
            GraphNode representing the type
        """
        # Use raw string as name (simple extraction)
        name = type_entity.raw.split("[")[0] if "[" in type_entity.raw else type_entity.raw

        return GraphNode(
            id=type_entity.id,
            kind=GraphNodeKind.TYPE,
            repo_id=ir_doc.repo_id,
            snapshot_id=ir_doc.snapshot_id,
            fqn=type_entity.id,  # Use ID as FQN for types
            name=name,
            path=None,
            span=None,
            attrs={
                "raw": type_entity.raw,
                "flavor": type_entity.flavor.value,
                "is_nullable": type_entity.is_nullable,
                "resolution_level": type_entity.resolution_level.value,
                "resolved_target": type_entity.resolved_target,
                "generic_param_ids": type_entity.generic_param_ids,
            },
        )

    def _convert_signature_entity(self, signature_entity: "SignatureEntity", ir_doc: IRDocument) -> GraphNode:
        """
        Convert SignatureEntity to GraphNode(SIGNATURE).

        Args:
            signature_entity: Signature entity from semantic IR

        Returns:
            GraphNode representing the function/method signature
        """
        return GraphNode(
            id=signature_entity.id,
            kind=GraphNodeKind.SIGNATURE,
            repo_id=ir_doc.repo_id,
            snapshot_id=ir_doc.snapshot_id,
            fqn=signature_entity.id,  # Use ID as FQN for signatures
            name=signature_entity.name,
            path=None,
            span=None,
            attrs={
                "raw": signature_entity.raw,
                "owner_node_id": signature_entity.owner_node_id,
                "parameter_type_ids": signature_entity.parameter_type_ids,
                "return_type_id": signature_entity.return_type_id,
                "is_async": signature_entity.is_async,
                "is_static": signature_entity.is_static,
                "visibility": signature_entity.visibility.value if signature_entity.visibility else None,
                "throws_type_ids": signature_entity.throws_type_ids,
                "signature_hash": signature_entity.signature_hash,
            },
        )

    def _convert_cfg_block(self, cfg_block: "CFGBlock", ir_doc: IRDocument) -> GraphNode:
        """
        Convert CFGBlock to GraphNode(CFG_BLOCK).

        Args:
            cfg_block: CFG block from semantic IR

        Returns:
            GraphNode representing the CFG block
        """
        return GraphNode(
            id=cfg_block.id,
            kind=GraphNodeKind.CFG_BLOCK,
            repo_id=ir_doc.repo_id,
            snapshot_id=ir_doc.snapshot_id,
            fqn=cfg_block.id,  # CFG blocks use ID as FQN
            name=cfg_block.kind.value,
            path=None,
            span=cfg_block.span,
            attrs={
                "block_kind": cfg_block.kind.value,
                "function_node_id": cfg_block.function_node_id,
                "defined_variable_ids": cfg_block.defined_variable_ids,
                "used_variable_ids": cfg_block.used_variable_ids,
            },
        )

    def _convert_variable_entity(self, variable: "VariableEntity", ir_doc: IRDocument) -> GraphNode:
        """
        Convert DFG VariableEntity to GraphNode(VARIABLE).

        Args:
            variable: DFG variable entity from semantic IR

        Returns:
            GraphNode representing the DFG variable
        """
        return GraphNode(
            id=variable.id,
            kind=GraphNodeKind.VARIABLE,
            repo_id=ir_doc.repo_id,
            snapshot_id=ir_doc.snapshot_id,
            fqn=variable.id,  # Use ID as FQN for DFG variables
            name=variable.name,
            path=None,  # DFG variables are semantic entities without direct source location
            span=None,  # Tracked at shadow level, not AST level
            attrs={
                "variable_kind": variable.kind,  # param/local/captured
                "type_id": variable.type_id,
                "decl_block_id": variable.decl_block_id,
                "file_path": variable.file_path,
                "function_fqn": variable.function_fqn,
                **variable.attrs,  # Include any additional DFG-specific attrs
            },
        )

    # ============================================================
    # Phase 2: Edge Conversion
    # ============================================================

    def _convert_edges(
        self,
        ir_doc: IRDocument,
        semantic_snapshot: SemanticIrSnapshot,
        graph: GraphDocument,
    ):
        """
        Convert all edges from IR + Semantic IR to graph edges.

        Handles:
        - Structural edges (CONTAINS, IMPORTS, INHERITS, IMPLEMENTS)
        - Call/Reference edges (CALLS, REFERENCES_TYPE, REFERENCES_SYMBOL)
        - Control flow edges (CFG_NEXT, CFG_BRANCH, CFG_LOOP, CFG_HANDLER)
        """
        # Convert IR edges
        self._convert_ir_edges(ir_doc, graph)

        # Generate REFERENCES_TYPE edges from declared_type_id
        self._generate_type_reference_edges(ir_doc, graph)

        # Convert CFG edges
        self._convert_cfg_edges(semantic_snapshot, graph)

        # Generate DFG edges (READS/WRITES) from CFG blocks
        self._generate_dfg_edges(semantic_snapshot, graph)

    def _convert_ir_edges(self, ir_doc: IRDocument, graph: GraphDocument):
        """
        Convert IR edges to graph edges.

        Handles: CONTAINS, CALLS, IMPORTS, INHERITS, IMPLEMENTS, etc.
        """
        from codegraph_engine.code_foundation.infrastructure.graph.models import GraphEdge

        edge_counter = 0

        for ir_edge in ir_doc.edges:
            # Map IR edge kind to graph edge kind
            try:
                graph_edge_kind = self._map_ir_edge_to_graph_edge(ir_edge.kind)
            except ValueError:
                # Skip unsupported edge kinds
                continue

            # Create graph edge
            edge_id = f"edge:{graph_edge_kind.value.lower()}:{edge_counter}"
            edge_counter += 1

            graph_edge = GraphEdge(
                id=edge_id,
                kind=graph_edge_kind,
                source_id=ir_edge.source_id,
                target_id=ir_edge.target_id,
                attrs={
                    "span": ir_edge.span,
                    **ir_edge.attrs,
                },
            )

            graph.graph_edges.append(graph_edge)

    def _generate_type_reference_edges(self, ir_doc: IRDocument, graph: GraphDocument):
        """
        Generate REFERENCES_TYPE edges from declared_type_id.

        Creates edges: Variable/Field → Type
        """
        from codegraph_engine.code_foundation.infrastructure.graph.models import GraphEdge, GraphEdgeKind

        edge_counter = len(graph.graph_edges)

        for node in ir_doc.nodes:
            # Check if node has declared_type_id
            if node.declared_type_id is not None:
                edge_id = f"edge:references_type:{edge_counter}"
                edge_counter += 1

                graph_edge = GraphEdge(
                    id=edge_id,
                    kind=GraphEdgeKind.REFERENCES_TYPE,
                    source_id=node.id,
                    target_id=node.declared_type_id,
                    attrs={},
                )

                graph.graph_edges.append(graph_edge)

    def _convert_cfg_edges(self, semantic_snapshot: SemanticIrSnapshot | None, graph: GraphDocument):
        """
        Convert CFG edges to graph edges.

        Handles: CFG_NEXT, CFG_BRANCH, CFG_LOOP, CFG_HANDLER
        """
        if semantic_snapshot is None:
            return

        from codegraph_engine.code_foundation.infrastructure.graph.models import GraphEdge

        edge_counter = len(graph.graph_edges)

        for cfg_edge in semantic_snapshot.cfg_edges:
            # Map CFG edge kind to graph edge kind
            graph_edge_kind = self._map_cfg_edge_to_graph_edge(cfg_edge.kind)

            edge_id = f"edge:{graph_edge_kind.value.lower()}:{edge_counter}"
            edge_counter += 1

            graph_edge = GraphEdge(
                id=edge_id,
                kind=graph_edge_kind,
                source_id=cfg_edge.source_block_id,
                target_id=cfg_edge.target_block_id,
                attrs={
                    "cfg_edge_kind": cfg_edge.kind.value,
                },
            )

            graph.graph_edges.append(graph_edge)

    def _generate_dfg_edges(self, semantic_snapshot: SemanticIrSnapshot | None, graph: GraphDocument):
        """
        Generate data flow edges (READS/WRITES) from CFG blocks.

        Uses the defined_variable_ids and used_variable_ids from CFG blocks
        to create READS and WRITES edges.

        Only creates edges for nodes that exist in the graph to avoid dangling edges.
        """
        if semantic_snapshot is None:
            return

        from codegraph_engine.code_foundation.infrastructure.graph.models import GraphEdge, GraphEdgeKind

        # logger already defined at module level

        edge_counter = len(graph.graph_edges)
        skipped_writes = 0
        skipped_reads = 0

        for cfg_block in semantic_snapshot.cfg_blocks:
            # Validate CFG block exists in graph
            if cfg_block.id not in graph.graph_nodes:
                logger.debug(f"Skipping DFG edges for missing CFG block: {cfg_block.id}")
                continue

            # Generate WRITES edges from defined_variable_ids
            for var_id in cfg_block.defined_variable_ids:
                # Validate variable node exists in graph
                if var_id not in graph.graph_nodes:
                    skipped_writes += 1
                    continue

                edge_id = f"edge:writes:{edge_counter}"
                edge_counter += 1

                graph_edge = GraphEdge(
                    id=edge_id,
                    kind=GraphEdgeKind.WRITES,
                    source_id=cfg_block.id,  # CFG block writes to variable
                    target_id=var_id,
                    attrs={
                        "function_node_id": cfg_block.function_node_id,
                    },
                )

                graph.graph_edges.append(graph_edge)

            # Generate READS edges from used_variable_ids
            for var_id in cfg_block.used_variable_ids:
                # Validate variable node exists in graph
                if var_id not in graph.graph_nodes:
                    skipped_reads += 1
                    continue

                edge_id = f"edge:reads:{edge_counter}"
                edge_counter += 1

                graph_edge = GraphEdge(
                    id=edge_id,
                    kind=GraphEdgeKind.READS,
                    source_id=cfg_block.id,  # CFG block reads from variable
                    target_id=var_id,
                    attrs={
                        "function_node_id": cfg_block.function_node_id,
                    },
                )

                graph.graph_edges.append(graph_edge)

        if skipped_writes > 0 or skipped_reads > 0:
            logger.debug(
                f"DFG edge generation: skipped {skipped_writes} writes, {skipped_reads} reads (nodes not in graph)"
            )

    # ============================================================
    # Phase 3: Index Building
    # ============================================================

    def _build_indexes(self, graph: GraphDocument):
        """
        Build all graph indexes for efficient queries.

        Creates:
        - Core indexes: Reverse indexes (target → sources) + Adjacency indexes
        - Extended indexes (Phase 3): routes_by_path, services_by_domain, etc.
        """
        # Initialize core index dictionaries
        from collections import defaultdict

        from codegraph_engine.code_foundation.infrastructure.graph.models import GraphEdgeKind

        called_by: dict[str, list[str]] = defaultdict(list)
        imported_by: dict[str, list[str]] = defaultdict(list)
        contains_children: dict[str, list[str]] = defaultdict(list)
        type_users: dict[str, list[str]] = defaultdict(list)
        reads_by: dict[str, list[str]] = defaultdict(list)
        writes_by: dict[str, list[str]] = defaultdict(list)
        outgoing: dict[str, list[str]] = defaultdict(list)
        incoming: dict[str, list[str]] = defaultdict(list)
        decorators_by_target: dict[str, list[str]] = defaultdict(list)

        # EdgeKind-specific adjacency indexes: (node_id, edge_kind.value) → list[target_node_id]
        outgoing_by_kind: dict[tuple[str, str], list[str]] = defaultdict(list)
        incoming_by_kind: dict[tuple[str, str], list[str]] = defaultdict(list)

        # FIX: HIGH #5 - Build edge_by_id index for O(1) lookup
        for edge in graph.graph_edges:
            graph.edge_by_id[edge.id] = edge

        # Build all indexes in a single pass (3x faster)
        for edge in graph.graph_edges:
            # Adjacency indexes (for all edges)
            outgoing[edge.source_id].append(edge.id)
            incoming[edge.target_id].append(edge.id)

            # EdgeKind-specific adjacency indexes: O(1) filtering by edge type
            edge_kind_value = edge.kind.value
            outgoing_by_kind[(edge.source_id, edge_kind_value)].append(edge.target_id)
            incoming_by_kind[(edge.target_id, edge_kind_value)].append(edge.source_id)

            # Reverse indexes by edge kind
            if edge.kind == GraphEdgeKind.CALLS:
                called_by[edge.target_id].append(edge.source_id)
            elif edge.kind == GraphEdgeKind.IMPORTS:
                imported_by[edge.target_id].append(edge.source_id)
            elif edge.kind == GraphEdgeKind.CONTAINS:
                contains_children[edge.source_id].append(edge.target_id)
            elif edge.kind == GraphEdgeKind.REFERENCES_TYPE:
                type_users[edge.target_id].append(edge.source_id)
            elif edge.kind == GraphEdgeKind.READS:
                reads_by[edge.target_id].append(edge.source_id)
            elif edge.kind == GraphEdgeKind.WRITES:
                writes_by[edge.target_id].append(edge.source_id)
            elif edge.kind == GraphEdgeKind.DECORATES:
                decorators_by_target[edge.target_id].append(edge.source_id)

        # Update core indexes
        graph.indexes.called_by = called_by
        graph.indexes.imported_by = imported_by
        graph.indexes.contains_children = contains_children
        graph.indexes.type_users = type_users
        graph.indexes.reads_by = reads_by
        graph.indexes.writes_by = writes_by
        graph.indexes.outgoing = outgoing
        graph.indexes.incoming = incoming

        # EdgeKind-specific adjacency indexes for O(1) filtering
        graph.indexes.outgoing_by_kind = outgoing_by_kind
        graph.indexes.incoming_by_kind = incoming_by_kind

        # Build extended indexes (Phase 3)
        graph.indexes.decorators_by_target = decorators_by_target
        self._build_routes_by_path_index(graph)
        self._build_services_by_domain_index(graph)
        self._build_request_flow_index(graph)

    def _build_routes_by_path_index(self, graph: GraphDocument):
        """
        Build routes_by_path index from Route nodes.

        Maps route path (e.g., "/api/users") to Route node IDs.
        """
        routes_by_path: dict[str, list[str]] = {}

        # Collect Route nodes
        for node in graph.graph_nodes.values():
            if node.kind == GraphNodeKind.ROUTE:
                # Extract route path from attrs
                route_path = node.attrs.get("route_path") or node.attrs.get("path")
                if route_path:
                    if route_path not in routes_by_path:
                        routes_by_path[route_path] = []
                    routes_by_path[route_path].append(node.id)

        graph.indexes.routes_by_path = routes_by_path

    def _build_services_by_domain_index(self, graph: GraphDocument):
        """
        Build services_by_domain index from Service nodes.

        Maps domain tag to Service node IDs.
        """
        services_by_domain: dict[str, list[str]] = {}

        # Collect Service nodes
        for node in graph.graph_nodes.values():
            if node.kind == GraphNodeKind.SERVICE:
                # Extract domain tags from attrs
                domain_tags = node.attrs.get("domain_tags", [])
                if isinstance(domain_tags, str):
                    domain_tags = [domain_tags]

                for domain in domain_tags:
                    if domain not in services_by_domain:
                        services_by_domain[domain] = []
                    services_by_domain[domain].append(node.id)

        graph.indexes.services_by_domain = services_by_domain

    def _build_request_flow_index(self, graph: GraphDocument):
        """
        Build request_flow_index from Route → Handler → Service → Repository edges.

        For each Route, traces the complete request flow:
        - Route -ROUTE_HANDLER→ Handler Function/Method
        - Handler -HANDLES_REQUEST→ Service
        - Service -USES_REPOSITORY→ Repository

        Uses graph edge indexes for O(1) lookups instead of O(E) loops.
        """
        request_flow_index: dict[str, dict[str, list[str]]] = {}

        # Collect Route nodes
        route_nodes = [n for n in graph.graph_nodes.values() if n.kind == GraphNodeKind.ROUTE]

        for route_node in route_nodes:
            flow = self._trace_route_flow(route_node.id, graph)
            request_flow_index[route_node.id] = flow

        graph.indexes.request_flow_index = request_flow_index

    def _trace_route_flow(self, route_id: str, graph: GraphDocument) -> dict[str, list[str]]:
        """
        Trace the complete flow for a single route using edge indexes.

        Returns dict with handlers, services, and repositories.
        """
        flow: dict[str, list[str]] = {
            "handlers": [],
            "services": [],
            "repositories": [],
        }

        # Find handlers using edge index (O(1) lookup)
        handler_ids = self._find_targets_by_edge_kind(route_id, GraphEdgeKind.ROUTE_HANDLER, graph)
        flow["handlers"] = handler_ids

        # Find services from all handlers
        service_ids_set: set[str] = set()
        for handler_id in handler_ids:
            services = self._find_targets_by_edge_kind(handler_id, GraphEdgeKind.HANDLES_REQUEST, graph)
            service_ids_set.update(services)

        flow["services"] = list(service_ids_set)

        # Find repositories from all services
        repo_ids_set: set[str] = set()
        for service_id in service_ids_set:
            repos = self._find_targets_by_edge_kind(service_id, GraphEdgeKind.USES_REPOSITORY, graph)
            repo_ids_set.update(repos)

        flow["repositories"] = list(repo_ids_set)

        return flow

    def _find_targets_by_edge_kind(self, source_id: str, edge_kind: GraphEdgeKind, graph: GraphDocument) -> list[str]:
        """
        Find all target node IDs connected from source_id by edges of given kind.

        Uses graph edge indexes for O(k) lookup where k = edges from source.
        """
        target_ids: list[str] = []

        # Get outgoing edge IDs from index (O(1))
        edge_ids_from_source = graph.indexes.outgoing.get(source_id, set())

        # FIX: HIGH #5 - Use edge_by_id for O(1) lookup per edge instead of O(E) scan
        for edge_id in edge_ids_from_source:
            edge = graph.edge_by_id.get(edge_id)
            if edge and edge.kind == edge_kind:
                target_ids.append(edge.target_id)

        return target_ids

    # ============================================================
    # Helpers
    # ============================================================

    def _map_ir_kind_to_graph_kind(self, ir_kind: NodeKind, role: str | None = None) -> GraphNodeKind:
        """
        Map IR NodeKind to GraphNodeKind.

        Most kinds map 1:1, with some exceptions (e.g., IMPORT handled separately).
        For FUNCTION/METHOD nodes, uses role to determine specialized node types
        (Route, Service, Repository, etc.)

        Args:
            ir_kind: IR node kind
            role: Optional role hint (controller, service, repo, etc.)

        Returns:
            GraphNodeKind
        """
        # First check role-based specialized types (Phase 3)
        if role and ir_kind in (NodeKind.FUNCTION, NodeKind.METHOD, NodeKind.CLASS):
            if "route" in role.lower() or "controller" in role.lower():
                return GraphNodeKind.ROUTE
            elif "service" in role.lower():
                return GraphNodeKind.SERVICE
            elif "repo" in role.lower() or "repository" in role.lower():
                return GraphNodeKind.REPOSITORY
            elif "config" in role.lower():
                return GraphNodeKind.CONFIG
            elif "job" in role.lower() or "task" in role.lower():
                return GraphNodeKind.JOB
            elif "middleware" in role.lower():
                return GraphNodeKind.MIDDLEWARE

        # Standard mapping (Phase 2)
        mapping = {
            NodeKind.FILE: GraphNodeKind.FILE,
            NodeKind.MODULE: GraphNodeKind.MODULE,
            NodeKind.CLASS: GraphNodeKind.CLASS,
            NodeKind.INTERFACE: GraphNodeKind.INTERFACE,  # TypeScript/Java interfaces
            NodeKind.FUNCTION: GraphNodeKind.FUNCTION,
            NodeKind.METHOD: GraphNodeKind.METHOD,
            NodeKind.VARIABLE: GraphNodeKind.VARIABLE,
            NodeKind.FIELD: GraphNodeKind.FIELD,
            NodeKind.IMPORT: GraphNodeKind.IMPORT,  # IMPORT nodes become graph nodes for cross_reference
            # CALL nodes don't become graph nodes - they become CALLS edges
        }

        if ir_kind not in mapping:
            raise ValueError(f"Unsupported IR kind: {ir_kind}")

        return mapping[ir_kind]

    def _map_ir_edge_to_graph_edge(self, ir_edge_kind) -> "GraphEdgeKind":
        """
        Map IR EdgeKind to GraphEdgeKind.

        Args:
            ir_edge_kind: IR edge kind

        Returns:
            GraphEdgeKind

        Raises:
            ValueError: If edge kind not supported
        """
        from codegraph_engine.code_foundation.infrastructure.graph.models import GraphEdgeKind
        from codegraph_engine.code_foundation.infrastructure.ir.models import EdgeKind

        mapping = {
            EdgeKind.CONTAINS: GraphEdgeKind.CONTAINS,
            EdgeKind.CALLS: GraphEdgeKind.CALLS,
            EdgeKind.IMPORTS: GraphEdgeKind.IMPORTS,
            EdgeKind.INHERITS: GraphEdgeKind.INHERITS,
            EdgeKind.IMPLEMENTS: GraphEdgeKind.IMPLEMENTS,
            EdgeKind.REFERENCES: GraphEdgeKind.REFERENCES_SYMBOL,
            # READS/WRITES handled by DFG (Step 4)
            # Other IR edge kinds can be added here
        }

        if ir_edge_kind not in mapping:
            raise ValueError(f"Unsupported IR edge kind: {ir_edge_kind}")

        return mapping[ir_edge_kind]

    def _map_cfg_edge_to_graph_edge(self, cfg_edge_kind) -> "GraphEdgeKind":
        """
        Map CFG EdgeKind to GraphEdgeKind.

        Args:
            cfg_edge_kind: CFG edge kind

        Returns:
            GraphEdgeKind
        """
        from codegraph_engine.code_foundation.infrastructure.graph.models import GraphEdgeKind
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import CFGEdgeKind

        # Map CFG edge kinds to graph edge kinds
        # NORMAL edges → CFG_NEXT
        # TRUE_BRANCH/FALSE_BRANCH → CFG_BRANCH
        # LOOP_BACK → CFG_LOOP
        # EXCEPTION → CFG_HANDLER

        mapping = {
            CFGEdgeKind.NORMAL: GraphEdgeKind.CFG_NEXT,
            CFGEdgeKind.TRUE_BRANCH: GraphEdgeKind.CFG_BRANCH,
            CFGEdgeKind.FALSE_BRANCH: GraphEdgeKind.CFG_BRANCH,
            CFGEdgeKind.LOOP_BACK: GraphEdgeKind.CFG_LOOP,
            CFGEdgeKind.EXCEPTION: GraphEdgeKind.CFG_HANDLER,
        }

        return mapping.get(cfg_edge_kind, GraphEdgeKind.CFG_NEXT)
