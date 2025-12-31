"""
TestPath Domain Model

테스트 생성 대상 경로 (ADR-011 Section 12)
"""

from dataclasses import dataclass
from enum import Enum

from codegraph_engine.code_foundation.domain.query.results import PathResult


class PathType(Enum):
    """경로 타입 (우선순위 정의)"""

    SECURITY = "security"  # Source → Sink (Priority: 100)
    EXCEPTION = "exception"  # Error handling path (Priority: 50)
    NEW_CODE = "new_code"  # 새로운 코드 (Priority: 30)
    UNCOVERED = "uncovered"  # 커버리지 미달 (Priority: 20)


# Priority mapping (ADR-011 명세)
PATH_PRIORITY = {
    PathType.SECURITY: 100,
    PathType.EXCEPTION: 50,
    PathType.NEW_CODE: 30,
    PathType.UNCOVERED: 20,
}


@dataclass(frozen=True)
class TestPath:
    """
    테스트 생성 대상 경로

    Immutable value object
    ADR-011 Section 12 명세 준수
    """

    path_result: PathResult  # Query DSL 결과
    path_type: PathType  # 경로 타입
    target_function: str  # 테스트 대상 함수 FQN
    context: dict[str, str]  # 추가 컨텍스트 (source, sink 등)

    @property
    def priority(self) -> int:
        """
        우선순위

        Returns:
            정수 (높을수록 우선)
        """
        return PATH_PRIORITY[self.path_type]

    @property
    def node_count(self) -> int:
        """경로 노드 수"""
        return len(self.path_result.nodes)

    def __lt__(self, other: "TestPath") -> bool:
        """우선순위 기반 정렬 (높은 우선순위가 먼저)"""
        if not isinstance(other, TestPath):
            return NotImplemented
        # Descending order (높은 우선순위가 작음)
        return self.priority > other.priority
