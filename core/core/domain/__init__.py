"""
Core Domain Models for Semantica Codegraph

This package contains pure domain models with no external dependencies.
Following Clean Architecture principles, domain models should not depend on
infrastructure or interface layers.
"""

from .graph import RelationshipType, Relationship, BaseSemanticaNode
from .context import (
    CodeRange,
    GitContext,
    SecurityLevel,
    SecurityContext,
    RuntimeStats,
    LexicalFeatures,
    SemanticFeatures,
    BehavioralTags,
    ErrorContext,
    Parameter,
)
from .nodes import (
    RepositoryNode,
    BranchNode,
    CommitNode,
    PullRequestNode,
    PullRequestState,
    TagNode,
    BranchChunkMapping,
    ProjectNode,
    ProjectType,
    ModuleNode,
    FileNode,
    FileCategory,
    SymbolNode,
    SymbolKind,
    Visibility,
)
from .chunks import CanonicalLeafChunk, VectorChunkPayload, canonical_leaf_to_vector_payload

__all__ = [
    # Graph
    "RelationshipType",
    "Relationship",
    "BaseSemanticaNode",
    # Context
    "CodeRange",
    "GitContext",
    "SecurityLevel",
    "SecurityContext",
    "RuntimeStats",
    "LexicalFeatures",
    "SemanticFeatures",
    "BehavioralTags",
    "ErrorContext",
    "Parameter",
    # Nodes
    "RepositoryNode",
    "BranchNode",
    "CommitNode",
    "PullRequestNode",
    "PullRequestState",
    "TagNode",
    "BranchChunkMapping",
    "ProjectNode",
    "ProjectType",
    "ModuleNode",
    "FileNode",
    "FileCategory",
    "SymbolNode",
    "SymbolKind",
    "Visibility",
    # Chunks
    "CanonicalLeafChunk",
    "VectorChunkPayload",
    "canonical_leaf_to_vector_payload",
]
