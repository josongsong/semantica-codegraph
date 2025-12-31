"""
Test Fakes Module

Provides fake/stub implementations for testing.
These are minimal implementations that satisfy interfaces without real dependencies.
"""

from tests.fakes.fake_chunk_store import FakeChunkStore
from tests.fakes.fake_llm import FakeLLM

__all__ = [
    "FakeLLM",
    "FakeChunkStore",
]
