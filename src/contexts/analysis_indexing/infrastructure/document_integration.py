"""
Document Integration for IndexingOrchestrator

Helper functions to integrate document indexing into existing orchestrator.
"""

from pathlib import Path

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.document import DocIndexConfig, DocIndexProfile
from src.contexts.code_foundation.infrastructure.document.service import DocumentIndexingService
from src.contexts.multi_index.infrastructure.common.documents import IndexDocument

logger = get_logger(__name__)


class DocumentIntegrationHelper:
    """
    Helper class to integrate document indexing into orchestrator.

    This provides a minimal integration point without modifying core orchestrator logic.
    """

    def __init__(
        self,
        repo_id: str,
        snapshot_id: str,
        profile: DocIndexProfile = DocIndexProfile.ADVANCED,
    ):
        """
        Initialize helper.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            profile: Document indexing profile
        """
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.profile = profile

        # Create document indexing service
        config = DocIndexConfig(profile=profile)
        self.service = DocumentIndexingService(config, repo_id, snapshot_id)

    def process_documents(self, files: list[Path]) -> tuple[list[IndexDocument], dict[str, str]]:
        """
        Process document files into IndexDocuments.

        Args:
            files: List of all discovered files

        Returns:
            Tuple of (index_documents, errors)
        """
        # Filter document files
        doc_files = [f for f in files if self._is_document(f)]

        if not doc_files:
            logger.info("No document files found")
            return [], {}

        logger.info(f"📄 Processing {len(doc_files)} document files")

        # Process documents
        index_docs, errors = self.service.process_documents_batch(doc_files)

        logger.info(f"✅ Processed documents: {len(index_docs)} chunks from {len(doc_files)} files")

        if errors:
            logger.warning(f"⚠️  Document processing errors: {len(errors)}")

        return index_docs, errors

    def _is_document(self, file_path: Path) -> bool:
        """Check if file is a document."""
        ext = file_path.suffix.lower()
        supported = self.service.config.get_supported_extensions()
        return ext in supported

    def get_stats(self) -> dict:
        """Get integration stats."""
        return {
            "profile": self.profile.value,
            "repo_id": self.repo_id,
            "snapshot_id": self.snapshot_id,
        }


def integrate_documents_into_orchestrator(
    orchestrator,
    repo_id: str,
    snapshot_id: str,
    files: list[Path],
    profile: DocIndexProfile = DocIndexProfile.ADVANCED,
) -> tuple[list[IndexDocument], dict]:
    """
    Integrate document indexing into orchestrator pipeline.

    This is a helper function that can be called from orchestrator.index_repository()
    after file discovery stage.

    Args:
        orchestrator: IndexingOrchestrator instance
        repo_id: Repository ID
        snapshot_id: Snapshot ID
        files: All discovered files
        profile: Document indexing profile

    Returns:
        Tuple of (document_index_docs, stats)
    """
    helper = DocumentIntegrationHelper(repo_id, snapshot_id, profile)

    # Process documents
    index_docs, errors = helper.process_documents(files)

    # Build stats
    stats = {
        "document_files_found": len([f for f in files if helper._is_document(f)]),
        "document_chunks_created": len(index_docs),
        "document_errors": len(errors),
        "errors": errors,
    }

    return index_docs, stats
