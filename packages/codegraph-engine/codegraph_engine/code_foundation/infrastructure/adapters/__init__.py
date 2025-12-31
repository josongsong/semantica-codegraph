"""
Infrastructure Adapters (SOTA Architecture)

Production-grade adapters organized by domain responsibility.

Structure:
- foundation/: ParserPort, IRGeneratorPort, GraphBuilderPort, ChunkerPort, ChunkStorePort
- ir/: IRNodePort, IRDocumentPort
- security/: IRProviderAdapter (legacy, for sanitizer analysis)
- converters/: Model converters

Architecture Principles:
- Hexagonal: Domain defines ports, Infrastructure implements adapters
- SOLID: Single responsibility, clear module boundaries
- DIP: Application depends on ports, not adapters

NO STUB, NO FAKE - Production-grade only.
"""

# Foundation adapters
from .foundation import (
    InMemoryChunkStoreAdapter,
    IRBasedChunkerAdapter,
    MultiLanguageIRGeneratorAdapter,
    SOTAGraphBuilderAdapter,
    TreeSitterParserAdapter,
    create_chunk_store_adapter,
    create_chunker_adapter,
    create_graph_builder_adapter,
    create_ir_generator_adapter,
    create_parser_adapter,
)

# IR adapters
from .ir import (
    IRDocumentAdapter,
    IRNodeAdapter,
    create_ir_document_adapter,
    create_ir_node_adapter,
)

# Security adapters (legacy)
from .security import IRProviderAdapter

__all__ = [
    # Foundation adapters
    "TreeSitterParserAdapter",
    "MultiLanguageIRGeneratorAdapter",
    "SOTAGraphBuilderAdapter",
    "IRBasedChunkerAdapter",
    "InMemoryChunkStoreAdapter",
    # IR adapters
    "IRNodeAdapter",
    "IRDocumentAdapter",
    # Security adapters (legacy)
    "IRProviderAdapter",
    # Factory functions - Foundation
    "create_parser_adapter",
    "create_ir_generator_adapter",
    "create_graph_builder_adapter",
    "create_chunker_adapter",
    "create_chunk_store_adapter",
    # Factory functions - IR
    "create_ir_document_adapter",
    "create_ir_node_adapter",
]
