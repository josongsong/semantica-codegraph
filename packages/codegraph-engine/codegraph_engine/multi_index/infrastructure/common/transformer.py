"""
Chunk → IndexDocument Transformer

Converts Chunk layer output to IndexDocument with:
- RepoMap importance scores
- Identifier extraction from IR
- Parent-child hierarchy information
- Search-optimized content formatting
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.chunk.models import Chunk
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument
from codegraph_engine.repo_structure.infrastructure.models import RepoMapSnapshot

logger = get_logger(__name__)


@dataclass
class TransformError:
    """Single transform error."""

    chunk_id: str
    file_path: str | None
    error: Exception
    error_message: str


@dataclass
class TransformBatchResult:
    """Result of batch transform operation."""

    documents: list[IndexDocument] = field(default_factory=list)
    errors: list[TransformError] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return len(self.documents)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def raise_if_errors(self) -> None:
        """Raise TransformBatchError if any errors occurred."""
        if self.errors:
            raise TransformBatchError(
                f"Transform batch had {len(self.errors)} errors",
                documents=self.documents,
                errors=self.errors,
            )


class TransformBatchError(Exception):
    """Exception raised when batch transform has errors (fail_fast mode)."""

    def __init__(
        self,
        message: str,
        documents: list[IndexDocument],
        errors: list[TransformError],
    ):
        super().__init__(message)
        self.documents = documents
        self.errors = errors


class IndexDocumentTransformer:
    """
    Transform Chunk to IndexDocument with enrichment.

    Enrichment sources:
    - RepoMap: importance scores, parent-child relationships
    - IR: identifiers, signatures
    - Source code: actual code content
    """

    def __init__(
        self,
        repomap_snapshot: RepoMapSnapshot | None = None,
        ir_document: IRDocument | None = None,
    ):
        """
        Initialize transformer.

        Args:
            repomap_snapshot: RepoMap snapshot for importance scores
            ir_document: IR document for identifier extraction
        """
        self.repomap_snapshot = repomap_snapshot
        self.ir_document = ir_document

        # Build lookup maps for fast access
        self._repomap_by_chunk_id: dict[str, Any] = {}
        if repomap_snapshot:
            for node in repomap_snapshot.nodes:
                if node.chunk_ids:  # None check to prevent TypeError
                    for chunk_id in node.chunk_ids:
                        self._repomap_by_chunk_id[chunk_id] = node

    def transform(
        self,
        chunk: Chunk,
        source_code: str | None = None,
        snapshot_id: str | None = None,
    ) -> IndexDocument:
        """
        Transform Chunk to IndexDocument.

        Args:
            chunk: Source chunk
            source_code: Actual source code content (optional)
            snapshot_id: Snapshot ID for index consistency

        Returns:
            Enriched IndexDocument
        """
        # Get RepoMap node for this chunk
        repomap_node = self._repomap_by_chunk_id.get(chunk.chunk_id)

        # Build content for search
        content = self._build_search_text(chunk, source_code)

        # Extract identifiers
        identifiers = self._collect_identifiers(chunk)

        # Build tags with RepoMap information
        tags = self._build_tags(chunk, repomap_node)

        return IndexDocument(
            id=chunk.chunk_id,
            chunk_id=chunk.chunk_id,
            repo_id=chunk.repo_id,
            snapshot_id=snapshot_id or chunk.last_indexed_commit or "unknown",
            file_path=chunk.file_path or "",
            language=chunk.language or "unknown",
            symbol_id=chunk.symbol_id,
            symbol_name=self._get_symbol_name(chunk),
            content=content,
            identifiers=identifiers,
            tags=tags,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def transform_batch(
        self,
        chunks: list[Chunk],
        source_codes: dict[str, str] | None = None,
        snapshot_id: str | None = None,
        fail_fast: bool = False,
    ) -> "TransformBatchResult":
        """
        Transform multiple chunks to IndexDocuments.

        Args:
            chunks: List of chunks
            source_codes: Dict mapping chunk_id to source code
            snapshot_id: Snapshot ID
            fail_fast: If True, raise on first error. If False, collect errors and continue.

        Returns:
            TransformBatchResult with documents and errors
        """
        source_codes = source_codes or {}
        documents: list[IndexDocument] = []
        errors: list[TransformError] = []

        for chunk in chunks:
            try:
                doc = self.transform(chunk, source_codes.get(chunk.chunk_id), snapshot_id)
                documents.append(doc)
            except Exception as e:
                error = TransformError(
                    chunk_id=chunk.chunk_id,
                    file_path=chunk.file_path,
                    error=e,
                    error_message=str(e),
                )
                errors.append(error)

                if fail_fast:
                    logger.error(
                        "transform_batch_fail_fast",
                        chunk_id=chunk.chunk_id,
                        file_path=chunk.file_path,
                        error=str(e),
                    )
                    raise TransformBatchError(
                        f"Transform failed for chunk {chunk.chunk_id}",
                        documents=documents,
                        errors=errors,
                    ) from e
                else:
                    logger.warning(
                        "transform_chunk_failed",
                        chunk_id=chunk.chunk_id,
                        file_path=chunk.file_path,
                        error=str(e),
                        remaining_chunks=len(chunks) - len(documents) - len(errors),
                    )

        if errors:
            logger.warning(
                "transform_batch_completed_with_errors",
                total=len(chunks),
                success=len(documents),
                failed=len(errors),
            )

        return TransformBatchResult(documents=documents, errors=errors)

    def _build_search_text(self, chunk: Chunk, source_code: str | None) -> str:
        """
        Build search-optimized content text.

        Format: [SUMMARY] + [SIGNATURE] + [CODE] + [META]
        """
        parts: list[str] = []

        # 1) SUMMARY (from Chunk or RepoMap)
        if chunk.summary:
            parts.append(f"[SUMMARY] {chunk.summary}")

        # 2) SIGNATURE (from Chunk.attrs)
        signature = chunk.attrs.get("signature", "")
        if signature:
            parts.append(f"[SIGNATURE] {signature}")

        # 3) CODE (for function/class/file)
        if chunk.kind in ("function", "class", "file") and source_code:
            # Limit code length for vector indexes
            max_code_length = 2000
            code_preview = source_code[:max_code_length]
            if len(source_code) > max_code_length:
                code_preview += "..."
            parts.append(f"[CODE]\n{code_preview}")

        # 4) META (structured metadata)
        meta_parts: list[str] = []
        if chunk.file_path:
            meta_parts.append(f"file={chunk.file_path}")
        meta_parts.append(f"symbol={chunk.fqn}")
        if chunk.module_path:
            meta_parts.append(f"module={chunk.module_path}")
        meta_parts.append(f"kind={chunk.kind}")
        if chunk.language:
            meta_parts.append(f"lang={chunk.language}")

        parts.append(f"[META] {' '.join(meta_parts)}")

        return "\n\n".join(parts)

    def _collect_identifiers(self, chunk: Chunk) -> list[str]:
        """
        Collect identifiers for search.

        Sources:
        1. Chunk.attrs["identifiers"] (pre-computed)
        2. FQN decomposition
        3. IR document (if available)
        """
        identifiers: set[str] = set()

        # 1) Pre-computed identifiers from Chunk
        if "identifiers" in chunk.attrs:
            chunk_identifiers = chunk.attrs["identifiers"]
            if isinstance(chunk_identifiers, list):
                identifiers.update(chunk_identifiers)

        # 2) FQN decomposition
        for part in chunk.fqn.split("."):
            if part:
                identifiers.add(part)

        # 3) IR document (future: extract from IR nodes)
        # if self.ir_document and chunk.symbol_id:
        #     ir_node = self._find_ir_node(chunk.symbol_id)
        #     if ir_node:
        #         identifiers.update(ir_node.identifiers)

        # Normalize: lowercase, sorted, non-empty
        return sorted({name.lower() for name in identifiers if name})

    def _build_tags(self, chunk: Chunk, repomap_node: Any | None) -> dict[str, str]:
        """
        Build metadata tags for filtering/ranking.

        Tags include:
        - Basic: kind, module, language, visibility
        - RepoMap: repomap_score, is_entrypoint, is_test
        - Hierarchy: parent_chunk_id
        """
        tags: dict[str, str] = {
            "kind": chunk.kind,
        }

        # Basic metadata
        if chunk.module_path:
            tags["module"] = chunk.module_path
        if chunk.language:
            tags["language"] = chunk.language
        if chunk.symbol_visibility:
            tags["visibility"] = chunk.symbol_visibility

        # Hierarchy
        if chunk.parent_id:
            tags["parent_chunk_id"] = chunk.parent_id

        # RepoMap information
        if repomap_node:
            # Importance score (0.0 - 1.0)
            tags["repomap_score"] = str(round(repomap_node.metrics.importance, 3))

            # PageRank score
            if repomap_node.metrics.pagerank > 0:
                tags["pagerank_score"] = str(round(repomap_node.metrics.pagerank, 4))

            # Entrypoint flag
            if repomap_node.is_entrypoint:
                tags["is_entrypoint"] = "true"

            # Test flag
            if repomap_node.is_test:
                tags["is_test"] = "true"

            # LOC
            if repomap_node.metrics.loc > 0:
                tags["loc"] = str(repomap_node.metrics.loc)

        return tags

    def _get_symbol_name(self, chunk: Chunk) -> str | None:
        """Extract symbol name from FQN."""
        if chunk.fqn:
            return chunk.fqn.split(".")[-1]
        return None
