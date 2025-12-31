"""Code Foundation Infrastructure"""

from ..adapters.foundation_adapters import (
    FoundationChunkerAdapter,
    FoundationGraphBuilderAdapter,
    FoundationIRGeneratorAdapter,
    FoundationParserAdapter,
)

# Fake implementations moved to tests/fakes/code_foundation/
# Only import them if explicitly needed

__all__ = [
    # "FakeChunker",  # Moved to tests/fakes/
    # "FakeGraphBuilder",  # Moved to tests/fakes/
    # "FakeIRGenerator",  # Moved to tests/fakes/
    # "FakeParser",  # Moved to tests/fakes/
    "FoundationChunkerAdapter",
    "FoundationGraphBuilderAdapter",
    "FoundationIRGeneratorAdapter",
    "FoundationParserAdapter",
]
