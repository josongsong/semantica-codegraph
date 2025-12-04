"""
External Analyzer Base

Protocol and base classes for external type checkers.

Supports:
- Basic type inference
- Union type decomposition
- Type narrowing (isinstance, TypeGuard)
- Control flow analysis for type refinement
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol


class NarrowingKind(Enum):
    """Type narrowing mechanism."""

    ISINSTANCE = "isinstance"  # isinstance(x, T)
    TYPE_GUARD = "type_guard"  # def is_str(x) -> TypeGuard[str]
    TRUTHINESS = "truthiness"  # if x: (narrows Optional to non-None)
    EQUALITY = "equality"  # if x == "value"
    IDENTITY = "identity"  # if x is None
    ASSERT = "assert"  # assert isinstance(x, T)
    WALRUS = "walrus"  # if (x := get_value()) is not None


@dataclass
class NarrowingContext:
    """
    Context for type narrowing at a specific location.

    Tracks how a Union type was narrowed through control flow.

    Example:
        x: int | str | None

        if isinstance(x, str):  # Narrowing: isinstance
            # x is narrowed to 'str'
            narrowed_type = "str"
            original_type = "int | str | None"
            narrowing_kind = NarrowingKind.ISINSTANCE
            guard_types = ["str"]
    """

    original_type: str
    """Original type before narrowing (e.g., 'int | str | None')"""

    narrowed_type: str
    """Type after narrowing (e.g., 'str')"""

    narrowing_kind: NarrowingKind
    """How the type was narrowed"""

    guard_types: list[str] = field(default_factory=list)
    """Types used in the guard (e.g., ['str'] for isinstance(x, str))"""

    negated: bool = False
    """True if in else branch (narrowed to complement)"""

    condition_line: int | None = None
    """Line of the narrowing condition"""

    condition_column: int | None = None
    """Column of the narrowing condition"""


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

    Union/Narrowing Attributes:
        is_union: Whether the type is a Union
        union_variants: Decomposed Union types (e.g., ['int', 'str', 'None'])
        narrowing_context: Context if type was narrowed
        type_guard_function: TypeGuard function name if applicable
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

    # Union type support
    is_union: bool = False
    union_variants: list[str] = field(default_factory=list)

    # Type narrowing support
    narrowing_context: NarrowingContext | None = None
    type_guard_function: str | None = None

    def get_effective_type(self) -> str | None:
        """
        Get the effective type, considering narrowing.

        Returns narrowed type if available, otherwise inferred type.
        """
        if self.narrowing_context:
            return self.narrowing_context.narrowed_type
        return self.inferred_type

    def is_narrowed(self) -> bool:
        """Check if type was narrowed from a Union."""
        return self.narrowing_context is not None

    def get_excluded_types(self) -> list[str]:
        """
        Get types excluded by narrowing.

        Returns types from the original Union that are not in narrowed type.
        """
        if not self.narrowing_context or not self.union_variants:
            return []

        narrowed = self.narrowing_context.narrowed_type
        # Simple check - in real impl would need proper type comparison
        return [v for v in self.union_variants if v != narrowed]


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
