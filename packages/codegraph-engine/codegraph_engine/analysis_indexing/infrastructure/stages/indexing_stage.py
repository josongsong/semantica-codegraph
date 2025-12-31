"""
Indexing Stage - Multi-Index Indexing

Stage 9: Index to all indexes (lexical, vector, symbol, fuzzy, domain)

Hexagonal Architecture:
- Optional import of IndexDocument from multi_index
- Graceful degradation if multi_index not available
"""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

from codegraph_engine.analysis_indexing.infrastructure.models import IndexingStage
from codegraph_shared.infra.observability import get_logger, record_counter

from .base import BaseStage, StageContext
from .parsing_stage import detect_language

# Hexagonal: Optional import to break circular dependency
try:
    from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument

    _INDEX_DOC_AVAILABLE = True
except ImportError:
    IndexDocument = None  # type: ignore
    _INDEX_DOC_AVAILABLE = False

if TYPE_CHECKING:
    from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument

logger = get_logger(__name__)


class IndexingStage_(BaseStage):
    """Multi-Index Indexing Stage"""

    stage_name = IndexingStage.DOMAIN_INDEXING  # Use DOMAIN_INDEXING as overall stage

    def __init__(self, components: Any = None):
        super().__init__(components)
        self.lexical_index = getattr(components, "lexical_index", None)
        self.vector_index = getattr(components, "vector_index", None)
        self.symbol_index = getattr(components, "symbol_index", None)
        self.fuzzy_index = getattr(components, "fuzzy_index", None)
        self.domain_index = getattr(components, "domain_index", None)
        self.chunk_store = getattr(components, "chunk_store", None)
        self.config = getattr(components, "config", None)

    async def execute(self, ctx: StageContext) -> None:
        """Execute multi-index indexing stage."""
        stage_start = datetime.now()

        logger.info("indexing_started")

        # Handle deleted chunks from incremental indexing
        deleted_chunk_ids = ctx.result.metadata.get("deleted_chunk_ids", [])
        if deleted_chunk_ids:
            await self._delete_chunks_from_indexes(ctx, deleted_chunk_ids)

        # Build list of indexing tasks to run in parallel
        tasks = []
        task_names = []

        if self._is_enabled("lexical"):
            tasks.append(self._index_lexical(ctx))
            task_names.append("lexical")

        if self._is_enabled("vector"):
            tasks.append(self._index_vector(ctx))
            task_names.append("vector")

        if self._is_enabled("symbol"):
            tasks.append(self._index_symbol(ctx))
            task_names.append("symbol")

        if self._is_enabled("fuzzy"):
            tasks.append(self._index_fuzzy(ctx))
            task_names.append("fuzzy")

        if self._is_enabled("domain"):
            tasks.append(self._index_domain(ctx))
            task_names.append("domain")

        # Execute all indexing tasks in parallel
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
                    ctx.result.add_warning(f"{index_name.capitalize()} index failed: {res}")
                    record_counter("index_failures_total", labels={"index": index_name})

        logger.info(
            f"Indexed: Lexical({ctx.result.lexical_docs_indexed}), "
            f"Vector({ctx.result.vector_docs_indexed}), "
            f"Symbol({ctx.result.symbol_entries_indexed})"
        )

        self._record_duration(ctx, stage_start)

    def _is_enabled(self, index_type: str) -> bool:
        """Check if an index type is enabled."""
        if not self.config:
            return True
        return getattr(self.config, f"enable_{index_type}_index", True)

    async def _index_lexical(self, ctx: StageContext):
        """Index to lexical index."""
        if ctx.is_incremental and hasattr(self.lexical_index, "reindex_paths"):
            changed_files = ctx.result.metadata.get("changed_files", [])
            if changed_files:
                logger.info("lexical_incremental_indexing", count=len(changed_files))
                await self.lexical_index.reindex_paths(ctx.repo_id, ctx.snapshot_id, changed_files)
                ctx.result.lexical_docs_indexed = len(changed_files)
                return

        await self.lexical_index.reindex_repo(ctx.repo_id, ctx.snapshot_id)
        ctx.result.lexical_docs_indexed = len(ctx.chunk_ids)

    async def _index_vector(self, ctx: StageContext):
        """Index to vector index with RepoMap enrichment."""
        batch_size = getattr(self.config, "vector_batch_size", 100)
        total_indexed = 0
        repomap = ctx.result.metadata.get("repomap")

        for i in range(0, len(ctx.chunk_ids), batch_size):
            batch_ids = ctx.chunk_ids[i : i + batch_size]
            chunks_batch = await self._load_chunks_by_ids(batch_ids)
            docs = self._chunks_to_index_docs(chunks_batch, ctx.repo_id, ctx.snapshot_id, repomap)
            await self.vector_index.index(ctx.repo_id, ctx.snapshot_id, docs)
            total_indexed += len(docs)

        ctx.result.vector_docs_indexed = total_indexed

    async def _index_symbol(self, ctx: StageContext):
        """Index to symbol index."""
        await self.symbol_index.index_graph(ctx.repo_id, ctx.snapshot_id, ctx.graph_doc)
        ctx.result.symbol_entries_indexed = len(getattr(ctx.graph_doc, "graph_nodes", {}))

    async def _index_fuzzy(self, ctx: StageContext):
        """Index to fuzzy index."""
        if not _INDEX_DOC_AVAILABLE or IndexDocument is None:
            logger.warning("IndexDocument not available - skipping fuzzy indexing")
            return

        nodes = getattr(ctx.ir_doc, "nodes", [])
        docs = []

        for node in nodes:
            if hasattr(node, "name") and node.name:
                node_id = getattr(node, "id", "") or ""
                file_path = getattr(node, "file_path", "") or ""
                doc = IndexDocument(
                    id=node_id,
                    chunk_id=node_id,
                    repo_id=ctx.repo_id,
                    snapshot_id=ctx.snapshot_id,
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
            await self.fuzzy_index.index(ctx.repo_id, ctx.snapshot_id, docs)
        ctx.result.fuzzy_entries_indexed = len(docs)

    async def _index_domain(self, ctx: StageContext):
        """Index to domain metadata index."""
        if not _INDEX_DOC_AVAILABLE or IndexDocument is None:
            logger.warning("IndexDocument not available - skipping domain indexing")
            return

        chunks = await self._load_chunks_by_ids(ctx.chunk_ids)

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
                    repo_id=ctx.repo_id,
                    snapshot_id=ctx.snapshot_id,
                    file_path=file_path,
                    language=detect_language(file_path),
                    symbol_id=getattr(chunk, "fqn", "") or "",
                    content=getattr(chunk, "content", "") or "",
                    tags={"kind": str(getattr(chunk, "kind", "unknown"))},
                )
                docs.append(doc)

        if docs:
            await self.domain_index.index(ctx.repo_id, ctx.snapshot_id, docs)
        ctx.result.domain_docs_indexed = len(docs)

    async def _delete_chunks_from_indexes(self, ctx: StageContext, chunk_ids: list[str]):
        """Delete chunks from all indexes (incremental cleanup)."""
        if not chunk_ids:
            return

        logger.info("deleting_chunks_from_indexes", count=len(chunk_ids))

        if self._is_enabled("vector") and self.vector_index:
            try:
                await self.vector_index.delete(ctx.repo_id, ctx.snapshot_id, chunk_ids)
                logger.info("vector_index_chunks_deleted", count=len(chunk_ids))
            except Exception as e:
                logger.warning(f"Failed to delete from vector index: {e}")
                ctx.result.add_warning(f"Vector index cleanup failed: {e}")

        if self._is_enabled("lexical") and self.lexical_index:
            if hasattr(self.lexical_index, "delete"):
                try:
                    await self.lexical_index.delete(ctx.repo_id, ctx.snapshot_id, chunk_ids)
                    logger.info("lexical_index_chunks_deleted", count=len(chunk_ids))
                except Exception as e:
                    logger.warning(f"Failed to delete from lexical index: {e}")
                    ctx.result.add_warning(f"Lexical index cleanup failed: {e}")

        record_counter("chunks_deleted_from_indexes_total", value=len(chunk_ids))

    # NOTE: _load_chunks_by_ids는 BaseStage에서 상속받음

    def _chunks_to_index_docs(self, chunks, repo_id: str, snapshot_id: str, repomap=None) -> list:
        """Convert chunks to index documents with optional RepoMap enrichment."""
        if not _INDEX_DOC_AVAILABLE or IndexDocument is None:
            logger.warning("IndexDocument not available - cannot convert chunks")
            return []

        docs = []
        importance_scores = repomap.get("importance", {}) if repomap else {}
        summaries = repomap.get("summaries", {}) if repomap else {}

        for chunk in chunks:
            chunk_id = getattr(chunk, "chunk_id", "") or ""
            file_path = getattr(chunk, "file_path", "") or ""

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
                importance=importance_scores.get(chunk_id, 0.0),
                summary=summaries.get(chunk_id, ""),
            )
            docs.append(doc)

        return docs
