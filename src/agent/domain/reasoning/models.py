"""
Reasoning Domain Models (v8.1)

순수 Domain Models - 외부 의존성 없음
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ReasoningPath(Enum):
    """추론 경로 (System 1 vs System 2)"""

    SYSTEM_1 = "fast"  # Linear, v7 Engine
    SYSTEM_2 = "slow"  # ReAct + ToT, v8 Engine


@dataclass
class QueryFeatures:
    """
    Query 분석 피처 (Domain Model)

    순수 데이터 + 비즈니스 로직
    """

    # Code Complexity
    file_count: int
    impact_nodes: int
    cyclomatic_complexity: float

    # Risk Factors
    has_test_failure: bool
    touches_security_sink: bool
    regression_risk: float

    # Historical Context
    similar_success_rate: float
    previous_attempts: int = 0

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)

    def calculate_complexity_score(self) -> float:
        """
        복잡도 점수 계산 (Domain Logic)

        Returns:
            0.0 ~ 1.0 점수
        """
        # 파일 수 영향 (최대 10개 기준)
        file_score = min(self.file_count / 10.0, 1.0)

        # 영향 노드 수 (최대 100개 기준)
        impact_score = min(self.impact_nodes / 100.0, 1.0)

        # Cyclomatic Complexity (최대 50 기준)
        complexity_score = min(self.cyclomatic_complexity / 50.0, 1.0)

        # 가중 평균
        return file_score * 0.2 + impact_score * 0.3 + complexity_score * 0.5

    def calculate_risk_score(self) -> float:
        """
        위험도 점수 계산 (Domain Logic)

        Returns:
            0.0 ~ 1.0 점수
        """
        score = self.regression_risk * 0.5

        if self.has_test_failure:
            score += 0.3

        if self.touches_security_sink:
            score += 0.2

        # 이전 시도 실패가 많으면 위험도 증가
        if self.previous_attempts > 2:
            score += 0.1 * (self.previous_attempts - 2)

        return min(score, 1.0)

    def calculate_confidence_penalty(self) -> float:
        """
        유사 성공률 기반 신뢰도 페널티

        Returns:
            0.0 ~ 0.3 페널티
        """
        if self.similar_success_rate > 0.8:
            return 0.0
        elif self.similar_success_rate > 0.5:
            return 0.1
        else:
            return 0.3


@dataclass
class ReasoningDecision:
    """
    추론 결정 결과 (Domain Model)
    """

    path: ReasoningPath
    confidence: float
    reasoning: str

    # Scores
    complexity_score: float
    risk_score: float

    # Estimates
    estimated_cost: float  # USD
    estimated_time: float  # seconds

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)

    def is_fast_path(self) -> bool:
        """System 1 경로인지"""
        return self.path == ReasoningPath.SYSTEM_1

    def is_slow_path(self) -> bool:
        """System 2 경로인지"""
        return self.path == ReasoningPath.SYSTEM_2

    def should_proceed(self, min_confidence: float = 0.6) -> bool:
        """진행 가능 여부 (신뢰도 기준)"""
        return self.confidence >= min_confidence


@dataclass
class CodeCandidate:
    """
    Tree-of-Thought 후보 전략 (Domain Model)
    """

    # Identity
    candidate_id: str
    strategy_description: str

    # Code
    code_diff: str
    approach_type: str  # "refactor", "bugfix", "feature", etc.

    # Execution Results
    compile_success: bool = False
    test_pass_rate: float = 0.0
    lint_errors: int = 0
    security_issues: int = 0

    # Graph Impact
    cfg_delta: int = 0
    dfg_impact_radius: int = 0

    # Metadata
    llm_confidence: float = 0.0
    execution_time: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)

    def is_executable(self) -> bool:
        """실행 가능한지 (컴파일 성공)"""
        return self.compile_success

    def has_critical_issues(self) -> bool:
        """치명적 이슈가 있는지"""
        return not self.compile_success or self.security_issues > 0 or self.test_pass_rate < 0.3

    def calculate_quality_score(self) -> float:
        """
        전체 품질 점수 (간략 버전)

        Returns:
            0.0 ~ 1.0 점수
        """
        if not self.compile_success:
            return 0.0

        # 기본 점수
        score = 0.3  # 컴파일 성공

        # 테스트 통과율
        score += self.test_pass_rate * 0.4

        # Lint 에러 페널티
        lint_penalty = min(self.lint_errors * 0.05, 0.2)
        score -= lint_penalty

        # 보안 이슈 페널티
        if self.security_issues > 0:
            score -= 0.3

        return max(score, 0.0)


class ReflectionVerdict(Enum):
    """Self-Reflection 판정"""

    ACCEPT = "accept"  # 승인
    REVISE = "revise"  # 수정 필요
    ROLLBACK = "rollback"  # 롤백
    RETRY = "retry"  # 다른 전략으로 재시도


@dataclass
class ReflectionInput:
    """Self-Reflection 입력 (Domain Model)"""

    # Problem Context
    original_problem: str
    strategy: CodeCandidate

    # Graph Delta (simplified)
    cfg_nodes_before: int
    cfg_nodes_after: int
    dfg_edges_before: int
    dfg_edges_after: int

    # Historical Context
    similar_failures_count: int = 0
    recent_success_rate: float = 0.0


@dataclass
class ReflectionOutput:
    """Self-Reflection 출력 (Domain Model)"""

    verdict: ReflectionVerdict
    confidence: float
    reasoning: str

    # Graph Stability
    stability_score: float
    impact_radius: int

    # Suggestions
    suggested_fixes: list[str] = field(default_factory=list)
    alternative_strategies: list[str] = field(default_factory=list)

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)

    def is_acceptable(self) -> bool:
        """승인 가능한지"""
        return self.verdict == ReflectionVerdict.ACCEPT

    def needs_revision(self) -> bool:
        """수정 필요한지"""
        return self.verdict == ReflectionVerdict.REVISE

    def should_rollback(self) -> bool:
        """롤백해야 하는지"""
        return self.verdict == ReflectionVerdict.ROLLBACK
