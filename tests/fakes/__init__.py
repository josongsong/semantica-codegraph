"""
Fake Implementations for Unit Testing

모든 Ports의 Fake 구현을 제공.
외부 IO 없이 behavior-driven mocking.

Available Fakes:
- FakeVectorStore: VectorStorePort 구현
- FakeGraphStore: GraphStorePort 구현
- FakeRelationalStore: RelationalStorePort 구현
- FakeLexicalSearch: LexicalSearchPort 구현
- FakeGitProvider: GitProviderPort 구현
- FakeLLMProvider: LLMProviderPort 구현
"""

from .fake_git import FakeGitProvider
from .fake_graph import FakeGraphStore
from .fake_lexical import FakeLexicalSearch
from .fake_llm import FakeLLMProvider
from .fake_relational import FakeRelationalStore
from .fake_vector import FakeVectorStore
from .fake_vector_index import FakeVectorIndex

__all__ = [
    "FakeVectorStore",
    "FakeVectorIndex",
    "FakeGraphStore",
    "FakeRelationalStore",
    "FakeLexicalSearch",
    "FakeGitProvider",
    "FakeLLMProvider",
]
