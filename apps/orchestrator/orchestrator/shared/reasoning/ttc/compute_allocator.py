"""
Compute Allocator

난이도에 따라 compute 예산 할당.
"""

import logging
from collections.abc import Callable

from .ttc_models import ComputeBudget, DifficultyLevel, TaskDifficulty, TTCConfig

logger = logging.getLogger(__name__)


class ComputeAllocator:
    """Compute 할당자"""

    def __init__(self, config: TTCConfig):
        self.config = config

    def allocate(
        self,
        task: str,
        difficulty_fn: Callable[[str], TaskDifficulty] | None = None,
    ) -> tuple[TaskDifficulty, ComputeBudget]:
        """
        작업에 compute 예산 할당

        Args:
            task: 작업
            difficulty_fn: 난이도 평가 함수 (없으면 휴리스틱 사용)

        Returns:
            (난이도, 예산)
        """
        # 1. 난이도 평가
        if difficulty_fn:
            difficulty = difficulty_fn(task)
        else:
            difficulty = self._estimate_difficulty(task)

        # 2. 예산 할당
        budget = self.config.budgets.get(difficulty.level)

        if not budget:
            logger.warning(f"No budget for difficulty {difficulty.level}, using MEDIUM")
            budget = self.config.budgets[DifficultyLevel.MEDIUM]

        logger.info(
            f"Allocated compute for {difficulty.level}: "
            f"{budget.num_samples} samples, {budget.max_reasoning_steps} steps, "
            f"{budget.max_tokens} tokens"
        )

        return difficulty, budget

    def _estimate_difficulty(self, task: str) -> TaskDifficulty:
        """
        작업 난이도 추정 (간단한 휴리스틱)

        Args:
            task: 작업

        Returns:
            난이도
        """
        task_lower = task.lower()

        # 키워드 기반 분류 (순서 중요: 더 구체적인 것부터)

        # 1. EXTREME (가장 구체적)
        if any(
            word in task_lower
            for word in [
                "extremely difficult",
                "extremely complex",
                "very difficult",
                "very complex",
                "extreme",
                "intricate",
                "distributed",
                "microservices",
                "event sourcing",
                "cqrs",
                "multi-region",
                "zero downtime",
            ]
        ):
            level = DifficultyLevel.EXTREME
            estimated_time = 120.0
            estimated_tokens = 6000

        # 2. HARD
        elif any(
            word in task_lower
            for word in [
                "complex",
                "difficult",
                "challenging",
                "advanced",
                "sophisticated",
                "refactor",
                "implement a",
                "migrate",
                "optimize",
                "design",
                "architect",
            ]
        ):
            level = DifficultyLevel.HARD
            estimated_time = 60.0
            estimated_tokens = 3000

        # 3. EASY (단순 작업 키워드 추가)
        elif any(
            word in task_lower
            for word in [
                "simple",
                "trivial",
                "easy",
                "basic",
                "straightforward",
                "fix typo",
                "rename",
                "add logging",
                "add comment",
                "update comment",
                "change variable name",
            ]
        ):
            level = DifficultyLevel.EASY
            estimated_time = 10.0
            estimated_tokens = 500

        # 4. MEDIUM (기본값)
        else:
            level = DifficultyLevel.MEDIUM
            estimated_time = 30.0
            estimated_tokens = 1500

        # 작업 길이로 조정
        if len(task) > 500:
            # 긴 작업은 더 어려움
            if level == DifficultyLevel.EASY:
                level = DifficultyLevel.MEDIUM
            elif level == DifficultyLevel.MEDIUM:
                level = DifficultyLevel.HARD

        return TaskDifficulty(
            level=level,
            confidence=0.6,  # 휴리스틱이므로 신뢰도 낮음
            estimated_time=estimated_time,
            estimated_tokens=estimated_tokens,
        )
