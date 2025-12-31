"""
Impact Analysis Models

변경 영향 전파 분석
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ImpactLevel(str, Enum):
    """Impact 강도"""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PropagationType(str, Enum):
    """전파 타입"""

    DIRECT_CALL = "direct_call"  # 직접 호출
    INDIRECT_CALL = "indirect_call"  # 간접 호출
    DATA_FLOW = "data_flow"  # 데이터 흐름
    TYPE_DEPENDENCY = "type_dependency"  # 타입 의존성
    INHERITANCE = "inheritance"  # 상속
    IMPORT = "import"  # import


@dataclass
class ImpactNode:
    """
    영향받는 노드

    Example:
        node = ImpactNode(
            symbol_id="func1",
            name="func1",
            kind="function",
            file_path="a.py",
            impact_level=ImpactLevel.HIGH,
            distance=1
        )
    """

    symbol_id: str
    name: str
    kind: str
    file_path: str
    impact_level: ImpactLevel = ImpactLevel.NONE
    distance: int = 0  # Source로부터의 거리
    propagation_type: PropagationType = PropagationType.DIRECT_CALL
    confidence: float = 1.0  # 0.0 ~ 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.symbol_id)

    def __eq__(self, other):
        if isinstance(other, ImpactNode):
            return self.symbol_id == other.symbol_id
        return False


@dataclass
class ImpactPath:
    """
    영향 전파 경로

    Example:
        path = ImpactPath(
            source="func1",
            target="func3",
            nodes=["func1", "func2", "func3"],
            propagation_types=[PropagationType.DIRECT_CALL, PropagationType.DATA_FLOW]
        )
    """

    source: str
    target: str
    nodes: list[str] = field(default_factory=list)  # Symbol IDs
    propagation_types: list[PropagationType] = field(default_factory=list)
    impact_level: ImpactLevel = ImpactLevel.NONE
    confidence: float = 1.0

    def __len__(self):
        return len(self.nodes)

    def __repr__(self):
        return f"ImpactPath({self.source} → {self.target}, len={len(self)})"


@dataclass
class ImpactReport:
    """
    전체 영향 분석 결과

    Example:
        report = ImpactReport(
            source_id="func1",
            impacted_nodes=[node1, node2, node3],
            impact_paths=[path1, path2],
            total_impact=ImpactLevel.HIGH
        )
    """

    source_id: str
    impacted_nodes: list[ImpactNode] = field(default_factory=list)
    impact_paths: list[ImpactPath] = field(default_factory=list)
    total_impact: ImpactLevel = ImpactLevel.NONE
    analyzed_at: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_critical_nodes(self) -> list[ImpactNode]:
        """Critical impact nodes 추출"""
        return [n for n in self.impacted_nodes if n.impact_level == ImpactLevel.CRITICAL]

    def get_high_impact_nodes(self) -> list[ImpactNode]:
        """High impact nodes 추출"""
        return [n for n in self.impacted_nodes if n.impact_level == ImpactLevel.HIGH]

    def get_nodes_by_file(self, file_path: str) -> list[ImpactNode]:
        """파일별 영향받는 노드"""
        return [n for n in self.impacted_nodes if n.file_path == file_path]

    def get_impacted_files(self) -> set[str]:
        """영향받는 파일 목록"""
        return {n.file_path for n in self.impacted_nodes}

    def summary(self) -> dict[str, Any]:
        """요약 정보"""
        return {
            "source": self.source_id,
            "total_impact": self.total_impact.value,
            "total_nodes": len(self.impacted_nodes),
            "total_files": len(self.get_impacted_files()),
            "critical_count": len(self.get_critical_nodes()),
            "high_count": len(self.get_high_impact_nodes()),
            "avg_distance": sum(n.distance for n in self.impacted_nodes) / len(self.impacted_nodes)
            if self.impacted_nodes
            else 0,
        }

    def __repr__(self):
        return f"ImpactReport({self.source_id}, impact={self.total_impact.value}, nodes={len(self.impacted_nodes)})"
