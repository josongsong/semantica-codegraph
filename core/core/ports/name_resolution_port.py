"""
Name Resolution Port

Interface for name resolution and symbol graph construction.
Supports pluggable backends (Stack Graphs, LSP, language-specific analyzers).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional
from enum import Enum

from pydantic import BaseModel

from ..domain.graph import RelationshipType


class ReferenceKind(str, Enum):
    """Types of symbol references."""
    DEFINITION = "definition"
    REFERENCE = "reference"
    CALL = "call"
    OVERRIDE = "override"
    IMPLEMENTATION = "implementation"


class SymbolLocation(BaseModel):
    """Location of a symbol in code."""
    file_path: str
    start_line: int
    end_line: int
    start_byte: Optional[int] = None
    end_byte: Optional[int] = None


class ReferenceEdge(BaseModel):
    """
    Edge representing a name reference/definition relationship.

    Used to build accurate symbol graphs with Stack Graphs or LSP.
    """
    source_symbol_id: str
    target_symbol_id: str
    kind: ReferenceKind
    relationship_type: RelationshipType  # Maps to graph RelationshipType

    # Location information
    source_location: SymbolLocation
    target_location: Optional[SymbolLocation] = None

    # Metadata
    confidence: float = 1.0  # Confidence score (0.0-1.0)
    context: str = ""  # Additional context


class NameResolutionInput(BaseModel):
    """Input for name resolution."""
    repo_id: str
    file_paths: List[str]
    language: str

    # Optional: Already parsed code nodes
    code_nodes: List[dict] = []

    # Optional: File dependency information
    import_graph: dict = {}


class NameResolutionResult(BaseModel):
    """Output from name resolution."""
    edges: List[ReferenceEdge]
    unresolved_references: List[dict] = []
    warnings: List[str] = []
    success: bool = True


class NameResolutionPort(ABC):
    """
    Abstract interface for name resolution.

    Implementations:
    - StackGraphsNameResolver: Use Stack Graphs for precise resolution
    - LspBasedNameResolver: Use LSP servers (pyright, tsserver, etc.)
    - SimpleNameResolver: Basic string-based matching (fallback)
    """

    @abstractmethod
    def resolve_names(
        self,
        input_data: NameResolutionInput
    ) -> NameResolutionResult:
        """
        Resolve symbol names and build reference edges.

        Args:
            input_data: Input with code nodes and dependencies

        Returns:
            Resolution result with reference edges
        """
        pass

    @abstractmethod
    def supports_language(self, language: str) -> bool:
        """
        Check if this resolver supports the given language.

        Args:
            language: Programming language

        Returns:
            True if supported
        """
        pass