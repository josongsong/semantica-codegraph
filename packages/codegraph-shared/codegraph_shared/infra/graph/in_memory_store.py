"""
In-Memory Graph Store - DEPRECATED

이 모듈은 더 이상 사용되지 않습니다.

현재 아키텍처:
- 로컬 개발: GraphDocument (src/contexts/code_foundation/infrastructure/graph/models.py)
  → 메모리 내 그래프 + 역방향 인덱스 (GraphIndex)
  → 외부 DB 의존성 없음, 충분한 성능

- 서버/프로덕션: Memgraph (src/infra/graph/memgraph.py)
  → 영속적 그래프 DB 필요 시 사용
  → Cypher 쿼리 지원

InMemoryGraphStore가 필요했던 이유:
- Memgraph fallback으로 설계됨
- 하지만 GraphDocument가 이미 완전한 인메모리 그래프 제공
- 중복 구현이므로 제거

나중에 영속적 그래프 DB가 필요한 경우:
1. Memgraph 사용 (현재 구현 있음)
2. Kuzu 인메모리 모드 (pip install kuzu, db = kuzu.Database())
3. Neo4j (서버 환경)

Migration:
- InMemoryGraphStore 사용처 → GraphDocument로 대체
- profile.should_use_memgraph() == False → GraphDocument 직접 사용
"""

# DEPRECATED: 이 클래스는 더 이상 사용하지 않습니다.
# 호환성을 위해 stub만 남겨둡니다.


class InMemoryGraphStore:
    """
    DEPRECATED: GraphDocument를 사용하세요.

    이 클래스는 호환성을 위한 stub입니다.
    실제 그래프 작업은 GraphDocument + GraphIndex를 사용합니다.
    """

    def __init__(self):
        import warnings

        warnings.warn(
            "InMemoryGraphStore is deprecated. Use GraphDocument from "
            "src.contexts.code_foundation.infrastructure.graph.models instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._nodes: dict = {}
        self._edges: list = []

    def health_check(self) -> bool:
        return True

    def close(self) -> None:
        pass

    def get_stats(self) -> dict[str, int]:
        return {"nodes": 0, "edges": 0, "deprecated": True}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False
