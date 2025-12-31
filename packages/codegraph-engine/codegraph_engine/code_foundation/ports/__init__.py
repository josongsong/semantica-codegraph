"""
Code Foundation Ports

Hexagonal Architecture port definitions.
Re-exports from domain/ports for standard hexagonal structure.

Usage:
    from codegraph_engine.code_foundation.ports import ParserPort, ChunkerPort
"""

from codegraph_engine.code_foundation.domain.ports import (
    ChunkerPort,
    ChunkStorePort,
    GraphBuilderPort,
    IRDocumentPort,
    IRGeneratorPort,
    IRNodePort,
    ParserPort,
)

__all__ = [
    "ChunkerPort",
    "ChunkStorePort",
    "GraphBuilderPort",
    "IRDocumentPort",
    "IRGeneratorPort",
    "IRNodePort",
    "ParserPort",
]
