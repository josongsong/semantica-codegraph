"""
Indexing Service Orchestrator

Coordinates indexing across all index types:
- Lexical (Zoekt): Full-text search on source files
- Vector (Qdrant): Semantic search on IndexDocuments
- Symbol (Kuzu): Graph-based symbol navigation
- Fuzzy (pg_trgm): Fuzzy identifier matching
- Domain (Qdrant): Documentation search
- Runtime (future): Execution trace analysis

Responsibilities:
- Full repo indexing (all indexes)
- Incremental indexing (changed files only)
- Index consistency (snapshot_id based)
- SearchHit fusion across indexes
- Two-phase indexing (fast core + background heavy)
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.chunk.models import Chunk
from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument
from src.contexts.multi_index.infrastructure.common.documents import IndexDocument, SearchHit
from src.contexts.multi_index.infrastructure.common.transformer import IndexDocumentTransformer
from src.contexts.repo_structure.infrastructure.models import RepoMapSnapshot

if TYPE_CHECKING:
    from src.ports import (
        DomainMetaIndexPort,
        FuzzyIndexPort,
        LexicalIndexPort,
        RuntimeIndexPort,
        SymbolIndexPort,
        VectorIndexPort,
    )

logger = get_logger(__name__)


@dataclass
class IndexingPhaseResult:
    """Result from two-phase indexing."""

    phase1_completed: bool  # Core indexes (Symbol, Lexical, Fuzzy)
    phase2_task: asyncio.Task | None  # Background task for heavy indexes (Vector)
    errors: list[tuple[str, Exception]]

    @property
    def is_fully_complete(self) -> bool:
        """Check if both phases are complete."""
        if self.phase2_task is None:
            return self.phase1_completed
        return self.phase1_completed and self.phase2_task.done()


class IndexingService:
    """
    Orchestrate indexing across all index types.

    Usage:
        service = IndexingService(lexical=zoekt, vector=qdrant)
        service.index_repo_full(repo_id, snapshot_id, chunks)
        hits = service.search(repo_id, snapshot_id, query)
    """

    def __init__(
        self,
        lexical_index: "LexicalIndexPort | None" = None,
        vector_index: "VectorIndexPort | None" = None,
        symbol_index: "SymbolIndexPort | None" = None,
        fuzzy_index: "FuzzyIndexPort | None" = None,
        domain_index: "DomainMetaIndexPort | None" = None,
        runtime_index: "RuntimeIndexPort | None" = None,
        file_queue=None,  # FileIndexingQueue
        queue_threshold: int = 10,  # 파일 개수 임계값
        idempotency_store=None,  # IdempotencyPort
        indexing_orchestrator=None,  # IndexingOrchestrator (전체 파이프라인용)
    ):
        """
        Initialize indexing service.

        Args:
            lexical_index: Zoekt-based lexical index (implements LexicalIndexPort)
            vector_index: Qdrant-based vector index (implements VectorIndexPort)
            symbol_index: Kuzu-based symbol index (implements SymbolIndexPort)
            fuzzy_index: PostgreSQL pg_trgm based fuzzy index (implements FuzzyIndexPort)
            domain_index: Domain metadata index (implements DomainMetaIndexPort)
            runtime_index: Runtime trace index (implements RuntimeIndexPort, Phase 3)

        Raises:
            TypeError: If any provided index doesn't implement the required Port protocol.
        """
        # Runtime type validation (Protocol conformance)
        from src.ports import (
            DomainMetaIndexPort,
            FuzzyIndexPort,
            LexicalIndexPort,
            RuntimeIndexPort,
            SymbolIndexPort,
            VectorIndexPort,
        )

        if lexical_index is not None and not isinstance(lexical_index, LexicalIndexPort):
            raise TypeError(f"lexical_index must implement LexicalIndexPort, got {type(lexical_index)}")
        if vector_index is not None and not isinstance(vector_index, VectorIndexPort):
            raise TypeError(f"vector_index must implement VectorIndexPort, got {type(vector_index)}")
        if symbol_index is not None and not isinstance(symbol_index, SymbolIndexPort):
            raise TypeError(f"symbol_index must implement SymbolIndexPort, got {type(symbol_index)}")
        if fuzzy_index is not None and not isinstance(fuzzy_index, FuzzyIndexPort):
            raise TypeError(f"fuzzy_index must implement FuzzyIndexPort, got {type(fuzzy_index)}")
        if domain_index is not None and not isinstance(domain_index, DomainMetaIndexPort):
            raise TypeError(f"domain_index must implement DomainMetaIndexPort, got {type(domain_index)}")
        if runtime_index is not None and not isinstance(runtime_index, RuntimeIndexPort):
            raise TypeError(f"runtime_index must implement RuntimeIndexPort, got {type(runtime_index)}")

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

    def set_indexing_orchestrator(self, orchestrator):
        """
        Set IndexingOrchestrator (lazy injection).

        순환 참조 방지를 위해 런타임에 주입.
        Container 초기화 후 호출됨.

        Args:
            orchestrator: IndexingOrchestrator instance
        """
        self.indexing_orchestrator = orchestrator
        logger.info("indexing_orchestrator_injected_for_full_pipeline")

    async def index_repo_full(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks: list[Chunk],
        graph_doc: GraphDocument | None = None,
        repomap_snapshot: RepoMapSnapshot | None = None,
        source_codes: dict[str, str] | None = None,
    ) -> None:
        """
        Full repository indexing.

        Indexes across all available index types.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier for consistency
            chunks: All chunks from Chunk layer
            graph_doc: Optional graph document for Symbol index
            repomap_snapshot: Optional RepoMap for importance scores
            source_codes: Optional source code mapping (chunk_id → code)
        """
        errors: list[tuple[str, Exception]] = []

        # Step 1: Transform Chunks → IndexDocuments (for Vector/Domain)
        try:
            transformer = IndexDocumentTransformer(
                repomap_snapshot=repomap_snapshot,
                ir_document=None,  # TODO: Pass IRDocument if available
            )
            index_docs = transformer.transform_batch(chunks, source_codes, snapshot_id)
        except Exception as e:
            logger.error(f"Failed to transform chunks for repo {repo_id}: {e}", exc_info=True)
            raise  # Cannot continue without IndexDocuments

        # Step 2: Index to Vector index (Qdrant)
        if self.vector_index:
            await self._safe_index_operation(
                "vector",
                lambda: self.vector_index.index(repo_id, snapshot_id, index_docs),
                repo_id,
                errors,
            )

        # Step 3: Index to Lexical index (Zoekt)
        # Note: Zoekt indexes source files directly, not IndexDocuments
        if self.lexical_index:
            await self._safe_index_operation(
                "lexical",
                lambda: self.lexical_index.reindex_repo(repo_id, snapshot_id),
                repo_id,
                errors,
            )

        # Step 4: Index to Symbol index (Kuzu Graph)
        if self.symbol_index and graph_doc:
            await self._safe_index_operation(
                "symbol",
                lambda: self.symbol_index.index_graph(repo_id, snapshot_id, graph_doc),
                repo_id,
                errors,
            )

        # Step 5: Index to Fuzzy index (pg_trgm)
        if self.fuzzy_index:
            await self._safe_index_operation(
                "fuzzy",
                lambda: self.fuzzy_index.index(repo_id, snapshot_id, index_docs),
                repo_id,
                errors,
            )

        # Step 6: Index to Domain index (if domain docs exist)
        if self.domain_index:
            domain_docs = [doc for doc in index_docs if self._is_domain_doc(doc)]
            if domain_docs:
                await self._safe_index_operation(
                    "domain",
                    lambda: self.domain_index.index(repo_id, snapshot_id, domain_docs),
                    repo_id,
                    errors,
                )

        # Report partial failures
        if errors:
            failed_indexes = ", ".join(name for name, _ in errors)
            logger.warning(f"Full indexing completed with {len(errors)} failures for repo {repo_id}: {failed_indexes}")

    async def index_repo_incremental(
        self,
        repo_id: str,
        snapshot_id: str,
        refresh_result: Any,  # ChunkRefreshResult
        repomap_snapshot: RepoMapSnapshot | None = None,
        source_codes: dict[str, str] | None = None,
    ) -> None:
        """
        Incremental repository indexing.

        Only indexes changed chunks.

        Args:
            repo_id: Repository identifier
            snapshot_id: New snapshot identifier
            refresh_result: ChunkRefreshResult with added/updated/deleted chunks
            repomap_snapshot: Optional RepoMap for importance scores
            source_codes: Optional source code mapping
        """
        errors: list[tuple[str, Exception]] = []

        # Step 1: Transform changed chunks
        changed_chunks = refresh_result.added_chunks + refresh_result.updated_chunks
        index_docs = []

        if changed_chunks:
            try:
                transformer = IndexDocumentTransformer(
                    repomap_snapshot=repomap_snapshot,
                    ir_document=None,
                )
                index_docs = transformer.transform_batch(changed_chunks, source_codes, snapshot_id)
            except Exception as e:
                logger.error(
                    f"Failed to transform {len(changed_chunks)} changed chunks for repo {repo_id}: {e}",
                    exc_info=True,
                )
                # Continue with deletions even if transform fails
                errors.append(("transform", e))

            # Update Vector index
            if self.vector_index and index_docs:
                try:
                    await self.vector_index.upsert(repo_id, snapshot_id, index_docs)
                    logger.info(f"Vector index updated for repo {repo_id} ({len(index_docs)} docs)")
                except Exception as e:
                    logger.error(f"Vector index update failed for repo {repo_id}: {e}", exc_info=True)
                    errors.append(("vector_upsert", e))

            # Update Fuzzy index
            if self.fuzzy_index and index_docs:
                try:
                    await self.fuzzy_index.upsert(repo_id, snapshot_id, index_docs)
                    logger.info(f"Fuzzy index updated for repo {repo_id}")
                except Exception as e:
                    logger.error(f"Fuzzy index update failed for repo {repo_id}: {e}", exc_info=True)
                    errors.append(("fuzzy_upsert", e))

            # Update Domain index
            if self.domain_index and index_docs:
                try:
                    domain_docs = [doc for doc in index_docs if self._is_domain_doc(doc)]
                    if domain_docs:
                        await self.domain_index.upsert(repo_id, snapshot_id, domain_docs)
                        logger.info(f"Domain index updated for repo {repo_id} ({len(domain_docs)} docs)")
                except Exception as e:
                    logger.error(f"Domain index update failed for repo {repo_id}: {e}", exc_info=True)
                    errors.append(("domain_upsert", e))

        # Step 2: Delete removed chunks
        if refresh_result.deleted_chunks:
            deleted_ids = [c.chunk_id for c in refresh_result.deleted_chunks]

            if self.vector_index:
                try:
                    await self.vector_index.delete(repo_id, snapshot_id, deleted_ids)
                    logger.info(f"Vector index deleted {len(deleted_ids)} chunks for repo {repo_id}")
                except Exception as e:
                    logger.error(f"Vector index deletion failed for repo {repo_id}: {e}", exc_info=True)
                    errors.append(("vector_delete", e))

            if self.fuzzy_index:
                try:
                    await self.fuzzy_index.delete(repo_id, snapshot_id, deleted_ids)
                    logger.info(f"Fuzzy index deleted {len(deleted_ids)} chunks for repo {repo_id}")
                except Exception as e:
                    logger.error(f"Fuzzy index deletion failed for repo {repo_id}: {e}", exc_info=True)
                    errors.append(("fuzzy_delete", e))

            if self.domain_index:
                try:
                    await self.domain_index.delete(repo_id, snapshot_id, deleted_ids)
                    logger.info(f"Domain index deleted {len(deleted_ids)} chunks for repo {repo_id}")
                except Exception as e:
                    logger.error(f"Domain index deletion failed for repo {repo_id}: {e}", exc_info=True)
                    errors.append(("domain_delete", e))

        # Step 3: Update Lexical index (Zoekt) for changed files
        if self.lexical_index and changed_chunks:
            try:
                changed_files = sorted({c.file_path for c in changed_chunks if c.file_path})
                if changed_files:
                    await self.lexical_index.reindex_paths(repo_id, snapshot_id, changed_files)
                    logger.info(f"Lexical index updated {len(changed_files)} files for repo {repo_id}")
            except Exception as e:
                logger.error(f"Lexical index update failed for repo {repo_id}: {e}", exc_info=True)
                errors.append(("lexical_update", e))

        # Report partial failures
        if errors:
            failed_operations = ", ".join(name for name, _ in errors)
            logger.warning(
                f"Incremental indexing completed with {len(errors)} failures for repo {repo_id}: {failed_operations}"
            )

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 50,
        weights: dict[str, float] | None = None,
    ) -> list[SearchHit]:
        """
        Unified search across all indexes.

        Performs weighted fusion of results from different indexes.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Search query
            limit: Maximum number of results
            weights: Index weights for fusion (default: equal weights)

        Returns:
            Fused SearchHit list sorted by score

        Note:
            Individual indexes do NOT need to sort their results, as fusion
            performs the final sorting. This avoids O(n log n) redundancy.
        """
        # Default weights
        if weights is None:
            weights = {
                "lexical": 0.3,
                "vector": 0.3,
                "symbol": 0.2,
                "fuzzy": 0.1,
                "domain": 0.1,
            }

        all_hits: list[SearchHit] = []
        errors: list[tuple[str, Exception]] = []

        # Query each index
        if self.lexical_index and "lexical" in weights:
            try:
                hits = await self.lexical_index.search(repo_id, snapshot_id, query, limit=100)
                all_hits.extend(hits)
                logger.debug(f"Lexical search returned {len(hits)} hits for query: {query}")
            except Exception as e:
                logger.error(f"Lexical search failed for repo {repo_id}: {e}", exc_info=True)
                errors.append(("lexical", e))

        if self.vector_index and "vector" in weights:
            try:
                hits = await self.vector_index.search(repo_id, snapshot_id, query, limit=100)
                all_hits.extend(hits)
                logger.debug(f"Vector search returned {len(hits)} hits for query: {query}")
            except Exception as e:
                logger.error(f"Vector search failed for repo {repo_id}: {e}", exc_info=True)
                errors.append(("vector", e))

        if self.symbol_index and "symbol" in weights:
            try:
                hits = await self.symbol_index.search(repo_id, snapshot_id, query, limit=100)
                all_hits.extend(hits)
                logger.debug(f"Symbol search returned {len(hits)} hits for query: {query}")
            except Exception as e:
                logger.error(f"Symbol search failed for repo {repo_id}: {e}", exc_info=True)
                errors.append(("symbol", e))

        if self.fuzzy_index and "fuzzy" in weights:
            try:
                hits = await self.fuzzy_index.search(repo_id, snapshot_id, query, limit=100)
                all_hits.extend(hits)
                logger.debug(f"Fuzzy search returned {len(hits)} hits for query: {query}")
            except Exception as e:
                logger.error(f"Fuzzy search failed for repo {repo_id}: {e}", exc_info=True)
                errors.append(("fuzzy", e))

        if self.domain_index and "domain" in weights:
            try:
                hits = await self.domain_index.search(repo_id, snapshot_id, query, limit=100)
                all_hits.extend(hits)
                logger.debug(f"Domain search returned {len(hits)} hits for query: {query}")
            except Exception as e:
                logger.error(f"Domain search failed for repo {repo_id}: {e}", exc_info=True)
                errors.append(("domain", e))

        # Report search failures
        if errors:
            failed_indexes = ", ".join(name for name, _ in errors)
            logger.warning(f"Search completed with {len(errors)} failures for repo {repo_id}: {failed_indexes}")

        # Fuse results using weighted scores
        if all_hits:
            fused_hits = self._fuse_hits(all_hits, weights)
            sources_count = len({h.source for h in all_hits})
            logger.info(
                f"Search fused {len(all_hits)} hits from {sources_count} sources into {len(fused_hits)} results"
            )
            return fused_hits[:limit]
        else:
            logger.warning(f"Search returned no hits for query: {query}")
            return []

    def _fuse_hits(self, hits: list[SearchHit], weights: dict[str, float]) -> list[SearchHit]:
        """
        Fuse search hits using weighted scoring.

        Implementation: Weighted sum of scores by source.

        Args:
            hits: All search hits from different sources (unsorted from each index)
            weights: Weights per source

        Returns:
            Fused and sorted hits (single O(n log n) sort at the end)

        Performance:
            - Grouping: O(n)
            - Fusion calculation: O(n)
            - Final sorting: O(n log n)
            - Total: O(n log n) single pass
        """
        # Group hits by chunk_id
        hit_groups: dict[str, list[SearchHit]] = {}
        for hit in hits:
            if hit.chunk_id not in hit_groups:
                hit_groups[hit.chunk_id] = []
            hit_groups[hit.chunk_id].append(hit)

        # Compute fused score per chunk
        fused: list[SearchHit] = []
        for chunk_id, chunk_hits in hit_groups.items():
            # Weighted average of scores
            weighted_score = 0.0
            total_weight = 0.0
            representative_hit = chunk_hits[0]  # Use first hit as template

            for hit in chunk_hits:
                weight = weights.get(hit.source, 0.0)
                weighted_score += hit.score * weight
                total_weight += weight

            # Normalize score
            final_score = weighted_score / total_weight if total_weight > 0 else 0.0

            # Determine source label and metadata
            # If single source, preserve original metadata; if multiple, add fusion info
            if len(chunk_hits) == 1:
                source_label = representative_hit.source
                # Preserve original metadata
                metadata = representative_hit.metadata.copy()
            else:
                source_label = representative_hit.source
                # Add fusion metadata
                metadata = {
                    **representative_hit.metadata,
                    "sources": [h.source for h in chunk_hits],
                    "original_scores": {h.source: h.score for h in chunk_hits},
                }

            # Create fused hit
            fused_hit = SearchHit(
                chunk_id=chunk_id,
                file_path=representative_hit.file_path,
                symbol_id=representative_hit.symbol_id,
                score=final_score,
                source=source_label,
                metadata=metadata,
            )
            fused.append(fused_hit)

        # Sort by fused score descending
        fused.sort(key=lambda h: h.score, reverse=True)
        return fused

    async def _safe_index_operation(
        self,
        operation_name: str,
        operation: Callable,
        repo_id: str,
        errors: list[tuple[str, Exception]],
    ) -> None:
        """
        Common wrapper for index operations with error handling.

        Args:
            operation_name: Name of the index operation (e.g., "vector", "lexical")
            operation: Async callable to execute
            repo_id: Repository identifier for logging
            errors: List to append errors to
        """
        try:
            await operation()
            logger.info(f"{operation_name.capitalize()} index completed for repo {repo_id}")
        except Exception as e:
            logger.error(
                f"{operation_name.capitalize()} index failed for repo {repo_id}: {e}",
                exc_info=True,
            )
            errors.append((operation_name, e))

    async def index_repo_two_phase(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks: list[Chunk],
        graph_doc: GraphDocument | None = None,
        repomap_snapshot: RepoMapSnapshot | None = None,
        source_codes: dict[str, str] | None = None,
    ) -> IndexingPhaseResult:
        """
        Two-phase indexing: fast core indexes first, heavy indexes in background.

        Phase 1 (synchronous, fast):
        - Symbol index (Kuzu): Graph-based symbol navigation
        - Lexical index (Zoekt): Full-text search
        - Fuzzy index (pg_trgm): Fuzzy identifier matching

        Phase 2 (background task, slow):
        - Vector index (Qdrant): Embedding-based semantic search
        - Domain index: Documentation search

        This allows IDE to start using search immediately after Phase 1,
        while expensive embedding operations run in background.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier for consistency
            chunks: All chunks from Chunk layer
            graph_doc: Optional graph document for Symbol index
            repomap_snapshot: Optional RepoMap for importance scores
            source_codes: Optional source code mapping (chunk_id → code)

        Returns:
            IndexingPhaseResult with phase1 status and phase2 background task
        """
        errors: list[tuple[str, Exception]] = []

        # Transform Chunks → IndexDocuments (needed for both phases)
        try:
            transformer = IndexDocumentTransformer(
                repomap_snapshot=repomap_snapshot,
                ir_document=None,
            )
            index_docs = transformer.transform_batch(chunks, source_codes, snapshot_id)
        except Exception as e:
            logger.error(f"Failed to transform chunks for repo {repo_id}: {e}", exc_info=True)
            return IndexingPhaseResult(
                phase1_completed=False,
                phase2_task=None,
                errors=[("transform", e)],
            )

        # ========== Phase 1: Fast Core Indexes ==========
        logger.info(f"Starting Phase 1 (fast) indexing for repo {repo_id}")

        # Symbol index (Kuzu) - graph queries are fast
        if self.symbol_index and graph_doc:
            await self._safe_index_operation(
                "symbol",
                lambda: self.symbol_index.index_graph(repo_id, snapshot_id, graph_doc),
                repo_id,
                errors,
            )

        # Lexical index (Zoekt) - text indexing is fast
        if self.lexical_index:
            await self._safe_index_operation(
                "lexical",
                lambda: self.lexical_index.reindex_repo(repo_id, snapshot_id),
                repo_id,
                errors,
            )

        # Fuzzy index (pg_trgm) - trigram indexing is fast
        if self.fuzzy_index:
            await self._safe_index_operation(
                "fuzzy",
                lambda: self.fuzzy_index.index(repo_id, snapshot_id, index_docs),
                repo_id,
                errors,
            )

        phase1_completed = len([e for e in errors if e[0] in ("symbol", "lexical", "fuzzy")]) == 0
        logger.info(
            f"Phase 1 completed for repo {repo_id}: success={phase1_completed}, errors={[e[0] for e in errors]}"
        )

        # ========== Phase 2: Heavy Indexes (Background) ==========
        async def _run_phase2():
            """Background task for heavy indexes."""
            phase2_errors: list[tuple[str, Exception]] = []
            logger.info(f"Starting Phase 2 (background) indexing for repo {repo_id}")

            # Vector index (Qdrant) - embedding is expensive
            if self.vector_index:
                await self._safe_index_operation(
                    "vector",
                    lambda: self.vector_index.index(repo_id, snapshot_id, index_docs),
                    repo_id,
                    phase2_errors,
                )

            # Domain index - also uses embeddings
            if self.domain_index:
                domain_docs = [doc for doc in index_docs if self._is_domain_doc(doc)]
                if domain_docs:
                    await self._safe_index_operation(
                        "domain",
                        lambda: self.domain_index.index(repo_id, snapshot_id, domain_docs),
                        repo_id,
                        phase2_errors,
                    )

            if phase2_errors:
                logger.warning(
                    f"Phase 2 completed with {len(phase2_errors)} errors for repo {repo_id}: "
                    f"{[e[0] for e in phase2_errors]}"
                )
            else:
                logger.info(f"Phase 2 completed successfully for repo {repo_id}")

            # Extend original errors list
            errors.extend(phase2_errors)

        # Start Phase 2 as background task
        phase2_task: asyncio.Task | None = None
        if self.vector_index or self.domain_index:
            phase2_task = asyncio.create_task(_run_phase2())
            logger.info(f"Phase 2 background task started for repo {repo_id}")

        return IndexingPhaseResult(
            phase1_completed=phase1_completed,
            phase2_task=phase2_task,
            errors=errors,
        )

    async def wait_for_full_indexing(self, result: IndexingPhaseResult) -> bool:
        """
        Wait for both phases to complete.

        Args:
            result: IndexingPhaseResult from index_repo_two_phase()

        Returns:
            True if all phases completed successfully
        """
        if result.phase2_task is not None:
            try:
                await result.phase2_task
            except Exception as e:
                logger.error(f"Phase 2 task failed: {e}", exc_info=True)
                result.errors.append(("phase2_task", e))

        return result.phase1_completed and (result.phase2_task is None or not result.phase2_task.cancelled())

    def _is_domain_doc(self, doc: IndexDocument) -> bool:
        """
        Check if document is a domain/documentation document.

        Heuristics:
        - README, CHANGELOG, LICENSE files
        - .md, .rst, .adoc files
        - docs/ directory
        - ADR (Architecture Decision Records)
        """
        if not doc.file_path:
            return False

        path_lower = doc.file_path.lower()

        # Check filename patterns
        if any(
            pattern in path_lower for pattern in ["readme", "changelog", "license", "contributing", "code_of_conduct"]
        ):
            return True

        # Check extensions
        if any(path_lower.endswith(ext) for ext in [".md", ".rst", ".adoc", ".txt"]):
            return True

        # Check directory
        if "docs/" in path_lower or "/docs/" in path_lower:
            return True

        return False

    # ========== IncrementalIndexingPort Implementation ==========

    async def index_files(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        reason: str | None = None,
        priority: int = 0,
        head_sha: str | None = None,
    ):
        """
        증분 인덱싱 구현 (IncrementalIndexingPort).

        Flow:
        1. 파일 필터링/정규화 (중복 제거, 바이너리 제외)
        2. 실행 전략 결정 (즉시 vs 큐) - 현재는 즉시만 지원
        3. 인덱싱 실행
        4. 결과 수집 및 상태 판단

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            file_paths: 인덱싱할 파일 경로 목록
            reason: 트리거 이유 (로깅용)
            priority: 우선순위 (미사용, 향후 큐 구현 시 사용)

        Returns:
            IncrementalIndexingResult
        """
        from src.contexts.agent_automation.domain.ports import IncrementalIndexingResult
        from src.contexts.multi_index.infrastructure.common.file_filter import FileFilter
        from src.infra.observability import record_counter

        # 1. 파일 필터링
        file_filter = FileFilter()

        # repo_root 가져오기 (파일 크기 체크용)
        repo_root = None
        if self.lexical_index and hasattr(self.lexical_index, "repo_resolver"):
            try:
                repo_path_str = self.lexical_index.repo_resolver.resolve_repo_path(repo_id)
                if repo_path_str:
                    repo_root = Path(repo_path_str)
            except Exception:
                pass

        normalized_paths = file_filter.normalize_and_filter(
            repo_id=repo_id,
            file_paths=file_paths,
            repo_root=repo_root,
        )

        if not normalized_paths:
            logger.info(
                "incremental_index_skipped_no_files",
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                original_count=len(file_paths),
            )
            return IncrementalIndexingResult(
                status="not_triggered",
                indexed_count=0,
                total_files=0,
                errors=[],
            )

        # 2. Idempotency 체크 (head_sha 제공 시)
        already_indexed = []
        if head_sha and self.idempotency_store:
            normalized_paths, already_indexed = await self.idempotency_store.filter_already_indexed(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                file_paths=normalized_paths,
                head_sha=head_sha,
            )

            if already_indexed:
                logger.info(
                    "idempotency_filter_applied",
                    repo_id=repo_id,
                    head_sha=head_sha[:8],
                    total_files=len(file_paths),
                    needs_indexing=len(normalized_paths),
                    already_indexed=len(already_indexed),
                )

            # 모두 이미 인덱싱됨
            if not normalized_paths:
                return IncrementalIndexingResult(
                    status="not_triggered",
                    indexed_count=0,
                    total_files=0,
                    errors=[],
                )

        # 3. 메트릭 기록
        record_counter(
            "incremental_indexing_triggered_total",
            labels={
                "repo_id": repo_id,
                "snapshot_id": snapshot_id,
                "trigger_source": reason or "unknown",
            },
        )

        logger.info(
            "incremental_index_starting",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            file_count=len(normalized_paths),
            reason=reason,
        )

        # 3. 실행 전략 결정: 즉시 vs 큐
        # Priority 높으면(Agent) 항상 즉시, 아니면 threshold 체크
        use_queue = (
            len(normalized_paths) > self.queue_threshold
            and self.file_queue
            and priority < 1  # Priority 1 이상은 항상 즉시
        )

        if use_queue:
            # 큐로 전송 (비동기 처리)
            added_count = await self.file_queue.enqueue_batch(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                file_paths=normalized_paths,
                reason=reason,
                priority=priority,
            )

            logger.info(
                "files_enqueued_for_indexing",
                repo_id=repo_id,
                file_count=added_count,
                queue_size=self.file_queue.get_queue_size(),
            )

            # 큐 등록 성공으로 간주
            return IncrementalIndexingResult(
                status="success",  # 큐 등록 성공
                indexed_count=added_count,
                total_files=len(normalized_paths),
                errors=[],
            )

        # 4. 즉시 인덱싱 (소량 파일 또는 큐 없음)
        indexed_count = 0
        errors = []

        for file_path in normalized_paths:
            try:
                # index_file_incremental 메서드 호출 (기존 메서드 활용)
                await self._index_single_file(
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    file_path=file_path,
                )
                indexed_count += 1
                logger.debug(
                    "incremental_index_file_success",
                    repo_id=repo_id,
                    file_path=file_path,
                )
            except Exception as e:
                logger.error(
                    "incremental_index_file_failed",
                    repo_id=repo_id,
                    file_path=file_path,
                    error=str(e),
                    exc_info=True,
                )
                errors.append(
                    {
                        "file_path": file_path,
                        "error": str(e),
                    }
                )
                record_counter(
                    "incremental_indexing_errors_total",
                    labels={
                        "repo_id": repo_id,
                        "file_path": file_path,
                    },
                )

        # 4. 상태 판단
        if indexed_count == len(normalized_paths):
            status = "success"
        elif indexed_count == 0:
            status = "failed"
        else:
            status = "partial_success"

        logger.info(
            "incremental_index_completed",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            status=status,
            indexed_count=indexed_count,
            total_files=len(normalized_paths),
            error_count=len(errors),
        )

        # 5. Idempotency 레코드 저장 (성공한 파일만)
        if head_sha and self.idempotency_store and indexed_count > 0:
            # 성공한 파일만 기록
            successfully_indexed = [
                path
                for i, path in enumerate(normalized_paths)
                if i < indexed_count  # errors가 없는 파일
            ]

            for file_path in successfully_indexed:
                try:
                    await self.idempotency_store.mark_indexed(
                        repo_id=repo_id,
                        snapshot_id=snapshot_id,
                        file_path=file_path,
                        head_sha=head_sha,
                    )
                except Exception as e:
                    logger.warning(
                        "idempotency_record_failed",
                        file_path=file_path,
                        error=str(e),
                    )

        return IncrementalIndexingResult(
            status=status,
            indexed_count=indexed_count,
            total_files=len(normalized_paths),
            errors=errors,
        )

    async def _index_single_file(
        self,
        repo_id: str,
        snapshot_id: str,
        file_path: str,
    ) -> None:
        """
        단일 파일 증분 인덱싱 (전체 파이프라인).

        Strategy:
        1. IndexingOrchestrator 있으면: 전체 파이프라인 (AST→IR→Graph→Chunk→Index)
        2. 없으면: Lexical Delta만 (간소화)

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            file_path: 파일 경로 (상대 경로)
        """
        logger.debug(
            "index_single_file_started",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            file_path=file_path,
        )

        # Strategy 1: 전체 파이프라인 (IndexingOrchestrator 사용)
        if self.indexing_orchestrator:
            try:
                # repo_path 가져오기 (여러 방법 시도)
                repo_path = None

                # 방법 1: lexical_index repo_resolver
                if self.lexical_index and hasattr(self.lexical_index, "repo_resolver"):
                    try:
                        repo_path = self.lexical_index.repo_resolver.resolve_repo_path(repo_id)
                    except Exception:
                        pass

                # 방법 2: Container (fallback)
                if not repo_path:
                    try:
                        from src.container import container

                        repo_path = getattr(container._settings, "workspace_path", None)
                    except Exception:
                        pass

                if not repo_path:
                    logger.warning("repo_path_not_resolved_fallback_to_delta", repo_id=repo_id)
                    # Fallback to Delta
                    raise RuntimeError("repo_path not available")

                # IndexingOrchestrator._index_single_file 호출 (전체 파이프라인)
                from src.contexts.analysis_indexing.infrastructure.models import IndexingResult, IndexingStatus
                from datetime import datetime

                temp_result = IndexingResult(
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    status=IndexingStatus.IN_PROGRESS,
                    start_time=datetime.now(),
                )

                success = await self.indexing_orchestrator._index_single_file(
                    repo_path=Path(repo_path),
                    file_path=file_path,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    result=temp_result,
                )

                if success:
                    logger.info(
                        "index_single_file_completed_full_pipeline",
                        repo_id=repo_id,
                        file_path=file_path,
                        chunks_created=temp_result.chunks_created,
                    )
                else:
                    logger.warning(
                        "index_single_file_failed_full_pipeline",
                        repo_id=repo_id,
                        file_path=file_path,
                    )
                    raise RuntimeError(f"Failed to index {file_path}")

                return

            except Exception as e:
                logger.error(
                    "full_pipeline_index_error",
                    repo_id=repo_id,
                    file_path=file_path,
                    error=str(e),
                )
                raise

        # Strategy 2: Lexical Delta만 (Fallback)
        if self.lexical_index and hasattr(self.lexical_index, "delta"):
            try:
                repo_path = self.lexical_index.repo_resolver.resolve_repo_path(repo_id)
                if not repo_path:
                    logger.warning("repo_path_not_resolved", repo_id=repo_id)
                    return

                full_path = Path(repo_path) / file_path
                if not full_path.exists():
                    logger.warning("file_not_found_for_index", file_path=file_path)
                    return

                content = full_path.read_text(encoding="utf-8", errors="replace")

                await self.lexical_index.delta.index_file(
                    repo_id=repo_id,
                    file_path=file_path,
                    content=content,
                )

                logger.debug(
                    "index_single_file_completed_delta_only",
                    repo_id=repo_id,
                    file_path=file_path,
                )
            except Exception as e:
                logger.error(
                    "lexical_delta_index_failed",
                    repo_id=repo_id,
                    file_path=file_path,
                    error=str(e),
                )
                raise

    async def wait_until_idle(
        self,
        repo_id: str,
        snapshot_id: str,
        timeout: float = 5.0,
    ) -> bool:
        """
        인덱싱 완료 대기 (IncrementalIndexingPort).

        현재는 간단한 폴링 구현.
        향후 큐 구현 시 실제 큐 상태를 체크하도록 개선.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            timeout: 최대 대기 시간 (초)

        Returns:
            완료 여부 (True: 완료, False: 타임아웃)
        """
        import time

        start_time = time.time()
        delay = 0.1  # 시작 100ms

        logger.debug(
            "wait_until_idle_started",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            timeout=timeout,
        )

        while time.time() - start_time < timeout:
            # 큐 체크 (있으면)
            if self.file_queue:
                if await self.file_queue.is_idle(repo_id, snapshot_id):
                    logger.debug(
                        "wait_until_idle_completed",
                        repo_id=repo_id,
                        elapsed_ms=(time.time() - start_time) * 1000,
                    )
                    return True

                # 대기
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, 1.0)  # Exponential backoff (최대 1초)
            else:
                # 큐 없으면 즉시 완료
                logger.debug(
                    "wait_until_idle_completed_no_queue",
                    repo_id=repo_id,
                )
                return True

        logger.warning(
            "wait_until_idle_timeout",
            repo_id=repo_id,
            timeout=timeout,
        )
        return False
