"""
Git Service - 실제 Git 메타데이터 조회

파일/코드의 Git 히스토리를 조회하여 recency/hotspot 점수 계산
"""

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GitMetadata:
    """Git 메타데이터"""

    file_path: str
    last_modified: datetime
    commit_count: int  # 이 파일이 수정된 커밋 수
    last_author: str


class GitService:
    """
    실제 Git 서비스

    Git 명령어를 실행하여 파일 메타데이터 조회
    """

    def __init__(self, repo_root: Path | None = None, cache_size: int = 1000):
        self.repo_root = repo_root or Path.cwd()
        self._cache = {}
        self._cache_size = cache_size
        self._cache_order = []  # LRU tracking

    def get_file_metadata(self, file_path: str) -> GitMetadata | None:
        """
        파일의 Git 메타데이터 조회

        Args:
            file_path: 파일 경로

        Returns:
            GitMetadata or None
        """
        # Cache check
        if file_path in self._cache:
            return self._cache[file_path]

        try:
            full_path = self.repo_root / file_path

            # Last modified date (with timeout)
            result = subprocess.run(
                ["git", "log", "-1", "--format=%at", "--", str(full_path)],
                capture_output=True,
                text=True,
                cwd=self.repo_root,
                timeout=5,  # 5초 timeout
            )

            if result.returncode != 0 or not result.stdout.strip():
                logger.debug(f"No git history for {file_path}")
                return None

            timestamp = int(result.stdout.strip())
            last_modified = datetime.fromtimestamp(timestamp)

            # Commit count (with timeout)
            result = subprocess.run(
                ["git", "log", "--oneline", "--", str(full_path)],
                capture_output=True,
                text=True,
                cwd=self.repo_root,
                timeout=5,
            )

            commit_count = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0

            # Last author (with timeout)
            result = subprocess.run(
                ["git", "log", "-1", "--format=%an", "--", str(full_path)],
                capture_output=True,
                text=True,
                cwd=self.repo_root,
                timeout=5,
            )

            last_author = result.stdout.strip() or "unknown"

            metadata = GitMetadata(
                file_path=file_path, last_modified=last_modified, commit_count=commit_count, last_author=last_author
            )

            # Cache with LRU
            self._add_to_cache(file_path, metadata)

            logger.debug(f"Git metadata for {file_path}: {commit_count} commits, last modified {last_modified}")

            return metadata

        except subprocess.TimeoutExpired:
            logger.error(f"Git command timeout for {file_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to get git metadata for {file_path}: {e}")
            raise  # Re-raise instead of silent failure

    def get_line_last_modified(self, file_path: str, line_number: int) -> datetime | None:
        """
        특정 라인의 마지막 수정 시각 조회 (git blame)

        Args:
            file_path: 파일 경로
            line_number: 라인 번호 (1-based)

        Returns:
            Last modified datetime or None
        """
        try:
            full_path = self.repo_root / file_path

            result = subprocess.run(
                ["git", "blame", "-L", f"{line_number},{line_number}", "--porcelain", str(full_path)],
                capture_output=True,
                text=True,
                cwd=self.repo_root,
                timeout=5,
            )

            if result.returncode != 0:
                return None

            # Parse porcelain output
            for line in result.stdout.split("\n"):
                if line.startswith("author-time "):
                    timestamp = int(line.split()[1])
                    return datetime.fromtimestamp(timestamp)

            return None

        except subprocess.TimeoutExpired:
            logger.error(f"Git blame timeout for {file_path}:{line_number}")
            return None
        except Exception as e:
            logger.error(f"Failed to get line blame for {file_path}:{line_number}: {e}")
            return None  # Blame은 optional이므로 None 반환 OK

    def _add_to_cache(self, key: str, value: GitMetadata):
        """LRU cache 추가"""
        # 이미 있으면 제거 (재추가를 위해)
        if key in self._cache:
            self._cache_order.remove(key)

        # 캐시가 가득 찼으면 가장 오래된 것 제거
        if len(self._cache) >= self._cache_size:
            oldest = self._cache_order.pop(0)
            del self._cache[oldest]

        # 새로 추가
        self._cache[key] = value
        self._cache_order.append(key)
