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
from .parser_port import ParserPort, ParsedFileInput, ParserResult, CodeNode, ParserDiagnostic
from .name_resolution_port import NameResolutionPort, ReferenceEdge, NameResolutionInput
from .language_service_port import LanguageServicePort, Location, DefinitionResult, ReferencesResult
from .framework_tagger_port import FrameworkTaggerPort, FrameworkType, FrameworkPattern, TaggedCodeNode

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
