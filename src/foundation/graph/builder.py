"""
Graph Builder

Converts Structural IR + Semantic IR → GraphDocument.

Phase 1: GraphNode conversion
Phase 2: GraphEdge conversion + External node creation
Phase 3: GraphIndex construction
"""

from typing import TYPE_CHECKING

from ..ir.models import IRDocument, NodeKind
from ..semantic_ir.context import SemanticIrSnapshot
from .models import GraphDocument, GraphEdgeKind, GraphNode, GraphNodeKind

if TYPE_CHECKING:
    from ..dfg.models import VariableEntity
    from ..semantic_ir.cfg.models import ControlFlowBlock as CFGBlock
    from ..semantic_ir.signature.models import SignatureEntity
    from ..semantic_ir.typing.models import TypeEntity


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

    def __init__(self):
        self._module_cache: dict[str, GraphNode] = {}

    def build_full(
        self,
        ir_doc: IRDocument,
        semantic_snapshot: SemanticIrSnapshot,
    ) -> GraphDocument:
        """
        Build complete graph from IR + Semantic IR.

        Args:
            ir_doc: Structural IR document
            semantic_snapshot: Semantic IR snapshot

        Returns:
            GraphDocument with all nodes, edges, and indexes
        """
        graph = GraphDocument(
            repo_id=ir_doc.repo_id,
            snapshot_id=ir_doc.snapshot_id,
        )

        # Phase 1: Convert all nodes
        self._convert_ir_nodes(ir_doc, graph)
        self._convert_semantic_nodes(semantic_snapshot, graph, ir_doc)

        # Phase 2: Convert edges
        self._convert_edges(ir_doc, semantic_snapshot, graph)

        # Phase 3: Build indexes
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
        for node in ir_doc.nodes:
            # Skip nodes that don't become graph nodes (IMPORT, CALL, etc.)
            try:
                # Phase 3: Pass role to mapper for specialized node type detection
                graph_kind = self._map_ir_kind_to_graph_kind(node.kind, node.role)
            except ValueError:
                # Skip unsupported kinds (they become edges instead)
                continue

            # Create graph node
            graph_node = GraphNode(
                id=node.id,
                kind=graph_kind,
                repo_id=ir_doc.repo_id,
                snapshot_id=ir_doc.snapshot_id,
                fqn=node.fqn,
                name=node.name or "",
                path=node.file_path if graph_kind == GraphNodeKind.FILE else None,
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

        # Auto-generate module nodes from file paths
        self._generate_module_nodes(ir_doc, graph)

    def _generate_module_nodes(self, ir_doc: IRDocument, graph: GraphDocument):
        """
        Auto-generate MODULE nodes from file paths.

        Example: "src/data/processor.py" → ["src", "src.data"]
        """
        self._module_cache.clear()

        # Collect all file nodes
        file_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FILE]

        for file_node in file_nodes:
            file_path = file_node.file_path
            parts = file_path.split("/")

            # Skip if no directory structure
            if len(parts) <= 1:
                continue

            # Generate module nodes for each directory level
            current_path = ""
            current_fqn = ""

            for _i, part in enumerate(parts[:-1]):  # Exclude file name
                # Build path
                if current_path:
                    current_path += "/" + part
                    current_fqn += "." + part
                else:
                    current_path = part
                    current_fqn = part

                # Skip if already generated
                module_id = f"module:{ir_doc.repo_id}::{current_fqn}"
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
        Convert semantic IR entities to graph nodes.

        Handles: Type, Signature, CfgBlock, DFG Variables
        """
        # Convert Type entities
        for type_entity in semantic_snapshot.types:
            graph_node = self._convert_type_entity(type_entity, ir_doc)
            graph.graph_nodes[graph_node.id] = graph_node

        # Convert Signature entities
        for signature_entity in semantic_snapshot.signatures:
            graph_node = self._convert_signature_entity(signature_entity, ir_doc)
            graph.graph_nodes[graph_node.id] = graph_node

        # Convert CFG blocks
        for cfg_block in semantic_snapshot.cfg_blocks:
            graph_node = self._convert_cfg_block(cfg_block, ir_doc)
            graph.graph_nodes[graph_node.id] = graph_node

        # Convert DFG variables
        if semantic_snapshot.dfg_snapshot:
            for variable in semantic_snapshot.dfg_snapshot.variables:
                graph_node = self._convert_variable_entity(variable, ir_doc)
                graph.graph_nodes[graph_node.id] = graph_node

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
        from .models import GraphEdge

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
        from .models import GraphEdge, GraphEdgeKind

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

    def _convert_cfg_edges(self, semantic_snapshot: SemanticIrSnapshot, graph: GraphDocument):
        """
        Convert CFG edges to graph edges.

        Handles: CFG_NEXT, CFG_BRANCH, CFG_LOOP, CFG_HANDLER
        """
        from .models import GraphEdge

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

    def _generate_dfg_edges(self, semantic_snapshot: SemanticIrSnapshot, graph: GraphDocument):
        """
        Generate data flow edges (READS/WRITES) from CFG blocks.

        Uses the defined_variable_ids and used_variable_ids from CFG blocks
        to create READS and WRITES edges.
        """
        from .models import GraphEdge, GraphEdgeKind

        edge_counter = len(graph.graph_edges)

        for cfg_block in semantic_snapshot.cfg_blocks:
            # Generate WRITES edges from defined_variable_ids
            for var_id in cfg_block.defined_variable_ids:
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

        from .models import GraphEdgeKind

        called_by: dict[str, list[str]] = defaultdict(list)
        imported_by: dict[str, list[str]] = defaultdict(list)
        contains_children: dict[str, list[str]] = defaultdict(list)
        type_users: dict[str, list[str]] = defaultdict(list)
        reads_by: dict[str, list[str]] = defaultdict(list)
        writes_by: dict[str, list[str]] = defaultdict(list)
        outgoing: dict[str, list[str]] = defaultdict(list)
        incoming: dict[str, list[str]] = defaultdict(list)
        decorators_by_target: dict[str, list[str]] = defaultdict(list)

        # Group edges by kind for efficient batch processing
        edges_by_kind: dict[GraphEdgeKind, list] = defaultdict(list)
        for edge in graph.graph_edges:
            edges_by_kind[edge.kind].append(edge)

        # Build adjacency indexes (all edges)
        for edge in graph.graph_edges:
            outgoing[edge.source_id].append(edge.id)
            incoming[edge.target_id].append(edge.id)

        # Build reverse indexes by edge kind (batch processing)
        for edge in edges_by_kind[GraphEdgeKind.CALLS]:
            called_by[edge.target_id].append(edge.source_id)

        for edge in edges_by_kind[GraphEdgeKind.IMPORTS]:
            imported_by[edge.target_id].append(edge.source_id)

        for edge in edges_by_kind[GraphEdgeKind.CONTAINS]:
            contains_children[edge.source_id].append(edge.target_id)

        for edge in edges_by_kind[GraphEdgeKind.REFERENCES_TYPE]:
            type_users[edge.target_id].append(edge.source_id)

        for edge in edges_by_kind[GraphEdgeKind.READS]:
            reads_by[edge.target_id].append(edge.source_id)

        for edge in edges_by_kind[GraphEdgeKind.WRITES]:
            writes_by[edge.target_id].append(edge.source_id)

        for edge in edges_by_kind[GraphEdgeKind.DECORATES]:
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
        """
        request_flow_index: dict[str, dict[str, list[str]]] = {}

        # Collect Route nodes
        route_nodes = [n for n in graph.graph_nodes.values() if n.kind == GraphNodeKind.ROUTE]

        for route_node in route_nodes:
            flow: dict[str, list[str]] = {
                "handlers": [],
                "services": [],
                "repositories": [],
            }

            # Find handlers for this route
            for edge in graph.graph_edges:
                if edge.kind == GraphEdgeKind.ROUTE_HANDLER and edge.source_id == route_node.id:
                    handler_id = edge.target_id
                    flow["handlers"].append(handler_id)

                    # Find services called by this handler
                    for service_edge in graph.graph_edges:
                        if service_edge.kind == GraphEdgeKind.HANDLES_REQUEST and service_edge.source_id == handler_id:
                            service_id = service_edge.target_id
                            if service_id not in flow["services"]:
                                flow["services"].append(service_id)

                            # Find repositories used by this service
                            for repo_edge in graph.graph_edges:
                                if (
                                    repo_edge.kind == GraphEdgeKind.USES_REPOSITORY
                                    and repo_edge.source_id == service_id
                                ):
                                    repo_id = repo_edge.target_id
                                    if repo_id not in flow["repositories"]:
                                        flow["repositories"].append(repo_id)

            request_flow_index[route_node.id] = flow

        graph.indexes.request_flow_index = request_flow_index

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
            NodeKind.FUNCTION: GraphNodeKind.FUNCTION,
            NodeKind.METHOD: GraphNodeKind.METHOD,
            NodeKind.VARIABLE: GraphNodeKind.VARIABLE,
            NodeKind.FIELD: GraphNodeKind.FIELD,
            # IMPORT nodes don't become graph nodes - they become IMPORTS edges
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
        from ..ir.models import EdgeKind
        from .models import GraphEdgeKind

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
        from ..semantic_ir.cfg.models import CFGEdgeKind
        from .models import GraphEdgeKind

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
