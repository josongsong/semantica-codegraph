"""
Experience Domain Models

과거 경험 저장 및 검색
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ProblemType(Enum):
    """문제 유형"""

    BUGFIX = "bugfix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    PERFORMANCE = "performance"
    SECURITY = "security"


@dataclass
class AgentExperience:
    """
    에이전트 경험 (Domain Model)

    과거 문제 해결 경험 저장
    """

    # Identity
    id: int | None = None

    # Problem
    problem_description: str = ""
    problem_type: ProblemType = ProblemType.BUGFIX

    # Strategy
    strategy_id: str = ""
    strategy_type: str = ""  # StrategyType.value

    # Code References (기존 Qdrant)
    code_chunk_ids: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)

    # Results
    success: bool = False
    tot_score: float = 0.0
    reflection_verdict: str = ""  # ReflectionVerdict.value

    # Metrics
    test_pass_rate: float = 0.0
    graph_impact: float = 0.0
    execution_time: float = 0.0

    # Context
    similar_to_ids: list[int] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)

    def is_successful(self) -> bool:
        """성공 여부"""
        return self.success and self.tot_score >= 0.6


@dataclass
class StrategyResult:
    """
    전략 실행 결과 상세 (Domain Model)
    """

    # Identity
    id: int | None = None
    experience_id: int | None = None

    strategy_id: str = ""
    rank: int = 0  # Top-K 순위

    # Detailed Scores
    correctness_score: float = 0.0
    quality_score: float = 0.0
    security_score: float = 0.0
    maintainability_score: float = 0.0
    performance_score: float = 0.0
    total_score: float = 0.0

    # Issues
    critical_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ExperienceQuery:
    """경험 검색 쿼리"""

    problem_type: ProblemType | None = None
    strategy_type: str | None = None

    min_score: float = 0.0
    success_only: bool = False

    similar_to_chunks: list[str] = field(default_factory=list)

    limit: int = 10


@dataclass
class ExperienceStats:
    """경험 통계"""

    total_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    avg_score: float = 0.0
    avg_graph_impact: float = 0.0

    by_problem_type: dict[str, int] = field(default_factory=dict)
    by_strategy_type: dict[str, int] = field(default_factory=dict)

    top_strategies: list[tuple[str, float]] = field(default_factory=list)  # (strategy, success_rate)
