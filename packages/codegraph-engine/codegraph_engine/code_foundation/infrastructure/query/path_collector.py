"""
Path Collector - RFC-021 Phase 1.5

경로 수집 및 Budget 체크 전용 클래스.

Responsibility (SRP):
- ✅ 경로 저장 (Materialize)
- ✅ Budget 체크 (Timeout/Node limit/Path limit)
- ✅ StopReason 결정
- ✅ Diagnostics 기록
- ❌ 다음 노드 탐색 (Engine 책임)
- ❌ BFS/DFS 알고리즘 (Engine 책임)
- ❌ 엣지 필터링 (Engine 책임)
- ❌ Context 생성 (DeepAnalyzer 책임)
"""

import time
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.query.options import QueryOptions
    from codegraph_engine.code_foundation.domain.query.results import PathResult, PathSet, StopReason

logger = get_logger(__name__)


class PathCollector:
    """
    경로 수집기 (RFC-021 Phase 1.5)

    역할: 발견된 경로 저장 및 Budget 체크만 담당
    제약: 탐색 로직(BFS/DFS)을 포함하지 않음
    """

    def __init__(self, options: "QueryOptions"):
        """
        Initialize PathCollector

        Args:
            options: Query options (budget 설정)
        """
        self.options = options
        self.paths: list[PathResult] = []
        self.nodes_visited: int = 0
        self.start_time = time.time()
        self.diagnostics: list[str] = []

    def add_path(self, path: "PathResult") -> None:
        """
        경로 추가

        Args:
            path: PathResult to add
        """
        self.paths.append(path)

    def increment_visited(self, count: int = 1) -> None:
        """
        방문 노드 수 증가

        Args:
            count: 증가할 노드 수
        """
        self.nodes_visited += count

    def should_stop(self) -> tuple[bool, "StopReason"]:
        """
        Budget 체크 (중단 여부 판단)

        Returns:
            (should_stop, stop_reason)

        Checks:
        1. Path limit
        2. Node limit
        3. Timeout

        Order matters: Path limit이 가장 먼저 체크됨 (가장 빈번)
        """
        from codegraph_engine.code_foundation.domain.query.results import StopReason

        # 1. Path limit (most frequent)
        if len(self.paths) >= self.options.max_paths:
            self.diagnostics.append(f"max_paths_reached: {len(self.paths)}")
            return True, StopReason.MAX_PATHS

        # 2. Node limit
        if self.nodes_visited >= self.options.max_nodes:
            self.diagnostics.append(f"max_nodes_reached: {self.nodes_visited}")
            return True, StopReason.MAX_NODES

        # 3. Timeout
        elapsed_ms = (time.time() - self.start_time) * 1000
        if elapsed_ms > self.options.timeout_ms:
            self.diagnostics.append(f"timeout: {int(elapsed_ms)}ms > {self.options.timeout_ms}ms")
            return True, StopReason.TIMEOUT

        return False, StopReason.COMPLETE

    def get_elapsed_ms(self) -> int:
        """현재 경과 시간 (밀리초)"""
        return int((time.time() - self.start_time) * 1000)

    def to_pathset(self, stop_reason: "StopReason") -> "PathSet":
        """
        PathSet으로 변환 (RFC-021: Stable Sorting)

        Args:
            stop_reason: Why execution stopped

        Returns:
            PathSet with collected paths (sorted) and metrics

        Sorting Order (RFC-021 Phase 3.2):
            1. severity (High → Medium → Low → None)
            2. uncertain (False 우선, True 후순위)
            3. length (짧은 경로 우선)
            4. node_id (lexicographic, tie-breaker)
        """
        from codegraph_engine.code_foundation.domain.query.results import PathSet

        # RFC-021: Stable sorting for CI diff stability
        SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, None: 999}

        sorted_paths = sorted(
            self.paths,
            key=lambda p: (
                SEVERITY_ORDER.get(p.severity, 999),  # 1. severity
                p.uncertain,  # 2. uncertain (False < True)
                len(p.nodes),  # 3. length (shorter first)
                p.nodes[0].id if p.nodes else "",  # 4. tie-breaker
            ),
        )

        # Add final diagnostics
        self.diagnostics.append(f"paths_found: {len(sorted_paths)}")
        self.diagnostics.append(f"nodes_visited: {self.nodes_visited}")
        self.diagnostics.append("paths_sorted: stable_order")

        return PathSet(
            paths=sorted_paths,
            stop_reason=stop_reason,
            elapsed_ms=self.get_elapsed_ms(),
            nodes_visited=self.nodes_visited,
            diagnostics=tuple(self.diagnostics),
        )

    def __len__(self) -> int:
        """Number of collected paths"""
        return len(self.paths)

    def __repr__(self) -> str:
        """Debug representation"""
        return (
            f"PathCollector(paths={len(self.paths)}, visited={self.nodes_visited}, elapsed={self.get_elapsed_ms()}ms)"
        )
