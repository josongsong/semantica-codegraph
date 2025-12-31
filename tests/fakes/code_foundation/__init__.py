"""
Test Fakes for Code Foundation

TEST ONLY - NOT FOR PRODUCTION
"""

from .fake_chunker import FakeChunker
from .fake_graph_builder import FakeGraphBuilder
from .fake_ir_generator import FakeIRGenerator
from .fake_parser import FakeParser

__all__ = [
    "FakeParser",
    "FakeIRGenerator",
    "FakeGraphBuilder",
    "FakeChunker",
]
