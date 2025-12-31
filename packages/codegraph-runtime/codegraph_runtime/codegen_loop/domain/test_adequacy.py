"""
TestAdequacy Domain Model

테스트 적정성 평가 (ADR-011 Section 6)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TestAdequacy:
    """
    테스트 적정성

    ADR-011 Minimum Test Adequacy 명세:
    - branch_coverage >= 60%
    - condition_coverage: MC/DC (True/False 각 1회)
    - error_path_count >= 1
    - flakiness_ratio < 30%

    Immutable value object
    """

    branch_coverage: float  # 0.0 ~ 1.0
    condition_coverage: dict[str, dict[str, bool]]  # {condition_id: {True: bool, False: bool}}
    error_path_count: int  # Exception 테스트 개수
    flakiness_ratio: float  # 0.0 ~ 1.0 (실패율)

    # Thresholds (ADR-011)
    MIN_BRANCH_COVERAGE = 0.60  # 60%
    MAX_FLAKINESS_RATIO = 0.30  # 30%
    MIN_ERROR_PATH_COUNT = 1

    def __post_init__(self):
        """Validate invariants"""
        if not (0.0 <= self.branch_coverage <= 1.0):
            raise ValueError(f"branch_coverage must be in [0, 1], got {self.branch_coverage}")

        if not (0.0 <= self.flakiness_ratio <= 1.0):
            raise ValueError(f"flakiness_ratio must be in [0, 1], got {self.flakiness_ratio}")

        if self.error_path_count < 0:
            raise ValueError(f"error_path_count must be >= 0, got {self.error_path_count}")

    def is_adequate(self, domain: str = "default") -> bool:
        """
        적정성 검증

        Args:
            domain: 도메인 (payment, auth는 더 높은 기준)

        Returns:
            적정 여부

        ADR-011 Domain Templates:
        - payment: branch >= 90%, mutation >= 85%
        - auth: branch >= 100%
        - default: branch >= 60%
        """
        min_coverage = self._get_min_coverage(domain)

        checks = [
            self.branch_coverage >= min_coverage,
            self.error_path_count >= self.MIN_ERROR_PATH_COUNT,
            self.flakiness_ratio < self.MAX_FLAKINESS_RATIO,
            self._has_mc_dc_coverage(),
        ]

        return all(checks)

    def _get_min_coverage(self, domain: str) -> float:
        """도메인별 최소 커버리지"""
        domain_thresholds = {
            "payment": 0.90,
            "auth": 1.0,
            "default": 0.60,
        }
        return domain_thresholds.get(domain, 0.60)

    def _has_mc_dc_coverage(self) -> bool:
        """
        MC/DC (Modified Condition/Decision Coverage) 검증

        모든 condition에 대해 True/False 각 1회 이상 실행

        Returns:
            MC/DC 만족 여부
        """
        if not self.condition_coverage:
            return True  # 조건문 없으면 통과

        for _condition_id, truth_table in self.condition_coverage.items():
            if not truth_table.get(True, False) or not truth_table.get(False, False):
                return False  # True 또는 False 중 하나 누락

        return True

    def get_coverage_gap(self, domain: str = "default") -> float:
        """
        커버리지 부족분

        Args:
            domain: 도메인

        Returns:
            부족분 (음수면 초과)
        """
        min_coverage = self._get_min_coverage(domain)
        return min_coverage - self.branch_coverage
