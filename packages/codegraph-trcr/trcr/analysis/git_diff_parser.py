"""
Git Diff Parser

Git diff 출력을 파싱하여 변경된 부분을 추출합니다.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class DiffHunk:
    """Diff hunk (변경 블록)"""

    old_start: int  # 원본 시작 라인
    old_count: int  # 원본 라인 수
    new_start: int  # 변경 후 시작 라인
    new_count: int  # 변경 후 라인 수

    # 변경 내용
    added_lines: list[tuple[int, str]] = field(default_factory=list)  # (라인번호, 내용)
    removed_lines: list[tuple[int, str]] = field(default_factory=list)
    context_lines: list[tuple[int, str]] = field(default_factory=list)

    @property
    def is_addition_only(self) -> bool:
        """추가만 있는지"""
        return len(self.added_lines) > 0 and len(self.removed_lines) == 0

    @property
    def is_deletion_only(self) -> bool:
        """삭제만 있는지"""
        return len(self.removed_lines) > 0 and len(self.added_lines) == 0

    @property
    def is_modification(self) -> bool:
        """수정인지"""
        return len(self.added_lines) > 0 and len(self.removed_lines) > 0


@dataclass
class FileDiff:
    """파일 단위 diff"""

    old_path: str | None  # None이면 새 파일
    new_path: str | None  # None이면 삭제된 파일
    hunks: list[DiffHunk] = field(default_factory=list)

    # 메타데이터
    is_binary: bool = False
    mode_change: str | None = None  # 예: "100644 → 100755"

    @property
    def status(self) -> Literal["added", "deleted", "modified", "renamed"]:
        """파일 상태"""
        if self.old_path is None:
            return "added"
        if self.new_path is None:
            return "deleted"
        if self.old_path != self.new_path:
            return "renamed"
        return "modified"

    @property
    def path(self) -> str:
        """대표 경로"""
        return self.new_path or self.old_path or ""

    @property
    def language(self) -> str | None:
        """파일 언어 추론"""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".go": "go",
            ".rb": "ruby",
            ".php": "php",
            ".cs": "csharp",
        }
        path = Path(self.path)
        return ext_map.get(path.suffix.lower())

    @property
    def added_line_count(self) -> int:
        return sum(len(h.added_lines) for h in self.hunks)

    @property
    def removed_line_count(self) -> int:
        return sum(len(h.removed_lines) for h in self.hunks)

    def get_changed_line_numbers(self) -> set[int]:
        """변경된 라인 번호들 (새 파일 기준)"""
        lines = set()
        for hunk in self.hunks:
            for line_no, _ in hunk.added_lines:
                lines.add(line_no)
        return lines


class GitDiffParser:
    """Git diff 파서"""

    # Hunk 헤더 패턴: @@ -old_start,old_count +new_start,new_count @@
    HUNK_HEADER_PATTERN = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

    # 파일 헤더 패턴
    DIFF_HEADER_PATTERN = re.compile(r"^diff --git a/(.*) b/(.*)$")
    OLD_FILE_PATTERN = re.compile(r"^--- (?:a/)?(.*)$")
    NEW_FILE_PATTERN = re.compile(r"^\+\+\+ (?:b/)?(.*)$")

    def parse(self, diff_text: str) -> list[FileDiff]:
        """Diff 텍스트 파싱"""
        files: list[FileDiff] = []
        current_file: FileDiff | None = None
        current_hunk: DiffHunk | None = None

        new_line_no = 0
        old_line_no = 0

        for line in diff_text.split("\n"):
            # 새 파일 diff 시작
            if match := self.DIFF_HEADER_PATTERN.match(line):
                if current_file:
                    if current_hunk:
                        current_file.hunks.append(current_hunk)
                    files.append(current_file)

                current_file = FileDiff(
                    old_path=match.group(1),
                    new_path=match.group(2),
                )
                current_hunk = None
                continue

            if current_file is None:
                continue

            # 파일 경로 업데이트
            if match := self.OLD_FILE_PATTERN.match(line):
                path = match.group(1)
                if path == "/dev/null":
                    current_file.old_path = None
                else:
                    current_file.old_path = path
                continue

            if match := self.NEW_FILE_PATTERN.match(line):
                path = match.group(1)
                if path == "/dev/null":
                    current_file.new_path = None
                else:
                    current_file.new_path = path
                continue

            # Hunk 헤더
            if match := self.HUNK_HEADER_PATTERN.match(line):
                if current_hunk:
                    current_file.hunks.append(current_hunk)

                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1

                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                )

                old_line_no = old_start
                new_line_no = new_start
                continue

            if current_hunk is None:
                continue

            # 변경 라인 파싱
            if line.startswith("+") and not line.startswith("+++"):
                current_hunk.added_lines.append((new_line_no, line[1:]))
                new_line_no += 1
            elif line.startswith("-") and not line.startswith("---"):
                current_hunk.removed_lines.append((old_line_no, line[1:]))
                old_line_no += 1
            elif line.startswith(" "):
                current_hunk.context_lines.append((new_line_no, line[1:]))
                old_line_no += 1
                new_line_no += 1
            elif line == "":
                # 빈 줄
                pass

        # 마지막 파일/hunk 추가
        if current_file:
            if current_hunk:
                current_file.hunks.append(current_hunk)
            files.append(current_file)

        return files

    def parse_from_git(
        self,
        repo_path: str | Path,
        base_ref: str = "HEAD~1",
        head_ref: str = "HEAD",
    ) -> list[FileDiff]:
        """Git 저장소에서 직접 diff 가져오기"""
        repo_path = Path(repo_path)

        result = subprocess.run(
            ["git", "diff", base_ref, head_ref, "--unified=3"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Git diff 실패: {result.stderr}")

        return self.parse(result.stdout)

    def parse_staged(self, repo_path: str | Path) -> list[FileDiff]:
        """Staged 변경사항 파싱"""
        repo_path = Path(repo_path)

        result = subprocess.run(
            ["git", "diff", "--staged", "--unified=3"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Git diff 실패: {result.stderr}")

        return self.parse(result.stdout)

    def parse_working_tree(self, repo_path: str | Path) -> list[FileDiff]:
        """Working tree 변경사항 파싱"""
        repo_path = Path(repo_path)

        result = subprocess.run(
            ["git", "diff", "--unified=3"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Git diff 실패: {result.stderr}")

        return self.parse(result.stdout)
