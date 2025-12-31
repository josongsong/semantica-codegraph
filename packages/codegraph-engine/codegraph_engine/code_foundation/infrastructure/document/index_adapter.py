"""
Document to Index Adapter

Converts DocumentChunk to IndexDocument and Chunk formats for indexing.

Hexagonal Architecture:
- Uses IndexDocument from multi_index (optional dependency)
- Graceful degradation if multi_index not available
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from codegraph_engine.code_foundation.infrastructure.chunk.models import Chunk
from codegraph_engine.code_foundation.infrastructure.document.chunker import DocumentChunk

# Hexagonal: Optional import for multi_index (graceful degradation)
try:
    from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument

    _INDEX_AVAILABLE = True
except ImportError:
    IndexDocument = None  # type: ignore
    _INDEX_AVAILABLE = False

if TYPE_CHECKING:
    from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument

# Translation table for safe file path conversion (more efficient than chained replace())
_PATH_SAFE_TRANS = str.maketrans({"/": "_", ".": "_", "\\": "_"})


class DocumentIndexAdapter:
    """
    Adapter to convert DocumentChunk to index-compatible formats.

    Converts:
    - DocumentChunk → IndexDocument (for Vector/Domain indexes)
    - DocumentChunk → Chunk (for chunk store)
    """

    def __init__(self, repo_id: str, snapshot_id: str):
        """
        Initialize adapter.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
        """
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id

    def to_index_document(self, doc_chunk: DocumentChunk) -> "IndexDocument | None":
        """
        Convert DocumentChunk to IndexDocument.

        Args:
            doc_chunk: Document chunk

        Returns:
            IndexDocument for vector/domain indexing, or None if multi_index unavailable
        """
        # Hexagonal: Check if multi_index is available
        if not _INDEX_AVAILABLE or IndexDocument is None:
            return None

        # Generate chunk ID
        chunk_id = self._generate_chunk_id(doc_chunk)

        # Build search content
        content = self._build_search_content(doc_chunk)

        # Extract identifiers (code symbols mentioned in doc)
        identifiers = self._extract_identifiers(doc_chunk)

        # Build tags
        tags = self._build_tags(doc_chunk)

        # Determine language (document format)
        language = self._get_document_language(doc_chunk)

        return IndexDocument(
            id=chunk_id,
            chunk_id=chunk_id,
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
            file_path=doc_chunk.file_path,
            language=language,
            symbol_id=None,  # Documents don't have symbols
            symbol_name=None,
            content=content,
            identifiers=identifiers,
            tags=tags,
            start_line=doc_chunk.line_start,
            end_line=doc_chunk.line_end,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_chunk(self, doc_chunk: DocumentChunk, chunk_id: str | None = None) -> Chunk:
        """
        Convert DocumentChunk to Chunk.

        Args:
            doc_chunk: Document chunk
            chunk_id: Optional chunk ID (generated if not provided)

        Returns:
            Chunk for chunk store
        """
        if chunk_id is None:
            chunk_id = self._generate_chunk_id(doc_chunk)

        # Build FQN (fully qualified name)
        fqn = self._build_fqn(doc_chunk)

        return Chunk(
            chunk_id=chunk_id,
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
            project_id=None,
            module_path=None,
            file_path=doc_chunk.file_path,
            kind="document",
            fqn=fqn,
            start_line=doc_chunk.line_start,
            end_line=doc_chunk.line_end,
            original_start_line=doc_chunk.line_start,
            original_end_line=doc_chunk.line_end,
            content_hash=None,
            parent_id=None,
            children=[],
            language=self._get_document_language(doc_chunk),
            symbol_visibility="public",  # Documents are public
            symbol_id=None,
            symbol_owner_id=None,
            summary=self._extract_summary(doc_chunk),
            importance=None,
            attrs={
                "chunk_type": doc_chunk.chunk_type,
                "heading_context": doc_chunk.heading_context,
                "code_language": doc_chunk.code_language,
                "is_code_block": doc_chunk.is_code_block(),
            },
            version=1,
            last_indexed_commit=self.snapshot_id,
            is_deleted=False,
        )

    def to_index_documents_batch(self, doc_chunks: list[DocumentChunk]) -> list[IndexDocument]:
        """
        Convert multiple DocumentChunks to IndexDocuments.

        Args:
            doc_chunks: List of document chunks

        Returns:
            List of IndexDocuments
        """
        return [self.to_index_document(chunk) for chunk in doc_chunks]

    def to_chunks_batch(self, doc_chunks: list[DocumentChunk]) -> list[Chunk]:
        """
        Convert multiple DocumentChunks to Chunks.

        Args:
            doc_chunks: List of document chunks

        Returns:
            List of Chunks
        """
        return [self.to_chunk(chunk) for chunk in doc_chunks]

    def _generate_chunk_id(self, doc_chunk: DocumentChunk) -> str:
        """
        Generate unique chunk ID for document chunk.

        Format: doc:{repo_id}:{file_path}:{line_start}-{line_end}
        """
        file_path_safe = doc_chunk.file_path.translate(_PATH_SAFE_TRANS)
        return f"doc:{self.repo_id}:{file_path_safe}:{doc_chunk.line_start}-{doc_chunk.line_end}"

    def _build_search_content(self, doc_chunk: DocumentChunk) -> str:
        """
        Build search-optimized content.

        Format:
        [HEADING] {heading_context}
        [CONTENT] {actual content}
        [META] file={file_path} type={chunk_type}
        """
        parts: list[str] = []

        # 1) Heading context (for navigation)
        if doc_chunk.heading_context:
            heading_path = " > ".join(doc_chunk.heading_context)
            parts.append(f"[HEADING] {heading_path}")

        # 2) Content
        if doc_chunk.is_code_block():
            parts.append(f"[CODE]\n{doc_chunk.content}")
        else:
            parts.append(f"[CONTENT] {doc_chunk.content}")

        # 3) Meta
        meta_parts = [
            f"file={doc_chunk.file_path}",
            f"type={doc_chunk.chunk_type}",
        ]
        if doc_chunk.code_language:
            meta_parts.append(f"lang={doc_chunk.code_language}")

        parts.append(f"[META] {' '.join(meta_parts)}")

        return "\n\n".join(parts)

    def _extract_identifiers(self, doc_chunk: DocumentChunk) -> list[str]:
        """
        Extract identifiers from document chunk.

        For code blocks, extract potential symbol names.
        For text, extract capitalized words that might be class/function names.
        """
        identifiers: set[str] = set()

        # Add file name as identifier
        if doc_chunk.file_path:
            file_name = doc_chunk.file_path.split("/")[-1]
            identifiers.add(file_name.replace(".md", "").replace("_", " "))

        # Add heading context as identifiers
        if doc_chunk.heading_context:
            for heading in doc_chunk.heading_context:
                # Split camelCase and PascalCase
                words = heading.replace("-", " ").replace("_", " ").split()
                identifiers.update(w.lower() for w in words if len(w) > 2)

        # For code blocks, try to extract function/class names
        if doc_chunk.is_code_block() and doc_chunk.content:
            import re

            # Match function/class definitions
            patterns = [
                r"\bdef\s+(\w+)",  # Python functions
                r"\bclass\s+(\w+)",  # Classes
                r"\bfunction\s+(\w+)",  # JS functions
                r"\b(\w+)\s*=\s*function",  # JS function expressions
                r"\bconst\s+(\w+)\s*=",  # JS/TS const
            ]

            for pattern in patterns:
                matches = re.findall(pattern, doc_chunk.content)
                identifiers.update(m.lower() for m in matches)

        return sorted(identifiers)

    def _build_tags(self, doc_chunk: DocumentChunk) -> dict[str, str]:
        """
        Build tags for filtering/ranking.

        Tags:
        - kind: document
        - doc_type: markdown/text/etc
        - chunk_type: section/code_block/etc
        - is_code: true/false
        - language: python/typescript/etc (for code blocks)
        """
        tags: dict[str, str] = {
            "kind": "document",
            "chunk_type": doc_chunk.chunk_type,
            "is_code": "true" if doc_chunk.is_code_block() else "false",
        }

        # Document language (Markdown, RST, etc.)
        tags["doc_format"] = self._get_document_language(doc_chunk)

        # Code language (for code blocks)
        if doc_chunk.code_language:
            tags["code_language"] = doc_chunk.code_language

        # Heading depth
        if doc_chunk.heading_context:
            tags["heading_depth"] = str(len(doc_chunk.heading_context))

        return tags

    def _get_document_language(self, doc_chunk: DocumentChunk) -> str:
        """
        Determine document language/format from file extension.

        Returns:
            Document format (markdown, rst, text, etc.)
        """
        if not doc_chunk.file_path:
            return "text"

        ext = doc_chunk.file_path.split(".")[-1].lower()
        ext_map = {
            "md": "markdown",
            "mdx": "markdown",
            "markdown": "markdown",
            "rst": "rst",
            "rest": "rst",
            "txt": "text",
            "text": "text",
            "adoc": "asciidoc",
            "asciidoc": "asciidoc",
        }

        return ext_map.get(ext, "text")

    def _build_fqn(self, doc_chunk: DocumentChunk) -> str:
        """
        Build fully qualified name for document chunk.

        Format: {file_path}#{heading_path}
        Example: README.md#Installation > Quick Start
        """
        if doc_chunk.heading_context:
            heading_path = " > ".join(doc_chunk.heading_context)
            return f"{doc_chunk.file_path}#{heading_path}"
        return doc_chunk.file_path

    def _extract_summary(self, doc_chunk: DocumentChunk) -> str | None:
        """
        Extract summary from document chunk.

        Takes first 100 chars as summary.
        """
        if not doc_chunk.content:
            return None

        # Clean content
        content = doc_chunk.content.strip()

        # Limit length
        max_length = 100
        if len(content) <= max_length:
            return content

        return content[:max_length] + "..."
