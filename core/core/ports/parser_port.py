"""
Parser Port

Defines the abstract interface for code parsers.
Separates parsing logic from infrastructure implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


# ==============================================================================
# Data Models
# ==============================================================================

class DiagnosticLevel(str, Enum):
    """Diagnostic severity levels."""
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class ParserDiagnostic(BaseModel):
    """
    Single diagnostic message from parsing.

    Tracks issues encountered during parsing (errors, warnings, info).
    """
    file_path: str
    level: DiagnosticLevel
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    code: Optional[str] = None  # Error code (e.g., "E001")


class ParsedFileInput(BaseModel):
    """
    Input to the parser.

    Contains all information needed to parse a single file.
    """
    file_path: Path
    content: str
    language: str
    file_hash: str  # SHA-256 hash for deduplication

    # LSP/IDE support (future)
    version: Optional[int] = None  # Document version for incremental parsing

    # Performance control
    analysis_budget_ms: Optional[int] = None  # Time budget for parsing

    # Context
    config_context: Dict[str, Any] = Field(default_factory=dict)  # Hints like "is_generated"


class CodeNode(BaseModel):
    """
    Intermediate code node representation (parser-specific).

    This is the parser's internal representation, separate from domain models.
    Will be converted to FileNode/SymbolNode/CanonicalLeafChunk later.
    """
    node_id: str
    node_type: str  # "file", "class", "function", "method", etc.
    name: str

    # Location
    file_path: str
    start_line: int
    end_line: int
    start_byte: Optional[int] = None
    end_byte: Optional[int] = None

    # Content
    raw_code: str

    # Hierarchy
    parent_id: Optional[str] = None
    children_ids: List[str] = Field(default_factory=list)

    # Attributes (language-specific metadata)
    attrs: Dict[str, Any] = Field(default_factory=dict)

    # Examples of attrs:
    # - signature: str
    # - decorators: List[str]
    # - docstring: str
    # - visibility: str (public/private/protected)
    # - is_async: bool
    # - parameters: List[dict]
    # - return_type: str


class ParserResult(BaseModel):
    """
    Output from the parser.

    Contains parsed nodes and diagnostic information.
    """
    file_path: str
    language: str
    nodes: List[CodeNode]
    diagnostics: List[ParserDiagnostic] = Field(default_factory=list)

    # Statistics
    parse_time_ms: Optional[float] = None
    node_count: Optional[int] = None

    # Success indicator
    success: bool = True


# ==============================================================================
# Port Interface
# ==============================================================================

class ParserPort(ABC):
    """
    Abstract parser interface.

    Defines the contract for all code parsers (Python, TypeScript, etc.).
    """

    @abstractmethod
    def supports(self, language: str) -> bool:
        """
        Check if this parser supports the given language.

        Args:
            language: Programming language (e.g., "python", "typescript")

        Returns:
            True if supported, False otherwise
        """
        pass

    @abstractmethod
    def parse_file(self, file_input: ParsedFileInput) -> ParserResult:
        """
        Parse a single file.

        Args:
            file_input: File to parse

        Returns:
            Parser result with nodes and diagnostics

        Raises:
            ParserError: If parsing fails catastrophically
        """
        pass

    def supports_incremental(self) -> bool:
        """
        Check if this parser supports incremental parsing.

        Returns:
            True if incremental parsing is supported (v3 feature)
        """
        return False

    def parse_incremental(
        self,
        prev_result: ParserResult,
        edits: List[Dict[str, Any]]
    ) -> ParserResult:
        """
        Parse incrementally based on previous result and edits.

        Args:
            prev_result: Previous parse result
            edits: List of edits (LSP-style)

        Returns:
            Updated parser result

        Raises:
            NotImplementedError: If incremental parsing is not supported
        """
        raise NotImplementedError("Incremental parsing not implemented")


class ParserError(Exception):
    """Base exception for parser errors."""
    pass


class ParserConfigError(ParserError):
    """Configuration error."""
    pass


class ParserRuntimeError(ParserError):
    """Runtime parsing error."""
    pass