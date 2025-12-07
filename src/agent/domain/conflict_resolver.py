"""
Conflict Resolver (SOTA급)

여러 Agent의 충돌을 자동/수동으로 해결합니다.

핵심 기능:
1. 충돌 감지
2. 3-Way Merge (Git 기반)
3. 수동 해결 지원
4. Merge 전략 선택
"""

import logging
import subprocess
import tempfile
from pathlib import Path

from src.agent.domain.multi_agent_models import (
    Conflict,
    ConflictType,
    MergeResult,
    MergeStrategy,
)

logger = logging.getLogger(__name__)


class ConflictResolver:
    """
    Conflict Resolver (SOTA급).

    Git 3-way merge를 활용한 자동 충돌 해결.
    """

    def __init__(self, vcs_applier=None):
        """
        Args:
            vcs_applier: VCS Applier (선택)
        """
        self.vcs_applier = vcs_applier

    async def detect_conflict(
        self,
        file_path: str,
        agent_a_changes: str,
        agent_b_changes: str,
        base_content: str | None = None,
    ) -> Conflict | None:
        """
        충돌 감지.

        Args:
            file_path: 파일 경로
            agent_a_changes: Agent A 변경사항
            agent_b_changes: Agent B 변경사항
            base_content: 원본 내용

        Returns:
            Conflict or None
        """
        logger.debug(f"Detecting conflict: {file_path}")

        try:
            # 동일하면 충돌 없음
            if agent_a_changes == agent_b_changes:
                logger.debug("No conflict: identical changes")
                return None

            # 충돌 생성
            from datetime import datetime

            conflict = Conflict(
                conflict_id=f"conflict-{datetime.now().timestamp()}",
                file_path=file_path,
                agent_a_id="agent-a",  # TODO: 실제 agent ID
                agent_b_id="agent-b",
                agent_a_changes=agent_a_changes,
                agent_b_changes=agent_b_changes,
                base_content=base_content,
                conflict_type=ConflictType.CONCURRENT_EDIT,
            )

            logger.warning(f"Conflict detected: {file_path}")
            return conflict

        except Exception as e:
            logger.error(f"Failed to detect conflict: {e}")
            return None

    async def resolve_3way_merge(
        self,
        conflict: Conflict,
    ) -> MergeResult:
        """
        3-Way Merge로 충돌 해결.

        Git의 3-way merge 알고리즘을 사용합니다:
        - Base: 충돌 시점 원본
        - Ours: Agent A 변경
        - Theirs: Agent B 변경

        Args:
            conflict: Conflict

        Returns:
            MergeResult
        """
        logger.info(f"Attempting 3-way merge: {conflict.file_path}")

        try:
            # Base, Ours, Theirs
            base = conflict.base_content or ""
            ours = conflict.agent_a_changes or ""
            theirs = conflict.agent_b_changes or ""

            # Git merge-file 사용
            merged_content, conflicts = await self._git_merge_file(base, ours, theirs)

            if not conflicts:
                # 자동 merge 성공
                logger.info("3-way merge succeeded (auto)")

                return MergeResult(
                    success=True,
                    merged_content=merged_content,
                    conflicts=[],
                    strategy=MergeStrategy.AUTO,
                    message="Auto-merged successfully",
                )
            else:
                # 충돌 영역 존재 → 수동 해결 필요
                logger.warning(f"3-way merge has conflicts: {len(conflicts)} regions")

                return MergeResult(
                    success=False,
                    merged_content=merged_content,  # 충돌 마커 포함
                    conflicts=conflicts,
                    strategy=MergeStrategy.MANUAL,
                    message=f"Manual resolution needed: {len(conflicts)} conflicts",
                )

        except Exception as e:
            logger.error(f"3-way merge failed: {e}")

            return MergeResult(
                success=False,
                conflicts=[],
                strategy=MergeStrategy.ABORT,
                message=f"Merge failed: {e}",
            )

    async def resolve_accept_ours(
        self,
        conflict: Conflict,
    ) -> MergeResult:
        """
        우리 것(Agent A) 채택.

        Args:
            conflict: Conflict

        Returns:
            MergeResult
        """
        logger.info(f"Accepting ours: {conflict.file_path}")

        return MergeResult(
            success=True,
            merged_content=conflict.agent_a_changes,
            conflicts=[],
            strategy=MergeStrategy.ACCEPT_OURS,
            message="Accepted Agent A changes",
        )

    async def resolve_accept_theirs(
        self,
        conflict: Conflict,
    ) -> MergeResult:
        """
        상대 것(Agent B) 채택.

        Args:
            conflict: Conflict

        Returns:
            MergeResult
        """
        logger.info(f"Accepting theirs: {conflict.file_path}")

        return MergeResult(
            success=True,
            merged_content=conflict.agent_b_changes,
            conflicts=[],
            strategy=MergeStrategy.ACCEPT_THEIRS,
            message="Accepted Agent B changes",
        )

    async def resolve_manual(
        self,
        conflict: Conflict,
        resolved_content: str,
    ) -> MergeResult:
        """
        수동 해결.

        Args:
            conflict: Conflict
            resolved_content: 해결된 내용

        Returns:
            MergeResult
        """
        logger.info(f"Manual resolution: {conflict.file_path}")

        # 충돌 마커 확인
        if "<<<<<<< " in resolved_content or ">>>>>>> " in resolved_content:
            logger.warning("Resolved content contains conflict markers")

            return MergeResult(
                success=False,
                merged_content=resolved_content,
                conflicts=["Conflict markers still present"],
                strategy=MergeStrategy.MANUAL,
                message="Conflict markers still present",
            )

        return MergeResult(
            success=True,
            merged_content=resolved_content,
            conflicts=[],
            strategy=MergeStrategy.MANUAL,
            message="Manually resolved",
        )

    async def _git_merge_file(
        self,
        base: str,
        ours: str,
        theirs: str,
    ) -> tuple[str, list[str]]:
        """
        Git merge-file로 3-way merge.

        Args:
            base: Base 내용
            ours: Ours 내용
            theirs: Theirs 내용

        Returns:
            (merged_content, conflicts)
        """
        # 임시 파일 생성
        with tempfile.TemporaryDirectory() as tmpdir:
            base_file = Path(tmpdir) / "base"
            ours_file = Path(tmpdir) / "ours"
            theirs_file = Path(tmpdir) / "theirs"

            base_file.write_text(base)
            ours_file.write_text(ours)
            theirs_file.write_text(theirs)

            # git merge-file
            result = subprocess.run(
                [
                    "git",
                    "merge-file",
                    "-p",  # stdout으로 출력
                    str(ours_file),
                    str(base_file),
                    str(theirs_file),
                ],
                capture_output=True,
                text=True,
            )

            merged_content = result.stdout

            # 충돌 영역 추출
            conflicts = self._extract_conflict_regions(merged_content)

            logger.debug(f"Git merge-file: {len(conflicts)} conflicts")

            return merged_content, conflicts

    def _extract_conflict_regions(self, content: str) -> list[str]:
        """
        충돌 마커 영역 추출.

        Git 충돌 마커:
        <<<<<<< ours
        Agent A 내용
        =======
        Agent B 내용
        >>>>>>> theirs

        Args:
            content: Merge 결과

        Returns:
            충돌 영역 리스트
        """
        conflicts = []
        lines = content.split("\n")

        in_conflict = False
        conflict_start = 0

        for i, line in enumerate(lines):
            if line.startswith("<<<<<<< "):
                in_conflict = True
                conflict_start = i
            elif line.startswith(">>>>>>> ") and in_conflict:
                conflict_end = i
                conflicts.append(f"lines {conflict_start + 1}-{conflict_end + 1}")
                in_conflict = False

        return conflicts

    async def get_conflict_preview(
        self,
        conflict: Conflict,
    ) -> str:
        """
        충돌 미리보기 (diff 형식).

        Args:
            conflict: Conflict

        Returns:
            미리보기 텍스트
        """
        from src.agent.domain.diff_manager import DiffManager

        diff_mgr = DiffManager()

        # Agent A vs Base
        diff_a = await diff_mgr.generate_diff(
            conflict.base_content or "",
            conflict.agent_a_changes or "",
            conflict.file_path,
        )

        # Agent B vs Base
        diff_b = await diff_mgr.generate_diff(
            conflict.base_content or "",
            conflict.agent_b_changes or "",
            conflict.file_path,
        )

        preview = f"""
Conflict Preview: {conflict.file_path}

Agent A Changes:
{diff_mgr.format_file_diff(diff_a, colorize=False, show_stats=True)}

Agent B Changes:
{diff_mgr.format_file_diff(diff_b, colorize=False, show_stats=True)}

Type: {conflict.conflict_type.value}
Detected: {conflict.detected_at.strftime("%Y-%m-%d %H:%M:%S")}
"""

        return preview.strip()
