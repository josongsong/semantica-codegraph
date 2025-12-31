"""L0: 변경 감지 레이어."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


@dataclass
class ChangeSet:
    """변경된 파일 집합."""

    added: set[str]  # 새로 추가된 파일
    modified: set[str]  # 수정된 파일
    deleted: set[str]  # 삭제된 파일
    renamed: dict[str, str] = None  # 리네임된 파일: {old_path: new_path}

    def __post_init__(self):
        """Initialize renamed dict if None."""
        if self.renamed is None:
            self.renamed = {}

    @property
    def all_changed(self) -> set[str]:
        """모든 변경 파일 (추가 + 수정 + 리네임된 새 파일)."""
        changed = self.added | self.modified
        # Renamed files: include new paths
        if self.renamed:
            changed.update(self.renamed.values())
        return changed

    @property
    def total_count(self) -> int:
        """전체 변경 파일 개수."""
        return len(self.added) + len(self.modified) + len(self.deleted) + len(self.renamed)

    def is_empty(self) -> bool:
        """변경이 없는지 확인."""
        return self.total_count == 0

    def mark_as_renamed(self, old_path: str, new_path: str) -> None:
        """
        파일을 renamed로 표시.

        Args:
            old_path: 이전 파일 경로
            new_path: 새 파일 경로
        """
        # renamed 추가
        self.renamed[old_path] = new_path

        # added/deleted에서 제거
        self.added.discard(new_path)
        self.deleted.discard(old_path)


class ChangeDetector:
    """변경 감지 (L0 레이어)."""

    def __init__(
        self,
        git_helper=None,
        file_hash_store=None,
        rename_similarity_threshold: float = 0.90,
        enable_content_similarity: bool = True,
    ):
        """
        Args:
            git_helper: GitHelper 인스턴스 (git diff 사용)
            file_hash_store: 파일 해시 저장소 (mtime/hash 기반 감지)
            rename_similarity_threshold: Rename 판정을 위한 content similarity 임계값 (0.90 = 90%)
            enable_content_similarity: Content similarity 기반 rename detection 활성화 여부
        """
        self.git_helper = git_helper
        self.file_hash_store = file_hash_store
        self.rename_similarity_threshold = rename_similarity_threshold
        self.enable_content_similarity = enable_content_similarity

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

        # 3. Content similarity로 rename 감지 (Git 없거나 실패했을 때)
        if self.enable_content_similarity and (not use_git or not self.git_helper):
            change_set = self._detect_renames_by_similarity(repo_path, change_set)

        logger.info(
            "total_changes_detected",
            added=len(change_set.added),
            modified=len(change_set.modified),
            deleted=len(change_set.deleted),
            renamed=len(change_set.renamed),
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
                # Git이 rename을 감지했으면 renamed dict에 저장
                if len(parts) >= 3:
                    old_path = parts[1]
                    new_path = parts[2]
                    result = ChangeSet(added=added, modified=modified, deleted=deleted, renamed={old_path: new_path})
                    return result

        return ChangeSet(added=added, modified=modified, deleted=deleted, renamed={})

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

    def _detect_renames_by_similarity(
        self,
        repo_path: Path,
        change_set: ChangeSet,
    ) -> ChangeSet:
        """
        Content similarity로 rename 감지 (SOTA - O(n) 최적화).

        전략:
        1. Extension으로 먼저 그룹핑 (O(n))
        2. 같은 extension 내에서만 비교 (O(k²), k는 같은 타입 파일 수)
        3. file_hash_store에서 deleted 파일 내용 복원

        Args:
            repo_path: 레포지토리 경로
            change_set: 변경 집합

        Returns:
            Rename이 감지된 ChangeSet
        """
        if not change_set.deleted or not change_set.added:
            return change_set

        logger.info(
            "rename_detection_started",
            deleted_count=len(change_set.deleted),
            added_count=len(change_set.added),
            threshold=self.rename_similarity_threshold,
        )

        # 🔥 O(n) 최적화: Extension별로 그룹핑
        deleted_by_ext: dict[str, list[str]] = {}
        added_by_ext: dict[str, list[str]] = {}

        for deleted_file in change_set.deleted:
            ext = Path(deleted_file).suffix or ".none"
            if ext not in deleted_by_ext:
                deleted_by_ext[ext] = []
            deleted_by_ext[ext].append(deleted_file)

        for added_file in change_set.added:
            ext = Path(added_file).suffix or ".none"
            if ext not in added_by_ext:
                added_by_ext[ext] = []
            added_by_ext[ext].append(added_file)

        # 🔥 개선: file_hash_store에서 deleted 파일 메타데이터 로드
        deleted_metadata: dict[str, dict] = {}
        if self.file_hash_store:
            try:
                # Get deleted file metadata (size, hash, etc.)
                for deleted_file in change_set.deleted:
                    metadata = self.file_hash_store.get_file_metadata(deleted_file)
                    if metadata:
                        deleted_metadata[deleted_file] = metadata
                logger.debug(
                    "loaded_deleted_metadata",
                    count=len(deleted_metadata),
                )
            except Exception as e:
                logger.warning("failed_to_load_deleted_metadata", error=str(e))

        matched_renames: list[tuple[str, str, float]] = []  # (old_path, new_path, similarity)

        # Extension별로 비교 (O(k²), k는 같은 extension 파일 수)
        for ext in added_by_ext.keys():
            if ext not in deleted_by_ext:
                continue  # 같은 extension 없으면 skip

            for added_file in added_by_ext[ext]:
                new_path = repo_path / added_file
                if not new_path.exists():
                    continue

                # Get new file metadata
                try:
                    new_stat = new_path.stat()
                    new_size = new_stat.st_size
                except Exception as e:
                    logger.debug("failed_to_stat_added_file", file=added_file, error=str(e))
                    continue

                best_match = None
                best_score = 0.0

                for deleted_file in deleted_by_ext[ext]:
                    # 🔥 Fast filter: Size similarity (±10%)
                    if deleted_file in deleted_metadata:
                        old_size = deleted_metadata[deleted_file].get("size", 0)
                        if old_size > 0:
                            size_ratio = min(new_size, old_size) / max(new_size, old_size)
                            if size_ratio < 0.90:  # Size 차이 10% 이상이면 skip
                                continue

                    # File name similarity (Jaccard on path components)
                    name_sim = self._filename_similarity(deleted_file, added_file)

                    if name_sim > best_score:
                        best_score = name_sim
                        best_match = deleted_file

                # Rename으로 간주 (임계값 통과)
                if best_score >= self.rename_similarity_threshold and best_match:
                    matched_renames.append((best_match, added_file, best_score))

        # ChangeSet에 rename 적용
        for old_path, new_path, similarity in matched_renames:
            change_set.mark_as_renamed(old_path, new_path)
            logger.info(
                "rename_detected_by_similarity",
                old_path=old_path,
                new_path=new_path,
                similarity=f"{similarity:.2f}",
            )

        logger.info(
            "rename_detection_completed",
            renamed_count=len(matched_renames),
            optimization="O(k²) per extension",
        )

        return change_set

    def _filename_similarity(self, path1: str, path2: str) -> float:
        """
        파일명 유사도 계산 (Jaccard similarity).

        Args:
            path1: 파일 경로 1
            path2: 파일 경로 2

        Returns:
            유사도 (0.0 ~ 1.0)
        """
        # Path components로 토큰화
        tokens1 = set(Path(path1).parts)
        tokens2 = set(Path(path2).parts)

        # Jaccard similarity
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2

        if not union:
            return 0.0

        return len(intersection) / len(union)


# NOTE: 파일 해시 저장소는 content_hash_checker.py의 HashStore를 사용하세요.
# from codegraph_engine.analysis_indexing.infrastructure.content_hash_checker import HashStore, InMemoryHashStore, RedisHashStore
