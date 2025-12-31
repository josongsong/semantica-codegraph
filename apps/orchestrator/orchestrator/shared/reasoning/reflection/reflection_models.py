"""
Self-Reflection Domain Models (v8.1)

SOTA: Graph-based Code Impact Analysis
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ReflectionVerdict(Enum):
    """Self-Reflection 판정"""

    ACCEPT = "accept"  # 승인 (배포 가능)
    REVISE = "revise"  # 수정 필요
    ROLLBACK = "rollback"  # 롤백 (원복)
    RETRY = "retry"  # 다른 전략 재시도


class StabilityLevel(Enum):
    """Graph 안정성 레벨"""

    STABLE = "stable"  # 안정적 (변경 최소)
    MODERATE = "moderate"  # 중간 (주의 필요)
    UNSTABLE = "unstable"  # 불안정 (위험)
    CRITICAL = "critical"  # 심각 (즉시 중단)


@dataclass
class GraphImpact:
    """
    Graph Impact Analysis (Domain Model)

    SOTA: CFG/DFG/PDG 변화 분석
    """

    # CFG (Control Flow Graph)
    cfg_nodes_before: int = 0
    cfg_nodes_after: int = 0
    cfg_nodes_added: int = 0
    cfg_nodes_removed: int = 0
    cfg_edges_changed: int = 0

    # DFG (Data Flow Graph)
    dfg_nodes_before: int = 0
    dfg_nodes_after: int = 0
    dfg_edges_changed: int = 0

    # PDG (Program Dependence Graph)
    pdg_impact_radius: int = 0  # BFS로 영향받는 노드 수

    # Metrics
    impact_score: float = 0.0  # 0.0 (minimal) ~ 1.0 (massive)
    stability_level: StabilityLevel = StabilityLevel.STABLE

    def calculate_impact_score(self) -> float:
        """
        Impact Score 계산 (Domain Logic)

        Returns:
            0.0 ~ 1.0
        """
        # CFG 변화율
        cfg_total = max(self.cfg_nodes_before, 1)
        cfg_change_rate = (abs(self.cfg_nodes_added) + abs(self.cfg_nodes_removed)) / cfg_total

        # DFG 변화율
        dfg_total = max(self.dfg_nodes_before, 1)
        dfg_change_rate = self.dfg_edges_changed / dfg_total

        # PDG Impact
        pdg_normalized = min(self.pdg_impact_radius / 50.0, 1.0)  # 50개 기준

        # Weighted Sum
        impact = cfg_change_rate * 0.4 + dfg_change_rate * 0.3 + pdg_normalized * 0.3

        return min(impact, 1.0)

    def determine_stability(self) -> StabilityLevel:
        """
        안정성 레벨 결정

        Returns:
            StabilityLevel
        """
        score = self.calculate_impact_score()

        if score < 0.2:
            return StabilityLevel.STABLE
        elif score < 0.5:
            return StabilityLevel.MODERATE
        elif score < 0.8:
            return StabilityLevel.UNSTABLE
        else:
            return StabilityLevel.CRITICAL


@dataclass
class ExecutionTrace:
    """
    실행 추적 (Domain Model)

    코드 변경 후 실행 경로 분석
    """

    # Execution Path
    functions_executed: list[str] = field(default_factory=list)
    coverage_before: float = 0.0  # 0.0 ~ 1.0
    coverage_after: float = 0.0

    # Error Tracking
    new_exceptions: list[str] = field(default_factory=list)
    fixed_exceptions: list[str] = field(default_factory=list)

    # Performance
    execution_time_delta: float = 0.0  # seconds (negative = faster)
    memory_delta: int = 0  # bytes

    def has_regressions(self) -> bool:
        """Regression 발생 여부"""
        return (
            len(self.new_exceptions) > 0
            or self.coverage_after < self.coverage_before - 0.05  # 5% 감소
            or self.execution_time_delta > 2.0  # 2초 이상 느려짐
        )


@dataclass
class ReflectionInput:
    """
    Self-Reflection 입력 (Domain Model)
    """

    # Problem & Solution
    original_problem: str
    strategy_id: str
    strategy_description: str

    # Code Changes
    files_changed: list[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0

    # Execution Results
    execution_success: bool = False
    test_pass_rate: float = 0.0

    # Graph Analysis
    graph_impact: GraphImpact = field(default_factory=GraphImpact)
    execution_trace: ExecutionTrace = field(default_factory=ExecutionTrace)

    # Historical Context
    similar_failures_count: int = 0
    previous_attempts: int = 0


@dataclass
class ReflectionOutput:
    """
    Self-Reflection 출력 (Domain Model)
    """

    # Verdict
    verdict: ReflectionVerdict
    confidence: float  # 0.0 ~ 1.0

    # Analysis
    reasoning: str
    graph_stability: StabilityLevel
    impact_score: float

    # Issues Found
    critical_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Recommendations
    suggested_fixes: list[str] = field(default_factory=list)
    alternative_strategies: list[str] = field(default_factory=list)

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)

    def is_acceptable(self) -> bool:
        """승인 가능한지"""
        return self.verdict == ReflectionVerdict.ACCEPT and self.confidence >= 0.7

    def needs_immediate_action(self) -> bool:
        """즉시 조치 필요한지"""
        return (
            self.verdict in (ReflectionVerdict.ROLLBACK, ReflectionVerdict.RETRY)
            or self.graph_stability == StabilityLevel.CRITICAL
            or len(self.critical_issues) > 0
        )


# ============================================================================
# Decision Rules (Domain Constants)
# ============================================================================


class ReflectionRules:
    """
    Self-Reflection 판정 규칙 (SOTA)

    참고: Multi-Criteria Decision Making
    """

    # Thresholds
    MIN_TEST_PASS_RATE = 0.8  # 80% 이상 통과
    MAX_GRAPH_IMPACT = 0.6  # 60% 미만 변화
    MIN_CONFIDENCE = 0.7  # 70% 이상 신뢰도

    # Weights
    EXECUTION_WEIGHT = 0.4  # 실행 성공
    GRAPH_WEIGHT = 0.3  # Graph 안정성
    TRACE_WEIGHT = 0.2  # 실행 추적
    HISTORICAL_WEIGHT = 0.1  # 과거 성공률

    @classmethod
    def validate_weights(cls) -> bool:
        """가중치 합 검증"""
        total = cls.EXECUTION_WEIGHT + cls.GRAPH_WEIGHT + cls.TRACE_WEIGHT + cls.HISTORICAL_WEIGHT
        return abs(total - 1.0) < 0.001

    @classmethod
    def get_weights(cls) -> dict[str, float]:
        """가중치 딕셔너리"""
        return {
            "execution": cls.EXECUTION_WEIGHT,
            "graph": cls.GRAPH_WEIGHT,
            "trace": cls.TRACE_WEIGHT,
            "historical": cls.HISTORICAL_WEIGHT,
        }
