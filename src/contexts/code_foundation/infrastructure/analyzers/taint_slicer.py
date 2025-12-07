"""
Taint-aware Program Slicer

Taint 분석과 Program Slicing을 결합한 고급 보안 분석기.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.common.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.analyzers.taint_analyzer import TaintPath
    from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument
    from src.contexts.reasoning_engine.infrastructure.pdg.pdg_builder import PDGBuilder
    from src.contexts.reasoning_engine.infrastructure.slicer.slicer import ProgramSlicer, SliceResult

logger = get_logger(__name__)


@dataclass
class TaintSliceResult:
    """Taint 슬라이싱 결과"""

    source_node: str
    """Taint source 노드"""

    sink_node: str
    """Taint sink 노드"""

    taint_path: list[str]
    """Taint propagation path (node IDs)"""

    slice_result: "SliceResult"
    """Program slice 결과"""

    severity: str
    """취약점 심각도 (high, medium, low)"""

    is_sanitized: bool
    """Sanitizer를 거쳤는지 여부"""

    vulnerability_type: str
    """취약점 유형 (sql_injection, xss, command_injection 등)"""


class TaintSlicer:
    """
    Taint-aware slicer

    Program slicing을 활용한 정교한 taint 분석:
    1. Source → Sink 경로 찾기 (taint analysis)
    2. 경로상 모든 영향 노드 찾기 (program slicing)
    3. Sanitizer 체크
    """

    def __init__(
        self,
        pdg_builder: "PDGBuilder",
        slicer: "ProgramSlicer",
        taint_analyzer: "TaintAnalyzer | None" = None,
    ):
        """
        Args:
            pdg_builder: PDG builder
            slicer: Program slicer
            taint_analyzer: Taint analyzer (optional)
        """
        self.pdg = pdg_builder
        self.slicer = slicer
        self.taint_analyzer = taint_analyzer

        if not taint_analyzer:
            from src.contexts.code_foundation.infrastructure.analyzers.taint_analyzer import TaintAnalyzer

            self.taint_analyzer = TaintAnalyzer()

    def analyze_taint_with_slicing(
        self,
        ir_doc: "IRDocument",
        max_depth: int = 100,
    ) -> list[TaintSliceResult]:
        """
        Taint 분석 + 슬라이싱 결합.

        각 taint path에 대해:
        1. Source → Sink 경로 찾기
        2. 경로상 모든 노드 슬라이싱
        3. 영향받는 모든 코드 포함

        Args:
            ir_doc: IR document
            max_depth: 최대 슬라이싱 깊이

        Returns:
            List of TaintSliceResult
        """
        results = []

        # Taint 분석
        taint_paths = self.taint_analyzer.analyze_taint_flow(ir_doc)

        logger.info(f"Found {len(taint_paths)} taint paths")

        for taint_path in taint_paths:
            try:
                result = self._analyze_single_path(taint_path, max_depth)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Failed to analyze taint path: {e}")
                continue

        return results

    def _analyze_single_path(
        self,
        taint_path: "TaintPath",
        max_depth: int,
    ) -> TaintSliceResult | None:
        """
        단일 taint path 분석.

        Args:
            taint_path: Taint path
            max_depth: Max slicing depth

        Returns:
            TaintSliceResult or None
        """
        # Source와 Sink 노드 ID 추출
        source_node_id = self._extract_node_id(taint_path.source.pattern)
        sink_node_id = self._extract_node_id(taint_path.sink.pattern)

        if not source_node_id or not sink_node_id:
            return None

        # Backward slice from sink (sink에 영향을 준 모든 코드)
        slice_result = self.slicer.backward_slice(sink_node_id, max_depth)

        # Check if source is in slice
        if source_node_id not in slice_result.slice_nodes:
            # Source가 슬라이스에 없으면 관련 없음
            return None

        # Extract path
        path_nodes = self._extract_path_from_slice(
            source_node_id,
            sink_node_id,
            slice_result.slice_nodes,
        )

        # Determine severity
        severity = taint_path.sink.severity if taint_path.sink else "medium"

        # Vulnerability type
        vuln_type = self._infer_vulnerability_type(taint_path.sink.pattern)

        return TaintSliceResult(
            source_node=source_node_id,
            sink_node=sink_node_id,
            taint_path=path_nodes,
            slice_result=slice_result,
            severity=severity,
            is_sanitized=taint_path.is_sanitized,
            vulnerability_type=vuln_type,
        )

    def _extract_node_id(self, pattern: str) -> str | None:
        """
        Pattern에서 노드 ID 추출.

        Args:
            pattern: Source/Sink pattern (e.g., "request.get", "db.execute")

        Returns:
            Node ID or None
        """
        # PDG에서 패턴과 매칭되는 노드 찾기
        for node_id, node in self.pdg.nodes.items():
            if pattern in node.statement:
                return node_id

        return None

    def _extract_path_from_slice(
        self,
        source_id: str,
        sink_id: str,
        slice_nodes: set[str],
    ) -> list[str]:
        """
        슬라이스에서 source → sink 경로 추출.

        Args:
            source_id: Source node ID
            sink_id: Sink node ID
            slice_nodes: Slice node IDs

        Returns:
            Path (list of node IDs)
        """
        # BFS로 경로 찾기
        from collections import deque

        queue = deque([(source_id, [source_id])])
        visited = set()

        while queue:
            current, path = queue.popleft()

            if current == sink_id:
                return path

            if current in visited:
                continue

            visited.add(current)

            # Get dependents (data flow only)
            deps = self.pdg.get_dependents(current)
            for dep in deps:
                if dep.to_node in slice_nodes and dep.to_node not in visited:
                    queue.append((dep.to_node, path + [dep.to_node]))

        # No path found, return slice nodes
        return list(slice_nodes)

    def _infer_vulnerability_type(self, sink_pattern: str) -> str:
        """
        Sink 패턴으로 취약점 유형 추론.

        Args:
            sink_pattern: Sink pattern

        Returns:
            Vulnerability type
        """
        if "execute" in sink_pattern or "raw" in sink_pattern:
            return "sql_injection"
        elif "eval" in sink_pattern or "exec" in sink_pattern:
            return "code_injection"
        elif "system" in sink_pattern or "subprocess" in sink_pattern:
            return "command_injection"
        elif "render" in sink_pattern or "template" in sink_pattern:
            return "xss"
        elif "open" in sink_pattern or "write" in sink_pattern:
            return "path_traversal"
        else:
            return "unknown"

    def get_vulnerability_report(
        self,
        results: list[TaintSliceResult],
    ) -> dict:
        """
        취약점 리포트 생성.

        Args:
            results: Taint slice results

        Returns:
            Report dict
        """
        # 심각도별 집계
        by_severity = {"high": [], "medium": [], "low": []}

        for result in results:
            if not result.is_sanitized:  # Sanitized는 제외
                by_severity.setdefault(result.severity, []).append(result)

        # 타입별 집계
        by_type = {}
        for result in results:
            if not result.is_sanitized:
                by_type.setdefault(result.vulnerability_type, []).append(result)

        return {
            "total_findings": len(results),
            "unsanitized": len([r for r in results if not r.is_sanitized]),
            "by_severity": {
                "high": len(by_severity.get("high", [])),
                "medium": len(by_severity.get("medium", [])),
                "low": len(by_severity.get("low", [])),
            },
            "by_type": {k: len(v) for k, v in by_type.items()},
            "findings": results,
        }
