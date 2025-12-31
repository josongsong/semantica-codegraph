"""
Adaptive Sampler

실시간으로 샘플 수를 조정하는 적응형 샘플러.
"""

import logging
from collections.abc import Callable
from typing import TypeVar

from .ttc_models import ComputeBudget

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AdaptiveSampler:
    """적응형 샘플러"""

    def __init__(self, initial_samples: int = 3):
        self.initial_samples = initial_samples

    def sample_adaptively(
        self,
        prompt: str,
        budget: ComputeBudget,
        generate_fn: Callable[[str, int], list[T]],
        quality_fn: Callable[[T], float],
        quality_threshold: float = 0.8,
    ) -> list[T]:
        """
        적응형 샘플링

        Args:
            prompt: 프롬프트
            budget: compute 예산
            generate_fn: 샘플 생성 함수
            quality_fn: 품질 평가 함수
            quality_threshold: 품질 임계값

        Returns:
            샘플 리스트
        """
        all_samples: list[T] = []
        remaining_budget = budget.num_samples

        # 1. 초기 샘플
        initial_count = min(self.initial_samples, remaining_budget)
        logger.info(f"Generating {initial_count} initial samples...")

        initial_samples = generate_fn(prompt, initial_count)
        all_samples.extend(initial_samples)
        remaining_budget -= initial_count

        # 2. 품질 평가
        qualities = [quality_fn(sample) for sample in initial_samples]
        avg_quality = sum(qualities) / len(qualities) if qualities else 0.0

        logger.info(f"Initial quality: {avg_quality:.2f}")

        # 3. 적응적으로 추가 샘플링
        if avg_quality < quality_threshold and remaining_budget > 0:
            # 품질이 낮으면 더 샘플링
            additional_count = min(remaining_budget, initial_count * 2)
            logger.info(f"Quality below threshold, generating {additional_count} more samples...")

            additional_samples = generate_fn(prompt, additional_count)
            all_samples.extend(additional_samples)
            remaining_budget -= additional_count

        logger.info(f"Adaptive sampling completed: {len(all_samples)} samples (budget remaining: {remaining_budget})")

        return all_samples
