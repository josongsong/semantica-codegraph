"""
Indexing Service Facade

기존 IndexingService와 동일한 인터페이스를 제공하는 Facade.
내부적으로 분리된 컴포넌트들을 조합합니다.

Backward Compatibility:
    기존 코드에서 IndexingService를 사용하던 부분은 변경 없이 동작합니다.
"""

from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit
from codegraph_engine.multi_index.infrastructure.service.incremental_indexer import IncrementalIndexer
from codegraph_engine.multi_index.infrastructure.service.index_orchestrator import (
    IndexingPhaseResult,
    IndexOrchestrator,
)
from codegraph_engine.multi_index.infrastructure.service.index_registry import IndexRegistry
from codegraph_engine.multi_index.infrastructure.service.search_fusion import SearchFusion

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.chunk.models import Chunk
    from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument
    from codegraph_engine.repo_structure.infrastructure.models import RepoMapSnapshot
    from codegraph_shared.ports import (
        DomainMetaIndexPort,
        FuzzyIndexPort,
        LexicalIndexPort,
        RuntimeIndexPort,
        SymbolIndexPort,
        VectorIndexPort,
    )

logger = get_logger(__name__)


class IndexingService:
    """
    Indexing Service Facade.

    기존 IndexingService와 동일한 인터페이스를 유지하면서,
    내부적으로 SRP에 맞게 분리된 컴포넌트들을 사용합니다.

    Components:
        - IndexRegistry: 인덱스 관리 (OCP)
        - IndexOrchestrator: 인덱싱 조정
        - SearchFusion: 검색 및 퓨전
        - IncrementalIndexer: 증분 인덱싱

    Usage (기존과 동일):
        service = IndexingService(lexical=tantivy, vector=qdrant)
        await service.index_repo_full(repo_id, snapshot_id, chunks)
        hits = await service.search(repo_id, snapshot_id, query)
    """

    def __init__(
        self,
        lexical_index: "LexicalIndexPort | None" = None,
        vector_index: "VectorIndexPort | None" = None,
        symbol_index: "SymbolIndexPort | None" = None,
        fuzzy_index: "FuzzyIndexPort | None" = None,
        domain_index: "DomainMetaIndexPort | None" = None,
        runtime_index: "RuntimeIndexPort | None" = None,
        file_queue: Any | None = None,
        queue_threshold: int = 10,
        idempotency_store: Any | None = None,
        indexing_orchestrator: Any | None = None,
    ):
        """
        Initialize indexing service.

        Args:
            lexical_index: Tantivy-based lexical index
            vector_index: Qdrant-based vector index
            symbol_index: Memgraph-based symbol index
            fuzzy_index: PostgreSQL pg_trgm based fuzzy index
            domain_index: Domain metadata index
            runtime_index: Runtime trace index (Phase 3)
            file_queue: File indexing queue
            queue_threshold: Queue usage threshold
            idempotency_store: Idempotency store
            indexing_orchestrator: Full pipeline orchestrator
        """
        # 기존 속성 유지 (하위 호환성)
        self.lexical_index = lexical_index
        self.vector_index = vector_index
        self.symbol_index = symbol_index
        self.fuzzy_index = fuzzy_index
        self.domain_index = domain_index
        self.runtime_index = runtime_index
        self.file_queue = file_queue
        self.queue_threshold = queue_threshold
        self.idempotency_store = idempotency_store
        self.indexing_orchestrator = indexing_orchestrator

        # Registry 초기화 및 인덱스 등록
        self._registry = IndexRegistry()
        self._register_indexes()

        # 컴포넌트 초기화
        self._orchestrator = IndexOrchestrator(self._registry)
        self._search_fusion = SearchFusion(self._registry)
        self._incremental_indexer = IncrementalIndexer(
            registry=self._registry,
            file_queue=file_queue,
            queue_threshold=queue_threshold,
            idempotency_store=idempotency_store,
            indexing_orchestrator=indexing_orchestrator,
        )

    def _register_indexes(self) -> None:
        """인덱스 레지스트리에 등록"""
        # Phase 1: Fast indexes
        self._registry.register("symbol", self.symbol_index, weight=0.2, phase=1)
        self._registry.register("lexical", self.lexical_index, weight=0.3, phase=1)
        self._registry.register("fuzzy", self.fuzzy_index, weight=0.1, phase=1)

        # Phase 2: Heavy indexes (embedding required)
        self._registry.register("vector", self.vector_index, weight=0.3, phase=2)
        self._registry.register("domain", self.domain_index, weight=0.1, phase=2)

    def set_indexing_orchestrator(self, orchestrator: Any) -> None:
        """IndexingOrchestrator 설정 (지연 주입)"""
        self.indexing_orchestrator = orchestrator
        self._incremental_indexer.set_indexing_orchestrator(orchestrator)
        logger.info("indexing_orchestrator_injected_for_full_pipeline")

    # ========== Full Indexing ==========

    async def index_repo_full(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks: list["Chunk"],
        graph_doc: "GraphDocument | None" = None,
        repomap_snapshot: "RepoMapSnapshot | None" = None,
        source_codes: dict[str, str] | None = None,
    ) -> None:
        """Full repository indexing."""
        errors = await self._orchestrator.index_repo_full(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            chunks=chunks,
            graph_doc=graph_doc,
            repomap_snapshot=repomap_snapshot,
            source_codes=source_codes,
        )

        if errors:
            logger.warning(f"index_repo_full_partial_failure: {[e[0] for e in errors]}")

    async def index_repo_incremental(
        self,
        repo_id: str,
        snapshot_id: str,
        refresh_result: Any,
        repomap_snapshot: "RepoMapSnapshot | None" = None,
        source_codes: dict[str, str] | None = None,
    ) -> None:
        """Incremental repository indexing."""
        errors = await self._orchestrator.index_repo_incremental(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            refresh_result=refresh_result,
            repomap_snapshot=repomap_snapshot,
            source_codes=source_codes,
        )

        if errors:
            logger.warning(f"index_repo_incremental_partial_failure: {[e[0] for e in errors]}")

    async def index_repo_two_phase(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks: list["Chunk"],
        graph_doc: "GraphDocument | None" = None,
        repomap_snapshot: "RepoMapSnapshot | None" = None,
        source_codes: dict[str, str] | None = None,
    ) -> IndexingPhaseResult:
        """Two-phase indexing."""
        return await self._orchestrator.index_repo_two_phase(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            chunks=chunks,
            graph_doc=graph_doc,
            repomap_snapshot=repomap_snapshot,
            source_codes=source_codes,
        )

    async def wait_for_full_indexing(self, result: IndexingPhaseResult) -> bool:
        """Wait for two-phase indexing to complete."""
        return await self._orchestrator.wait_for_full_indexing(result)

    # ========== Search ==========

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 50,
        weights: dict[str, float] | None = None,
    ) -> list[SearchHit]:
        """Unified search across all indexes."""
        return await self._search_fusion.search(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            limit=limit,
            weights=weights,
        )

    # ========== Incremental Indexing ==========

    async def index_files(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        reason: str | None = None,
        priority: int = 0,
        head_sha: str | None = None,
    ):
        """Incremental file indexing."""
        return await self._incremental_indexer.index_files(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            file_paths=file_paths,
            reason=reason,
            priority=priority,
            head_sha=head_sha,
        )

    async def wait_until_idle(
        self,
        repo_id: str,
        snapshot_id: str,
        timeout: float = 5.0,
    ) -> bool:
        """Wait for indexing to complete."""
        return await self._incremental_indexer.wait_until_idle(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            timeout=timeout,
        )

    # ========== Legacy Methods (하위 호환성) ==========

    def _is_domain_doc(self, doc: Any) -> bool:
        """Check if document is a domain document (delegate to orchestrator)."""
        return self._orchestrator._is_domain_doc(doc)

    def _fuse_hits(
        self,
        hits: list[SearchHit],
        weights: dict[str, float],
    ) -> list[SearchHit]:
        """Fuse search hits (delegate to search_fusion)."""
        return self._search_fusion._fuse_hits(hits, weights)

    async def _safe_index_operation(
        self,
        operation_name: str,
        operation: Any,
        repo_id: str,
        errors: list[tuple[str, Exception]],
    ) -> None:
        """Safe index operation wrapper (legacy support)."""
        try:
            await operation()
            logger.info(f"{operation_name}_completed: repo={repo_id}")
        except Exception as e:
            logger.error(f"{operation_name}_failed: repo={repo_id}", exc_info=True)
            errors.append((operation_name, e))
