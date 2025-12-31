"""
Diff Manager (SOTA급)

Git diff 생성, 파싱, 관리를 담당합니다.

핵심 기능:
1. Unified diff 생성 (Git 호환)
2. Hunk 단위 파싱
3. Context lines 지원
4. Color 지원 (CLI)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DiffHunk:
    """
    Git diff hunk (@@ ... @@ 단위).

    예시:
        @@ -10,5 +10,7 @@
         context line
        -old line
        +new line
         context line
    """

    header: str  # "@@ -10,5 +10,7 @@"
    old_start: int  # 10
    old_count: int  # 5
    new_start: int  # 10
    new_count: int  # 7
    lines: list[str]  # [" context", "-old", "+new", " context"]

    @property
    def added_lines(self) -> list[str]:
        """추가된 라인 (+ 제외)"""
        return [line[1:] for line in self.lines if line.startswith("+")]

    @property
    def removed_lines(self) -> list[str]:
        """삭제된 라인 (- 제외)"""
        return [line[1:] for line in self.lines if line.startswith("-")]

    @property
    def context_lines(self) -> list[str]:
        """Context 라인 (공백 제외)"""
        return [line[1:] for line in self.lines if line.startswith(" ")]

    def to_patch(self) -> str:
        """Patch 문자열로 변환 (git apply 가능)"""
        return self.header + "\n" + "\n".join(self.lines)


@dataclass
class FileDiff:
    """
    파일 단위 diff.

    하나의 파일에 대한 모든 변경사항을 포함합니다.
    """

    file_path: str
    old_path: str | None = None  # rename 시
    change_type: str = "modified"  # "added", "deleted", "modified", "renamed"
    hunks: list[DiffHunk] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_new_file(self) -> bool:
        """새 파일인지 확인"""
        return self.change_type == "added"

    @property
    def is_deleted(self) -> bool:
        """삭제된 파일인지 확인"""
        return self.change_type == "deleted"

    @property
    def is_renamed(self) -> bool:
        """이름 변경된 파일인지 확인"""
        return self.change_type == "renamed"

    @property
    def total_added(self) -> int:
        """총 추가된 라인 수"""
        return sum(len(hunk.added_lines) for hunk in self.hunks)

    @property
    def total_removed(self) -> int:
        """총 삭제된 라인 수"""
        return sum(len(hunk.removed_lines) for hunk in self.hunks)

    def get_hunk(self, index: int) -> DiffHunk | None:
        """특정 hunk 가져오기"""
        if 0 <= index < len(self.hunks):
            return self.hunks[index]
        return None

    def get_hunks_patch(self, indices: list[int]) -> str:
        """
        선택한 hunk들만 적용한 patch.

        Args:
            indices: Hunk 인덱스 리스트

        Returns:
            Git patch 문자열
        """
        selected_hunks = [self.hunks[i] for i in indices if 0 <= i < len(self.hunks)]

        if not selected_hunks:
            return ""

        # Patch header
        lines = []
        lines.append(f"diff --git a/{self.file_path} b/{self.file_path}")

        if self.is_new_file:
            lines.append("new file mode 100644")
        elif self.is_deleted:
            lines.append("deleted file mode 100644")

        lines.append(f"--- a/{self.old_path or self.file_path}")
        lines.append(f"+++ b/{self.file_path}")

        # Hunks
        for hunk in selected_hunks:
            lines.append(hunk.to_patch())

        # CRITICAL: Patch는 newline으로 끝나야 함 (git apply 요구사항)
        return "\n".join(lines) + "\n"

    def to_patch(self) -> str:
        """전체 patch 문자열로 변환"""
        return self.get_hunks_patch(list(range(len(self.hunks))))


class DiffManager:
    """
    Git diff 생성 및 관리 (SOTA급).

    Git unified diff 형식을 생성하고 파싱합니다.
    """

    def __init__(self, context_lines: int = 3):
        """
        Args:
            context_lines: Context 라인 수 (기본 3)
        """
        self.context_lines = context_lines

    async def generate_diff(
        self,
        old_content: str,
        new_content: str,
        file_path: str,
        old_file_path: str | None = None,
    ) -> FileDiff:
        """
        두 파일 내용으로 diff 생성.

        Args:
            old_content: 이전 내용
            new_content: 새 내용
            file_path: 파일 경로
            old_file_path: 이전 파일 경로 (rename 시)

        Returns:
            FileDiff

        Raises:
            ValueError: Invalid input
        """
        # 입력 검증
        if not file_path or not file_path.strip():
            raise ValueError("file_path cannot be empty")

        if old_content is None or new_content is None:
            raise ValueError("old_content and new_content cannot be None")

        try:
            # difflib를 사용한 unified diff 생성
            import difflib

            logger.debug(f"Generating diff for {file_path}")

            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)

            # Unified diff 생성
            diff_lines = list(
                difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=f"a/{old_file_path or file_path}",
                    tofile=f"b/{file_path}",
                    n=self.context_lines,
                )
            )

            if not diff_lines:
                # 변경 없음
                logger.debug(f"No changes in {file_path}")
                return FileDiff(file_path=file_path, hunks=[])

            # Diff 텍스트로 변환
            diff_text = "".join(diff_lines)

            # 파싱
            file_diff = await self.parse_diff_text(diff_text)

            # Change type 결정
            if not old_content:
                file_diff.change_type = "added"
                logger.debug(f"New file: {file_path}")
            elif not new_content:
                file_diff.change_type = "deleted"
                logger.debug(f"Deleted file: {file_path}")
            elif old_file_path and old_file_path != file_path:
                file_diff.change_type = "renamed"
                file_diff.old_path = old_file_path
                logger.debug(f"Renamed: {old_file_path} -> {file_path}")

            logger.info(
                f"Diff generated: {file_path}, {len(file_diff.hunks)} hunks, +{file_diff.total_added}/-{file_diff.total_removed}"
            )
            return file_diff

        except Exception as e:
            logger.error(f"Failed to generate diff for {file_path}: {e}")
            raise

    async def parse_diff_text(self, diff_text: str) -> FileDiff:
        """
        Git diff 텍스트 파싱.

        Args:
            diff_text: Git diff 출력

        Returns:
            FileDiff

        Raises:
            ValueError: Invalid diff text
        """
        if not diff_text:
            raise ValueError("diff_text cannot be empty")

        try:
            lines = diff_text.split("\n")

            # File path 추출
            file_path = None
            old_path = None
            change_type = "modified"

            for line in lines[:10]:  # Header는 처음 몇 줄
                if line.startswith("+++"):
                    # +++ b/src/file.py
                    file_path = line[6:].strip()  # "b/" 제거
                elif line.startswith("---"):
                    # --- a/src/file.py
                    old_path = line[6:].strip()  # "a/" 제거
                elif "new file mode" in line:
                    change_type = "added"
                elif "deleted file mode" in line:
                    change_type = "deleted"

            if not file_path:
                file_path = "unknown"

            # Hunks 파싱
            hunks = self._parse_hunks(lines)

            logger.debug(f"Parsed diff: {file_path}, {len(hunks)} hunks, type={change_type}")

            return FileDiff(
                file_path=file_path,
                old_path=old_path if old_path != file_path else None,
                change_type=change_type,
                hunks=hunks,
            )

        except Exception as e:
            logger.error(f"Failed to parse diff text: {e}")
            raise

    def _parse_hunks(self, lines: list[str]) -> list[DiffHunk]:
        """
        Hunk 파싱.

        Hunk header: @@ -10,5 +10,7 @@
        - 10: old start line
        - 5: old count
        - 10: new start line
        - 7: new count
        """
        hunks = []
        current_hunk = None
        current_lines = []
        old_start = 0
        old_count = 0
        new_start = 0
        new_count = 0

        # Hunk header pattern: @@ -10,5 +10,7 @@
        hunk_pattern = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

        for line in lines:
            match = hunk_pattern.match(line)

            if match:
                # 이전 hunk 저장
                if current_hunk:
                    hunks.append(
                        DiffHunk(
                            header=current_hunk,
                            old_start=old_start,
                            old_count=old_count,
                            new_start=new_start,
                            new_count=new_count,
                            lines=current_lines,
                        )
                    )

                # 새 hunk 시작
                current_hunk = line
                current_lines = []

                # Parse numbers
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1

            elif current_hunk and (line.startswith(" ") or line.startswith("+") or line.startswith("-")):
                # Hunk content
                current_lines.append(line.rstrip())

        # 마지막 hunk 저장
        if current_hunk:
            hunks.append(
                DiffHunk(
                    header=current_hunk,
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=current_lines,
                )
            )

        return hunks

    def format_hunk(
        self,
        hunk: DiffHunk,
        colorize: bool = False,
        show_line_numbers: bool = True,
    ) -> str:
        """
        Hunk을 읽기 좋게 포맷팅.

        Args:
            hunk: DiffHunk
            colorize: Color 적용 여부
            show_line_numbers: 라인 번호 표시 여부

        Returns:
            포맷팅된 문자열
        """
        lines = []

        # Header
        if colorize:
            lines.append(f"\033[36m{hunk.header}\033[0m")  # Cyan
        else:
            lines.append(hunk.header)

        # Content
        old_line = hunk.old_start
        new_line = hunk.new_start

        for line in hunk.lines:
            prefix = line[0] if line else " "
            line[1:] if line else ""

            # Line numbers
            if show_line_numbers:
                if prefix == "-":
                    line_num = f"{old_line:4} |    |"
                    old_line += 1
                elif prefix == "+":
                    line_num = f"    |{new_line:4}|"
                    new_line += 1
                else:
                    line_num = f"{old_line:4}|{new_line:4}|"
                    old_line += 1
                    new_line += 1
            else:
                line_num = ""

            # Colorize
            if colorize:
                if prefix == "-":
                    formatted = f"{line_num}\033[31m{line}\033[0m"  # Red
                elif prefix == "+":
                    formatted = f"{line_num}\033[32m{line}\033[0m"  # Green
                else:
                    formatted = f"{line_num}{line}"
            else:
                formatted = f"{line_num}{line}"

            lines.append(formatted)

        return "\n".join(lines)

    def format_file_diff(
        self,
        file_diff: FileDiff,
        colorize: bool = False,
        show_stats: bool = True,
    ) -> str:
        """
        FileDiff를 읽기 좋게 포맷팅.

        Args:
            file_diff: FileDiff
            colorize: Color 적용 여부
            show_stats: 통계 표시 여부

        Returns:
            포맷팅된 문자열
        """
        lines = []

        # File header
        if colorize:
            lines.append(f"\033[1m{file_diff.file_path}\033[0m")  # Bold
        else:
            lines.append(file_diff.file_path)

        # Stats
        if show_stats:
            added = file_diff.total_added
            removed = file_diff.total_removed
            stats = f"+{added} -{removed} ({len(file_diff.hunks)} hunks)"

            if colorize:
                stats = f"\033[32m+{added}\033[0m \033[31m-{removed}\033[0m ({len(file_diff.hunks)} hunks)"

            lines.append(stats)

        lines.append("")  # Blank line

        # Hunks
        for i, hunk in enumerate(file_diff.hunks):
            if i > 0:
                lines.append("")  # Blank line between hunks

            lines.append(f"Hunk {i + 1}/{len(file_diff.hunks)}")
            lines.append(self.format_hunk(hunk, colorize=colorize))

        return "\n".join(lines)
