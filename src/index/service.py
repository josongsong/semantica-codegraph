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
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.foundation.chunk.models import Chunk
from src.foundation.graph.models import GraphDocument
from src.index.common.documents import IndexDocument, SearchHit
from src.index.common.transformer import IndexDocumentTransformer
from src.repomap.models import RepoMapSnapshot

if TYPE_CHECKING:
    from src.ports import (
        DomainMetaIndexPort,
        FuzzyIndexPort,
        LexicalIndexPort,
        RuntimeIndexPort,
        SymbolIndexPort,
        VectorIndexPort,
    )

logger = logging.getLogger(__name__)


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
                f"Search fused {len(all_hits)} hits from {sources_count} sources " f"into {len(fused_hits)} results"
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
            hits: All search hits from different sources
            weights: Weights per source

        Returns:
            Fused and sorted hits
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
