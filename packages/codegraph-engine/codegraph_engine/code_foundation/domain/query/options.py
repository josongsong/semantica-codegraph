"""
Query Options - RFC-021 Phase 1

QueryOptions: Immutable query execution configuration
ScopeSpec: Scope filtering specification
PRESETS: Mode-based preset configurations
"""

from dataclasses import dataclass
from typing import Any

from .types import EdgeType


@dataclass(frozen=True)
class ScopeSpec:
    """
    탐색 범위 명세

    Intersection Rule (RFC-021):
    1. files, dirs, globs로 1차 후보군(Candidate Set) 생성
    2. fqns가 존재하면 AND 조건(Intersection) 적용
    3. fqns만 있으면 FQN → 파일 역추적
    """

    files: tuple[str, ...] = ()
    """특정 파일로 제한"""

    dirs: tuple[str, ...] = ()
    """특정 디렉토리로 제한"""

    globs: tuple[str, ...] = ()
    """Glob 패턴 (e.g., "**/*.py", "src/security/**")"""

    fqns: tuple[str, ...] = ()
    """Fully Qualified Names (e.g., "module.Class.method")"""


@dataclass(frozen=True)
class QueryOptions:
    """
    쿼리 실행 옵션 (불변 객체)

    RFC-021 Design:
    - Immutable (frozen=True) for caching
    - mode-based presets for common scenarios
    - Override individual options for customization
    """

    # ─────────────────────────────────────────────────────────────────────────
    # Scope
    # ─────────────────────────────────────────────────────────────────────────
    scope: ScopeSpec | None = None
    """탐색 범위 제한"""

    # ─────────────────────────────────────────────────────────────────────────
    # Traversal Limits
    # ─────────────────────────────────────────────────────────────────────────
    max_depth: int = 10
    """최대 탐색 깊이"""

    max_paths: int = 100
    """최대 경로 개수"""

    max_nodes: int = 10000
    """최대 방문 노드 수"""

    max_contexts_per_source: int = 10
    """Source당 최대 Context 수 (context-sensitive analysis)"""

    max_total_contexts: int = 50
    """전체 최대 Context 수"""

    timeout_ms: int = 5000
    """Timeout (밀리초)"""

    # ─────────────────────────────────────────────────────────────────────────
    # Edge Filtering
    # ─────────────────────────────────────────────────────────────────────────
    edge_types: tuple[EdgeType, ...] = (EdgeType.DFG, EdgeType.CALL)
    """허용할 엣지 타입 (EdgeType.DFG, EdgeType.CFG, EdgeType.CALL)"""

    # ─────────────────────────────────────────────────────────────────────────
    # Analysis Precision
    # ─────────────────────────────────────────────────────────────────────────
    context_sensitive: bool = False
    """Context-sensitive analysis (k-CFA)"""

    k_limit: int = 2
    """k-CFA의 k (context depth)"""

    alias_analysis: bool = False
    """Alias analysis (points-to)"""

    # ─────────────────────────────────────────────────────────────────────────
    # Algorithm
    # ─────────────────────────────────────────────────────────────────────────
    algorithm: str = "bfs"
    """탐색 알고리즘: "bfs" | "dfs"  """

    def replace(self, **changes: Any) -> "QueryOptions":
        """
        Create new QueryOptions with specified fields replaced

        Args:
            **changes: Fields to replace (type-checked at runtime)

        Returns:
            New QueryOptions instance with updated fields

        Example:
            new_opts = opts.replace(max_depth=15, timeout_ms=10000)
        """
        from dataclasses import replace as dataclass_replace

        return dataclass_replace(self, **changes)


# =============================================================================
# Mode-Based Presets (RFC-021)
# =============================================================================

PRESETS: dict[str, QueryOptions] = {
    "realtime": QueryOptions(
        max_depth=3,
        max_paths=10,
        max_contexts_per_source=3,
        max_total_contexts=10,
        timeout_ms=100,
        context_sensitive=False,
    ),
    "pr": QueryOptions(
        max_depth=10,
        max_paths=100,
        max_contexts_per_source=5,
        max_total_contexts=50,
        timeout_ms=5000,
        context_sensitive=False,
    ),
    "full": QueryOptions(
        max_depth=20,
        max_paths=1000,
        max_contexts_per_source=20,
        max_total_contexts=200,
        timeout_ms=300000,  # 5분
        context_sensitive=True,
        k_limit=2,
        alias_analysis=True,
    ),
}
