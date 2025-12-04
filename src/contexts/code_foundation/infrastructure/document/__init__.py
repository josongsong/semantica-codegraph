"""
Foundation: Document Layer

Document parsing, chunking, and indexing infrastructure.

Components:
- profile: Document indexing profile configuration
- parser: Document parsers for various formats (Markdown, PDF, Text, etc.)
- models: Document data structures
- chunker: Document-aware chunking strategies
"""

from src.contexts.code_foundation.infrastructure.document.chunker import (
    AdvancedChunkingStrategy,
    BasicChunkingStrategy,
    DocumentChunk,
    DocumentChunker,
    SOTAChunkingStrategy,
)
from src.contexts.code_foundation.infrastructure.document.code_linker import (
    CodeLink,
    CodeReference,
    DocumentCodeLinker,
)
from src.contexts.code_foundation.infrastructure.document.index_adapter import DocumentIndexAdapter
from src.contexts.code_foundation.infrastructure.document.models import (
    CodeBlock,
    DocumentSection,
    DocumentType,
    ParsedDocument,
    SectionType,
)
from src.contexts.code_foundation.infrastructure.document.parser import (
    DocumentParser,
    DocumentParserRegistry,
    MarkdownParser,
    RstParser,
    TextParser,
    get_document_parser_registry,
)
from src.contexts.code_foundation.infrastructure.document.profile import DocIndexConfig, DocIndexProfile
from src.contexts.code_foundation.infrastructure.document.scoring import (
    DocumentScore,
    DocumentScorer,
    DriftDetector,
    DriftResult,
    DriftSeverity,
)

# Optional parsers (imported lazily)
try:
    from src.contexts.code_foundation.infrastructure.document.parsers.notebook_parser import (
        NotebookParser as _NotebookParser,
    )
except ImportError:
    _NotebookParser = None

try:
    from src.contexts.code_foundation.infrastructure.document.parsers.pdf_parser import PDFParser as _PDFParser
except ImportError:
    _PDFParser = None

NotebookParser: type[DocumentParser] | None = _NotebookParser
PDFParser: type[DocumentParser] | None = _PDFParser

__all__ = [
    # Profile
    "DocIndexProfile",
    "DocIndexConfig",
    # Models
    "DocumentType",
    "SectionType",
    "CodeBlock",
    "DocumentSection",
    "ParsedDocument",
    # Parsers
    "DocumentParser",
    "MarkdownParser",
    "TextParser",
    "RstParser",
    "NotebookParser",
    "PDFParser",
    "DocumentParserRegistry",
    "get_document_parser_registry",
    # Chunker
    "DocumentChunk",
    "DocumentChunker",
    "BasicChunkingStrategy",
    "AdvancedChunkingStrategy",
    "SOTAChunkingStrategy",
    # Code Linker
    "DocumentCodeLinker",
    "CodeReference",
    "CodeLink",
    # Adapter
    "DocumentIndexAdapter",
    # Scoring
    "DocumentScorer",
    "DocumentScore",
    "DriftDetector",
    "DriftResult",
    "DriftSeverity",
]
