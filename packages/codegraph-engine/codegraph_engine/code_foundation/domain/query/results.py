"""
Query Results - Pure Domain

PathResult, PathSet, VerificationResult, UnifiedNode, UnifiedEdge

RFC-031 Compliance:
- NodeKind: Canonical from ir/models/kinds.py (via types.py re-export)
- EdgeType: Query-specific edge abstraction
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from .types import EdgeType, NodeKind  # NodeKind is canonical (RFC-031)

if TYPE_CHECKING:
    from .ports import CodeTraceProvider
    from .selectors import EdgeSelector, NodeSelector


class TruncationReason(Enum):
    """Why path search was truncated (Legacy - use StopReason)"""

    TIMEOUT = "timeout"
    NODE_LIMIT = "node_limit"
    PATH_LIMIT = "path_limit"


class StopReason(Enum):
    """
    Why query execution stopped (RFC-021 Phase 1)

    Replaces TruncationReason with more comprehensive reasons.
    """

    COMPLETE = "complete"  # 정상 종료
    TIMEOUT = "timeout"  # 시간 초과
    MAX_PATHS = "max_paths"  # 경로 개수 초과
    MAX_NODES = "max_nodes"  # 방문 노드 수 초과
    MAX_DEPTH = "max_depth"  # 탐색 깊이 초과
    SCOPE_LIMIT = "scope_limit"  # ScopeSpec에 의해 탐색 불가
    NO_MATCH = "no_match"  # Source/Sink 매칭 실패
    ERROR = "error"  # Exception 발생 (Phase 3에서 사용)


class UncertainReason(Enum):
    """
    불확실성 근거 (RFC-021 Phase 1)

    PathResult.uncertain=True 원인
    """

    MAY_ALIAS = "may_alias"  # Alias 분석 한계
    CONTEXT_CUTOFF = "context_cutoff"  # k-CFA 깊이 초과
    SUMMARY_APPROX = "summary_approx"  # 함수 요약 근사치
    HEAP_CUTOFF = "heap_cutoff"  # 힙 추상화 한계
    EXTERNAL_CALL = "external_call"  # 외부 라이브러리 호출


@dataclass
class UnifiedNode:
    """
    Unified node (abstraction over IR entities)

    Can represent:
    - Node (Function, Class, Module, etc)
    - VariableEntity (from DFG)
    - ControlFlowBlock (from CFG)

    Provides uniform interface for Query Engine.

    Attributes:
        id: Unique node ID
        kind: Node kind (NodeKind enum)
        name: Node name
        file_path: Source file path
        span: Source location (start_line, start_col, end_line, end_col)
        attrs: Additional attributes
    """

    id: str
    kind: NodeKind
    name: str | None
    file_path: str
    span: tuple[int, int, int, int] | None  # (start_line, start_col, end_line, end_col)
    attrs: dict = field(default_factory=dict)
    context: str | None = None  # Call context for context-sensitive analysis

    def __repr__(self) -> str:
        """Human-readable representation"""
        location = f"{self.file_path}:{self.span[0]}" if self.span else self.file_path
        return f"<{self.kind}: {self.name or self.id} @ {location}>"

    def __hash__(self) -> int:
        """Enable use in sets and dict keys"""
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        """Equality based on id"""
        if isinstance(other, UnifiedNode):
            return self.id == other.id
        return False


@dataclass
class UnifiedEdge:
    """
    Unified edge (abstraction over IR edges)

    Can represent:
    - DataFlowEdge (from DFG)
    - ControlFlowEdge (from CFG)
    - PreciseCallEdge (from Call Graph)

    Attributes:
        from_node: Source node ID
        to_node: Target node ID
        edge_type: Edge type (EdgeType enum)
        attrs: Additional attributes
    """

    from_node: str
    to_node: str
    edge_type: EdgeType
    attrs: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        """Human-readable representation"""
        return f"<{self.edge_type}: {self.from_node} → {self.to_node}>"


@dataclass
class PathResult:
    """
    Single path result

    Represents one path found by Query Engine.

    Attributes:
        nodes: Ordered list of nodes in path
        edges: Ordered list of edges connecting nodes
        uncertain: True if contains may-alias (v3.4+)
        uncertain_reasons: 불확실성 근거 (RFC-021 Phase 1)
        tainted_variables: Taint 분석 확장 필드
        call_context_ids: k-CFA context IDs
        is_sanitized: Sanitizer 통과 여부
        severity: 심각도 (정책에서 결정, QueryEngine은 전달만)
    """

    nodes: list[UnifiedNode]
    edges: list[UnifiedEdge]
    uncertain: bool = False
    uncertain_reasons: tuple[UncertainReason, ...] = ()  # RFC-021 Phase 1

    # Deep 분석 확장 필드 (Phase 2에서 사용)
    tainted_variables: frozenset[str] = field(default_factory=frozenset)
    call_context_ids: tuple[int, ...] = ()
    is_sanitized: bool = False
    severity: str | None = None  # 정책에서 결정, QueryEngine은 전달만

    def __len__(self) -> int:
        """Path length (number of nodes)"""
        return len(self.nodes)

    def __getitem__(self, idx: int) -> UnifiedNode:
        """Get node by index"""
        return self.nodes[idx]

    def __iter__(self) -> Iterator[UnifiedNode]:
        """Iterate over nodes"""
        return iter(self.nodes)

    def has_node(self, selector: "NodeSelector") -> bool:
        """
        Check if path contains node matching selector

        Pure logic - checks node attributes against selector criteria.

        Example:
            path.has_node(Q.Var("x"))
            path.has_node(Q.Call("sanitize"))
        """
        for node in self.nodes:
            if self._node_matches(node, selector):
                return True
        return False

    def has_edge(self, edge_type: "EdgeSelector") -> bool:
        """
        Check if path contains edge of type

        Example:
            path.has_edge(E.CALL)
            path.has_edge(E.DFG)
        """
        target_type = edge_type.edge_type

        if target_type == EdgeType.ALL:
            return len(self.edges) > 0

        for edge in self.edges:
            if edge.edge_type == target_type:
                return True
        return False

    def subpath(self, start: int, end: int) -> "PathResult":
        """
        Extract subpath

        Args:
            start: Start index (inclusive)
            end: End index (exclusive)

        Example:
            path.subpath(1, 3)  # Nodes 1, 2
        """
        return PathResult(
            nodes=self.nodes[start:end],
            edges=self.edges[start : end - 1] if end > start else [],
            uncertain=self.uncertain,
        )

    def show_code_trace(self, trace_provider: "CodeTraceProvider", context_lines: int = 2) -> str:
        """
        Show code trace with context

        Args:
            trace_provider: Code trace provider (from infrastructure)
            context_lines: Lines of context before/after

        Returns:
            Formatted code trace

        Example:
            from infra.query.code_trace import DefaultCodeTraceProvider
            provider = DefaultCodeTraceProvider(ir_doc)
            trace = path.show_code_trace(provider, context_lines=3)
        """

        return trace_provider.get_trace(self, context_lines)

    def _node_matches(self, node: UnifiedNode, selector: "NodeSelector") -> bool:
        """
        Check if node matches selector (pure logic)

        RFC-031: Uses SelectorType → NodeKind mapping for comparison.
        """
        from .types import SelectorType

        # Type check
        if selector.selector_type == SelectorType.ANY:
            return True

        # RFC-031: SelectorType → NodeKind mapping
        selector_to_kinds: dict[SelectorType, set[NodeKind]] = {
            SelectorType.VAR: {NodeKind.VARIABLE},
            SelectorType.FUNC: {NodeKind.FUNCTION, NodeKind.METHOD},
            SelectorType.CALL: {NodeKind.FUNCTION},  # Call sites represented as function refs
            SelectorType.BLOCK: {NodeKind.BLOCK, NodeKind.CFG_BLOCK},
            SelectorType.MODULE: {NodeKind.MODULE, NodeKind.FILE},
            SelectorType.CLASS: {NodeKind.CLASS, NodeKind.INTERFACE},
            SelectorType.FIELD: {NodeKind.FIELD, NodeKind.PROPERTY},
            SelectorType.EXPR: set(),  # Expressions use attrs matching
        }

        allowed_kinds = selector_to_kinds.get(selector.selector_type, set())
        if allowed_kinds and node.kind not in allowed_kinds:
            return False

        # Name check
        if selector.name:
            if node.name != selector.name:
                return False

        # Pattern check (infrastructure will handle)
        # Attrs check (infrastructure will handle)

        return True

    def __repr__(self) -> str:
        """Human-readable representation"""
        return f"PathResult({len(self)} nodes, {len(self.edges)} edges)"


@dataclass
class PathSet:
    """
    Collection of paths (∃ query result)

    Result of existential query (any_path()).
    Contains one or more paths.

    RFC-021 Phase 1:
    - Added stop_reason (replaces complete + truncation_reason)
    - Added diagnostics for debugging
    - Added elapsed_ms, nodes_visited for metrics

    Attributes:
        paths: List of path results
        stop_reason: Why execution stopped (RFC-021)
        elapsed_ms: Execution time in milliseconds
        nodes_visited: Number of nodes visited
        diagnostics: Debug information (format: "key: value")
        complete: (Legacy) True if all paths explored
        truncation_reason: (Legacy) Why truncated
    """

    paths: list[PathResult]
    stop_reason: StopReason = StopReason.COMPLETE
    elapsed_ms: int = 0
    nodes_visited: int = 0
    diagnostics: tuple[str, ...] = ()  # Format: "key: value"

    # Legacy fields (for backward compatibility) - CRITICAL: init=True for old tests
    complete: bool | None = None
    truncation_reason: TruncationReason | None = None

    def __post_init__(self):
        """
        Backward compatibility handler (Critical Fix)

        Supports both signatures:
        - Old: PathSet(paths=[], complete=True, truncation_reason=...)
        - New: PathSet(paths=[], stop_reason=..., elapsed_ms=...)
        """
        # Case 1: Old signature (complete provided)
        if self.complete is not None and self.stop_reason is None:
            # Old → New
            if self.complete:
                object.__setattr__(self, "stop_reason", StopReason.COMPLETE)
            elif self.truncation_reason == TruncationReason.TIMEOUT:
                object.__setattr__(self, "stop_reason", StopReason.TIMEOUT)
            elif self.truncation_reason == TruncationReason.PATH_LIMIT:
                object.__setattr__(self, "stop_reason", StopReason.MAX_PATHS)
            elif self.truncation_reason == TruncationReason.NODE_LIMIT:
                object.__setattr__(self, "stop_reason", StopReason.MAX_NODES)
            else:
                # complete=False but no truncation_reason
                object.__setattr__(self, "stop_reason", StopReason.TIMEOUT)

        # Case 2: New signature (stop_reason provided)
        elif self.stop_reason is not None:
            # New → Old
            if self.complete is None:
                object.__setattr__(self, "complete", self.stop_reason == StopReason.COMPLETE)

            if self.truncation_reason is None:
                # Map stop_reason to truncation_reason
                if self.stop_reason == StopReason.TIMEOUT:
                    object.__setattr__(self, "truncation_reason", TruncationReason.TIMEOUT)
                elif self.stop_reason in (StopReason.MAX_PATHS, StopReason.MAX_DEPTH):
                    object.__setattr__(self, "truncation_reason", TruncationReason.PATH_LIMIT)
                elif self.stop_reason == StopReason.MAX_NODES:
                    object.__setattr__(self, "truncation_reason", TruncationReason.NODE_LIMIT)

        # Case 3: Neither provided (default)
        else:
            object.__setattr__(self, "stop_reason", StopReason.COMPLETE)
            object.__setattr__(self, "complete", True)

    @property
    def is_partial(self) -> bool:
        """RFC-021: True if result is partial (timeout/limit)"""
        return self.stop_reason in (
            StopReason.TIMEOUT,
            StopReason.MAX_PATHS,
            StopReason.MAX_NODES,
            StopReason.MAX_DEPTH,
        )

    def __len__(self) -> int:
        """Number of paths"""
        return len(self.paths)

    def __iter__(self) -> Iterator[PathResult]:
        """Iterate over paths"""
        return iter(self.paths)

    def __bool__(self) -> bool:
        """True if at least one path found"""
        return len(self.paths) > 0

    def shortest(self) -> PathResult:
        """
        Get shortest path

        Raises:
            ValueError: If no paths
        """
        if not self.paths:
            raise ValueError("No paths in PathSet")
        return min(self.paths, key=len)

    def longest(self) -> PathResult:
        """
        Get longest path

        Raises:
            ValueError: If no paths
        """
        if not self.paths:
            raise ValueError("No paths in PathSet")
        return max(self.paths, key=len)

    def limit(self, n: int) -> "PathSet":
        """
        Limit to first n paths

        Args:
            n: Number of paths to keep

        Example:
            paths.limit(5)  # First 5 paths
        """
        return PathSet(paths=self.paths[:n], complete=self.complete, truncation_reason=self.truncation_reason)

    def describe(self) -> str:
        """
        Human-readable description

        Example:
            "PathSet: 15 paths, complete"
            "PathSet: 100 paths, truncated (timeout)"
        """
        status = "complete" if self.complete else f"truncated ({self.truncation_reason.value})"
        return f"PathSet: {len(self)} paths, {status}"

    def __repr__(self) -> str:
        """Human-readable representation"""
        return self.describe()


@dataclass
class VerificationResult:
    """
    Universal query result (∀)

    Result of universal query (all_paths()).
    Checks if ALL paths satisfy condition.

    Attributes:
        ok: True if all paths satisfy condition
        violation_path: First path that violates condition (if ok=False)
    """

    ok: bool
    violation_path: PathResult | None = None

    def __bool__(self) -> bool:
        """True if verification passed"""
        return self.ok

    def __repr__(self) -> str:
        """Human-readable representation"""
        if self.ok:
            return "VerificationResult(ok=True)"
        else:
            return f"VerificationResult(ok=False, violation={self.violation_path})"
