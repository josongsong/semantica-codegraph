"""VCS Models"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class CommitInfo:
    """Git 커밋 정보"""

    hash: str
    message: str
    author: str
    timestamp: datetime
    branch: str
    files_changed: list[str]

    def short_hash(self) -> str:
        """짧은 해시"""
        return self.hash[:7]

    def to_dict(self):
        """딕셔너리로 변환"""
        return {
            "hash": self.hash,
            "short_hash": self.short_hash(),
            "message": self.message,
            "author": self.author,
            "timestamp": self.timestamp.isoformat(),
            "branch": self.branch,
            "files_changed": self.files_changed,
        }

    def __str__(self):
        """문자열 표현"""
        return f"{self.short_hash()} - {self.message} ({self.author})"
