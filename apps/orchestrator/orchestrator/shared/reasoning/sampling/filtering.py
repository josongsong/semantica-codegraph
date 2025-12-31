"""
Filter Engine

샘플을 필터링하여 최종 후보 선택.
"""

import logging

from .alphacode_models import AlphaCodeConfig, SampleCandidate

logger = logging.getLogger(__name__)


class FilterEngine:
    """샘플 필터링"""

    def __init__(self, config: AlphaCodeConfig):
        self.config = config

    def filter(self, samples: list[SampleCandidate]) -> list[SampleCandidate]:
        """
        샘플을 필터링하여 최종 후보 선택

        Args:
            samples: 샘플 리스트

        Returns:
            필터링된 샘플 리스트
        """
        if not samples:
            return []

        # 1. 기본 필터: 컴파일 성공
        compiled = [s for s in samples if s.compile_success]

        compile_rate = len(compiled) / len(samples) if samples else 0
        logger.info(f"Compile rate: {compile_rate:.2%} ({len(compiled)}/{len(samples)})")

        if compile_rate < self.config.min_compile_rate:
            logger.warning(f"Low compile rate: {compile_rate:.2%} < {self.config.min_compile_rate:.2%}")

        # 2. 품질 필터: 테스트 통과율
        quality_samples = [s for s in compiled if s.test_pass_rate >= 0.5]

        logger.info(f"Quality samples: {len(quality_samples)}/{len(compiled)}")

        # 3. 점수로 정렬
        sorted_samples = sorted(quality_samples, key=lambda s: s.calculate_final_score(), reverse=True)

        # 4. Top-k 선택
        final_samples = sorted_samples[: self.config.max_candidates]

        logger.info(f"Final candidates: {len(final_samples)}")
        return final_samples

    def deduplicate(self, samples: list[SampleCandidate]) -> list[SampleCandidate]:
        """
        중복 제거

        Args:
            samples: 샘플 리스트

        Returns:
            중복 제거된 리스트
        """
        seen_codes = set()
        unique = []

        for sample in samples:
            # 코드의 처음 100자로 중복 체크
            code_prefix = sample.code[:100]

            if code_prefix not in seen_codes:
                seen_codes.add(code_prefix)
                unique.append(sample)

        logger.info(f"Deduplicated: {len(samples)} -> {len(unique)}")
        return unique
