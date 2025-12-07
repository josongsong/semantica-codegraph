"""Code Generation Models"""

from dataclasses import dataclass
from typing import Any


@dataclass
class CodeChange:
    """생성된 코드 변경사항"""

    file_path: str
    content: str  # 새 코드
    explanation: str
    confidence: float = 1.0
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self):
        """딕셔너리로 변환"""
        return {
            "file_path": self.file_path,
            "content": self.content,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }
