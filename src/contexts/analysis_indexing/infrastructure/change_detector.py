"""L0: 변경 감지 레이어."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from src.infra.observability import get_logger

logger = get_logger(__name__)


@dataclass
class ChangeSet:
    """변경된 파일 집합."""

    added: set[str]  # 새로 추가된 파일
    modified: set[str]  # 수정된 파일
    deleted: set[str]  # 삭제된 파일

    @property
    def all_changed(self) -> set[str]:
        """모든 변경 파일 (추가 + 수정)."""
        return self.added | self.modified

    @property
    def total_count(self) -> int:
        """전체 변경 파일 개수."""
        return len(self.added) + len(self.modified) + len(self.deleted)

    def is_empty(self) -> bool:
        """변경이 없는지 확인."""
        return self.total_count == 0


class ChangeDetector:
    """변경 감지 (L0 레이어)."""

    def __init__(self, git_helper=None, file_hash_store=None):
        """
        Args:
            git_helper: GitHelper 인스턴스 (git diff 사용)
            file_hash_store: 파일 해시 저장소 (mtime/hash 기반 감지)
        """
        self.git_helper = git_helper
        self.file_hash_store = file_hash_store

    def detect_changes(
        self,
        repo_path: Path,
        repo_id: str,
        base_commit: str | None = None,
        use_git: bool = True,
        use_mtime: bool = True,
        use_hash: bool = True,
    ) -> ChangeSet:
        """
        변경 파일 감지 (L0).

        전략:
        1. git diff (빠름, 정확)
        2. mtime (git 없을 때)
        3. content hash (최종 검증)

        Args:
            repo_path: 레포지토리 경로
            repo_id: 레포지토리 ID
            base_commit: 비교 기준 커밋 (None이면 HEAD)
            use_git: git diff 사용 여부
            use_mtime: mtime 체크 사용 여부
            use_hash: content hash 체크 사용 여부

        Returns:
            ChangeSet (added, modified, deleted)
        """
        change_set = ChangeSet(added=set(), modified=set(), deleted=set())

        # 1. Git diff (우선)
        if use_git and self.git_helper:
            try:
                git_changes = self._detect_git_changes(repo_path, base_commit)
                change_set.added.update(git_changes.added)
                change_set.modified.update(git_changes.modified)
                change_set.deleted.update(git_changes.deleted)
                logger.info(
                    "git_diff_detected",
                    added=len(git_changes.added),
                    modified=len(git_changes.modified),
                    deleted=len(git_changes.deleted),
                )
            except Exception as e:
                logger.warning("git_diff_failed", error=str(e), fallback="mtime/hash")

        # 2. mtime + hash (git 실패 시 또는 추가 검증)
        if (use_mtime or use_hash) and self.file_hash_store:
            try:
                hash_changes = self._detect_hash_changes(repo_path, repo_id, use_mtime, use_hash)
                # Git과 merge (union)
                change_set.added.update(hash_changes.added)
                change_set.modified.update(hash_changes.modified)
                change_set.deleted.update(hash_changes.deleted)
                logger.info(
                    "hash_mtime_detected",
                    added=len(hash_changes.added),
                    modified=len(hash_changes.modified),
                    deleted=len(hash_changes.deleted),
                )
            except Exception as e:
                logger.warning("hash_mtime_detection_failed", error=str(e))

        logger.info(
            "total_changes_detected",
            added=len(change_set.added),
            modified=len(change_set.modified),
            deleted=len(change_set.deleted),
            total=change_set.total_count,
        )

        return change_set

    def _detect_git_changes(self, repo_path: Path, base_commit: str | None) -> ChangeSet:
        """Git diff 기반 변경 감지."""
        if not self.git_helper:
            return ChangeSet(added=set(), modified=set(), deleted=set())

        # git diff --name-status
        diff_output = self.git_helper.get_diff_files(repo_path, base_commit)

        added = set()
        modified = set()
        deleted = set()

        for line in diff_output.splitlines():
            if not line.strip():
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                continue

            status, file_path = parts[0], parts[1]

            if status == "A":
                added.add(file_path)
            elif status == "M":
                modified.add(file_path)
            elif status == "D":
                deleted.add(file_path)
            elif status.startswith("R"):  # Rename
                # R100 old_path new_path
                if len(parts) >= 3:
                    deleted.add(parts[1])
                    added.add(parts[2])

        return ChangeSet(added=added, modified=modified, deleted=deleted)

    def _detect_hash_changes(self, repo_path: Path, repo_id: str, use_mtime: bool, use_hash: bool) -> ChangeSet:
        """파일 해시/mtime 기반 변경 감지."""
        if not self.file_hash_store:
            return ChangeSet(added=set(), modified=set(), deleted=set())

        added = set()
        modified = set()
        deleted = set()

        # 현재 파일 목록
        current_files = {str(f.relative_to(repo_path)) for f in repo_path.rglob("*") if f.is_file()}

        # DB에서 이전 상태 로드
        previous_state = self.file_hash_store.get_repo_state(repo_id)

        # 새로 추가된 파일
        new_files = current_files - previous_state.keys()
        added.update(new_files)

        # 삭제된 파일
        removed_files = previous_state.keys() - current_files
        deleted.update(removed_files)

        # 기존 파일 중 변경 체크
        for file_path in current_files & previous_state.keys():
            full_path = repo_path / file_path
            prev_state = previous_state[file_path]

            changed = False

            # mtime 체크
            if use_mtime:
                current_mtime = full_path.stat().st_mtime
                if current_mtime > prev_state.get("mtime", 0):
                    changed = True

            # hash 체크 (더 정확)
            if use_hash and not changed:
                current_hash = self._compute_file_hash(full_path)
                if current_hash != prev_state.get("hash"):
                    changed = True

            if changed:
                modified.add(file_path)

        return ChangeSet(added=added, modified=modified, deleted=deleted)

    def _compute_file_hash(self, file_path: Path) -> str:
        """파일 content hash 계산."""
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.warning("hash_computation_failed", file_path=str(file_path), error=str(e))
            return ""


# Stub for file hash store (실제 구현은 별도)
class FileHashStore:
    """파일 해시 저장소 인터페이스."""

    def get_repo_state(self, repo_id: str) -> dict[str, dict]:
        """
        레포지토리의 이전 파일 상태 로드.

        Returns:
            {file_path: {"mtime": float, "hash": str}}
        """
        raise NotImplementedError

    def save_repo_state(self, repo_id: str, state: dict[str, dict]) -> None:
        """파일 상태 저장."""
        raise NotImplementedError
