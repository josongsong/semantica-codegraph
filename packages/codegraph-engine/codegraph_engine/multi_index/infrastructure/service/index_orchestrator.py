"""
Index Orchestrator

인덱싱 조정 담당 (Single Responsibility).

Responsibilities:
- Full repository indexing
- Incremental indexing
- Two-phase indexing
- 에러 핸들링 및 로깅
"""

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument
from codegraph_engine.multi_index.infrastructure.common.transformer import IndexDocumentTransformer
from codegraph_engine.multi_index.infrastructure.service.index_registry import IndexRegistry

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.chunk.models import Chunk
    from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument
    from codegraph_engine.repo_structure.infrastructure.models import RepoMapSnapshot

logger = get_logger(__name__)


@dataclass
class IndexingPhaseResult:
    """Two-phase 인덱싱 결과"""

    phase1_completed: bool
    phase2_task: asyncio.Task | None
    errors: list[tuple[str, Exception]]

    @property
    def is_fully_complete(self) -> bool:
        if self.phase2_task is None:
            return self.phase1_completed
        return self.phase1_completed and self.phase2_task.done()


class IndexOrchestrator:
    """
    인덱싱 조정 서비스.

    Usage:
        orchestrator = IndexOrchestrator(registry)
        await orchestrator.index_repo_full(repo_id, snapshot_id, chunks)
    """

    # 캐시 최대 크기 (메모리 누수 방지)
    MAX_TRANSFORMER_CACHE_SIZE = 100

    def __init__(
        self,
        registry: IndexRegistry,
        transformer_cache: dict[str, IndexDocumentTransformer] | None = None,
    ):
        """
        Args:
            registry: 인덱스 레지스트리
            transformer_cache: Transformer 캐시 (재사용)
        """
        self._registry = registry
        self._transformer_cache = transformer_cache or {}
        self._cache_lock = asyncio.Lock()  # Thread-safe cache access

    async def _get_transformer(
        self,
        repomap_snapshot: "RepoMapSnapshot | None",
        cache_key: str | None = None,
    ) -> IndexDocumentTransformer:
        """Transformer 가져오기 (캐시 사용, LRU 방식, thread-safe)"""
        async with self._cache_lock:
            if cache_key and cache_key in self._transformer_cache:
                # LRU: 접근 시 순서 업데이트 (move to end)
                transformer = self._transformer_cache.pop(cache_key)
                self._transformer_cache[cache_key] = transformer
                return transformer

            transformer = IndexDocumentTransformer(
                repomap_snapshot=repomap_snapshot,
                ir_document=None,
            )

            if cache_key:
                # 캐시 크기 제한 (LRU: 가장 오래된 것 제거)
                if len(self._transformer_cache) >= self.MAX_TRANSFORMER_CACHE_SIZE:
                    oldest_key = next(iter(self._transformer_cache))
                    del self._transformer_cache[oldest_key]
                self._transformer_cache[cache_key] = transformer

            return transformer

    async def index_repo_full(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks: list["Chunk"],
        graph_doc: "GraphDocument | None" = None,
        repomap_snapshot: "RepoMapSnapshot | None" = None,
        source_codes: dict[str, str] | None = None,
    ) -> list[tuple[str, Exception]]:
        """
        Full repository 인덱싱.

        모든 등록된 인덱스에 대해 인덱싱 수행.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            chunks: 청크 리스트
            graph_doc: 그래프 문서 (Symbol 인덱스용)
            repomap_snapshot: RepoMap (중요도 점수용)
            source_codes: 소스 코드 맵 (chunk_id -> code)

        Returns:
            에러 리스트 [(index_name, exception), ...]
        """
        errors: list[tuple[str, Exception]] = []

        # Chunks -> IndexDocuments 변환
        try:
            transformer = await self._get_transformer(repomap_snapshot, f"{repo_id}:{snapshot_id}")
            transform_result = transformer.transform_batch(chunks, source_codes, snapshot_id)
            index_docs = transform_result.documents

            # Log transform errors but continue with successful docs
            if transform_result.has_errors:
                for err in transform_result.errors:
                    errors.append((f"transform:{err.chunk_id}", err.error))
        except Exception:
            logger.error(f"transform_failed: repo={repo_id}", exc_info=True)
            raise

        # 인덱스별 작업 정의
        # NOTE: 각 인덱스의 메서드 시그니처가 다르므로 name 기반 분기 필요.
        # 완전한 OCP를 위해서는 IndexPort에 통일된 index(docs, context) 메서드가 필요하지만,
        # 기존 어댑터와의 하위 호환성 때문에 현재는 이 방식 유지.
        async def _index_operation(name: str, index: Any) -> None:
            if name == "vector":
                await index.index(repo_id, snapshot_id, index_docs)
            elif name == "lexical":
                await index.reindex_repo(repo_id, snapshot_id)
            elif name == "symbol" and graph_doc:
                await index.index_graph(repo_id, snapshot_id, graph_doc)
            elif name == "fuzzy":
                await index.index(repo_id, snapshot_id, index_docs)
            elif name == "domain":
                domain_docs = [d for d in index_docs if self._is_domain_doc(d)]
                if domain_docs:
                    await index.index(repo_id, snapshot_id, domain_docs)

        # 모든 인덱스에 대해 실행
        results = await self._registry.execute_all(_index_operation, parallel=True)

        for name, exc in results:
            if exc:
                errors.append((name, exc))
            else:
                logger.info(f"index_completed: {name} for repo={repo_id}")

        if errors:
            logger.warning(f"index_repo_full_partial_failure: repo={repo_id}, failed={[e[0] for e in errors]}")

        return errors

    async def index_repo_incremental(
        self,
        repo_id: str,
        snapshot_id: str,
        refresh_result: Any,  # ChunkRefreshResult
        repomap_snapshot: "RepoMapSnapshot | None" = None,
        source_codes: dict[str, str] | None = None,
    ) -> list[tuple[str, Exception]]:
        """
        증분 인덱싱.

        변경된 청크만 업데이트.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            refresh_result: ChunkRefreshResult (added/updated/deleted)
            repomap_snapshot: RepoMap
            source_codes: 소스 코드 맵

        Returns:
            에러 리스트
        """
        errors: list[tuple[str, Exception]] = []

        # 변경된 청크 처리
        changed_chunks = refresh_result.added_chunks + refresh_result.updated_chunks
        index_docs: list[IndexDocument] = []

        if changed_chunks:
            try:
                transformer = await self._get_transformer(repomap_snapshot, f"{repo_id}:{snapshot_id}")
                transform_result = transformer.transform_batch(changed_chunks, source_codes, snapshot_id)
                index_docs = transform_result.documents

                # Log transform errors but continue with successful docs
                if transform_result.has_errors:
                    for err in transform_result.errors:
                        errors.append((f"transform:{err.chunk_id}", err.error))
            except Exception as e:
                logger.error(f"transform_incremental_failed: repo={repo_id}", exc_info=True)
                errors.append(("transform", e))

        # Upsert 작업 (병렬)
        if index_docs:

            async def _upsert_op(name: str, index: Any) -> None:
                if not hasattr(index, "upsert"):
                    return
                if name == "domain":
                    domain_docs = [d for d in index_docs if self._is_domain_doc(d)]
                    if domain_docs:
                        await index.upsert(repo_id, snapshot_id, domain_docs)
                else:
                    await index.upsert(repo_id, snapshot_id, index_docs)

            upsert_results = await self._registry.execute_all(_upsert_op, parallel=True)
            for name, exc in upsert_results:
                if exc:
                    errors.append((f"{name}_upsert", exc))
                else:
                    logger.info(f"upsert_completed: {name}")

        # Delete 작업 (병렬)
        if refresh_result.deleted_chunks:
            deleted_ids = [c.chunk_id for c in refresh_result.deleted_chunks]

            async def _delete_op(name: str, index: Any) -> None:
                if hasattr(index, "delete"):
                    await index.delete(repo_id, snapshot_id, deleted_ids)

            delete_results = await self._registry.execute_all(_delete_op, parallel=True)
            for name, exc in delete_results:
                if exc:
                    errors.append((f"{name}_delete", exc))
                else:
                    logger.info(f"delete_completed: {name}, count={len(deleted_ids)}")

        # Lexical 파일 업데이트
        lexical = self._registry.get("lexical")
        if lexical and changed_chunks:
            try:
                changed_files = sorted({c.file_path for c in changed_chunks if c.file_path})
                if changed_files:
                    await lexical.reindex_paths(repo_id, snapshot_id, changed_files)
                    logger.info(f"lexical_paths_updated: {len(changed_files)} files")
            except Exception as e:
                logger.error("lexical_paths_update_failed", exc_info=True)
                errors.append(("lexical_update", e))

        return errors

    async def index_repo_two_phase(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks: list["Chunk"],
        graph_doc: "GraphDocument | None" = None,
        repomap_snapshot: "RepoMapSnapshot | None" = None,
        source_codes: dict[str, str] | None = None,
    ) -> IndexingPhaseResult:
        """
        Two-phase 인덱싱.

        Phase 1 (동기, 빠름): Symbol, Lexical, Fuzzy
        Phase 2 (백그라운드, 느림): Vector, Domain

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            chunks: 청크 리스트
            graph_doc: 그래프 문서
            repomap_snapshot: RepoMap
            source_codes: 소스 코드 맵

        Returns:
            IndexingPhaseResult
        """
        errors: list[tuple[str, Exception]] = []

        # Transform
        try:
            transformer = await self._get_transformer(repomap_snapshot, f"{repo_id}:{snapshot_id}")
            transform_result = transformer.transform_batch(chunks, source_codes, snapshot_id)
            index_docs = transform_result.documents

            # Log transform errors but continue with successful docs
            if transform_result.has_errors:
                for err in transform_result.errors:
                    errors.append((f"transform:{err.chunk_id}", err.error))
        except Exception as e:
            logger.error(f"transform_failed: repo={repo_id}", exc_info=True)
            return IndexingPhaseResult(
                phase1_completed=False,
                phase2_task=None,
                errors=[("transform", e)],
            )

        # Phase 1: Fast indexes
        logger.info(f"two_phase_phase1_started: repo={repo_id}")

        async def _phase1_op(name: str, index: Any) -> None:
            if name == "symbol" and graph_doc:
                await index.index_graph(repo_id, snapshot_id, graph_doc)
            elif name == "lexical":
                await index.reindex_repo(repo_id, snapshot_id)
            elif name == "fuzzy":
                await index.index(repo_id, snapshot_id, index_docs)

        phase1_results = await self._registry.execute_all(_phase1_op, phase=1)
        phase1_errors = [(n, e) for n, e in phase1_results if e]
        errors.extend(phase1_errors)

        phase1_completed = len(phase1_errors) == 0
        logger.info(f"two_phase_phase1_completed: success={phase1_completed}")

        # Phase 2: Heavy indexes (background)
        # NOTE: Phase 2 errors are returned from the task, NOT mutated in shared list
        # This avoids race conditions between background task and caller
        #
        # CRITICAL: Create immutable copy to prevent data loss if original is modified/GC'd
        # before Phase 2 completes (see RFC review Issue #4)
        phase2_index_docs = list(index_docs)  # Shallow copy - safe for immutable IndexDocument

        async def _run_phase2() -> list[tuple[str, Exception]]:
            logger.info(f"two_phase_phase2_started: repo={repo_id}")
            phase2_errors: list[tuple[str, Exception]] = []

            async def _phase2_op(name: str, index: Any) -> None:
                if name == "vector":
                    await index.index(repo_id, snapshot_id, phase2_index_docs)
                elif name == "domain":
                    domain_docs = [d for d in phase2_index_docs if self._is_domain_doc(d)]
                    if domain_docs:
                        await index.index(repo_id, snapshot_id, domain_docs)

            results = await self._registry.execute_all(_phase2_op, phase=2)
            for name, exc in results:
                if exc:
                    phase2_errors.append((name, exc))

            if phase2_errors:
                logger.warning(f"two_phase_phase2_partial: errors={[e[0] for e in phase2_errors]}")
            else:
                logger.info(f"two_phase_phase2_completed: repo={repo_id}")

            return phase2_errors  # Return instead of mutating shared state

        # Background task
        phase2_task: asyncio.Task[list[tuple[str, Exception]]] | None = None
        phase2_entries = self._registry.get_all(phase=2)
        if phase2_entries:
            phase2_task = asyncio.create_task(_run_phase2())

        return IndexingPhaseResult(
            phase1_completed=phase1_completed,
            phase2_task=phase2_task,
            errors=errors,
        )

    async def wait_for_full_indexing(self, result: IndexingPhaseResult) -> bool:
        """Phase 2 완료 대기"""
        if result.phase2_task is not None:
            try:
                # Collect errors returned from phase2 task (thread-safe)
                phase2_errors = await result.phase2_task
                if phase2_errors:
                    result.errors.extend(phase2_errors)
            except asyncio.CancelledError:
                logger.warning("phase2_task_cancelled")
                result.errors.append(("phase2_task", asyncio.CancelledError("Task was cancelled")))
            except Exception as e:
                logger.error("phase2_task_failed", exc_info=True)
                result.errors.append(("phase2_task", e))

        return result.phase1_completed and (result.phase2_task is None or not result.phase2_task.cancelled())

    def _is_domain_doc(self, doc: IndexDocument) -> bool:
        """도메인 문서 여부 판단"""
        if not doc.file_path:
            return False

        path_lower = doc.file_path.lower()

        # 파일명 패턴
        if any(p in path_lower for p in ["readme", "changelog", "license", "contributing"]):
            return True

        # 확장자
        if any(path_lower.endswith(ext) for ext in [".md", ".rst", ".adoc", ".txt"]):
            return True

        # 디렉토리
        if "docs/" in path_lower or "/docs/" in path_lower:
            return True

        return False
