"""
Convergence Calculator

순수 함수 기반 수렴 판정
"""

from .patch import Patch


class ConvergenceCalculator:
    """
    수렴 계산기 (순수 로직)

    외부 의존 없음, 테스트 용이
    """

    def __init__(self, threshold: float = 0.95):
        if not (0.0 <= threshold <= 1.0):
            raise ValueError("threshold must be between 0 and 1")
        self.threshold = threshold

    def is_converged(self, patches: list[Patch]) -> bool:
        """
        패치 시퀀스가 수렴했는지 판정

        기준:
        - 마지막 패치가 모든 테스트 통과
        - 변경량이 임계값 이하
        """
        if not patches:
            return False

        last_patch = patches[-1]

        # 테스트 통과 확인
        if not self._all_tests_passed(last_patch):
            return False

        # 변경량 확인 (2개 이상 패치 필요)
        if len(patches) >= 2:
            change_ratio = self._calculate_change_ratio(patches[-2], patches[-1])
            return change_ratio < (1.0 - self.threshold)

        return False

    def _all_tests_passed(self, patch: Patch) -> bool:
        """모든 테스트 통과 여부"""
        if not patch.test_results:
            return False

        return patch.test_results.get("pass_rate", 0.0) >= 1.0

    def _calculate_change_ratio(self, prev: Patch, curr: Patch) -> float:
        """
        변경 비율 계산

        간단한 diff 길이 기반 (추후 AST 기반으로 개선 가능)
        """
        # Multi-file 지원
        prev_total = sum(len(f.diff_lines) for f in prev.files)
        curr_total = sum(len(f.diff_lines) for f in curr.files)

        if prev_total == 0:
            return 1.0

        return abs(curr_total - prev_total) / prev_total
