"""
Session Memory Domain Models

세션 메모리 도메인 모델
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MemoryType(str, Enum):
    """메모리 타입"""

    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


@dataclass
class Memory:
    """메모리"""

    id: str
    session_id: str
    type: MemoryType
    content: str
    timestamp: datetime
    metadata: dict[str, str | int] = field(default_factory=dict)


@dataclass
class Session:
    """세션"""

    id: str
    repo_id: str
    started_at: datetime
    ended_at: datetime | None = None
