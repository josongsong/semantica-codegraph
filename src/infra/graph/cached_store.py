"""
Cached Graph Store (3-tier)

L1: In-Memory LRU (~0.1ms)
L2: Redis (~1-2ms, shared)
L3: Memgraph (~10-50ms, persistent)

주요 캐싱 대상:
- 노드 조회 (by ID, by FQN)
- 관계 조회 (callers, importers)
- 파일 기반 관계 조회

All public methods are async for consistency with other adapters.
"""

from typing import TYPE_CHECKING, Any, Literal

from src.common.observability import get_logger
from src.common.utils import TTLCache
from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument
from src.infra.cache.three_tier_cache import L3DatabaseLoader, ThreeTierCache

if TYPE_CHECKING:
    from src.infra.graph.memgraph import MemgraphGraphStore

logger = get_logger(__name__)


class GraphNodeLoader(L3DatabaseLoader[dict]):
    """Graph 노드용 L3 로더"""

    def __init__(self, graph_store: "MemgraphGraphStore"):
        self.store = graph_store

    async def load(self, key: str) -> dict | None:
        """
        Memgraph에서 노드 로드.

        Args:
            key: node_id

        Returns:
            노드 딕셔너리 or None
        """
        try:
            # MemgraphGraphStore is now async
            return await self.store.query_node_by_id(key)
        except Exception as e:
            logger.warning("graph_node_load_failed", node_id=key, error=str(e))
            return None

    async def save(self, key: str, value: dict) -> None:
        """Save는 지원 안 함 (read-only cache)"""
        pass

    async def delete(self, key: str) -> None:
        """Delete는 지원 안 함 (read-only cache)"""
        pass


class CachedGraphStore:
    """
    3-tier 캐싱이 적용된 Graph Store.

    캐시 전략:
    - 노드 조회: 3-tier 캐싱 (자주 조회됨)
    - 관계 조회: L1 only (동적 쿼리)
    - 저장 연산: 캐시 무효화

    성능 향상:
    - L1 hit: ~0.1ms (vs 10-50ms Memgraph 쿼리)
    - L2 hit: ~1-2ms
    - Expected hit rate: 50-70%

    Usage:
        cached_store = CachedGraphStore(
            graph_store=memgraph_store,
            redis_client=redis,
            l1_node_maxsize=5000,
            l1_relation_maxsize=2000,
        )

        # 투명한 API (async)
        node = await cached_store.query_node_by_id(node_id)
        callers = await cached_store.get_callers_by_file(repo_id, file_path)
    """

    def __init__(
        self,
        graph_store: "MemgraphGraphStore",
        redis_client: Any | None = None,
        l1_node_maxsize: int = 5000,
        l1_relation_maxsize: int = 2000,
        ttl: int = 600,  # 10분 (그래프는 자주 변경되지 않음)
    ):
        """
        Args:
            graph_store: 기존 MemgraphGraphStore
            redis_client: Redis 클라이언트 (optional)
            l1_node_maxsize: L1 노드 캐시 최대 크기
            l1_relation_maxsize: L1 관계 캐시 최대 크기
            ttl: TTL (초)
        """
        self.store = graph_store
        self.ttl = ttl

        # Expose _store for direct driver access (used by adapter_memgraph.py)
        # This delegates to the underlying MemgraphGraphStore._store
        if hasattr(graph_store, "_store"):
            self._store = graph_store._store

        # 노드 캐시 (3-tier)
        self._node_cache = ThreeTierCache[dict](
            l1_maxsize=l1_node_maxsize,
            l2_redis=redis_client,
            l3_loader=GraphNodeLoader(graph_store),
            ttl=ttl,
            namespace="graph:nodes",
        )

        # 관계 캐시 (L1 only - 쿼리 결과가 동적)
        # TTLCache 사용 (공통 유틸리티)
        self._relation_cache: TTLCache[str, set[str]] = TTLCache(
            maxsize=l1_relation_maxsize,
            ttl=ttl // 2,  # 관계는 더 짧은 TTL
        )

    # ==================== 노드 조회 (캐싱) ====================

    async def query_node_by_id(self, node_id: str) -> dict | None:
        """
        노드 ID로 조회 (3-tier 캐싱, async).

        Args:
            node_id: Node ID

        Returns:
            노드 딕셔너리 or None
        """
        return await self._node_cache.get(node_id)

    async def query_nodes_by_ids(self, node_ids: list[str]) -> list[dict]:
        """
        여러 노드 조회 (일부 캐싱).

        캐시 히트는 빠르게 반환, 미스는 DB에서 batch 조회.
        """
        cached = []
        cache_misses = []

        # L1/L2에서 먼저 조회
        for node_id in node_ids:
            node = await self._node_cache.get(node_id)
            if node is not None:
                cached.append(node)
            else:
                cache_misses.append(node_id)

        # 미스는 DB에서 batch 조회
        if cache_misses:
            db_nodes = await self.store.query_nodes_by_ids(cache_misses)
            # Populate cache
            for node in db_nodes:
                if node and "node_id" in node:
                    await self._node_cache.set(node["node_id"], node, write_through=False)
            cached.extend(db_nodes)

        return cached

    # ==================== 관계 조회 (L1 캐싱) ====================

    async def _cached_relation_query(
        self,
        cache_key: str,
        fetcher: Any,  # Callable that returns Awaitable[set[str] | list[str]]
        return_as_list: bool = False,
    ) -> set[str] | list[str]:
        """
        관계 조회 공통 헬퍼 (캐시 적용).

        8개 중복 메서드에서 추출한 공통 패턴.

        Args:
            cache_key: 캐시 키
            fetcher: 실제 데이터 조회 코루틴
            return_as_list: True면 list로 반환, False면 set 반환
        """
        cached = self._relation_cache.get(cache_key)
        if cached is not None:
            return list(cached) if return_as_list else cached

        # Cache miss - fetch from store
        result = await fetcher
        # Ensure we store as set
        result_set = set(result) if isinstance(result, list) else result
        self._relation_cache.set(cache_key, result_set)

        return list(result_set) if return_as_list else result_set

    async def query_called_by(self, function_id: str) -> list[str]:
        """함수를 호출하는 노드 ID 목록 (L1 캐싱)"""
        result = await self._cached_relation_query(
            f"called_by:{function_id}",
            self.store.query_called_by(function_id),
            return_as_list=True,
        )
        return list(result)

    async def query_imported_by(self, module_id: str) -> list[str]:
        """모듈을 import하는 노드 ID 목록 (L1 캐싱)"""
        result = await self._cached_relation_query(
            f"imported_by:{module_id}",
            self.store.query_imported_by(module_id),
            return_as_list=True,
        )
        return list(result)

    async def get_callers_by_file(self, repo_id: str, file_path: str) -> set[str]:
        """파일의 함수를 호출하는 파일 목록 (L1 캐싱)"""
        result = await self._cached_relation_query(
            f"callers_by_file:{repo_id}:{file_path}",
            self.store.get_callers_by_file(repo_id, file_path),
        )
        return set(result)

    async def get_subclasses_by_file(self, repo_id: str, file_path: str) -> set[str]:
        """파일의 클래스를 상속하는 파일 목록 (L1 캐싱)"""
        result = await self._cached_relation_query(
            f"subclasses_by_file:{repo_id}:{file_path}",
            self.store.get_subclasses_by_file(repo_id, file_path),
        )
        return set(result)

    async def get_superclasses_by_file(self, repo_id: str, file_path: str) -> set[str]:
        """파일이 상속하는 부모 클래스 파일 목록 (L1 캐싱)"""
        result = await self._cached_relation_query(
            f"superclasses_by_file:{repo_id}:{file_path}",
            self.store.get_superclasses_by_file(repo_id, file_path),
        )
        return set(result)

    async def get_imports(self, repo_id: str, file_path: str) -> set[str]:
        """파일이 import하는 파일 목록 (L1 캐싱)"""
        result = await self._cached_relation_query(
            f"imports:{repo_id}:{file_path}",
            self.store.get_imports(repo_id, file_path),
        )
        return set(result)

    async def get_imported_by(self, repo_id: str, file_path: str) -> set[str]:
        """파일을 import하는 파일 목록 (L1 캐싱)"""
        result = await self._cached_relation_query(
            f"imported_by_file:{repo_id}:{file_path}",
            self.store.get_imported_by(repo_id, file_path),
        )
        return set(result)

    # ==================== 저장 연산 (캐시 무효화) ====================

    async def save_graph(
        self,
        graph_doc: GraphDocument,
        mode: Literal["create", "merge", "upsert"] = "upsert",
        parallel_edges: bool = True,
    ) -> dict[str, Any]:
        """
        GraphDocument 저장 (캐시 무효화).

        Args:
            graph_doc: Graph document
            mode: Insert mode
            parallel_edges: 병렬 edge 저장

        Returns:
            저장 통계
        """
        # DB에 저장
        result = await self.store.save_graph(graph_doc, mode=mode, parallel_edges=parallel_edges)

        # 관련 캐시 무효화
        repo_id = graph_doc.repo_id
        self._invalidate_repo_caches(repo_id)

        return result

    def save_graph_sync(
        self,
        graph_doc: GraphDocument,
        mode: Literal["create", "merge", "upsert"] = "upsert",
        parallel_edges: bool = True,
    ) -> dict[str, Any]:
        """
        GraphDocument 저장 (동기 버전).

        DEPRECATED: Use async save_graph() instead.

        Args:
            graph_doc: Graph document
            mode: Insert mode
            parallel_edges: 병렬 edge 저장

        Returns:
            저장 통계
        """
        # 동기 저장
        result = self.store.save_graph_sync(graph_doc, mode=mode, parallel_edges=parallel_edges)

        # 관련 캐시 무효화
        repo_id = graph_doc.repo_id
        self._invalidate_repo_caches(repo_id)

        return result

    async def delete_repo(self, repo_id: str) -> dict[str, int]:
        """레포지토리 삭제 (캐시 무효화)"""
        result = await self.store.delete_repo(repo_id)
        self._invalidate_repo_caches(repo_id)
        return result

    async def delete_snapshot(self, repo_id: str, snapshot_id: str) -> dict[str, int]:
        """스냅샷 삭제 (캐시 무효화)"""
        result = await self.store.delete_snapshot(repo_id, snapshot_id)
        self._invalidate_repo_caches(repo_id)
        return result

    async def delete_nodes_for_deleted_files(self, repo_id: str, file_paths: list[str]) -> int:
        """Delete nodes for files that have been deleted."""
        # Write operation - invalidate cache and delegate
        self._invalidate_repo_caches(repo_id)  # sync method
        return await self.store.delete_nodes_for_deleted_files(repo_id, file_paths)

    async def delete_outbound_edges_by_file_paths(self, repo_id: str, file_paths: list[str]) -> int:
        """Delete only outbound edges from nodes belonging to specific file paths."""
        # Write operation - invalidate cache and delegate
        self._invalidate_repo_caches(repo_id)  # sync method
        return await self.store.delete_outbound_edges_by_file_paths(repo_id, file_paths)

    async def delete_orphan_module_nodes(self, repo_id: str) -> int:
        """Delete orphan module nodes that have no child nodes."""
        # Write operation - invalidate cache and delegate
        self._invalidate_repo_caches(repo_id)  # sync method
        return await self.store.delete_orphan_module_nodes(repo_id)

    def _invalidate_repo_caches(self, repo_id: str) -> None:
        """레포지토리 관련 캐시 무효화"""
        # TTLCache.invalidate_by_prefix 사용
        count = self._relation_cache.invalidate_by_prefix(repo_id)
        logger.debug("graph_cache_invalidated", repo_id=repo_id, keys_invalidated=count)

    # ==================== 통계 ====================

    def stats(self) -> dict:
        """캐시 통계 조회"""
        return {
            "nodes": self._node_cache.stats(),
            "relations": self._relation_cache.stats(),
        }

    # ==================== Pass-through methods ====================

    async def query_contains_children(self, parent_id: str) -> list[str]:
        """Pass-through (캐싱 없음 - 덜 자주 사용)"""
        return await self.store.query_contains_children(parent_id)

    async def query_nodes_by_fqns(self, fqns: list[str], repo_id: str | None = None) -> list[dict]:
        """Pass-through (bulk operation)"""
        return await self.store.query_nodes_by_fqns(fqns, repo_id)

    async def query_neighbors_bulk(
        self,
        node_ids: list[str],
        rel_types: list[str] | None = None,
        direction: Literal["outgoing", "incoming", "both"] = "both",
    ) -> dict[str, list[str]]:
        """Pass-through (bulk operation)"""
        return await self.store.query_neighbors_bulk(node_ids, rel_types, direction)

    async def query_paths_between(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
        rel_types: list[str] | None = None,
    ) -> list[list[str]]:
        """Pass-through (동적 쿼리)"""
        return await self.store.query_paths_between(source_id, target_id, max_depth, rel_types)

    async def close(self) -> None:
        """Close database connection"""
        await self.store.close()
