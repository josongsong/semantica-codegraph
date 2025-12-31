"""
Domain Models - 순수 데이터 구조

불변성, 타입 안전성, 명시적 상태 전이

NOTE: Patch와 PatchStatus는 patch.py로 이동
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .patch import Patch


# PatchStatus moved to patch.py


class LoopStatus(Enum):
    """루프 상태"""

    RUNNING = "running"
    CONVERGED = "converged"  # 수렴 완료
    OSCILLATING = "oscillating"  # 진동 중
    BUDGET_EXCEEDED = "budget_exceeded"  # 예산 초과
    FAILED = "failed"  # 실패
    ABORTED = "aborted"  # 중단됨


@dataclass(frozen=True)
class Contract:
    """
    의미론적 계약 (Semantic Contract)

    함수/클래스가 지켜야 하는 불변식
    """

    target: str  # 대상 FQN
    preconditions: list[str]  # 사전 조건
    postconditions: list[str]  # 사후 조건
    invariants: list[str]  # 불변 조건
    side_effects: list[str]  # 부작용
    dependencies: set[str]  # 의존성
    complexity: int  # 복잡도
    metadata: dict[str, any] = field(default_factory=dict)

    def __post_init__(self):
        """Production-Grade Validation"""
        if not self.target:
            raise ValueError("target cannot be empty")
        if self.complexity < 0:
            raise ValueError("complexity cannot be negative")


@dataclass(frozen=True)
class Violation:
    """계약 위반"""

    contract_id: str
    rule: str  # 위반된 규칙
    severity: str  # critical/major/minor
    message: str
    location: str | None = None
    suggested_fix: str | None = None

    def __post_init__(self):
        """Production-Grade Validation"""
        valid_severities = {"critical", "major", "minor"}
        if self.severity not in valid_severities:
            raise ValueError(f"severity must be one of {valid_severities}, got {self.severity}")

        if not self.contract_id:
            raise ValueError("contract_id cannot be empty")
        if not self.rule:
            raise ValueError("rule cannot be empty")
        if not self.message:
            raise ValueError("message cannot be empty")


@dataclass(frozen=True)
class Budget:
    """
    리소스 예산

    무한 루프 방지
    """

    max_iterations: int = 10
    max_tokens: int = 100_000
    max_time_seconds: int = 300
    max_llm_calls: int = 50
    max_test_runs: int = 20

    current_iterations: int = 0
    current_tokens: int = 0
    current_time_seconds: float = 0.0
    current_llm_calls: int = 0
    current_test_runs: int = 0

    def __post_init__(self):
        """Production-Grade Validation"""
        # Max 값 검증
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be > 0")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be > 0")
        if self.max_time_seconds <= 0:
            raise ValueError("max_time_seconds must be > 0")
        if self.max_llm_calls <= 0:
            raise ValueError("max_llm_calls must be > 0")
        if self.max_test_runs <= 0:
            raise ValueError("max_test_runs must be > 0")

        # Current 값 검증
        if self.current_iterations < 0:
            raise ValueError("current_iterations cannot be negative")
        if self.current_tokens < 0:
            raise ValueError("current_tokens cannot be negative")
        if self.current_time_seconds < 0:
            raise ValueError("current_time_seconds cannot be negative")
        if self.current_llm_calls < 0:
            raise ValueError("current_llm_calls cannot be negative")
        if self.current_test_runs < 0:
            raise ValueError("current_test_runs cannot be negative")

    def is_exceeded(self) -> bool:
        """예산 초과 여부"""
        return (
            self.current_iterations >= self.max_iterations
            or self.current_tokens >= self.max_tokens
            or self.current_time_seconds >= self.max_time_seconds
            or self.current_llm_calls >= self.max_llm_calls
            or self.current_test_runs >= self.max_test_runs
        )

    def remaining_iterations(self) -> int:
        """남은 반복 횟수"""
        return max(0, self.max_iterations - self.current_iterations)

    def usage_ratio(self) -> float:
        """사용률 (0.0~1.0)"""
        ratios = [
            self.current_iterations / self.max_iterations,
            self.current_tokens / self.max_tokens,
            self.current_time_seconds / self.max_time_seconds,
            self.current_llm_calls / self.max_llm_calls,
            self.current_test_runs / self.max_test_runs,
        ]
        return max(ratios)

    def with_usage(
        self,
        iterations: int = 0,
        tokens: int = 0,
        time_seconds: float = 0.0,
        llm_calls: int = 0,
        test_runs: int = 0,
    ) -> Budget:
        """사용량 증가"""
        return Budget(
            max_iterations=self.max_iterations,
            max_tokens=self.max_tokens,
            max_time_seconds=self.max_time_seconds,
            max_llm_calls=self.max_llm_calls,
            max_test_runs=self.max_test_runs,
            current_iterations=self.current_iterations + iterations,
            current_tokens=self.current_tokens + tokens,
            current_time_seconds=self.current_time_seconds + time_seconds,
            current_llm_calls=self.current_llm_calls + llm_calls,
            current_test_runs=self.current_test_runs + test_runs,
        )


@dataclass(frozen=True)
class Metrics:
    """성능 메트릭"""

    test_pass_rate: float = 0.0  # 0.0~1.0
    coverage: float = 0.0  # 0.0~1.0
    quality_score: float = 0.0  # 0.0~1.0
    syntax_valid: bool = False
    type_valid: bool = False
    lint_score: float = 0.0
    violations_count: int = 0
    contract_violations: list[Violation] = field(default_factory=list)

    def __post_init__(self):
        """Production-Grade Validation"""
        # 범위 검증 (0~1)
        if not (0.0 <= self.test_pass_rate <= 1.0):
            raise ValueError("test_pass_rate must be between 0 and 1")
        if not (0.0 <= self.coverage <= 1.0):
            raise ValueError("coverage must be between 0 and 1")
        if not (0.0 <= self.quality_score <= 1.0):
            raise ValueError("quality_score must be between 0 and 1")
        if not (0.0 <= self.lint_score <= 1.0):
            raise ValueError("lint_score must be between 0 and 1")

        # violations_count 검증
        if self.violations_count < 0:
            raise ValueError("violations_count cannot be negative")

    def overall_score(self) -> float:
        """종합 점수"""
        if not self.syntax_valid or not self.type_valid:
            return 0.0

        weights = {
            "test_pass_rate": 0.4,
            "coverage": 0.2,
            "quality_score": 0.2,
            "lint_score": 0.1,
            "violations": 0.1,
        }

        violation_penalty = min(1.0, self.violations_count * 0.1)

        score = (
            self.test_pass_rate * weights["test_pass_rate"]
            + self.coverage * weights["coverage"]
            + self.quality_score * weights["quality_score"]
            + self.lint_score * weights["lint_score"]
            - violation_penalty * weights["violations"]
        )

        return max(0.0, min(1.0, score))


# Patch moved to patch.py - import from there


@dataclass(frozen=True)
class LoopState:
    """
    루프 상태 (불변)

    히스토리 기반 의사결정
    """

    task_id: str
    status: LoopStatus
    current_iteration: int
    patches: list[Patch]  # 패치 히스토리 (from patch.py)
    budget: Budget
    best_patch: Patch | None = None
    convergence_score: float = 0.0
    oscillation_detected: bool = False
    error_message: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, any] = field(default_factory=dict)

    def with_patch(self, patch: Patch) -> LoopState:
        """패치 추가"""
        new_patches = self.patches + [patch]
        new_best = self._update_best_patch(patch)

        return LoopState(
            task_id=self.task_id,
            status=self.status,
            current_iteration=self.current_iteration,
            patches=new_patches,
            budget=self.budget,
            best_patch=new_best,
            convergence_score=self.convergence_score,
            oscillation_detected=self.oscillation_detected,
            error_message=self.error_message,
            started_at=self.started_at,
            metadata=self.metadata,
        )

    def with_status(self, status: LoopStatus) -> LoopState:
        """상태 전이"""
        return LoopState(
            task_id=self.task_id,
            status=status,
            current_iteration=self.current_iteration,
            patches=self.patches,
            budget=self.budget,
            best_patch=self.best_patch,
            convergence_score=self.convergence_score,
            oscillation_detected=self.oscillation_detected,
            error_message=self.error_message,
            started_at=self.started_at,
            metadata=self.metadata,
        )

    def with_budget(self, budget: Budget) -> LoopState:
        """예산 업데이트"""
        return LoopState(
            task_id=self.task_id,
            status=self.status,
            current_iteration=self.current_iteration,
            patches=self.patches,
            budget=budget,
            best_patch=self.best_patch,
            convergence_score=self.convergence_score,
            oscillation_detected=self.oscillation_detected,
            error_message=self.error_message,
            started_at=self.started_at,
            metadata=self.metadata,
        )

    def with_iteration(self, iteration: int) -> LoopState:
        """iteration 번호만 변경"""
        return LoopState(
            task_id=self.task_id,
            status=self.status,
            current_iteration=iteration,
            patches=self.patches,
            budget=self.budget,
            best_patch=self.best_patch,
            convergence_score=self.convergence_score,
            oscillation_detected=self.oscillation_detected,
            error_message=self.error_message,
            started_at=self.started_at,
            metadata=self.metadata,
        )

    def next_iteration(self) -> LoopState:
        """다음 반복"""
        return LoopState(
            task_id=self.task_id,
            status=self.status,
            current_iteration=self.current_iteration + 1,
            patches=self.patches,
            budget=self.budget.with_usage(iterations=1),
            best_patch=self.best_patch,
            convergence_score=self.convergence_score,
            oscillation_detected=self.oscillation_detected,
            error_message=self.error_message,
            started_at=self.started_at,
            metadata=self.metadata,
        )

    def _update_best_patch(self, new_patch: Patch) -> Patch | None:
        """
        최고 패치 업데이트

        patch.Patch 사용 (test_results 기반 비교)
        """
        if not new_patch.test_results:
            return self.best_patch

        if not self.best_patch:
            return new_patch

        if not self.best_patch.test_results:
            return new_patch

        new_rate = new_patch.test_results.get("pass_rate", 0.0)
        best_rate = self.best_patch.test_results.get("pass_rate", 0.0)

        if new_rate > best_rate:
            return new_patch

        return self.best_patch

    def get_recent_patches(self, n: int = 3) -> list[Patch]:
        """최근 N개 패치"""
        return self.patches[-n:]

    def get_accepted_patches(self) -> list[Patch]:
        """승인된 패치들"""
        return [p for p in self.patches if p.is_accepted()]

    def should_stop(self) -> bool:
        """중단 여부"""
        return (
            self.status != LoopStatus.RUNNING
            or self.budget.is_exceeded()
            or (self.best_patch and self.best_patch.is_accepted() and self.convergence_score > 0.95)
        )
