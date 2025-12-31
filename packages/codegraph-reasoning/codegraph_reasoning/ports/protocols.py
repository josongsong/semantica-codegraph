"""
Reasoning Engine Ports

추론 엔진의 포트(인터페이스) 정의
Hexagonal Architecture의 Port 레이어
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

# Domain models import (architecture-compliant)
from ..domain.effect_models import EffectDiff
from ..domain.impact_models import ImpactReport
from ..domain.speculative_models import RiskReport, SpeculativePatch

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument


@dataclass
class SliceResult:
    """Slice 결과 (Port용 공통 타입)"""

    target_symbol: str
    slice_nodes: set[str]
    confidence: float = 0.5
    metadata: dict[str, Any] | None = None


@dataclass
class CacheEntry:
    """Cache 엔트리 (Port용 공통 타입)"""

    updated_graph: "GraphDocument"
    plan_meta: dict[str, Any]
    stats: dict[str, Any]


class ImpactAnalyzerPort(Protocol):
    """
    Impact 분석 포트

    변경된 심볼이 다른 코드에 미치는 영향을 분석
    """

    def analyze_impact(
        self,
        symbol_id: str,
        effect_diff: EffectDiff | None = None,
    ) -> ImpactReport:
        """단일 심볼의 Impact 분석"""
        ...

    def batch_analyze(
        self,
        symbol_ids: list[str],
        effect_diffs: dict[str, EffectDiff] | None = None,
    ) -> dict[str, ImpactReport]:
        """여러 심볼의 Impact 일괄 분석"""
        ...


class EffectAnalyzerPort(Protocol):
    """
    Effect 분석 포트

    코드 변경 전후의 Side Effect 변화 분석
    """

    def compare(
        self,
        symbol_id: str,
        old_code: str,
        new_code: str,
    ) -> EffectDiff:
        """단일 심볼의 Effect 비교"""
        ...

    def batch_compare(
        self,
        changes: dict[str, tuple[str, str]],
    ) -> list[EffectDiff]:
        """여러 심볼의 Effect 일괄 비교"""
        ...

    def get_breaking_changes(
        self,
        diffs: list[EffectDiff],
    ) -> list[EffectDiff]:
        """Breaking change 필터링"""
        ...


class SlicerPort(Protocol):
    """
    Program Slicing 포트

    특정 변수/위치에 영향을 주는 코드 조각 추출
    """

    def slice_for_impact(
        self,
        source_location: str,
        file_path: str,
        line_number: int,
    ) -> SliceResult:
        """Impact 분석용 Slice 생성"""
        ...


class CachePort(Protocol):
    """
    Rebuild Cache 포트

    증분 빌드 결과 캐싱
    """

    def get(
        self,
        old_graph: "GraphDocument",
        changes: dict[str, tuple[str, str]],
    ) -> CacheEntry | None:
        """캐시 조회"""
        ...

    def set(
        self,
        old_graph: "GraphDocument",
        changes: dict[str, tuple[str, str]],
        updated_graph: "GraphDocument",
        plan_meta: dict[str, Any],
        stats: dict[str, Any],
    ) -> None:
        """캐시 저장"""
        ...

    def invalidate(self, changes: dict[str, tuple[str, str]]) -> None:
        """캐시 무효화"""
        ...

    def get_metrics(self) -> dict[str, Any]:
        """캐시 메트릭 조회"""
        ...


class GraphAdapterPort(Protocol):
    """
    Graph Adapter 포트

    GraphDocument 변환 및 조작
    """

    def apply_delta(self, base_graph: Any, delta: Any) -> Any:
        """Delta layer 적용"""
        ...


class SimulatorPort(Protocol):
    """
    Graph Simulator 포트

    Speculative 실행 시뮬레이션
    """

    def simulate_patch(
        self,
        patch: SpeculativePatch,
        base_graph: "GraphDocument | None" = None,
    ) -> Any:  # DeltaGraph (infrastructure 타입)
        """패치 시뮬레이션"""
        ...


class RiskAnalyzerPort(Protocol):
    """
    Risk Analyzer 포트

    변경 위험도 분석
    """

    def analyze_risk(
        self,
        patch: SpeculativePatch,
        delta_graph: Any,  # DeltaGraph (infrastructure 타입)
        base_graph: "GraphDocument",
    ) -> RiskReport:
        """위험도 분석"""
        ...


class ReasoningEnginePort(Protocol):
    """
    Reasoning Engine 통합 포트

    전체 추론 파이프라인
    """

    def analyze_change_impact(
        self,
        old_code: dict[str, str],
        new_code: dict[str, str],
    ) -> dict[str, ImpactReport]:
        """변경 영향도 분석"""
        ...

    def evaluate_speculative_patch(
        self,
        patch: SpeculativePatch,
    ) -> RiskReport:
        """Speculative 패치 평가"""
        ...


# ============================================================
# RFC-007 High-Performance Engine Ports
# ============================================================


@dataclass
class TaintPath:
    """Taint 분석 경로 결과"""

    source_id: str
    sink_id: str
    path: list[str]
    confidence: float = 1.0


@dataclass
class VFGData:
    """ValueFlowGraph 추출 데이터"""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    stats: dict[str, Any]


class TaintEnginePort(Protocol):
    """
    고성능 Taint 분석 포트

    rustworkx 기반 10-50x 빠른 taint analysis
    """

    def load_from_data(self, vfg_data: dict[str, Any]) -> dict[str, Any]:
        """VFG 데이터 로드"""
        ...

    def trace_taint(
        self,
        sources: list[str],
        sinks: list[str],
        max_paths: int = 100,
        timeout_seconds: float = 10.0,
    ) -> list[list[str]]:
        """Taint 경로 추적"""
        ...

    def fast_reachability(self, source_id: str, sink_id: str) -> bool:
        """빠른 도달성 검사"""
        ...

    def invalidate(self, affected_nodes: list[str]) -> int:
        """캐시 무효화"""
        ...

    def get_stats(self) -> dict[str, Any]:
        """엔진 통계"""
        ...


class VFGExtractorPort(Protocol):
    """
    ValueFlowGraph 추출 포트

    Memgraph → VFG 데이터 추출
    """

    def extract_vfg(
        self,
        repo_id: str | None = None,
        snapshot_id: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """VFG 노드/엣지 추출"""
        ...

    def extract_sources_and_sinks(
        self,
        repo_id: str | None = None,
        snapshot_id: str | None = None,
    ) -> dict[str, list[str]]:
        """Source/Sink 노드 추출"""
        ...

    def get_affected_nodes(
        self,
        file_paths: list[str],
        repo_id: str,
        snapshot_id: str,
    ) -> list[str]:
        """변경 영향받는 노드 조회"""
        ...


class ValueFlowBuilderPort(Protocol):
    """
    ValueFlowGraph 빌더 포트

    IRDocument → ValueFlowGraph 변환
    """

    def discover_boundaries(self) -> list[Any]:
        """서비스 경계 자동 발견"""
        ...

    def build_from_ir(
        self,
        ir_documents: list[Any],
        graph_document: "GraphDocument | None" = None,
    ) -> Any:
        """IR에서 ValueFlowGraph 빌드"""
        ...

    def add_boundary_flows(
        self,
        vfg: Any,
        boundaries: list[Any],
        ir_documents: list[Any],
    ) -> int:
        """경계 간 플로우 추가"""
        ...
