"""
File Filter for Incremental Indexing

Handles file normalization and filtering for indexing pipeline.
"""

import fnmatch
from pathlib import Path

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


def _is_relative_to_compat(path: Path, other: Path) -> bool:
    """
    Check if path is relative to other (Python 3.8 compatible).

    Python 3.9+ has Path.is_relative_to(), but we need to support 3.8.
    """
    return path.is_relative_to(other)


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
        3. Path traversal 공격 방어 (../, 절대 경로)
        4. 바이너리 파일 제외
        5. Ignore 패턴 제외
        6. 파일 크기 체크 (선택적, repo_root 제공 시)

        Args:
            repo_id: 저장소 ID (로깅용)
            file_paths: 원본 파일 경로 목록
            repo_root: 저장소 루트 경로 (파일 크기 체크용, 선택사항)

        Returns:
            정규화/필터링된 파일 경로 목록 (정렬됨)
        """
        if not file_paths:
            return []

        # 1. 중복 제거 + 정규화 + Path traversal 방어
        normalized = set()

        for path in file_paths:
            # 경로 정규화 (POSIX 스타일: /)
            # Windows 스타일 백슬래시를 슬래시로 변환
            norm_path = path.replace("\\", "/")

            # 빈 경로 제외
            if not norm_path or norm_path == ".":
                continue

            # 🔥 SECURITY: Path traversal 공격 방어
            if not self._is_safe_path(norm_path, repo_root):
                logger.warning(
                    "file_filtered_path_traversal",
                    repo_id=repo_id,
                    file_path=path,
                    reason="potential_path_traversal_attack",
                )
                continue

            normalized.add(norm_path)

        # 2. 필터링
        filtered = []
        path_traversal_blocked = len(file_paths) - len(normalized)  # 이미 필터링된 개수
        stats = {
            "total": len(file_paths),
            "path_traversal": path_traversal_blocked,
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
        if stats["binary"] > 0 or stats["ignored"] > 0 or stats["too_large"] > 0 or stats["path_traversal"] > 0:
            logger.info(
                "file_filter_completed",
                repo_id=repo_id,
                total=stats["total"],
                passed=stats["passed"],
                binary=stats["binary"],
                ignored=stats["ignored"],
                too_large=stats["too_large"],
                path_traversal=stats["path_traversal"],
            )

        return filtered

    def _matches_ignore_pattern(self, path: str) -> bool:
        """
        경로가 ignore 패턴과 매칭되는지 확인 (gitignore-style).

        Gitignore semantics:
        - 패턴이 경로의 어느 디렉토리 부분과 정확히 일치하면 매칭
        - 패턴에 /가 포함되면 전체 경로 glob 매칭
        - *, ?, ** 같은 glob 패턴 지원

        Args:
            path: 파일 경로

        Returns:
            매칭 여부
        """
        path_parts = Path(path).parts

        for pattern in self.ignore_patterns:
            # Case 1: Pattern contains '/' - treat as full path glob
            if "/" in pattern:
                if fnmatch.fnmatch(path, pattern):
                    return True
                # Also try with ** prefix for nested matches
                if fnmatch.fnmatch(path, f"**/{pattern}"):
                    return True
                continue

            # Case 2: Simple directory name - exact match on any path component
            # This is gitignore-style: "node_modules" matches "a/node_modules/b.js"
            if pattern in path_parts:
                return True

            # Case 3: Glob pattern without / - match against each component
            # e.g., "*.pyc" would match any component ending with .pyc
            if any(fnmatch.fnmatch(part, pattern) for part in path_parts):
                return True

        return False

    def _is_safe_path(self, path: str, repo_root: Path | None = None) -> bool:
        """
        경로가 path traversal 공격에 안전한지 확인.

        Security checks:
        1. 절대 경로 거부 (/, C:\\, etc.)
        2. Parent directory 참조 거부 (..)
        3. Null byte 거부 (\\x00)
        4. repo_root 외부 경로 거부 (resolve 후 체크)

        Args:
            path: 검사할 파일 경로
            repo_root: 저장소 루트 경로 (경계 체크용)

        Returns:
            안전한 경로면 True
        """
        # 1. Null byte injection 방어
        if "\x00" in path:
            return False

        # 2. 절대 경로 거부 (Unix와 Windows 모두)
        path_obj = Path(path)
        if path_obj.is_absolute():
            return False

        # 3. Parent directory 참조 거부 (.. 를 포함하는 경로)
        # 정규화된 경로에서도 .. 체크
        if ".." in path_obj.parts:
            return False

        # 4. repo_root 경계 체크 (제공된 경우)
        if repo_root:
            try:
                # 경로 resolve 후 repo_root 내에 있는지 확인
                resolved_root = repo_root.resolve()
                resolved_path = (repo_root / path).resolve()

                # resolved_path가 resolved_root의 하위인지 확인
                # Use compatibility function for Python 3.8 support
                if not _is_relative_to_compat(resolved_path, resolved_root):
                    return False
            except (ValueError, OSError):
                # resolve 실패 시 안전하지 않은 것으로 처리
                return False

        return True
