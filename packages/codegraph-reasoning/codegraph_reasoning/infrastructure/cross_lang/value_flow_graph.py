"""
Cross-Language Value Flow Graph (SOTA)

End-to-end 값 흐름 추적: FE → BE → DB
OpenAPI/Protobuf/GraphQL/SQL 기반 boundary 모델링

Reference:
- Facebook's Infer (Cross-language taint analysis)
- CodeQL's data flow analysis
- Semgrep's cross-file analysis
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FlowEdgeKind(Enum):
    """Value flow edge 타입"""

    # Intra-language (within same service)
    CALL = "call"  # Function call
    RETURN = "return"  # Function return
    ASSIGN = "assign"  # Variable assignment
    PARAMETER = "parameter"  # Parameter passing

    # Cross-language (service boundary)
    HTTP_REQUEST = "http_request"  # REST API call
    HTTP_RESPONSE = "http_response"  # REST API response
    GRPC_CALL = "grpc_call"  # gRPC call
    GRPC_RETURN = "grpc_return"  # gRPC return
    GRAPHQL_QUERY = "graphql_query"  # GraphQL query
    GRAPHQL_MUTATION = "graphql_mutation"  # GraphQL mutation

    # Data persistence
    DB_WRITE = "db_write"  # Database INSERT/UPDATE
    DB_READ = "db_read"  # Database SELECT
    CACHE_WRITE = "cache_write"  # Cache write
    CACHE_READ = "cache_read"  # Cache read

    # Message queue
    QUEUE_SEND = "queue_send"  # Message queue send
    QUEUE_RECEIVE = "queue_receive"  # Message queue receive

    # Serialization
    SERIALIZE = "serialize"  # Object → JSON/Protobuf
    DESERIALIZE = "deserialize"  # JSON/Protobuf → Object

    # Data transformation
    TRANSFORM = "transform"  # Data transformation


class Confidence(Enum):
    """Confidence level"""

    HIGH = "high"  # 100% certain (static analysis)
    MEDIUM = "medium"  # 70-90% (pattern matching)
    LOW = "low"  # 40-70% (heuristic)
    GUESS = "guess"  # < 40% (best effort)


@dataclass
class BoundarySpec:
    """
    Service boundary specification

    OpenAPI/Protobuf/GraphQL schema로부터 추출
    """

    boundary_type: str  # "rest_api" | "grpc" | "graphql"
    service_name: str  # Service identifier
    endpoint: str  # Endpoint path/name

    # Request/Response schema
    request_schema: dict[str, str]  # {field_name: type}
    response_schema: dict[str, str]  # {field_name: type}

    # Source file locations
    server_file: str | None = None  # Server implementation file
    client_file: str | None = None  # Client call site

    # Metadata
    http_method: str | None = None  # GET/POST/PUT/DELETE
    grpc_method: str | None = None  # gRPC method name
    graphql_type: str | None = None  # Query/Mutation

    confidence: Confidence = Confidence.MEDIUM


@dataclass
class ValueFlowNode:
    """
    Value flow graph node

    Variable/Expression at specific location
    """

    node_id: str  # Unique ID
    symbol_name: str  # Variable/function name
    file_path: str  # Source file
    line: int  # Line number
    language: str  # Programming language

    # Type information (INTEGRATED with TypeSystem)
    # Note: Uses Any for now to avoid circular imports
    # In practice, should be TypeInfo from type_system.py
    value_type: Any | None = None  # TypeInfo object
    schema: dict | None = None  # JSON schema (for boundaries)

    # Context
    function_context: str | None = None  # Enclosing function
    service_context: str | None = None  # Service name

    # Taint tracking
    is_source: bool = False  # Source (user input, DB read)
    is_sink: bool = False  # Sink (DB write, HTTP response)
    taint_labels: set[str] = field(default_factory=set)  # e.g., {"PII", "sensitive"}

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValueFlowEdge:
    """Value flow edge"""

    source_id: str  # Source node ID
    target_id: str  # Target node ID
    kind: FlowEdgeKind  # Edge type

    # Boundary info (if cross-service)
    boundary_spec: BoundarySpec | None = None

    # Field mapping (for transformations)
    field_mapping: dict[str, str] | None = None  # {source_field: target_field}

    confidence: Confidence = Confidence.HIGH
    metadata: dict[str, Any] = field(default_factory=dict)


class ValueFlowGraph:
    """
    Cross-language Value Flow Graph

    Tracks data flow across services, languages, and persistence layers.

    Example:
        vfg = ValueFlowGraph()

        # Frontend (TypeScript)
        fe_node = ValueFlowNode(
            node_id="fe:login_button_click",
            symbol_name="loginData",
            file_path="src/Login.tsx",
            line=42,
            language="typescript"
        )
        vfg.add_node(fe_node)

        # Backend (Python)
        be_node = ValueFlowNode(
            node_id="be:login_handler",
            symbol_name="credentials",
            file_path="api/auth.py",
            line=15,
            language="python"
        )
        vfg.add_node(be_node)

        # HTTP boundary
        boundary = BoundarySpec(
            boundary_type="rest_api",
            service_name="auth_service",
            endpoint="/api/login",
            request_schema={"username": "string", "password": "string"},
            response_schema={"token": "string"}
        )

        edge = ValueFlowEdge(
            source_id=fe_node.node_id,
            target_id=be_node.node_id,
            kind=FlowEdgeKind.HTTP_REQUEST,
            boundary_spec=boundary
        )
        vfg.add_edge(edge)

        # Trace flow
        path = vfg.trace_forward(fe_node.node_id)
    """

    def __init__(self):
        """Initialize value flow graph"""
        self.nodes: dict[str, ValueFlowNode] = {}
        self.edges: list[ValueFlowEdge] = []

        # Indices for fast lookup
        self._outgoing: dict[str, list[ValueFlowEdge]] = defaultdict(list)
        self._incoming: dict[str, list[ValueFlowEdge]] = defaultdict(list)
        self._boundaries: list[BoundarySpec] = []

        # Taint sources and sinks
        self._sources: set[str] = set()  # Source node IDs
        self._sinks: set[str] = set()  # Sink node IDs

        logger.info("ValueFlowGraph initialized")

    def add_node(self, node: ValueFlowNode):
        """Add node to graph"""
        self.nodes[node.node_id] = node

        if node.is_source:
            self._sources.add(node.node_id)
        if node.is_sink:
            self._sinks.add(node.node_id)

    def add_edge(self, edge: ValueFlowEdge):
        """Add edge to graph"""
        self.edges.append(edge)
        self._outgoing[edge.source_id].append(edge)
        self._incoming[edge.target_id].append(edge)

        if edge.boundary_spec:
            self._boundaries.append(edge.boundary_spec)

    def add_boundary(self, boundary: BoundarySpec):
        """Register service boundary"""
        self._boundaries.append(boundary)

    def trace_forward(
        self, start_node_id: str, max_depth: int = 50, filter_kinds: set[FlowEdgeKind] | None = None
    ) -> list[list[str]]:
        """
        Forward trace: 이 값이 어디로 흘러가는가?

        Args:
            start_node_id: Starting node
            max_depth: Max trace depth
            filter_kinds: Filter edge kinds (None = all)

        Returns:
            List of paths (each path is list of node IDs)
        """
        logger.info(f"Forward trace from {start_node_id}")

        paths = []
        queue = deque([(start_node_id, [start_node_id], 0)])
        visited_paths = set()

        while queue:
            current_id, path, depth = queue.popleft()

            if depth > max_depth:
                continue

            # Avoid duplicate paths
            path_key = tuple(path)
            if path_key in visited_paths:
                continue
            visited_paths.add(path_key)

            # Get outgoing edges
            edges = self._outgoing.get(current_id, [])

            # Filter by kind
            if filter_kinds:
                edges = [e for e in edges if e.kind in filter_kinds]

            if not edges:
                # Terminal node - add path
                paths.append(path)
                continue

            # Explore neighbors
            for edge in edges:
                next_id = edge.target_id

                # Avoid cycles (allow revisit with different paths)
                if next_id not in path:
                    new_path = path + [next_id]
                    queue.append((next_id, new_path, depth + 1))

        logger.info(f"Found {len(paths)} forward paths")
        return paths

    def trace_backward(
        self, end_node_id: str, max_depth: int = 50, filter_kinds: set[FlowEdgeKind] | None = None
    ) -> list[list[str]]:
        """
        Backward trace: 이 값이 어디서 왔는가?

        Args:
            end_node_id: Ending node
            max_depth: Max trace depth
            filter_kinds: Filter edge kinds (None = all)

        Returns:
            List of paths (each path is list of node IDs, reversed)
        """
        logger.info(f"Backward trace from {end_node_id}")

        paths = []
        queue = deque([(end_node_id, [end_node_id], 0)])
        visited_paths = set()

        while queue:
            current_id, path, depth = queue.popleft()

            if depth > max_depth:
                continue

            path_key = tuple(path)
            if path_key in visited_paths:
                continue
            visited_paths.add(path_key)

            # Get incoming edges
            edges = self._incoming.get(current_id, [])

            if filter_kinds:
                edges = [e for e in edges if e.kind in filter_kinds]

            if not edges:
                # Terminal node - add reversed path
                paths.append(list(reversed(path)))
                continue

            for edge in edges:
                prev_id = edge.source_id

                if prev_id not in path:
                    new_path = path + [prev_id]
                    queue.append((prev_id, new_path, depth + 1))

        logger.info(f"Found {len(paths)} backward paths")
        return paths

    def trace_taint(
        self,
        source_id: str | None = None,
        sink_id: str | None = None,
        taint_label: str | None = None,
        max_paths: int = 10000,
        timeout_seconds: float = 30.0,
    ) -> list[list[str]]:
        """
        Taint analysis: Source → Sink 경로 추적 (OPTIMIZED)

        Multi-source BFS for O(V+E) instead of O(sources × V × E)

        Use cases:
        - PII tracking
        - Security vulnerability detection
        - Compliance (GDPR, HIPAA)

        Args:
            source_id: Specific source (None = all sources)
            sink_id: Specific sink (None = all sinks)
            taint_label: Filter by taint label (e.g., "PII")
            max_paths: Maximum paths to return
            timeout_seconds: Timeout in seconds

        Returns:
            List of paths from sources to sinks
        """
        import time

        start_time = time.time()

        logger.info(f"Taint analysis: source={source_id}, sink={sink_id}, label={taint_label}")

        # Determine sources
        source_set = {source_id} if source_id else set(self._sources)

        # Filter by taint label
        if taint_label:
            source_set = {s for s in source_set if taint_label in self.nodes[s].taint_labels}

        # Determine sinks
        sink_set = {sink_id} if sink_id else set(self._sinks)

        # Multi-source BFS (OPTIMIZED)
        all_paths = []
        queue = deque()

        # Initialize with all sources
        for src in source_set:
            queue.append((src, [src], 0))

        visited_paths = set()

        while queue and len(all_paths) < max_paths:
            # Timeout check
            if time.time() - start_time > timeout_seconds:
                logger.warning(
                    f"Taint analysis timeout after {timeout_seconds}s, returning {len(all_paths)} partial paths"
                )
                break

            current, path, depth = queue.popleft()

            # Sink reached?
            if current in sink_set:
                all_paths.append(path)
                # Don't stop - may have multiple paths
                continue

            # Depth limit
            if depth > 50:
                continue

            # Path deduplication
            path_key = tuple(path)
            if path_key in visited_paths:
                continue

            # Memory limit
            if len(visited_paths) > max_paths * 2:
                logger.warning("Path memory limit reached")
                break

            visited_paths.add(path_key)

            # Expand neighbors
            for edge in self._outgoing.get(current, []):
                next_id = edge.target_id

                # Cycle prevention
                if next_id not in path:
                    queue.append((next_id, path + [next_id], depth + 1))

        elapsed = time.time() - start_time
        logger.info(f"Found {len(all_paths)} taint paths (visited {len(visited_paths)} states, {elapsed:.2f}s)")

        return all_paths

    def find_cross_service_flows(self) -> list[ValueFlowEdge]:
        """
        Find all cross-service flows

        Returns:
            List of boundary edges
        """
        boundary_edges = [e for e in self.edges if e.boundary_spec is not None]

        logger.info(f"Found {len(boundary_edges)} cross-service flows")
        return boundary_edges

    def get_service_boundaries(self, service_name: str) -> list[BoundarySpec]:
        """
        Get all boundaries for a service

        Args:
            service_name: Service name

        Returns:
            List of BoundarySpec
        """
        boundaries = [b for b in self._boundaries if b.service_name == service_name]

        return boundaries

    def visualize_path(self, path: list[str]) -> str:
        """
        Visualize flow path (for LLM)

        Args:
            path: List of node IDs

        Returns:
            Human-readable path description
        """
        if not path:
            return "Empty path"

        parts = []

        for i, node_id in enumerate(path):
            node = self.nodes.get(node_id)
            if not node:
                parts.append(f"[{node_id}]")
                continue

            # Node info
            node_desc = f"{node.symbol_name} ({node.file_path}:{node.line})"
            parts.append(node_desc)

            # Edge info (if not last node)
            if i < len(path) - 1:
                next_id = path[i + 1]

                # Find edge
                edges = self._outgoing.get(node_id, [])
                edge = next((e for e in edges if e.target_id == next_id), None)

                if edge:
                    edge_desc = self._format_edge(edge)
                    parts.append(f"  → {edge_desc}")

        return "\n".join(parts)

    def _format_edge(self, edge: ValueFlowEdge) -> str:
        """Format edge for visualization"""
        kind_name = edge.kind.value

        if edge.boundary_spec:
            boundary = edge.boundary_spec
            return f"[{kind_name}] {boundary.boundary_type}: {boundary.service_name}/{boundary.endpoint}"

        return f"[{kind_name}]"

    def get_statistics(self) -> dict:
        """Get graph statistics"""
        cross_service_count = len([e for e in self.edges if e.boundary_spec])

        # Count by language
        lang_counts = defaultdict(int)
        for node in self.nodes.values():
            lang_counts[node.language] += 1

        # Count by edge kind
        kind_counts = defaultdict(int)
        for edge in self.edges:
            kind_counts[edge.kind.value] += 1

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "cross_service_edges": cross_service_count,
            "sources": len(self._sources),
            "sinks": len(self._sinks),
            "boundaries": len(self._boundaries),
            "languages": dict(lang_counts),
            "edge_kinds": dict(kind_counts),
        }

    def to_dict(self) -> dict:
        """Serialize to dict"""
        return {
            "nodes": [
                {
                    "node_id": n.node_id,
                    "symbol_name": n.symbol_name,
                    "file_path": n.file_path,
                    "line": n.line,
                    "language": n.language,
                    "value_type": n.value_type,
                    "is_source": n.is_source,
                    "is_sink": n.is_sink,
                    "taint_labels": list(n.taint_labels),
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "kind": e.kind.value,
                    "confidence": e.confidence.value,
                    "has_boundary": e.boundary_spec is not None,
                }
                for e in self.edges
            ],
            "statistics": self.get_statistics(),
        }
