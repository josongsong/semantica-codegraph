"""
Risk Assessor Adapter

Historical Experience 기반 위험도 평가
IRiskAssessor Port 구현
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class HistoricalRiskAssessor:
    """
    경험 기반 위험도 평가 Adapter

    구현: IRiskAssessor Port
    """

    # Security Sink 패턴 (간략화)
    SECURITY_SINKS = [
        r"os\.system\(",
        r"subprocess\.",
        r"eval\(",
        r"exec\(",
        r"__import__\(",
        r'open\(.+[\'"]w',  # write mode
    ]

    def __init__(self, experience_store=None):
        """
        Args:
            experience_store: Experience Store (Optional)
        """
        self._experience_store = experience_store

    def assess_regression_risk(self, problem_description: str, file_paths: list[str]) -> float:
        """
        Regression 위험도 평가

        Strategy:
        1. Experience Store에서 유사 케이스 검색
        2. 실패율 기반 위험도 계산
        3. 파일 히스토리 고려
        """
        if not self._experience_store:
            # Experience Store 없으면 파일 기반 추정
            return self._estimate_risk_from_files(file_paths)

        try:
            # TODO: Experience Store v2 연동 (Phase 3)
            # similar_cases = await self._experience_store.retrieve_similar(
            #     problem_description,
            #     top_k=10
            # )
            #
            # if not similar_cases:
            #     return 0.3  # Default medium risk
            #
            # failures = sum(1 for c in similar_cases if not c.success)
            # failure_rate = failures / len(similar_cases)
            #
            # return min(failure_rate * 1.2, 1.0)  # 20% buffer

            # 임시: 파일 기반 추정
            return self._estimate_risk_from_files(file_paths)

        except Exception as e:
            logger.error(f"Failed to assess regression risk: {e}")
            return 0.5  # Default medium-high risk

    def check_security_sink(self, code: str) -> bool:
        """
        보안 sink 접근 여부 확인

        Strategy:
        정규표현식으로 위험 패턴 감지
        """
        try:
            for pattern in self.SECURITY_SINKS:
                if re.search(pattern, code):
                    logger.warning(f"Security sink detected: {pattern}")
                    return True

            return False

        except Exception as e:
            logger.error(f"Failed to check security sink: {e}")
            return False  # Conservative: assume no sink

    def check_test_failure(self, file_paths: list[str]) -> bool:
        """
        최근 테스트 실패 여부 확인

        Strategy:
        1. Git 히스토리에서 최근 CI 실패 확인 (TODO)
        2. 임시: 파일명 패턴 기반 추정
        """
        try:
            # TODO: Git/CI 연동 (Phase 1 완료 후)
            # git_history = self._get_recent_ci_history(file_paths)
            # return any(h.failed for h in git_history)

            # 임시: 테스트 파일이면 위험도 증가
            has_test_file = any("test" in Path(fp).name.lower() for fp in file_paths)

            return has_test_file

        except Exception as e:
            logger.error(f"Failed to check test failure: {e}")
            return False

    # ======================================================================
    # Private Methods
    # ======================================================================

    def _estimate_risk_from_files(self, file_paths: list[str]) -> float:
        """
        파일 기반 위험도 추정

        Heuristics:
        - 파일 수가 많으면 위험
        - 핵심 파일(models, services)이면 위험
        - 테스트 파일만이면 안전
        """
        if not file_paths:
            return 0.1

        risk = 0.0

        # 파일 수 기반 (최대 10개 기준)
        risk += min(len(file_paths) / 10.0, 0.4)

        # 핵심 파일 여부
        critical_patterns = ["model", "service", "core", "domain"]
        for path in file_paths:
            path_lower = path.lower()

            if any(pattern in path_lower for pattern in critical_patterns):
                risk += 0.2
                break

        # 테스트 파일만이면 안전
        all_tests = all("test" in Path(fp).name.lower() for fp in file_paths)
        if all_tests:
            risk *= 0.3

        return min(risk, 1.0)
