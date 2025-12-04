"""
Indexing Handler for Indexing Pipeline

Stage 9: Index to all indexes (lexical, vector, symbol, fuzzy, domain).
Supports parallel execution for improved performance.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from src.contexts.analysis_indexing.infrastructure.handlers.base import BaseHandler, HandlerContext
from src.contexts.analysis_indexing.infrastructure.handlers.parsing import detect_language
from src.contexts.analysis_indexing.infrastructure.models import IndexingResult, IndexingStage
from src.infra.observability import get_logger, record_counter
from src.pipeline.decorators import index_execution

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class IndexingHandler(BaseHandler):
    """
    Stage 9: Index to all configured indexes.

    Supports:
    - Parallel execution of multiple index types
    - Incremental indexing with deletion cleanup
    - Batch processing for memory efficiency
    """

    stage = IndexingStage.LEXICAL_INDEXING  # Primary stage (covers all indexing)

    def __init__(
        self,
        lexical_index: Any,
        vector_index: Any,
        symbol_index: Any,
        fuzzy_index: Any,
        domain_index: Any,
        config: Any,
        chunk_store: Any,
        embedding_queue: Any = None,
    ):
        """
        Initialize indexing handler.

        Args:
            lexical_index: Lexical index service (Zoekt)
            vector_index: Vector index service (Qdrant)
            symbol_index: Symbol index service (Memgraph)
            fuzzy_index: Fuzzy index service
            domain_index: Domain metadata index service
            config: IndexingConfig
            chunk_store: Chunk storage for loading chunks
            embedding_queue: Embedding queue for priority-based embedding (optional)
        """
        super().__init__()
        self.lexical_index = lexical_index
        self.vector_index = vector_index
        self.symbol_index = symbol_index
        self.fuzzy_index = fuzzy_index
        self.domain_index = domain_index
        self.config = config
        self.chunk_store = chunk_store
        self.embedding_queue = embedding_queue

    async def execute(
        self,
        ctx: HandlerContext,
        result: IndexingResult,
        chunk_ids: list[str],
        graph_doc: Any,
        ir_doc: Any,
        repomap: Any | None = None,
    ) -> None:
        """
        Execute indexing stage (parallel execution).

        Args:
            ctx: Handler context
            result: Indexing result to update
            chunk_ids: List of chunk IDs to index
            graph_doc: Graph document for symbol index
            ir_doc: IR document for fuzzy index
            repomap: RepoMap snapshot for enrichment
        """
        logger.info("indexing_started_parallel")

        repo_id = ctx.repo_id
        snapshot_id = ctx.snapshot_id

        # Handle deleted chunks from incremental indexing
        deleted_chunk_ids = result.metadata.get("deleted_chunk_ids", [])
        if deleted_chunk_ids:
            await self._delete_chunks_from_indexes(repo_id, snapshot_id, deleted_chunk_ids, result)

        # Build list of indexing tasks
        tasks = []
        task_names = []

        if self.config.enable_lexical_index:
            tasks.append(self._index_lexical(result, repo_id, snapshot_id, chunk_ids))
            task_names.append("lexical")

        if self.config.enable_vector_index:
            tasks.append(self._index_vector(result, repo_id, snapshot_id, chunk_ids, repomap))
            task_names.append("vector")

        if self.config.enable_symbol_index:
            tasks.append(self._index_symbol(result, repo_id, snapshot_id, graph_doc))
            task_names.append("symbol")

        if self.config.enable_fuzzy_index:
            tasks.append(self._index_fuzzy(result, repo_id, snapshot_id, ir_doc))
            task_names.append("fuzzy")

        if self.config.enable_domain_index:
            tasks.append(self._index_domain(result, repo_id, snapshot_id, chunk_ids))
            task_names.append("domain")

        # Execute in parallel with exception handling
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    index_name = task_names[i]
                    logger.warning(
                        "index_failed",
                        index=index_name,
                        error=str(res),
                    )
                    result.add_warning(f"{index_name.capitalize()} index failed: {res}")
                    record_counter("index_failures_total", labels={"index": index_name})

        logger.info(
            f"Indexed: Lexical({result.lexical_docs_indexed}), "
            f"Vector({result.vector_docs_indexed}), "
            f"Symbol({result.symbol_entries_indexed})"
        )

    @index_execution(IndexingStage.LEXICAL_INDEXING, "Lexical")
    async def _index_lexical(
        self,
        result: IndexingResult,
        repo_id: str,
        snapshot_id: str,
        chunk_ids: list[str],
    ) -> None:
        """Index to lexical index (Base+Delta v4.5).

        증분 모드:
        - Delta Index에만 업데이트 (파일 단위)
        - Base는 건드리지 않음

        전체 모드:
        - Base 전체 재인덱싱
        """
        if result.incremental and hasattr(self.lexical_index, "reindex_paths"):
            changed_files = result.metadata.get("changed_files", [])

            # v4.5: Delta Index 사용 가능 여부 체크
            if hasattr(self.lexical_index, "delta") and changed_files:
                logger.info("lexical_delta_indexing", count=len(changed_files))

                # Delta Index로 파일 단위 증분 업데이트
                from pathlib import Path

                base_path = Path(result.metadata.get("repo_path", "."))

                for file_path in changed_files:
                    full_path = base_path / file_path
                    if full_path.exists():
                        content = full_path.read_text()
                        # Delta.index_file() 호출
                        await self.lexical_index.delta.index_file(
                            repo_id=repo_id,
                            file_path=file_path,
                            content=content,
                        )

                result.lexical_docs_indexed = len(changed_files)
                logger.info("lexical_delta_indexing_completed", count=len(changed_files))
                return

            # Fallback: 기존 Zoekt incremental
            if changed_files:
                logger.info("lexical_incremental_indexing", count=len(changed_files))
                await self.lexical_index.reindex_paths(repo_id, snapshot_id, changed_files)
                result.lexical_docs_indexed = len(changed_files)
                return

        # 전체 인덱싱: Base 재인덱싱
        await self.lexical_index.reindex_repo(repo_id, snapshot_id)
        result.lexical_docs_indexed = len(chunk_ids)

    @index_execution(IndexingStage.VECTOR_INDEXING, "Vector")
    async def _index_vector(
        self,
        result: IndexingResult,
        repo_id: str,
        snapshot_id: str,
        chunk_ids: list[str],
        repomap: Any | None = None,
    ) -> None:
        """Index to vector index (Qdrant) with priority-based processing."""
        batch_size = self.config.vector_batch_size
        total_indexed = 0

        # Load chunks
        chunks = await self._load_chunks_by_ids(chunk_ids, batch_size=batch_size)

        if not chunks:
            logger.warning("no_chunks_to_index_vector", repo_id=repo_id)
            return

        # Priority 기반 분리
        try:
            from src.contexts.multi_index.infrastructure.vector.priority import partition_by_priority

            high, medium, low = partition_by_priority(chunks)

            logger.info(
                "vector_indexing_priority_split",
                high=len(high),
                medium=len(medium),
                low=len(low),
            )

            # 1. 우선순위 높은 것만 즉시 embedding (function, usage, class)
            if high:
                index_docs = self._chunks_to_index_docs(high, repo_id, snapshot_id, repomap)
                await self.vector_index.index(repo_id, snapshot_id, index_docs)
                total_indexed += len(high)
                logger.info("high_priority_embedded_immediately", count=len(high))

            # 2. 중간/낮은 우선순위는 큐로 전송 (embedding_queue 있으면)
            if hasattr(self, "embedding_queue") and self.embedding_queue:
                queued_chunks = medium + low
                if queued_chunks:
                    queued_count = await self.embedding_queue.enqueue(
                        queued_chunks,
                        repo_id,
                        snapshot_id,
                    )
                    logger.info("medium_low_priority_queued", count=queued_count)
                    total_indexed += queued_count
            else:
                # Queue 없으면 전체 즉시 처리 (기존 방식)
                all_chunks = medium + low
                if all_chunks:
                    index_docs = self._chunks_to_index_docs(all_chunks, repo_id, snapshot_id, repomap)
                    await self.vector_index.index(repo_id, snapshot_id, index_docs)
                    total_indexed += len(all_chunks)

        except ImportError:
            # priority 모듈 없으면 기존 방식 (전체 즉시)
            logger.debug("priority_module_not_available_using_legacy")
            index_docs = self._chunks_to_index_docs(chunks, repo_id, snapshot_id, repomap)
            await self.vector_index.index(repo_id, snapshot_id, index_docs)
            total_indexed = len(chunks)

        result.vector_docs_indexed = total_indexed

    @index_execution(IndexingStage.SYMBOL_INDEXING, "Symbol")
    async def _index_symbol(
        self,
        result: IndexingResult,
        repo_id: str,
        snapshot_id: str,
        graph_doc: Any,
    ) -> None:
        """Index to symbol index (Memgraph)."""
        await self.symbol_index.index_graph(repo_id, snapshot_id, graph_doc)
        result.symbol_entries_indexed = len(getattr(graph_doc, "graph_nodes", {}))

    @index_execution(IndexingStage.FUZZY_INDEXING, "Fuzzy")
    async def _index_fuzzy(
        self,
        result: IndexingResult,
        repo_id: str,
        snapshot_id: str,
        ir_doc: Any,
    ) -> None:
        """Index to fuzzy index."""
        from src.contexts.multi_index.infrastructure.common.documents import IndexDocument

        nodes = getattr(ir_doc, "nodes", [])
        docs = []

        for node in nodes:
            if hasattr(node, "name") and node.name:
                node_id = getattr(node, "id", "") or ""
                file_path = getattr(node, "file_path", "") or ""
                doc = IndexDocument(
                    id=node_id,
                    chunk_id=node_id,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    file_path=file_path,
                    language=detect_language(file_path),
                    symbol_id=node_id,
                    symbol_name=node.name,
                    content=node.name,
                    identifiers=[node.name],
                    tags={"kind": str(getattr(node, "kind", "unknown"))},
                )
                docs.append(doc)

        if docs:
            await self.fuzzy_index.index(repo_id, snapshot_id, docs)
        result.fuzzy_entries_indexed = len(docs)

    @index_execution(IndexingStage.DOMAIN_INDEXING, "Domain")
    async def _index_domain(
        self,
        result: IndexingResult,
        repo_id: str,
        snapshot_id: str,
        chunk_ids: list[str],
    ) -> None:
        """Index domain-related documents (README, docs, etc.)."""
        from src.contexts.multi_index.infrastructure.common.documents import IndexDocument

        chunks = await self._load_chunks_by_ids(chunk_ids)

        domain_extensions = {".md", ".rst", ".txt", ".adoc"}
        domain_patterns = {"readme", "changelog", "license", "contributing", "docs/", "doc/"}

        docs = []
        for chunk in chunks:
            file_path = getattr(chunk, "file_path", "") or ""
            file_lower = file_path.lower()

            is_domain = any(ext in file_lower for ext in domain_extensions) or any(
                pattern in file_lower for pattern in domain_patterns
            )

            if is_domain:
                chunk_id = getattr(chunk, "chunk_id", "") or ""
                doc = IndexDocument(
                    id=chunk_id,
                    chunk_id=chunk_id,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    file_path=file_path,
                    language=detect_language(file_path),
                    symbol_id=getattr(chunk, "fqn", "") or "",
                    content=getattr(chunk, "content", "") or "",
                    tags={"kind": str(getattr(chunk, "kind", "unknown"))},
                )
                docs.append(doc)

        if docs:
            await self.domain_index.index(repo_id, snapshot_id, docs)
        result.domain_docs_indexed = len(docs)

    async def _delete_chunks_from_indexes(
        self,
        repo_id: str,
        snapshot_id: str,
        chunk_ids: list[str],
        result: IndexingResult,
    ) -> None:
        """Delete chunks from all indexes (incremental cleanup)."""
        if not chunk_ids:
            return

        logger.info("deleting_chunks_from_indexes", count=len(chunk_ids))

        # Delete from vector index
        if self.config.enable_vector_index and self.vector_index:
            try:
                await self.vector_index.delete(repo_id, snapshot_id, chunk_ids)
                logger.info("vector_index_chunks_deleted", count=len(chunk_ids))
            except Exception as e:
                logger.warning(f"Failed to delete from vector index: {e}")
                result.add_warning(f"Vector index cleanup failed: {e}")

        # Delete from lexical index
        if self.config.enable_lexical_index and self.lexical_index:
            if hasattr(self.lexical_index, "delete"):
                try:
                    await self.lexical_index.delete(repo_id, snapshot_id, chunk_ids)
                    logger.info("lexical_index_chunks_deleted", count=len(chunk_ids))
                except Exception as e:
                    logger.warning(f"Failed to delete from lexical index: {e}")
                    result.add_warning(f"Lexical index cleanup failed: {e}")

        record_counter("chunks_deleted_from_indexes_total", value=len(chunk_ids))

    async def _load_chunks_by_ids(self, chunk_ids: list[str], batch_size: int = 100) -> list[Any]:
        """Load chunks from store by IDs."""
        if not chunk_ids:
            return []

        all_chunks = []
        for i in range(0, len(chunk_ids), batch_size):
            batch_ids = chunk_ids[i : i + batch_size]
            batch_result = await self.chunk_store.get_chunks_batch(batch_ids)

            for chunk_id in batch_ids:
                if chunk_id in batch_result:
                    all_chunks.append(batch_result[chunk_id])

        return all_chunks

    def _chunks_to_index_docs(
        self,
        chunks: list[Any],
        repo_id: str,
        snapshot_id: str,
        repomap_snapshot: Any | None = None,
    ) -> list[Any]:
        """Convert chunks to index documents with RepoMap metadata."""
        from src.contexts.multi_index.infrastructure.common.documents import IndexDocument

        # Build chunk_id to RepoMapNode mapping
        chunk_to_node: dict[str, Any] = {}
        if repomap_snapshot:
            nodes = getattr(repomap_snapshot, "nodes", None)
            if nodes is None and isinstance(repomap_snapshot, dict):
                nodes = repomap_snapshot.get("nodes", [])
            if nodes:
                for node in nodes:
                    node_chunk_id = getattr(node, "chunk_id", None)
                    if node_chunk_id:
                        chunk_to_node[node_chunk_id] = node

        # File content cache for efficient I/O
        file_cache: dict[str, list[str]] = {}

        docs = []
        for chunk in chunks:
            chunk_id = getattr(chunk, "chunk_id", "") or ""
            file_path = getattr(chunk, "file_path", "") or ""

            # Extract content
            content = self._extract_chunk_content_cached(chunk, file_cache)

            # Get RepoMap metadata
            repomap_node = chunk_to_node.get(chunk_id)
            pagerank = getattr(repomap_node, "pagerank", 0.0) if repomap_node else 0.0
            summary = getattr(repomap_node, "summary", "") if repomap_node else ""

            doc = IndexDocument(
                id=chunk_id,
                chunk_id=chunk_id,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                file_path=file_path,
                language=detect_language(file_path),
                symbol_id=getattr(chunk, "fqn", "") or "",
                content=content,
                pagerank_score=pagerank,
                summary=summary,
                tags={"kind": str(getattr(chunk, "kind", "unknown"))},
            )
            docs.append(doc)

        return docs

    def _extract_chunk_content_cached(self, chunk: Any, file_cache: dict[str, list[str]]) -> str:
        """Extract chunk content with file caching."""
        file_path = getattr(chunk, "file_path", None)
        start_line = getattr(chunk, "start_line", None)
        end_line = getattr(chunk, "end_line", None)

        if not file_path or start_line is None or end_line is None:
            return getattr(chunk, "content", "") or ""

        # Load file if not cached
        if file_path not in file_cache:
            try:
                with open(file_path, encoding="utf-8") as f:
                    file_cache[file_path] = f.readlines()
            except Exception:
                return getattr(chunk, "content", "") or ""

        lines = file_cache[file_path]
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)

        return "".join(lines[start_idx:end_idx])
