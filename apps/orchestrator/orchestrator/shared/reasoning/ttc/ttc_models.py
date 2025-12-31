"""
Test-Time Compute Models

난이도 기반 compute 할당 모델.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DifficultyLevel(str, Enum):
    """난이도 레벨"""

    TRIVIAL = "trivial"  # 즉시 해결 가능
    EASY = "easy"  # 단순 추론
    MEDIUM = "medium"  # 중간 추론
    HARD = "hard"  # 복잡한 추론
    EXTREME = "extreme"  # 매우 복잡


@dataclass
class TaskDifficulty:
    """작업 난이도 평가"""

    level: DifficultyLevel
    confidence: float  # 평가 신뢰도 (0.0 ~ 1.0)

    # 난이도 지표
    code_complexity: float = 0.0  # 코드 복잡도
    dependency_count: int = 0  # 의존성 수
    test_count: int = 0  # 테스트 수

    # 추정값
    estimated_time: float = 0.0  # 예상 시간 (초)
    estimated_tokens: int = 0  # 예상 토큰 수


@dataclass
class ComputeBudget:
    """Compute 예산"""

    # 샘플링
    num_samples: int = 1
    temperature: float = 0.7

    # 추론
    max_reasoning_steps: int = 3
    max_verification_attempts: int = 1

    # 비용
    max_tokens: int = 1000
    max_time_seconds: float = 30.0


@dataclass
class TTCConfig:
    """Test-Time Compute 설정"""

    # 난이도별 예산
    budgets: dict[DifficultyLevel, ComputeBudget] = field(default_factory=dict)

    # 적응형 샘플링
    use_adaptive_sampling: bool = True
    initial_samples: int = 3  # 초기 샘플 수

    # 예산 최적화
    enable_budget_optimization: bool = True

    def __post_init__(self):
        """기본 예산 설정"""
        if not self.budgets:
            self.budgets = {
                DifficultyLevel.TRIVIAL: ComputeBudget(
                    num_samples=1,
                    max_reasoning_steps=1,
                    max_tokens=500,
                    max_time_seconds=5.0,
                ),
                DifficultyLevel.EASY: ComputeBudget(
                    num_samples=3,
                    max_reasoning_steps=3,
                    max_tokens=1000,
                    max_time_seconds=15.0,
                ),
                DifficultyLevel.MEDIUM: ComputeBudget(
                    num_samples=5,
                    max_reasoning_steps=5,
                    max_tokens=2000,
                    max_time_seconds=30.0,
                ),
                DifficultyLevel.HARD: ComputeBudget(
                    num_samples=10,
                    max_reasoning_steps=10,
                    max_tokens=4000,
                    max_time_seconds=60.0,
                ),
                DifficultyLevel.EXTREME: ComputeBudget(
                    num_samples=20,
                    max_reasoning_steps=15,
                    max_tokens=8000,
                    max_time_seconds=120.0,
                ),
            }


@dataclass
class TTCResult:
    """Test-Time Compute 결과"""

    # Task info
    task_difficulty: TaskDifficulty
    allocated_budget: ComputeBudget

    # Result
    final_answer: str = ""
    success: bool = False

    # Usage
    actual_samples: int = 0
    actual_reasoning_steps: int = 0
    actual_tokens: int = 0
    actual_time: float = 0.0

    # Efficiency
    budget_utilization: float = 0.0  # 예산 활용률 (0.0 ~ 1.0)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)

    def calculate_efficiency(self) -> float:
        """
        효율성 계산

        Returns:
            효율성 점수 (0.0 ~ 1.0)
        """
        if not self.success:
            return 0.0

        # 적게 사용할수록 효율적
        time_efficiency = 1.0 - (self.actual_time / self.allocated_budget.max_time_seconds)
        token_efficiency = 1.0 - (self.actual_tokens / self.allocated_budget.max_tokens)

        return (time_efficiency + token_efficiency) / 2
