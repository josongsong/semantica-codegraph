"""
Snapshot ID Value Object

불변 값 객체 - 스냅샷 ID
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class SnapshotId:
    """스냅샷 ID"""

    value: str

    @classmethod
    def generate(cls) -> "SnapshotId":
        """
        새 스냅샷 ID 생성

        Returns:
            SnapshotId 객체
        """
        return cls(value=str(uuid.uuid4()))

    @classmethod
    def from_string(cls, value: str) -> "SnapshotId":
        """
        문자열로부터 생성

        Args:
            value: 스냅샷 ID 문자열

        Returns:
            SnapshotId 객체
        """
        return cls(value=value)

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SnapshotId):
            return False
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)
