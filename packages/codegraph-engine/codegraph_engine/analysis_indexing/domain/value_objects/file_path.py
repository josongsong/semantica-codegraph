"""
File Path Value Object

불변 값 객체 - 파일 경로
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FilePath:
    """파일 경로"""

    value: str

    @classmethod
    def from_string(cls, path: str) -> "FilePath":
        """
        문자열로부터 생성

        Args:
            path: 파일 경로

        Returns:
            FilePath 객체
        """
        return cls(value=str(Path(path).resolve()))

    @property
    def path(self) -> Path:
        """Path 객체 반환"""
        return Path(self.value)

    @property
    def name(self) -> str:
        """파일명 반환"""
        return self.path.name

    @property
    def extension(self) -> str:
        """확장자 반환"""
        return self.path.suffix

    def exists(self) -> bool:
        """파일 존재 여부"""
        return self.path.exists()

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FilePath):
            return False
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)
