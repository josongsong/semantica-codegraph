"""
External Analyzer Base

Protocol and base classes for external type checkers.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class TypeInfo:
    """
    Type information from external analyzer.

    Attributes:
        symbol_name: Symbol name (e.g., "MyClass.method")
        file_path: File path
        line: Line number (1-indexed)
        column: Column number (0-indexed)
        inferred_type: Inferred type string
        declared_type: Declared type string (if any)
        is_builtin: Whether type is builtin
        definition_path: Path to definition (if resolved)
        definition_line: Line number of definition
    """

    symbol_name: str
    file_path: str
    line: int
    column: int
    inferred_type: str | None = None
    declared_type: str | None = None
    is_builtin: bool = False
    definition_path: str | None = None
    definition_line: int | None = None


@dataclass
class Location:
    """
    Source code location.

    Used for definition/reference sites.
    """

    file_path: str
    line: int  # 1-indexed
    column: int  # 0-indexed
    end_line: int | None = None
    end_column: int | None = None


class ExternalAnalyzer(Protocol):
    """
    External code analyzer interface.

    Implementations: Pyright, Mypy, LSP servers
    """

    def analyze_file(self, file_path: Path) -> list[TypeInfo]:
        """
        Analyze a single file and extract type information.

        Args:
            file_path: Path to source file

        Returns:
            List of type information for symbols in the file
        """
        ...

    def analyze_symbol(self, file_path: Path, line: int, column: int) -> TypeInfo | None:
        """
        Analyze a specific symbol at a location.

        Args:
            file_path: Path to source file
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            Type information or None if not found
        """
        ...

    def get_definition(self, file_path: Path, line: int, column: int) -> Location | None:
        """
        Get definition location for a symbol (LSP: textDocument/definition).

        Args:
            file_path: Path to source file
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            Definition location or None if not found
        """
        ...

    def get_references(self, file_path: Path, line: int, column: int) -> list[Location]:
        """
        Get all reference locations for a symbol (LSP: textDocument/references).

        Args:
            file_path: Path to source file where symbol is defined
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            List of reference locations (may be empty)
        """
        ...

    def shutdown(self):
        """Clean up resources (e.g., stop LSP server)"""
        ...
