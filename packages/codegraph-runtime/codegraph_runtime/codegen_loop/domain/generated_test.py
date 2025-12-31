"""
GeneratedTest Domain Model

생성된 테스트 코드와 메타데이터
"""

from dataclasses import dataclass

from .test_adequacy import TestAdequacy


@dataclass(frozen=True)
class GeneratedTest:
    """
    생성된 테스트

    Immutable value object
    """

    test_code: str  # 생성된 테스트 코드
    test_name: str  # 테스트 함수명
    target_function: str  # 대상 함수 FQN
    adequacy: TestAdequacy  # 적정성 평가
    coverage_delta: float  # 커버리지 증가분 (0.0 ~ 1.0)

    def is_valuable(self, min_delta: float = 0.05) -> bool:
        """
        가치 있는 테스트 여부

        Args:
            min_delta: 최소 커버리지 증가분 (기본 5%)

        Returns:
            가치 여부
        """
        return self.coverage_delta >= min_delta and self.adequacy.is_adequate()
