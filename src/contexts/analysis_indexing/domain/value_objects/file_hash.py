"""
File Hash Value Object

불변 값 객체 - 파일 해시
"""

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class FileHash:
    """파일 해시 (SHA256)"""

    value: str

    @classmethod
    def from_content(cls, content: str) -> "FileHash":
        """
        파일 내용으로부터 해시 생성

        Args:
            content: 파일 내용

        Returns:
            FileHash 객체
        """
        hash_value = hashlib.sha256(content.encode()).hexdigest()
        return cls(value=hash_value)

    @classmethod
    def from_file(cls, file_path: str) -> "FileHash":
        """
        파일로부터 해시 생성

        Args:
            file_path: 파일 경로

        Returns:
            FileHash 객체
        """
        with open(file_path, "rb") as f:
            hash_value = hashlib.sha256(f.read()).hexdigest()
        return cls(value=hash_value)

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FileHash):
            return False
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)
