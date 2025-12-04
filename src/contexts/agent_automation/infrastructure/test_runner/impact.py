"""Test Impact Analyzer - 변경 파일에 영향받는 테스트 분석."""

from pathlib import Path

from src.infra.observability import get_logger

logger = get_logger(__name__)


class TestImpactAnalyzer:
    """테스트 영향 분석기.

    변경된 파일들에 영향받는 테스트를 분석합니다.
    pytest-testmon이 자동으로 dependency tracking을 하지만,
    추가 휴리스틱을 제공할 수 있습니다.
    """

    def __init__(self, project_root: Path):
        """
        Args:
            project_root: 프로젝트 루트 디렉토리
        """
        self.project_root = Path(project_root)

    def get_affected_test_patterns(self, changed_files: list[str]) -> list[str]:
        """변경 파일에 영향받는 테스트 패턴 추출.

        Args:
            changed_files: 변경된 파일 경로 리스트

        Returns:
            테스트 파일 패턴 리스트 (pytest 인자로 사용 가능)
        """
        patterns = []

        for file_path in changed_files:
            path = Path(file_path)

            # 1. 테스트 파일 자체가 변경되었으면 그대로 실행
            if self._is_test_file(path):
                patterns.append(str(path))
                continue

            # 2. src/ 파일이면 대응하는 test_*.py 찾기
            if "src/" in str(path):
                test_file = self._find_corresponding_test(path)
                if test_file:
                    patterns.append(str(test_file))

        # 중복 제거
        patterns = list(set(patterns))

        logger.debug(
            f"Test impact analysis: {len(changed_files)} changed files -> {len(patterns)} test patterns",
            extra={"changed_files": changed_files, "patterns": patterns},
        )

        return patterns

    def _is_test_file(self, path: Path) -> bool:
        """테스트 파일 여부 판단.

        Args:
            path: 파일 경로

        Returns:
            테스트 파일 여부
        """
        name = path.name
        return name.startswith("test_") or name.endswith("_test.py")

    def _find_corresponding_test(self, src_file: Path) -> Path | None:
        """소스 파일에 대응하는 테스트 파일 찾기.

        Args:
            src_file: 소스 파일 경로 (e.g. src/agent/tools/base.py)

        Returns:
            테스트 파일 경로 또는 None
        """
        # src/agent/tools/base.py -> tests/agent/tools/test_base.py
        parts = src_file.parts

        if "src" not in parts:
            return None

        src_idx = parts.index("src")
        rel_parts = parts[src_idx + 1 :]  # agent/tools/base.py

        # tests/ + 경로 + test_{filename}
        test_parts = ["tests"] + list(rel_parts[:-1])
        test_filename = f"test_{rel_parts[-1]}"
        test_file = self.project_root / Path(*test_parts) / test_filename

        if test_file.exists():
            return test_file

        return None
