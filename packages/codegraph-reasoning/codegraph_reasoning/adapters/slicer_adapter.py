"""
Slicer Adapter

ProgramSlicer를 SlicerPort로 래핑

Note: ProgramSlicer는 PDGBuilder를 필요로 하므로,
      GraphDocument만으로는 직접 슬라이싱이 불가능합니다.
      이 어댑터는 간단한 그래프 기반 슬라이싱을 제공합니다.

Hexagonal Architecture:
- Implements SlicerPort (defined in code_foundation domain)
- Adapter pattern: Infrastructure implements Domain Port
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from codegraph_engine.code_foundation.domain.ports.analysis_ports import (
    CodeFragment as PortCodeFragment,
    SliceResult as PortSliceResult,
    SlicerPort,
)
from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument, GraphEdgeKind

logger = logging.getLogger(__name__)


# Slicer constants
DEFAULT_MAX_DEPTH = 3
DEFAULT_CONFIDENCE = 0.7  # Graph-based only (no data flow)


@dataclass
class SimpleSliceResult:
    """간단한 슬라이스 결과"""

    target_symbol: str
    slice_nodes: set[str] = field(default_factory=set)
    code_fragments: list["CodeFragment"] = field(default_factory=list)
    control_context: list[str] = field(default_factory=list)
    total_tokens: int = 0
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_total_lines(self) -> int:
        return sum(frag.end_line - frag.start_line + 1 for frag in self.code_fragments)


@dataclass
class CodeFragment:
    """코드 조각"""

    file_path: str
    start_line: int
    end_line: int
    code: str
    node_id: str
    relevance_score: float = 1.0


class SlicerAdapter(SlicerPort):
    """
    Graph 기반 Slicer Adapter (implements SlicerPort)

    ProgramSlicer가 PDGBuilder를 요구하므로,
    GraphDocument만으로 동작하는 간단한 슬라이서를 제공합니다.

    Hexagonal Architecture:
    - Implements SlicerPort (code_foundation domain)
    - Returns PortSliceResult (Port-defined types)

    제한사항:
    - Data dependency 분석 없음 (call graph만 사용)
    - Control flow 분석 없음
    - Interprocedural 분석 제한적
    """

    def __init__(self, graph: GraphDocument):
        """
        Initialize adapter

        Args:
            graph: GraphDocument
        """
        self.graph = graph
        self._build_indices()
        logger.info(f"SlicerAdapter initialized: {len(graph.graph_nodes)} nodes")

    def _build_indices(self) -> None:
        """
        역방향 인덱스 구축

        Performance: Reuses GraphDocument's pre-built indexes instead of O(E) scan
        """
        # Reuse GraphDocument's pre-built called_by index (callee → callers)
        # Convert list to set for O(1) membership check
        self.callers_index: dict[str, set[str]] = {k: set(v) for k, v in self.graph.indexes.called_by.items()}

        # Build callees index from outgoing edges (caller → callees)
        # This is O(E) but only for CALLS edges via index
        self.callees_index: dict[str, set[str]] = {}
        for node_id in self.graph.graph_nodes:
            edge_ids = self.graph.indexes.outgoing.get(node_id, [])
            for edge_id in edge_ids:
                edge = self.graph.edge_by_id.get(edge_id)
                if edge and edge.kind == GraphEdgeKind.CALLS:
                    if node_id not in self.callees_index:
                        self.callees_index[node_id] = set()
                    self.callees_index[node_id].add(edge.target_id)

    def backward_slice(
        self,
        anchor: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> PortSliceResult:
        """
        Backward slice: anchor의 값에 영향을 주는 모든 심볼 추적

        Implements SlicerPort.backward_slice (Hexagonal Architecture)

        Data dependency 관점:
        - target이 호출하는 함수들 (callees) = target이 의존하는 코드
        - target의 값은 이 함수들의 반환값에 의존

        Call graph 기반 (callees 추적 = dependencies)
        """
        slice_nodes: set[str] = set()
        visited: set[str] = set()

        from collections import deque
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import SliceDirection

        queue = deque([(anchor, 0)])

        while queue:
            current, depth = queue.popleft()

            if current in visited or depth > max_depth:
                continue

            visited.add(current)

            if current in self.graph.graph_nodes:
                slice_nodes.add(current)

            # Backward: callees (이 함수가 호출하는 함수들 = dependencies)
            # target -> calls -> callee 방향 추적
            callees = self.callees_index.get(current, set())
            for callee in callees:
                if callee not in visited:
                    queue.append((callee, depth + 1))

        # Code fragments 추출 (internal format)
        internal_fragments = self._extract_fragments(slice_nodes)

        # Convert to Port format (Hexagonal)
        port_fragments = [
            PortCodeFragment(
                file_path=f.file_path,
                start_line=f.start_line,
                end_line=f.end_line,
                code=f.code,
                node_id=f.node_id,
            )
            for f in internal_fragments
        ]

        return PortSliceResult(
            slice_nodes=slice_nodes,
            code_fragments=port_fragments,
            anchor=anchor,
            direction=SliceDirection.BACKWARD,
        )

    def forward_slice(
        self,
        anchor: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> PortSliceResult:
        """
        Forward slice: anchor의 변경이 영향을 미치는 모든 심볼 추적

        Implements SlicerPort.forward_slice (Hexagonal Architecture)

        Impact 관점:
        - source를 호출하는 함수들 (callers) = source에 의존하는 코드
        - source 변경 시 이 함수들이 영향받음

        Call graph 기반 (callers 추적 = dependents)
        """
        slice_nodes: set[str] = set()
        visited: set[str] = set()

        from collections import deque
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import SliceDirection

        queue = deque([(anchor, 0)])

        while queue:
            current, depth = queue.popleft()

            if current in visited or depth > max_depth:
                continue

            visited.add(current)

            if current in self.graph.graph_nodes:
                slice_nodes.add(current)

            # Forward: callers (이 함수를 호출하는 함수들 = dependents)
            # caller -> calls -> source 역방향 추적
            callers = self.callers_index.get(current, set())
            for caller in callers:
                if caller not in visited:
                    queue.append((caller, depth + 1))

        # Code fragments 추출 (internal format)
        internal_fragments = self._extract_fragments(slice_nodes)

        # Convert to Port format (Hexagonal)
        port_fragments = [
            PortCodeFragment(
                file_path=f.file_path,
                start_line=f.start_line,
                end_line=f.end_line,
                code=f.code,
                node_id=f.node_id,
            )
            for f in internal_fragments
        ]

        return PortSliceResult(
            slice_nodes=slice_nodes,
            code_fragments=port_fragments,
            anchor=anchor,
            direction=SliceDirection.FORWARD,
        )

    def slice_for_impact(
        self,
        source_location: str,
        file_path: str,
        line_number: int,
    ) -> SimpleSliceResult:
        """
        영향도 분석용 슬라이스 (SlicerPort 호환)

        Args:
            source_location: Symbol ID
            file_path: 파일 경로 (현재 미사용)
            line_number: 라인 번호 (현재 미사용)

        Returns:
            Forward slice 결과
        """
        return self.forward_slice(source_location)

    def _extract_fragments(self, node_ids: set[str]) -> list[CodeFragment]:
        """노드들의 코드 조각 추출"""
        fragments = []

        for node_id in node_ids:
            node = self.graph.graph_nodes.get(node_id)
            if not node:
                continue

            # Node span이 있으면 사용
            if node.span:
                start_line = node.span.start_line
                end_line = node.span.end_line
            else:
                start_line = 1
                end_line = 1

            # Code는 attrs에서 가져오거나 placeholder
            code = ""
            if node.attrs and "code" in node.attrs:
                code = node.attrs["code"]
            elif node.attrs and "body" in node.attrs:
                code = str(node.attrs["body"])
            else:
                code = f"# {node.name}"

            fragment = CodeFragment(
                file_path=node.path or "<unknown>",
                start_line=start_line,
                end_line=end_line,
                code=code,
                node_id=node_id,
            )
            fragments.append(fragment)

        # Sort by file and line
        fragments.sort(key=lambda f: (f.file_path, f.start_line))
        return fragments


# Type check
def _type_check() -> None:
    """Static type check (not executed at runtime)"""

    # SlicerAdapter requires GraphDocument
    pass
