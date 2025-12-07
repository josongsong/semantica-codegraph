"""ShadowFS Models

데이터 모델
"""

from dataclasses import dataclass


@dataclass
class FileDiff:
    """파일 변경사항 Diff"""

    file_path: str
    old_content: str
    new_content: str
    unified_diff: str  # Unified diff 형식
    lines_added: int
    lines_removed: int

    def to_dict(self):
        """딕셔너리로 변환"""
        return {
            "file_path": self.file_path,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "unified_diff": self.unified_diff,
        }

    def __str__(self):
        """문자열 표현"""
        return f"FileDiff({self.file_path}: +{self.lines_added}/-{self.lines_removed})"


@dataclass
class ShadowFSState:
    """ShadowFS 상태"""

    workspace_path: str
    modified_files: list[str]
    total_lines_added: int
    total_lines_removed: int
    is_committed: bool

    def to_dict(self):
        """딕셔너리로 변환"""
        return {
            "workspace_path": self.workspace_path,
            "modified_files": self.modified_files,
            "total_lines_added": self.total_lines_added,
            "total_lines_removed": self.total_lines_removed,
            "is_committed": self.is_committed,
        }
