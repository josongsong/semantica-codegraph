"""
File Filter for Incremental Indexing

Handles file normalization and filtering for indexing pipeline.
"""

from pathlib import Path

from src.common.observability import get_logger

logger = get_logger(__name__)


class FileFilter:
    """
    파일 필터링 및 정규화.

    Responsibilities:
    - 중복 파일 제거
    - 바이너리 파일 제외
    - Ignore 패턴 매칭 (gitignore-style)
    - 상대 경로 정규화

    Usage:
        file_filter = FileFilter()
        normalized = file_filter.normalize_and_filter(
            repo_id="current",
            file_paths=["src/main.py", "src/main.py", "build/app.exe"],
        )
        # Returns: ["src/main.py"]  (deduped, binary excluded)
    """

    # 바이너리 파일 확장자
    BINARY_EXTENSIONS = {
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".exe",
        ".bin",
        ".o",
        ".a",
        ".dylib",
        ".class",
        ".jar",
        ".war",
        ".ear",
        ".whl",
        ".egg",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".7z",
        ".rar",
        ".iso",
        ".dmg",
        ".pkg",
        ".deb",
        ".rpm",
    }

    # Ignore 패턴 (gitignore-style)
    IGNORE_PATTERNS = {
        "__pycache__",
        ".git",
        ".svn",
        ".hg",
        ".bzr",
        "node_modules",
        ".venv",
        "venv",
        ".env",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cache",
        "build",
        "dist",
        "target",  # Rust/Java
        "out",
        ".next",  # Next.js
        ".nuxt",  # Nuxt.js
        "coverage",
        ".coverage",
        "htmlcov",
    }

    # 최대 파일 크기 (100MB)
    MAX_FILE_SIZE_MB = 100

    def __init__(
        self,
        binary_extensions: set[str] | None = None,
        ignore_patterns: set[str] | None = None,
        max_file_size_mb: int | None = None,
    ):
        """
        Initialize file filter.

        Args:
            binary_extensions: 커스텀 바이너리 확장자 (None이면 기본값 사용)
            ignore_patterns: 커스텀 ignore 패턴 (None이면 기본값 사용)
            max_file_size_mb: 최대 파일 크기 MB (None이면 기본값 100MB)
        """
        self.binary_extensions = binary_extensions or self.BINARY_EXTENSIONS
        self.ignore_patterns = ignore_patterns or self.IGNORE_PATTERNS
        self.max_file_size_mb = max_file_size_mb or self.MAX_FILE_SIZE_MB

    def normalize_and_filter(
        self,
        repo_id: str,
        file_paths: list[str],
        repo_root: Path | None = None,
    ) -> list[str]:
        """
        파일 경로 정규화 및 필터링.

        Steps:
        1. 중복 제거 (set으로 변환)
        2. 경로 정규화 (POSIX 스타일)
        3. 바이너리 파일 제외
        4. Ignore 패턴 제외
        5. 파일 크기 체크 (선택적, repo_root 제공 시)

        Args:
            repo_id: 저장소 ID (로깅용)
            file_paths: 원본 파일 경로 목록
            repo_root: 저장소 루트 경로 (파일 크기 체크용, 선택사항)

        Returns:
            정규화/필터링된 파일 경로 목록 (정렬됨)
        """
        if not file_paths:
            return []

        # 1. 중복 제거 + 정규화
        normalized = set()

        for path in file_paths:
            # 경로 정규화 (POSIX 스타일: /)
            # Windows 스타일 백슬래시를 슬래시로 변환
            norm_path = path.replace("\\", "/")

            # 빈 경로 제외
            if not norm_path or norm_path == ".":
                continue

            normalized.add(norm_path)

        # 2. 필터링
        filtered = []
        stats = {
            "total": len(normalized),
            "binary": 0,
            "ignored": 0,
            "too_large": 0,
            "passed": 0,
        }

        for path in normalized:
            path_obj = Path(path)

            # 바이너리 확장자 제외
            if path_obj.suffix.lower() in self.binary_extensions:
                stats["binary"] += 1
                logger.debug(
                    "file_filtered_binary",
                    repo_id=repo_id,
                    file_path=path,
                )
                continue

            # Ignore 패턴 제외
            if self._matches_ignore_pattern(path):
                stats["ignored"] += 1
                logger.debug(
                    "file_filtered_ignored",
                    repo_id=repo_id,
                    file_path=path,
                )
                continue

            # 파일 크기 체크 (repo_root 제공 시)
            if repo_root:
                full_path = repo_root / path
                if full_path.exists():
                    file_size_mb = full_path.stat().st_size / (1024 * 1024)
                    if file_size_mb > self.max_file_size_mb:
                        stats["too_large"] += 1
                        logger.warning(
                            "file_filtered_too_large",
                            repo_id=repo_id,
                            file_path=path,
                            size_mb=file_size_mb,
                        )
                        continue

            # 통과
            filtered.append(path)
            stats["passed"] += 1

        # 3. 정렬
        filtered.sort()

        # 로깅
        if stats["binary"] > 0 or stats["ignored"] > 0 or stats["too_large"] > 0:
            logger.info(
                "file_filter_completed",
                repo_id=repo_id,
                total=stats["total"],
                passed=stats["passed"],
                binary=stats["binary"],
                ignored=stats["ignored"],
                too_large=stats["too_large"],
            )

        return filtered

    def _matches_ignore_pattern(self, path: str) -> bool:
        """
        경로가 ignore 패턴과 매칭되는지 확인.

        Args:
            path: 파일 경로

        Returns:
            매칭 여부
        """
        # 경로의 각 부분이 ignore 패턴과 매칭되는지 확인
        path_parts = Path(path).parts

        for pattern in self.ignore_patterns:
            # 정확히 매칭
            if pattern in path_parts:
                return True

            # 부분 문자열 매칭 (전체 경로)
            if pattern in path:
                return True

        return False
