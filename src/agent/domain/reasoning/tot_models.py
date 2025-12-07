"""
Tree-of-Thought Domain Models (v8.1)

SOTA: Multi-Criteria Scoring for Code Domain
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


class StrategyType(Enum):
    """전략 유형 (Code Domain 특화)"""

    DIRECT_FIX = "direct_fix"  # 직접 수정
    REFACTOR_THEN_FIX = "refactor_fix"  # 리팩토링 후 수정
    TEST_DRIVEN = "test_driven"  # TDD 접근
    DEFENSIVE = "defensive"  # 방어적 코딩
    PATTERN_BASED = "pattern_based"  # 디자인 패턴 적용


class ExecutionStatus(Enum):
    """실행 상태"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class CodeStrategy:
    """
    ToT 전략 (Domain Model)

    SOTA: Code Domain 특화 속성
    """

    # Identity
    strategy_id: str
    strategy_type: StrategyType

    # Description
    title: str
    description: str
    rationale: str  # Why this approach?

    # Code Changes
    file_changes: dict[str, str] = field(default_factory=dict)  # {path: new_content}

    # Execution State
    status: ExecutionStatus = ExecutionStatus.PENDING

    # Metadata
    llm_confidence: float = 0.0
    estimated_effort: int = 0  # Lines of code to change
    created_at: datetime = field(default_factory=datetime.now)

    def is_completed(self) -> bool:
        """실행 완료되었는지"""
        return self.status == ExecutionStatus.COMPLETED

    def is_failed(self) -> bool:
        """실행 실패했는지"""
        return self.status in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT)


@dataclass
class ExecutionResult:
    """
    Sandbox 실행 결과 (Domain Model)

    SOTA: Multi-Criteria 평가
    """

    strategy_id: str

    # Compilation
    compile_success: bool = False
    compile_errors: list[str] = field(default_factory=list)

    # Testing
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    test_pass_rate: float = 0.0

    # Static Analysis
    lint_errors: int = 0
    lint_warnings: int = 0
    type_errors: int = 0

    # Security
    security_issues: int = 0
    security_severity: Literal["none", "low", "medium", "high", "critical"] = "none"

    # Code Quality
    complexity_before: float = 0.0
    complexity_after: float = 0.0
    complexity_delta: float = 0.0  # Negative is better

    # Graph Impact (CFG/DFG)
    cfg_nodes_added: int = 0
    cfg_nodes_removed: int = 0
    dfg_edges_changed: int = 0

    # Performance
    execution_time: float = 0.0  # seconds
    memory_delta: int = 0  # bytes

    # Error Details
    error_message: str = ""
    stack_trace: str = ""

    def has_critical_issues(self) -> bool:
        """치명적 이슈 여부"""
        return not self.compile_success or self.security_severity in ("high", "critical") or self.test_pass_rate < 0.3


@dataclass
class StrategyScore:
    """
    전략 점수 (Domain Model)

    SOTA: Multi-Criteria Decision Making
    """

    strategy_id: str

    # Individual Scores (0.0 ~ 1.0)
    correctness_score: float = 0.0  # 정확성 (테스트 통과)
    quality_score: float = 0.0  # 품질 (복잡도, lint)
    security_score: float = 0.0  # 보안
    maintainability_score: float = 0.0  # 유지보수성
    performance_score: float = 0.0  # 성능

    # Weighted Total (0.0 ~ 1.0)
    total_score: float = 0.0

    # Confidence
    confidence: float = 0.0

    # Reasoning
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    recommendation: str = ""

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)

    def is_acceptable(self, threshold: float = 0.6) -> bool:
        """승인 가능한 점수인지"""
        return self.total_score >= threshold and self.confidence >= 0.5

    def get_ranking_key(self) -> tuple[float, float]:
        """정렬 키 (total_score desc, confidence desc)"""
        return (-self.total_score, -self.confidence)


@dataclass
class ToTResult:
    """
    Tree-of-Thought 최종 결과 (Domain Model)
    """

    # Strategies
    all_strategies: list[CodeStrategy] = field(default_factory=list)
    executed_strategies: list[CodeStrategy] = field(default_factory=list)

    # Scores
    scores: dict[str, StrategyScore] = field(default_factory=dict)  # {strategy_id: score}

    # Best Strategy
    best_strategy_id: str | None = None
    best_score: float = 0.0

    # Stats
    total_generated: int = 0
    total_executed: int = 0
    total_passed: int = 0

    # Metadata
    generation_time: float = 0.0
    execution_time: float = 0.0
    total_time: float = 0.0

    def get_top_k(self, k: int = 3) -> list[tuple[str, StrategyScore]]:
        """
        상위 K개 전략 반환

        Args:
            k: 반환할 전략 수

        Returns:
            [(strategy_id, score), ...]
        """
        sorted_scores = sorted(self.scores.items(), key=lambda x: x[1].get_ranking_key())
        return sorted_scores[:k]

    def has_acceptable_solution(self, threshold: float = 0.6) -> bool:
        """승인 가능한 솔루션이 있는지"""
        return any(score.is_acceptable(threshold) for score in self.scores.values())


# ============================================================================
# Scoring Weights (Domain Constants)
# ============================================================================


class ScoringWeights:
    """
    Multi-Criteria 가중치 (SOTA)

    참고: MCDM (Multi-Criteria Decision Making)
    """

    # Default Weights
    CORRECTNESS = 0.40  # 정확성이 가장 중요
    QUALITY = 0.25  # 코드 품질
    SECURITY = 0.20  # 보안
    MAINTAINABILITY = 0.10  # 유지보수성
    PERFORMANCE = 0.05  # 성능

    @classmethod
    def validate(cls) -> bool:
        """가중치 합이 1.0인지 검증"""
        total = cls.CORRECTNESS + cls.QUALITY + cls.SECURITY + cls.MAINTAINABILITY + cls.PERFORMANCE
        return abs(total - 1.0) < 0.001

    @classmethod
    def get_weights(cls) -> dict[str, float]:
        """가중치 딕셔너리 반환"""
        return {
            "correctness": cls.CORRECTNESS,
            "quality": cls.QUALITY,
            "security": cls.SECURITY,
            "maintainability": cls.MAINTAINABILITY,
            "performance": cls.PERFORMANCE,
        }
