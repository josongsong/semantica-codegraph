"""
Port Interfaces (Hexagonal Architecture)

This package defines abstract interfaces (ports) that the core business logic
uses to interact with external systems. Concrete implementations (adapters)
are provided in the infra layer.

Following the Dependency Inversion Principle:
- Core depends on these abstract interfaces
- Infrastructure implements these interfaces
- This allows core to remain independent of external dependencies
"""

from .vector_store import VectorStorePort
from .graph_store import GraphStorePort
from .relational_store import RelationalStorePort
from .git_provider import GitProviderPort
from .llm_provider import LLMProviderPort
from .lexical_search_port import LexicalSearchPort

__all__ = [
    "VectorStorePort",
    "GraphStorePort",
    "RelationalStorePort",
    "GitProviderPort",
    "LLMProviderPort",
    "LexicalSearchPort",
]
