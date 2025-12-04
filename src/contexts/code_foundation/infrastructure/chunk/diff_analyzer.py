"""
Git Diff Analyzer

Git diff를 분석하여 변경된 코드 블록을 추출합니다.
PR 리뷰, 커밋 분석 등에 활용됩니다.
"""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from src.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class DiffBlock:
    """변경된 코드 블록"""

    file_path: str
    old_start: int  # 이전 파일의 시작 라인
    old_lines: int  # 이전 파일의 라인 수
    new_start: int  # 새 파일의 시작 라인
    new_lines: int  # 새 파일의 라인 수
    change_type: str  # 'added', 'modified', 'deleted'
    old_content: str | None  # 이전 내용 (deleted/modified)
    new_content: str | None  # 새 내용 (added/modified)
    context_before: str | None  # 변경 전 컨텍스트
    context_after: str | None  # 변경 후 컨텍스트


@dataclass
class FileDiff:
    """파일별 diff 정보"""

    file_path: str
    change_type: str  # 'added', 'modified', 'deleted', 'renamed'
    old_path: str | None  # renamed인 경우
    blocks: list[DiffBlock]


class DiffAnalyzer:
    """Git diff 분석기"""

    def __init__(self, repo_path: Path | str):
        self.repo_path = Path(repo_path)

    async def analyze_commit(self, commit_sha: str) -> list[FileDiff]:
        """
        커밋의 diff 분석.

        Args:
            commit_sha: Git commit SHA

        Returns:
            파일별 diff 정보
        """
        try:
            # git show --unified=3 --no-color {commit_sha}
            proc = await asyncio.create_subprocess_exec(
                "git",
                "show",
                "--unified=3",
                "--no-color",
                commit_sha,
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Git show failed: {error_msg}")
                raise RuntimeError(f"Git show failed: {error_msg}")

            return self._parse_diff(stdout.decode())

        except Exception as e:
            logger.error(f"Git show failed: {e}")
            raise

    async def analyze_diff(self, base_sha: str, head_sha: str) -> list[FileDiff]:
        """
        두 커밋 간 diff 분석 (PR용).

        Args:
            base_sha: Base commit (e.g., main)
            head_sha: Head commit (e.g., feature branch)

        Returns:
            파일별 diff 정보
        """
        try:
            # git diff --unified=3 --no-color base..head
            proc = await asyncio.create_subprocess_exec(
                "git",
                "diff",
                "--unified=3",
                "--no-color",
                f"{base_sha}..{head_sha}",
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Git diff failed: {error_msg}")
                raise RuntimeError(f"Git diff failed: {error_msg}")

            return self._parse_diff(stdout.decode())

        except Exception as e:
            logger.error(f"Git diff failed: {e}")
            raise

    async def analyze_uncommitted(self) -> list[FileDiff]:
        """
        Uncommitted changes 분석 (working directory).

        Returns:
            파일별 diff 정보
        """
        try:
            # git diff --unified=3 --no-color
            proc = await asyncio.create_subprocess_exec(
                "git",
                "diff",
                "--unified=3",
                "--no-color",
                "HEAD",
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Git diff failed: {error_msg}")
                raise RuntimeError(f"Git diff failed: {error_msg}")

            return self._parse_diff(stdout.decode())

        except Exception as e:
            logger.error(f"Git diff failed: {e}")
            raise

    def _parse_diff(self, diff_output: str) -> list[FileDiff]:
        """
        Git diff 출력 파싱.

        Args:
            diff_output: git diff 출력

        Returns:
            FileDiff 리스트
        """
        file_diffs = []
        current_file: FileDiff | None = None
        current_blocks: list[DiffBlock] = []

        lines = diff_output.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # File header: diff --git a/path b/path
            if line.startswith("diff --git"):
                # Save previous file
                if current_file:
                    current_file.blocks = current_blocks
                    file_diffs.append(current_file)

                # Parse new file (greedy to handle spaces in filename)
                match = re.match(r"diff --git a/(.*) b/(.*)$", line)
                if match:
                    old_path = match.group(1)
                    new_path = match.group(2)

                    # Determine change type
                    if old_path == new_path:
                        change_type = "modified"
                    else:
                        change_type = "renamed"

                    current_file = FileDiff(
                        file_path=new_path,
                        change_type=change_type,
                        old_path=old_path if change_type == "renamed" else None,
                        blocks=[],
                    )
                    current_blocks = []

            # Binary file (skip)
            elif "Binary files" in line:
                if current_file:
                    # Mark as binary and skip content parsing
                    current_file.change_type = "binary"
                    logger.debug(f"Skipping binary file: {current_file.file_path}")

            # New file
            elif line.startswith("new file mode"):
                if current_file:
                    current_file.change_type = "added"

            # Deleted file
            elif line.startswith("deleted file mode"):
                if current_file:
                    current_file.change_type = "deleted"

            # Rename detection (more accurate)
            elif line.startswith("rename from"):
                if current_file:
                    # Will be followed by "rename to"
                    pass

            elif line.startswith("rename to"):
                if current_file:
                    current_file.change_type = "renamed"

            # Hunk header: @@ -old_start,old_lines +new_start,new_lines @@
            elif line.startswith("@@"):
                if current_file:
                    block, end_idx = self._parse_hunk(lines, i, current_file.file_path)
                    if block:
                        current_blocks.append(block)
                    i = end_idx  # Skip to end of hunk
                    continue

            i += 1

        # Save last file
        if current_file:
            current_file.blocks = current_blocks
            file_diffs.append(current_file)

        return file_diffs

    def _parse_hunk(self, lines: list[str], start_idx: int, file_path: str) -> tuple[DiffBlock | None, int]:
        """
        Hunk 파싱 (변경 블록 하나).

        Args:
            lines: 전체 라인
            start_idx: Hunk header 시작 인덱스
            file_path: 현재 파일 경로

        Returns:
            (DiffBlock, end_idx) - end_idx는 다음 파싱 시작 위치
        """
        header = lines[start_idx]

        # Parse hunk header: @@ -old_start,old_lines +new_start,new_lines @@
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", header)
        if not match:
            return None, start_idx + 1

        old_start = int(match.group(1))
        old_lines = int(match.group(2)) if match.group(2) else 1
        new_start = int(match.group(3))
        new_lines = int(match.group(4)) if match.group(4) else 1

        # Extract content
        old_content_lines = []
        new_content_lines = []
        context_lines = []

        idx = start_idx + 1
        while idx < len(lines):
            line = lines[idx]

            # End of hunk
            if line.startswith("@@") or line.startswith("diff --git"):
                break

            # Skip "No newline at end of file" marker
            if line.startswith("\\ No newline"):
                idx += 1
                continue

            # Deleted line
            if line.startswith("-") and not line.startswith("---"):
                old_content_lines.append(line[1:])

            # Added line
            elif line.startswith("+") and not line.startswith("+++"):
                new_content_lines.append(line[1:])

            # Context line
            elif line.startswith(" "):
                context_lines.append(line[1:])
                old_content_lines.append(line[1:])
                new_content_lines.append(line[1:])

            idx += 1

        # Determine change type
        if old_content_lines and new_content_lines:
            change_type = "modified"
        elif old_content_lines:
            change_type = "deleted"
        elif new_content_lines:
            change_type = "added"
        else:
            change_type = "modified"

        block = DiffBlock(
            file_path=file_path,
            old_start=old_start,
            old_lines=old_lines,
            new_start=new_start,
            new_lines=new_lines,
            change_type=change_type,
            old_content="\n".join(old_content_lines) if old_content_lines else None,
            new_content="\n".join(new_content_lines) if new_content_lines else None,
            context_before=None,
            context_after=None,
        )

        return block, idx

    async def get_changed_files(self, base_sha: str, head_sha: str) -> set[str]:
        """
        변경된 파일 목록만 추출 (빠른 버전).

        Args:
            base_sha: Base commit
            head_sha: Head commit

        Returns:
            변경된 파일 경로 set
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "diff",
                "--name-only",
                f"{base_sha}..{head_sha}",
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Git diff --name-only failed: {error_msg}")
                return set()

            output = stdout.decode()
            return {line.strip() for line in output.split("\n") if line.strip()}

        except Exception as e:
            logger.error(f"Git diff --name-only failed: {e}")
            return set()

    async def get_changed_lines_map(self, base_sha: str, head_sha: str) -> dict[str, list[tuple[int, int]]]:
        """
        파일별 변경된 라인 범위 맵.

        Args:
            base_sha: Base commit
            head_sha: Head commit

        Returns:
            {file_path: [(start_line, end_line), ...]}
        """
        file_diffs = await self.analyze_diff(base_sha, head_sha)

        lines_map: dict[str, list[tuple[int, int]]] = {}

        for file_diff in file_diffs:
            ranges = []
            for block in file_diff.blocks:
                # Use new file line numbers
                start = block.new_start
                end = block.new_start + block.new_lines - 1
                ranges.append((start, end))

            lines_map[file_diff.file_path] = ranges

        return lines_map
