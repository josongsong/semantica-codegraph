"""Code Foundation Domain"""

from .language_detector import LanguageDetector
from .models import (
    ASTDocument,
    Chunk,
    IRDocument,
    Language,
    Reference,
    Symbol,
)

# GraphDocument, GraphEdge, GraphNode은 infrastructure에 있음
# (Hexagonal Architecture: Domain이 Infrastructure import 안 함)
from .ports import (
    ChunkerPort,
    ChunkStorePort,
    GraphBuilderPort,
    IRGeneratorPort,
    ParserPort,
)

__all__ = [
    # Utilities
    "LanguageDetector",
    # Models
    "ASTDocument",
    "Chunk",
    "IRDocument",
    "Language",
    "Reference",
    "Symbol",
    # Ports
    "ChunkerPort",
    "ChunkStorePort",
    "GraphBuilderPort",
    "IRGeneratorPort",
    "ParserPort",
]
