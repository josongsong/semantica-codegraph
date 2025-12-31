"""
Memory Persistence Layer

Provides storage abstractions for memory systems:
- MemoryStore: Abstract interface for key-value storage
- InMemoryStore: Development/testing storage
- FileStore: File-based JSON storage
- PostgresMemoryStore: Production PostgreSQL storage with graph memory
- EmbeddingMemoryStore: Qdrant-based semantic search
"""

from .embedding_store import EmbeddingMemoryStore, EmbeddingProvider
from .postgres_store import PostgresMemoryStore
from .store import FileStore, InMemoryStore, MemoryStore, create_store

__all__ = [
    # Abstract interface
    "MemoryStore",
    # Simple stores
    "InMemoryStore",
    "FileStore",
    "create_store",
    # Production stores
    "PostgresMemoryStore",
    "EmbeddingMemoryStore",
    "EmbeddingProvider",
]
