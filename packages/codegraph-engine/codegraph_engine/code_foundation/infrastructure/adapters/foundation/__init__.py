"""
Foundation Port Adapters

Production-grade implementations for foundation_ports.py.

Exports:
- ParserPort → TreeSitterParserAdapter
- IRGeneratorPort → MultiLanguageIRGeneratorAdapter
- GraphBuilderPort → SOTAGraphBuilderAdapter
- ChunkerPort → IRBasedChunkerAdapter
- ChunkStorePort → InMemoryChunkStoreAdapter
"""

from .chunk_store_adapter import InMemoryChunkStoreAdapter, create_chunk_store_adapter
from .chunker_adapter import IRBasedChunkerAdapter, create_chunker_adapter
from .graph_builder_adapter import SOTAGraphBuilderAdapter, create_graph_builder_adapter
from .ir_generator_adapter import MultiLanguageIRGeneratorAdapter, create_ir_generator_adapter
from .parser_adapter import TreeSitterParserAdapter, create_parser_adapter

__all__ = [
    # Adapters
    "TreeSitterParserAdapter",
    "MultiLanguageIRGeneratorAdapter",
    "SOTAGraphBuilderAdapter",
    "IRBasedChunkerAdapter",
    "InMemoryChunkStoreAdapter",
    # Factory functions
    "create_parser_adapter",
    "create_ir_generator_adapter",
    "create_graph_builder_adapter",
    "create_chunker_adapter",
    "create_chunk_store_adapter",
]
