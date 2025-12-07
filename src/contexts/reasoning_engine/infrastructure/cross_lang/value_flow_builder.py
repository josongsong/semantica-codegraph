"""
ValueFlow Graph Builder (INTEGRATION)

IRDocument + BoundarySpec → ValueFlowGraph
"""

from __future__ import annotations

import logging
from typing import Any

from src.contexts.code_foundation.infrastructure.graph.models import (
    GraphDocument,
)
from src.contexts.code_foundation.infrastructure.ir.models import IRDocument

from .boundary_analyzer import BoundaryAnalyzer
from .boundary_matcher import BoundaryCodeMatcher, MatchCandidate
from .type_system import TypeInference
from .value_flow_graph import (
    BoundarySpec,
    Confidence,
    FlowEdgeKind,
    ValueFlowEdge,
    ValueFlowGraph,
    ValueFlowNode,
)

logger = logging.getLogger(__name__)


class ValueFlowBuilder:
    """
    Build ValueFlowGraph from code analysis results

    Integration layer:
    - IRDocument → ValueFlowNode
    - GraphDocument → ValueFlowEdge
    - BoundarySpec → Cross-service edges

    Example:
        builder = ValueFlowBuilder(workspace_root="/path/to/project")

        # Auto-discover schemas
        boundaries = builder.discover_boundaries()

        # Build graph from IR
        vfg = builder.build_from_ir(ir_documents, graph_document)

        # Add cross-service flows
        builder.add_boundary_flows(vfg, boundaries, ir_documents)
    """

    def __init__(self, workspace_root: str):
        """
        Initialize builder

        Args:
            workspace_root: Project root directory
        """
        self.workspace_root = workspace_root

        # Components
        self.boundary_analyzer = BoundaryAnalyzer(workspace_root)
        self.boundary_matcher = BoundaryCodeMatcher()
        self.type_inference = TypeInference()

        logger.info(f"ValueFlowBuilder initialized: {workspace_root}")

    def discover_boundaries(self) -> list[BoundarySpec]:
        """
        Auto-discover service boundaries from schemas

        Scans for:
        - openapi.yaml, swagger.json
        - *.proto files
        - schema.graphql

        Returns:
            List of BoundarySpec
        """
        logger.info("Auto-discovering service boundaries...")

        boundaries = self.boundary_analyzer.discover_all()

        logger.info(f"Discovered {len(boundaries)} boundaries")
        return boundaries

    def build_from_ir(
        self, ir_documents: list[IRDocument], graph_document: GraphDocument | None = None
    ) -> ValueFlowGraph:
        """
        Build ValueFlowGraph from IRDocument

        Args:
            ir_documents: IR documents from code analysis
            graph_document: Optional GraphDocument for edges

        Returns:
            ValueFlowGraph
        """
        logger.info(f"Building ValueFlowGraph from {len(ir_documents)} IR documents")

        vfg = ValueFlowGraph()

        # Add nodes from IR
        for ir_doc in ir_documents:
            for node in ir_doc.nodes:
                # Create ValueFlowNode
                vf_node = self._create_node_from_ir(node, ir_doc)
                vfg.add_node(vf_node)

        # Add edges from GraphDocument
        if graph_document:
            self._add_edges_from_graph(vfg, graph_document)

        logger.info(f"Built ValueFlowGraph: {len(vfg.nodes)} nodes, {len(vfg.edges)} edges")

        return vfg

    def add_boundary_flows(
        self, vfg: ValueFlowGraph, boundaries: list[BoundarySpec], ir_documents: list[IRDocument]
    ) -> int:
        """
        Add cross-service boundary flows

        Matches BoundarySpec to code and creates edges

        Args:
            vfg: ValueFlowGraph to augment
            boundaries: Discovered boundaries
            ir_documents: IR documents for matching

        Returns:
            Number of boundary edges added
        """
        logger.info(f"Adding boundary flows for {len(boundaries)} boundaries")

        # Match boundaries to code
        matches = self.boundary_matcher.batch_match(boundaries, ir_documents)

        added_count = 0

        for boundary, match in matches.items():
            if not match or match.confidence == Confidence.LOW:
                continue

            # Create boundary edge
            edge = self._create_boundary_edge(boundary, match, vfg)

            if edge:
                vfg.add_edge(edge)
                added_count += 1

        logger.info(f"Added {added_count} boundary edges")
        return added_count

    def _create_node_from_ir(self, ir_node: Any, ir_doc: IRDocument) -> ValueFlowNode:
        """
        Create ValueFlowNode from IR node

        Args:
            ir_node: IR node
            ir_doc: Parent IR document

        Returns:
            ValueFlowNode
        """
        # Extract type info (if available)
        value_type = None

        # Try to infer type from annotations
        if hasattr(ir_node, "attrs") and "return_type" in ir_node.attrs:
            type_annotation = ir_node.attrs["return_type"]
            try:
                value_type = self.type_inference.infer_from_python_annotation(str(type_annotation))
            except Exception as e:
                logger.debug(f"Failed to infer type: {e}")

        # Detect sources/sinks
        is_source = self._is_source(ir_node)
        is_sink = self._is_sink(ir_node)

        # Taint labels
        taint_labels = set()
        if self._handles_pii(ir_node):
            taint_labels.add("PII")
        if self._handles_auth(ir_node):
            taint_labels.add("AUTH")

        return ValueFlowNode(
            node_id=ir_node.id,
            symbol_name=ir_node.name,
            file_path=ir_doc.file_path,
            line=ir_node.location.get("line", 0) if hasattr(ir_node, "location") else 0,
            language=self._detect_language(ir_doc.file_path),
            value_type=value_type,
            function_context=ir_node.parent_id if hasattr(ir_node, "parent_id") else None,
            is_source=is_source,
            is_sink=is_sink,
            taint_labels=taint_labels,
        )

    def _add_edges_from_graph(self, vfg: ValueFlowGraph, graph_doc: GraphDocument):
        """Add edges from GraphDocument"""
        for graph_node in graph_doc.nodes.values():
            # Get outgoing edges
            for edge in graph_node.outgoing:
                # Determine edge kind
                kind = self._map_edge_kind(edge.kind)

                if kind:
                    vf_edge = ValueFlowEdge(
                        source_id=edge.source_id,
                        target_id=edge.target_id,
                        kind=kind,
                        confidence=Confidence.HIGH,
                    )

                    vfg.add_edge(vf_edge)

    def _create_boundary_edge(
        self, boundary: BoundarySpec, match: MatchCandidate, vfg: ValueFlowGraph
    ) -> ValueFlowEdge | None:
        """Create boundary edge from match"""

        # Find source (client) and target (server) nodes
        server_node = vfg.nodes.get(match.symbol_id)

        if not server_node:
            logger.warning(f"Server node not found: {match.symbol_id}")
            return None

        # Determine edge kind
        if boundary.boundary_type == "rest_api":
            kind = FlowEdgeKind.HTTP_REQUEST
        elif boundary.boundary_type == "grpc":
            kind = FlowEdgeKind.GRPC_CALL
        elif boundary.boundary_type == "graphql":
            kind = FlowEdgeKind.GRAPHQL_QUERY
        else:
            kind = FlowEdgeKind.CALL

        # For now, create edge without source (client-side matching needed)
        # This would be enhanced with client-side analysis

        # Store boundary info
        vfg.add_boundary(boundary)

        return None  # Would return actual edge when client is found

    def _is_source(self, ir_node: Any) -> bool:
        """Check if node is a data source"""
        # Heuristic: input functions, request handlers, DB reads
        name_lower = ir_node.name.lower()

        source_hints = [
            "request",
            "input",
            "read",
            "fetch",
            "get",
            "receive",
        ]

        return any(hint in name_lower for hint in source_hints)

    def _is_sink(self, ir_node: Any) -> bool:
        """Check if node is a data sink"""
        name_lower = ir_node.name.lower()

        sink_hints = [
            "response",
            "output",
            "write",
            "save",
            "send",
            "execute",
            "query",
        ]

        return any(hint in name_lower for hint in sink_hints)

    def _handles_pii(self, ir_node: Any) -> bool:
        """Check if handles PII"""
        name_lower = ir_node.name.lower()

        pii_hints = [
            "user",
            "email",
            "phone",
            "password",
            "ssn",
            "credit",
            "personal",
        ]

        return any(hint in name_lower for hint in pii_hints)

    def _handles_auth(self, ir_node: Any) -> bool:
        """Check if handles auth"""
        name_lower = ir_node.name.lower()

        auth_hints = [
            "auth",
            "login",
            "token",
            "credential",
            "permission",
        ]

        return any(hint in name_lower for hint in auth_hints)

    def _detect_language(self, file_path: str) -> str:
        """Detect language from file path"""
        if file_path.endswith(".py"):
            return "python"
        elif file_path.endswith((".ts", ".tsx")):
            return "typescript"
        elif file_path.endswith((".js", ".jsx")):
            return "javascript"
        elif file_path.endswith(".go"):
            return "go"
        elif file_path.endswith(".java"):
            return "java"
        elif file_path.endswith(".rs"):
            return "rust"
        else:
            return "unknown"

    def _map_edge_kind(self, graph_edge_kind: str) -> FlowEdgeKind | None:
        """Map GraphEdge kind to FlowEdgeKind"""
        mapping = {
            "CALLS": FlowEdgeKind.CALL,
            "RETURNS": FlowEdgeKind.RETURN,
            "ASSIGNS": FlowEdgeKind.ASSIGN,
            "PARAMETER": FlowEdgeKind.PARAMETER,
        }

        return mapping.get(graph_edge_kind)
