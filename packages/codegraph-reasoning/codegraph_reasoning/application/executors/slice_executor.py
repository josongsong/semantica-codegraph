"""
Slice Extraction Executor

프로그램 슬라이싱 전담
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# 매직 숫자 상수화
DEFAULT_MAX_BUDGET = 2000
DEFAULT_MAX_DEPTH = 3


@dataclass
class SliceExtractionResult:
    """슬라이싱 결과"""

    slices: dict[str, Any] = field(default_factory=dict)
    total_tokens: int = 0
    over_budget_count: int = 0

    def get_within_budget(self, budget: int) -> dict[str, Any]:
        """예산 내 슬라이스만 반환"""
        return {k: v for k, v in self.slices.items() if getattr(v, "total_tokens", 0) <= budget}


class SliceExtractionExecutor:
    """
    프로그램 슬라이싱 전담 실행자

    책임: symbol들의 backward/forward slice 추출
    입력: symbol_ids, max_budget
    출력: SliceExtractionResult
    """

    def __init__(self, slicer: Any):
        """
        Args:
            slicer: SlicerAdapter (DI)
        """
        self._slicer = slicer

    def execute(
        self,
        symbol_ids: list[str],
        max_budget: int = DEFAULT_MAX_BUDGET,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> SliceExtractionResult:
        """
        슬라이싱 실행

        Args:
            symbol_ids: 슬라이스할 symbol IDs
            max_budget: 최대 토큰 예산
            max_depth: 최대 슬라이스 깊이

        Returns:
            SliceExtractionResult
        """
        logger.info(f"Extracting slices for {len(symbol_ids)} symbols (budget={max_budget})")

        result = SliceExtractionResult()

        for symbol_id in symbol_ids:
            try:
                slice_data = self._slicer.backward_slice(symbol_id, max_depth=max_depth)

                tokens = getattr(slice_data, "total_tokens", 0)
                result.total_tokens += tokens

                if tokens > max_budget:
                    result.over_budget_count += 1
                    logger.warning(f"Slice for {symbol_id} exceeds budget: {tokens} > {max_budget}")

                result.slices[symbol_id] = slice_data

            except Exception as e:
                logger.error(f"Failed to slice {symbol_id}: {e}")

        logger.info(f"Slice extraction complete: {len(result.slices)} slices, {result.over_budget_count} over budget")
        return result
