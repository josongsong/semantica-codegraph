"""
Document Indexing Service

Orchestrates document parsing, chunking, and index preparation.

Hexagonal Architecture:
- Uses IndexDocument from multi_index (optional dependency)
- Graceful degradation if multi_index not available
"""

from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from codegraph_engine.code_foundation.infrastructure.document.chunker import DocumentChunk, DocumentChunker
from codegraph_engine.code_foundation.infrastructure.document.index_adapter import DocumentIndexAdapter
from codegraph_engine.code_foundation.infrastructure.document.parser import get_document_parser_registry
from codegraph_engine.code_foundation.infrastructure.document.profile import DocIndexConfig, DocIndexProfile

# Hexagonal: Optional import for multi_index (graceful degradation)
try:
    from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument

    _INDEX_AVAILABLE = True
except ImportError:
    IndexDocument = None  # type: ignore
    _INDEX_AVAILABLE = False

if TYPE_CHECKING:
    from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument


class DocumentStats(TypedDict):
    total_files: int
    by_format: dict[str, int]
    total_chunks: int
    code_blocks: int


class DocumentIndexingService:
    """
    Service for processing documents into indexed chunks.

    Pipeline:
    1. Parse document files (Markdown, RST, Text, etc.)
    2. Chunk documents based on profile
    3. Convert to IndexDocument format
    """

    def __init__(self, config: DocIndexConfig, repo_id: str, snapshot_id: str):
        """
        Initialize document indexing service.

        Args:
            config: Document indexing configuration
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
        """
        self.config = config
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id

        # Initialize components
        self.parser_registry = get_document_parser_registry()
        self.chunker = DocumentChunker(config)
        self.adapter = DocumentIndexAdapter(repo_id, snapshot_id)

    def process_document_file(self, file_path: Path) -> list[IndexDocument]:
        """
        Process a single document file.

        Args:
            file_path: Path to document file

        Returns:
            List of IndexDocuments ready for indexing
        """
        # Check if profile allows document indexing
        if self.config.profile == DocIndexProfile.OFF:
            return []

        # Parse document
        parsed_doc = self.parser_registry.parse_file(file_path)
        if not parsed_doc:
            return []

        # Chunk document
        doc_chunks = self.chunker.chunk(parsed_doc)

        # Convert to IndexDocuments
        index_docs = self.adapter.to_index_documents_batch(doc_chunks)

        return index_docs

    def process_documents_batch(self, file_paths: list[Path]) -> tuple[list[IndexDocument], dict[str, str]]:
        """
        Process multiple document files.

        Args:
            file_paths: List of document file paths

        Returns:
            Tuple of (index_documents, errors)
            - index_documents: List of all IndexDocuments
            - errors: Dict mapping file_path to error message
        """
        all_index_docs: list[IndexDocument] = []
        errors: dict[str, str] = {}

        for file_path in file_paths:
            try:
                index_docs = self.process_document_file(file_path)
                all_index_docs.extend(index_docs)
            except Exception as e:
                errors[str(file_path)] = str(e)

        return all_index_docs, errors

    def parse_and_chunk(self, file_path: Path) -> list[DocumentChunk]:
        """
        Parse and chunk a document (without index conversion).

        Useful for testing or intermediate processing.

        Args:
            file_path: Path to document file

        Returns:
            List of DocumentChunks
        """
        # Parse
        parsed_doc = self.parser_registry.parse_file(file_path)
        if not parsed_doc:
            return []

        # Chunk
        doc_chunks = self.chunker.chunk(parsed_doc)
        return doc_chunks

    def get_document_stats(self, file_paths: list[Path]) -> dict[str, int | dict[str, int]]:
        """
        Get statistics about documents to be processed.

        Args:
            file_paths: List of document file paths

        Returns:
            Statistics dictionary
        """
        stats: DocumentStats = {
            "total_files": len(file_paths),
            "by_format": {},
            "total_chunks": 0,
            "code_blocks": 0,
        }

        by_format: dict[str, int] = {}

        for file_path in file_paths:
            # Count by format
            ext = file_path.suffix.lower()
            by_format[ext] = by_format.get(ext, 0) + 1

            # Count chunks (sample processing)
            try:
                chunks = self.parse_and_chunk(file_path)
                stats["total_chunks"] += len(chunks)
                stats["code_blocks"] += sum(1 for c in chunks if c.is_code_block())
            except Exception:
                pass

        stats["by_format"] = by_format

        return stats


def create_document_indexing_service(
    repo_id: str,
    snapshot_id: str,
    profile: DocIndexProfile = DocIndexProfile.ADVANCED,
) -> DocumentIndexingService:
    """
    Factory function to create DocumentIndexingService.

    Args:
        repo_id: Repository identifier
        snapshot_id: Snapshot identifier
        profile: Document indexing profile

    Returns:
        Configured DocumentIndexingService
    """
    config = DocIndexConfig(profile=profile)
    return DocumentIndexingService(config, repo_id, snapshot_id)
