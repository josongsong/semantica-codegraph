"""
Repo Structure Domain Models

리포지토리 구조(RepoMap) 도메인 모델
"""

from dataclasses import dataclass, field


@dataclass
class RepoNode:
    """리포지토리 노드"""

    id: str
    path: str
    type: str  # file, directory, function, class
    importance: float = 0.0
    metadata: dict[str, str | int] = field(default_factory=dict)


@dataclass
class RepoEdge:
    """리포지토리 엣지"""

    source: str
    target: str
    type: str  # imports, calls, contains
    weight: float = 1.0


@dataclass
class RepoMap:
    """리포지토리 맵"""

    repo_id: str
    nodes: list[RepoNode] = field(default_factory=list)
    edges: list[RepoEdge] = field(default_factory=list)
    metadata: dict[str, str | int] = field(default_factory=dict)
