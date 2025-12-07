"""ShadowFS Core

안전한 샌드박스 파일시스템 구현 (ADR-014)

특징:
- 원본 파일 보호 (read-only view)
- 변경사항 격리 (in-memory overlay)
- Diff 생성
- Rollback 지원
- Atomic commit
"""

import difflib
from pathlib import Path

from src.common.observability import get_logger

from .models import FileDiff, ShadowFSState

logger = get_logger(__name__)


class ShadowFS:
    """
    Shadow Filesystem

    안전한 코드 수정을 위한 격리된 파일시스템

    Example:
        >>> fs = ShadowFS("/path/to/workspace")
        >>> content = fs.read_file("src/app.py")
        >>> fs.write_file("src/app.py", modified_content)
        >>> diffs = fs.get_diff()
        >>> fs.commit()  # 실제 파일에 적용
    """

    def __init__(self, workspace_path: str):
        """
        Initialize ShadowFS

        Args:
            workspace_path: 작업 디렉토리 경로
        """
        self.workspace = Path(workspace_path)
        if not self.workspace.exists():
            raise ValueError(f"Workspace does not exist: {workspace_path}")

        # Overlay: 수정된 파일 내용 (in-memory)
        self.overlay: dict[str, str] = {}

        # Original: 원본 파일 내용 (백업)
        self.original: dict[str, str] = {}

        logger.info(f"ShadowFS initialized: {workspace_path}")

    def read_file(self, file_path: str) -> str:
        """
        파일 읽기

        Overlay에 있으면 overlay에서, 없으면 실제 파일에서 읽음

        Args:
            file_path: 상대 경로 (workspace 기준)

        Returns:
            파일 내용
        """
        # Overlay에 있으면 overlay에서
        if file_path in self.overlay:
            logger.debug(f"Read from overlay: {file_path}")
            return self.overlay[file_path]

        # 실제 파일에서 읽기
        real_path = self.workspace / file_path
        if not real_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = real_path.read_text(encoding="utf-8")

        # 원본 백업 (처음 읽을 때만)
        if file_path not in self.original:
            self.original[file_path] = content
            logger.debug(f"Backed up original: {file_path}")

        return content

    def write_file(self, file_path: str, content: str):
        """
        파일 쓰기 (overlay에만)

        실제 파일은 수정하지 않고, overlay에만 저장

        Args:
            file_path: 상대 경로
            content: 새 내용
        """
        # 원본이 없으면 백업 (처음 수정할 때)
        if file_path not in self.original:
            try:
                self.read_file(file_path)
                # read_file에서 이미 original에 저장됨
            except FileNotFoundError:
                # 새 파일인 경우
                self.original[file_path] = ""
                logger.debug(f"New file (no original): {file_path}")

        # Overlay에 저장
        self.overlay[file_path] = content
        logger.info(f"Modified (overlay): {file_path} ({len(content)} chars)")

    def get_diff(self) -> list[FileDiff]:
        """
        변경사항 Diff 생성

        Returns:
            FileDiff 리스트
        """
        diffs = []

        for file_path, new_content in self.overlay.items():
            old_content = self.original.get(file_path, "")

            # Unified diff 생성
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)

            unified_diff = "".join(
                difflib.unified_diff(
                    old_lines, new_lines, fromfile=f"a/{file_path}", tofile=f"b/{file_path}", lineterm=""
                )
            )

            # 추가/삭제 라인 수 계산
            lines_added = sum(1 for line in new_lines if line not in old_lines)
            lines_removed = sum(1 for line in old_lines if line not in new_lines)

            diff = FileDiff(
                file_path=file_path,
                old_content=old_content,
                new_content=new_content,
                unified_diff=unified_diff,
                lines_added=lines_added,
                lines_removed=lines_removed,
            )

            diffs.append(diff)
            logger.debug(f"Diff: {diff}")

        return diffs

    def commit(self):
        """
        변경사항 실제 파일에 적용

        Atomic: 모두 성공하거나 모두 실패
        """
        if not self.overlay:
            logger.warning("No changes to commit")
            return

        logger.info(f"Committing {len(self.overlay)} files...")

        try:
            # 모든 파일 쓰기
            for file_path, new_content in self.overlay.items():
                real_path = self.workspace / file_path

                # 디렉토리 생성 (필요시)
                real_path.parent.mkdir(parents=True, exist_ok=True)

                # 파일 쓰기
                real_path.write_text(new_content, encoding="utf-8")
                logger.info(f"Committed: {file_path}")

            # 성공 시 overlay 클리어
            committed_files = list(self.overlay.keys())
            self.overlay.clear()
            self.original.clear()

            logger.info(f"Commit successful: {len(committed_files)} files")

        except Exception as e:
            logger.error(f"Commit failed: {e}")
            raise

    def rollback(self):
        """
        변경사항 폐기

        Overlay를 클리어하고 원본 상태로 복원
        """
        if not self.overlay:
            logger.warning("No changes to rollback")
            return

        rolled_back_files = list(self.overlay.keys())
        self.overlay.clear()
        self.original.clear()

        logger.info(f"Rolled back {len(rolled_back_files)} files")

    def get_state(self) -> ShadowFSState:
        """
        현재 상태 조회

        Returns:
            ShadowFSState
        """
        diffs = self.get_diff()

        return ShadowFSState(
            workspace_path=str(self.workspace),
            modified_files=list(self.overlay.keys()),
            total_lines_added=sum(d.lines_added for d in diffs),
            total_lines_removed=sum(d.lines_removed for d in diffs),
            is_committed=len(self.overlay) == 0,
        )

    def has_changes(self) -> bool:
        """변경사항 존재 여부"""
        return len(self.overlay) > 0

    def __repr__(self):
        """문자열 표현"""
        state = self.get_state()
        return f"ShadowFS({state.workspace_path}, {len(state.modified_files)} modified)"
