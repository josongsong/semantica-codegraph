"""
Document Parsers

Extended parsers for specialized document formats.
"""

__all__ = []

try:
    from src.contexts.code_foundation.infrastructure.document.parsers.notebook_parser import NotebookParser

    __all__.append("NotebookParser")
except ImportError:
    pass

try:
    from src.contexts.code_foundation.infrastructure.document.parsers.pdf_parser import PDFParser

    __all__.append("PDFParser")
except ImportError:
    pass
