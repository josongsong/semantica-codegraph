"""
SBFL (Spectrum-Based Fault Localization) Analyzer

RFC-060 Section 2.1.2: Tarantula 공식 기반 버그 위치 특정

Suspiciousness(s) = (failed(s)/total_failed) /
                    ((failed(s)/total_failed) + (passed(s)/total_passed))

높은 의심도 = 실패 테스트에서 많이 실행되고, 성공 테스트에서는 적게 실행된 라인
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SuspiciousLine:
    """의심 라인 (Immutable Value Object)"""

    file_path: str
    line_number: int
    suspiciousness: float  # 0.0 ~ 1.0
    executed_in_failed: int  # 실패 테스트에서 실행된 횟수
    executed_in_passed: int  # 성공 테스트에서 실행된 횟수


class ICoverageCollector(Protocol):
    """Coverage 수집 Port"""

    async def collect(self, test_file: str) -> dict[str, set[int]]:
        """
        테스트 실행 + 커버리지 수집

        Args:
            test_file: 테스트 파일 경로

        Returns:
            {file_path: {실행된 라인 번호들}}
        """
        ...


class SBFLAnalyzer:
    """
    SBFL Analyzer (Tarantula Formula)

    책임:
    - 실패/성공 테스트별 커버리지 수집
    - 라인별 의심도 계산 (Tarantula)
    - 의심 라인 순위화
    """

    def __init__(self, coverage_collector: ICoverageCollector):
        """
        Args:
            coverage_collector: 커버리지 수집 어댑터
        """
        self._coverage = coverage_collector

    async def analyze(
        self,
        failing_tests: list[str],
        passing_tests: list[str],
        target_files: list[str] | None = None,
    ) -> list[SuspiciousLine]:
        """
        SBFL 분석 실행

        Args:
            failing_tests: 실패하는 테스트 파일들
            passing_tests: 성공하는 테스트 파일들
            target_files: 분석 대상 파일 (None이면 전체)

        Returns:
            의심도 내림차순 정렬된 SuspiciousLine 리스트
        """
        # 1. 실패 테스트 커버리지 수집
        failed_coverage = await self._collect_coverage(failing_tests)

        # 2. 성공 테스트 커버리지 수집
        passed_coverage = await self._collect_coverage(passing_tests)

        # 3. 모든 라인에 대해 의심도 계산
        all_files = self._merge_files(failed_coverage, passed_coverage)
        if target_files:
            all_files = {f for f in all_files if f in target_files}

        total_failed = len(failing_tests)
        total_passed = len(passing_tests)

        suspicious_lines: list[SuspiciousLine] = []

        for file_path in all_files:
            all_lines = self._get_all_lines(file_path, failed_coverage, passed_coverage)

            for line_num in all_lines:
                ef = self._count_executions(failed_coverage, file_path, line_num)
                ep = self._count_executions(passed_coverage, file_path, line_num)

                # 실패 테스트에서 한 번도 실행 안 됨 → 의심도 0
                if ef == 0:
                    continue

                susp = self._tarantula(ef, total_failed, ep, total_passed)

                suspicious_lines.append(
                    SuspiciousLine(
                        file_path=file_path,
                        line_number=line_num,
                        suspiciousness=susp,
                        executed_in_failed=ef,
                        executed_in_passed=ep,
                    )
                )

        # 의심도 내림차순 정렬
        return sorted(suspicious_lines, key=lambda x: x.suspiciousness, reverse=True)

    async def _collect_coverage(
        self,
        test_files: list[str],
    ) -> dict[str, dict[str, set[int]]]:
        """
        여러 테스트의 커버리지 수집

        Returns:
            {test_file: {source_file: {lines}}}
        """
        result: dict[str, dict[str, set[int]]] = {}

        for test_file in test_files:
            cov = await self._coverage.collect(test_file)
            result[test_file] = cov

        return result

    def _tarantula(
        self,
        ef: int,  # executed in failed
        tf: int,  # total failed
        ep: int,  # executed in passed
        tp: int,  # total passed
    ) -> float:
        """
        Tarantula 공식 계산

        Suspiciousness = (ef/tf) / ((ef/tf) + (ep/tp))
        """
        if tf == 0:
            return 0.0

        failed_ratio = ef / tf
        passed_ratio = ep / tp if tp > 0 else 0.0

        denominator = failed_ratio + passed_ratio
        if denominator == 0:
            return 0.0

        return failed_ratio / denominator

    def _merge_files(
        self,
        failed_cov: dict[str, dict[str, set[int]]],
        passed_cov: dict[str, dict[str, set[int]]],
    ) -> set[str]:
        """모든 파일 목록 병합"""
        files: set[str] = set()
        for test_cov in failed_cov.values():
            files.update(test_cov.keys())
        for test_cov in passed_cov.values():
            files.update(test_cov.keys())
        return files

    def _get_all_lines(
        self,
        file_path: str,
        failed_cov: dict[str, dict[str, set[int]]],
        passed_cov: dict[str, dict[str, set[int]]],
    ) -> set[int]:
        """파일의 모든 실행된 라인 수집"""
        lines: set[int] = set()
        for test_cov in failed_cov.values():
            if file_path in test_cov:
                lines.update(test_cov[file_path])
        for test_cov in passed_cov.values():
            if file_path in test_cov:
                lines.update(test_cov[file_path])
        return lines

    def _count_executions(
        self,
        coverage: dict[str, dict[str, set[int]]],
        file_path: str,
        line_num: int,
    ) -> int:
        """특정 라인이 실행된 테스트 수"""
        count = 0
        for test_cov in coverage.values():
            if file_path in test_cov and line_num in test_cov[file_path]:
                count += 1
        return count
