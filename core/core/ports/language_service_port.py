"""
Language Service Port

Interface for LSP (Language Server Protocol) and compiler API integration.
Enables IDE-level code intelligence features.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional
from enum import Enum

from pydantic import BaseModel


class SymbolKind(str, Enum):
    """LSP symbol kinds."""
    FILE = "file"
    MODULE = "module"
    NAMESPACE = "namespace"
    PACKAGE = "package"
    CLASS = "class"
    METHOD = "method"
    PROPERTY = "property"
    FIELD = "field"
    CONSTRUCTOR = "constructor"
    ENUM = "enum"
    INTERFACE = "interface"
    FUNCTION = "function"
    VARIABLE = "variable"
    CONSTANT = "constant"
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"


class Location(BaseModel):
    """
    Code location in LSP format.

    Compatible with LSP textDocument/definition and textDocument/references.
    """
    file_path: str
    line: int  # 0-indexed (LSP format)
    character: int  # 0-indexed (LSP format)

    # Optional byte offsets
    byte_offset: Optional[int] = None


class Range(BaseModel):
    """Code range in LSP format."""
    start: Location
    end: Location


class SymbolInformation(BaseModel):
    """Symbol information from LSP."""
    name: str
    kind: SymbolKind
    location: Location
    container_name: Optional[str] = None  # Parent symbol name


class DefinitionResult(BaseModel):
    """Result from textDocument/definition."""
    locations: List[Location]
    success: bool = True
    error: Optional[str] = None


class ReferencesResult(BaseModel):
    """Result from textDocument/references."""
    locations: List[Location]
    success: bool = True
    error: Optional[str] = None


class HoverResult(BaseModel):
    """Result from textDocument/hover."""
    content: str
    range: Optional[Range] = None
    success: bool = True
    error: Optional[str] = None


class LanguageServicePort(ABC):
    """
    Abstract interface for language service integration.

    Implementations:
    - PyrightLanguageService: Python (pyright LSP)
    - TypeScriptLanguageService: TypeScript (tsserver)
    - RustAnalyzerService: Rust (rust-analyzer)
    - etc.
    """

    @abstractmethod
    def get_definitions(self, location: Location) -> DefinitionResult:
        """
        Get definitions for a symbol at location.

        Args:
            location: Cursor position

        Returns:
            Definition locations
        """
        pass

    @abstractmethod
    def get_references(
        self,
        location: Location,
        include_declaration: bool = True
    ) -> ReferencesResult:
        """
        Get all references to a symbol.

        Args:
            location: Symbol location
            include_declaration: Include declaration in results

        Returns:
            Reference locations
        """
        pass

    @abstractmethod
    def get_hover(self, location: Location) -> HoverResult:
        """
        Get hover information for a symbol.

        Args:
            location: Cursor position

        Returns:
            Hover content (type info, docs, etc.)
        """
        pass

    @abstractmethod
    def supports_language(self, language: str) -> bool:
        """
        Check if this service supports the given language.

        Args:
            language: Programming language

        Returns:
            True if supported
        """
        pass

    def get_document_symbols(self, file_path: str) -> List[SymbolInformation]:
        """
        Get all symbols in a document.

        Args:
            file_path: File path

        Returns:
            List of symbols in the file

        Raises:
            NotImplementedError: If not supported by implementation
        """
        raise NotImplementedError("Document symbols not implemented")