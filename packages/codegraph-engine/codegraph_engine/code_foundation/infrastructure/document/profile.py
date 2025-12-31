"""
Document Indexing Profile Configuration

Defines document indexing levels and configuration based on ADR-0XY.
"""

from dataclasses import dataclass, field
from enum import Enum


class DocIndexProfile(str, Enum):
    """
    Document indexing profile levels.

    Each level defines what document formats are processed and how deeply
    they are analyzed and integrated with code.
    """

    OFF = "OFF"  # No document indexing
    BASIC = "BASIC"  # Markdown/Text only, simple chunking
    ADVANCED = "ADVANCED"  # + Notebook, code-doc linking, domain index
    SOTA = "SOTA"  # + PDF/OCR, drift detection, full features


@dataclass
class DocIndexConfig:
    """
    Configuration for document indexing.

    Attributes:
        profile: Indexing profile level
        include_patterns: File patterns to include
        exclude_patterns: File patterns to exclude
        max_pdf_size_mb: Maximum PDF file size to process
        enable_pdf_ocr: Enable OCR for scanned PDFs
        max_doc_tokens_per_chunk: Maximum tokens per document chunk
        enable_drift_detection: Enable document-code drift detection (SOTA only)
        enable_quality_scoring: Enable document quality scoring (SOTA only)
    """

    profile: DocIndexProfile = DocIndexProfile.ADVANCED

    # File patterns
    include_patterns: list[str] = field(
        default_factory=lambda: [
            "README.md",
            "docs/**",
            "design/**",
            "**/*.md",
            "**/*.mdx",
            "**/*.txt",
            "**/*.rst",
        ]
    )
    exclude_patterns: list[str] = field(
        default_factory=lambda: [
            "**/node_modules/**",
            "**/__pycache__/**",
            ".git/**",
            "build/**",
            "dist/**",
            ".next/**",
            ".cache/**",
        ]
    )

    # Format-specific limits
    max_pdf_size_mb: int = 50
    enable_pdf_ocr: bool = False  # Only enabled in SOTA profile
    max_doc_tokens_per_chunk: int = 1024

    # Advanced features (SOTA profile)
    enable_drift_detection: bool = False
    enable_quality_scoring: bool = False

    def get_supported_extensions(self) -> list[str]:
        """
        Get list of supported file extensions based on profile.

        Returns:
            List of file extensions (e.g., ['.md', '.txt'])
        """
        if self.profile == DocIndexProfile.OFF:
            return []

        if self.profile == DocIndexProfile.BASIC:
            return [".md", ".mdx", ".txt", ".rst"]

        if self.profile == DocIndexProfile.ADVANCED:
            return [".md", ".mdx", ".txt", ".rst", ".adoc", ".ipynb"]

        if self.profile == DocIndexProfile.SOTA:
            return [".md", ".mdx", ".txt", ".rst", ".adoc", ".ipynb", ".pdf"]

        return []

    def should_create_code_links(self) -> bool:
        """
        Check if code-document linking should be enabled.

        Returns:
            True if profile is ADVANCED or SOTA
        """
        return self.profile in [DocIndexProfile.ADVANCED, DocIndexProfile.SOTA]

    def should_index_code_blocks_separately(self) -> bool:
        """
        Check if code blocks should be indexed as separate chunks.

        Returns:
            True if profile is ADVANCED or SOTA
        """
        return self.profile in [DocIndexProfile.ADVANCED, DocIndexProfile.SOTA]

    def get_max_document_hits(self) -> int:
        """
        Get maximum number of document hits to return in retrieval.

        Returns:
            Max document hits based on profile
        """
        if self.profile == DocIndexProfile.OFF:
            return 0
        if self.profile == DocIndexProfile.BASIC:
            return 3
        if self.profile == DocIndexProfile.ADVANCED:
            return 10
        if self.profile == DocIndexProfile.SOTA:
            return 20
        return 0
