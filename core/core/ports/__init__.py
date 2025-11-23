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

from .framework_tagger_port import (
    FrameworkPattern,
    FrameworkTaggerPort,
    FrameworkType,
    TaggedCodeNode,
)
from .git_provider import GitProviderPort
from .graph_store import GraphStorePort
from .language_service_port import DefinitionResult, LanguageServicePort, Location, ReferencesResult
from .lexical_search_port import LexicalSearchPort
from .llm_provider import LLMProviderPort
from .name_resolution_port import NameResolutionInput, NameResolutionPort, ReferenceEdge
from .parser_port import CodeNode, ParsedFileInput, ParserDiagnostic, ParserPort, ParserResult
from .relational_store import RelationalStorePort
from .vector_store import VectorStorePort

__all__ = [
    # Storage ports
    "VectorStorePort",
    "GraphStorePort",
    "RelationalStorePort",
    # Service ports
    "GitProviderPort",
    "LLMProviderPort",
    "LexicalSearchPort",
    # Parser ports (v2 extension)
    "ParserPort",
    "ParsedFileInput",
    "ParserResult",
    "CodeNode",
    "ParserDiagnostic",
    # Advanced analysis ports (v2 extension)
    "NameResolutionPort",
    "ReferenceEdge",
    "NameResolutionInput",
    "LanguageServicePort",
    "Location",
    "DefinitionResult",
    "ReferencesResult",
    "FrameworkTaggerPort",
    "FrameworkType",
    "FrameworkPattern",
    "TaggedCodeNode",
]
