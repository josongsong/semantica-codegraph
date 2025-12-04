"""
Occurrence Models (SCIP-compatible)

SCIP-level occurrence tracking for retrieval optimization.

Key concepts:
- Occurrence: Single use of a symbol (definition, reference, write, etc.)
- SymbolRole: Type of occurrence (SCIP-compatible bitflags)
- OccurrenceIndex: Fast lookup indexes for retrieval

Reference: https://github.com/sourcegraph/scip
"""

from dataclasses import dataclass, field
from enum import IntFlag
from typing import Any

from src.contexts.code_foundation.infrastructure.ir.models.core import Span


class SymbolRole(IntFlag):
    """
    SCIP-compatible symbol roles.

    Uses bitflags (IntFlag) for combining multiple roles:
    - Can check multiple roles: role & SymbolRole.DEFINITION
    - Can combine roles: SymbolRole.DEFINITION | SymbolRole.TEST

    SCIP reference:
    https://github.com/sourcegraph/scip/blob/main/scip.proto#L138
    """

    NONE = 0

    # Primary roles
    DEFINITION = 1  # Symbol is defined here (class Foo, def bar, etc.)
    IMPORT = 2  # Symbol is imported (from X import Y)
    WRITE_ACCESS = 4  # Symbol is written to (x = 10, x += 1)
    READ_ACCESS = 8  # Symbol is read from (y = x, foo(x))

    # Metadata roles
    GENERATED = 16  # Generated code (protobuf, ORM models, etc.)
    TEST = 32  # Test code (test files, test functions)
    FORWARD_DEFINITION = 64  # Forward declaration (C/C++, type hints)

    def __str__(self) -> str:
        """Human-readable role string"""
        roles = []
        if self & SymbolRole.DEFINITION:
            roles.append("DEFINITION")
        if self & SymbolRole.IMPORT:
            roles.append("IMPORT")
        if self & SymbolRole.WRITE_ACCESS:
            roles.append("WRITE")
        if self & SymbolRole.READ_ACCESS:
            roles.append("READ")
        if self & SymbolRole.GENERATED:
            roles.append("GENERATED")
        if self & SymbolRole.TEST:
            roles.append("TEST")
        if self & SymbolRole.FORWARD_DEFINITION:
            roles.append("FORWARD")

        return " | ".join(roles) if roles else "NONE"


@dataclass(slots=True)
class Occurrence:
    """
    Single occurrence of a symbol.

    Represents one use of a symbol in the code:
    - Definition: class Foo, def bar
    - Reference: calling bar(), using Foo
    - Write: x = 10
    - Read: y = x

    SCIP-compatible but with retrieval optimizations:
    - importance_score: For ranking in search results
    - file_path: For O(1) file-based queries
    - parent_symbol_id: For scope/context awareness

    Examples:
        # Definition occurrence
        Occurrence(
            id="occ:def:class:Calculator",
            symbol_id="class:Calculator",
            span=Span(10, 0, 10, 20),
            roles=SymbolRole.DEFINITION,
            file_path="src/calc.py",
            importance_score=0.9,  # Public class
        )

        # Reference occurrence (method call)
        Occurrence(
            id="occ:ref:calc_add:5",
            symbol_id="method:Calculator::add",
            span=Span(25, 8, 25, 11),
            roles=SymbolRole.READ_ACCESS,
            file_path="src/main.py",
            parent_symbol_id="function:main",
            importance_score=0.5,
        )
    """

    # Core fields (SCIP-compatible)
    id: str  # Unique occurrence ID (e.g., "occ:def:Calculator")
    symbol_id: str  # Reference to Node.id (e.g., "class:Calculator")
    span: Span  # Location in source code
    roles: SymbolRole  # Bitflags: can combine multiple roles

    # Retrieval optimization fields
    file_path: str  # File containing this occurrence (for O(1) file queries)

    # Context fields (optional, for rich results)
    enclosing_range: Span | None = None  # Larger context (e.g., entire function body)
    parent_symbol_id: str | None = None  # Enclosing scope (e.g., class or function)

    # Ranking signal (0.0-1.0, higher = more important)
    importance_score: float = 0.5

    # Additional metadata
    syntax_kind: str | None = None  # AST node type (e.g., "call_expression")
    is_implicit: bool = False  # Implicit reference (e.g., self in Python)

    # Extensibility
    attrs: dict[str, Any] = field(default_factory=dict)

    def is_definition(self) -> bool:
        """Check if this is a definition occurrence"""
        return bool(self.roles & SymbolRole.DEFINITION)

    def is_reference(self) -> bool:
        """Check if this is a reference (read access)"""
        return bool(self.roles & SymbolRole.READ_ACCESS)

    def is_write(self) -> bool:
        """Check if this is a write access"""
        return bool(self.roles & SymbolRole.WRITE_ACCESS)

    def is_import(self) -> bool:
        """Check if this is an import"""
        return bool(self.roles & SymbolRole.IMPORT)

    def has_role(self, role: SymbolRole) -> bool:
        """Check if occurrence has specific role"""
        return bool(self.roles & role)

    def get_context_snippet(self, source_lines: list[str]) -> str:
        """
        Extract code snippet with context.

        Args:
            source_lines: Source file lines

        Returns:
            Code snippet (enclosing_range if available, else span)
        """
        snippet_span = self.enclosing_range or self.span

        try:
            lines = source_lines[snippet_span.start_line : snippet_span.end_line + 1]
            return "\n".join(lines)
        except IndexError:
            return ""


@dataclass
class OccurrenceIndex:
    """
    Fast lookup indexes for occurrences.

    Optimized for retrieval queries:
    - by_symbol: "Find all references to symbol X" → O(1)
    - by_file: "Find all symbols in file Y" → O(1)
    - by_role: "Find all definitions" → O(1)
    - by_id: Get occurrence by ID → O(1)

    All indexes use occurrence IDs (not full objects) to save memory.
    Actual Occurrence objects stored in by_id only.

    Example usage:
        index = OccurrenceIndex()

        # Add occurrence
        index.add(occurrence)

        # Find all references to a symbol
        refs = index.get_references("class:Calculator")

        # Find all definitions in a file
        defs = index.get_definitions_in_file("src/calc.py")

        # Find all write accesses
        writes = index.get_by_role(SymbolRole.WRITE_ACCESS)
    """

    # Primary indexes
    by_symbol: dict[str, list[str]] = field(default_factory=dict)  # symbol_id → [occurrence_id]
    by_file: dict[str, list[str]] = field(default_factory=dict)  # file_path → [occurrence_id]
    by_role: dict[SymbolRole, list[str]] = field(default_factory=dict)  # role → [occurrence_id]

    # Storage (single source of truth)
    by_id: dict[str, Occurrence] = field(default_factory=dict)  # occurrence_id → Occurrence

    # Stats
    total_occurrences: int = 0
    definitions_count: int = 0
    references_count: int = 0

    def add(self, occurrence: Occurrence) -> None:
        """
        Add occurrence to all indexes.

        Args:
            occurrence: Occurrence to index
        """
        occ_id = occurrence.id

        # Store occurrence
        self.by_id[occ_id] = occurrence

        # Index by symbol
        self.by_symbol.setdefault(occurrence.symbol_id, []).append(occ_id)

        # Index by file
        self.by_file.setdefault(occurrence.file_path, []).append(occ_id)

        # Index by role (handle bitflags - occurrence can have multiple roles)
        for role in SymbolRole:
            if role != SymbolRole.NONE and occurrence.roles & role:
                self.by_role.setdefault(role, []).append(occ_id)

        # Update stats
        self.total_occurrences += 1
        if occurrence.is_definition():
            self.definitions_count += 1
        if occurrence.is_reference():
            self.references_count += 1

    def get(self, occurrence_id: str) -> Occurrence | None:
        """Get occurrence by ID (O(1))"""
        return self.by_id.get(occurrence_id)

    def get_references(self, symbol_id: str) -> list[Occurrence]:
        """
        Get all occurrences of a symbol (O(1) lookup).

        Args:
            symbol_id: Symbol to find references for

        Returns:
            List of all occurrences (definitions + references)
        """
        occ_ids = self.by_symbol.get(symbol_id, [])
        return [self.by_id[oid] for oid in occ_ids if oid in self.by_id]

    def get_definitions(self, symbol_id: str) -> list[Occurrence]:
        """
        Get definition occurrences for a symbol.

        Usually returns 1 definition, but can be multiple for:
        - Method overloads (in languages that support it)
        - Forward declarations + actual definition

        Args:
            symbol_id: Symbol to find definitions for

        Returns:
            List of definition occurrences
        """
        occs = self.get_references(symbol_id)
        return [o for o in occs if o.is_definition()]

    def get_usages(self, symbol_id: str, include_definitions: bool = False) -> list[Occurrence]:
        """
        Get usage occurrences (references, not definitions).

        Args:
            symbol_id: Symbol to find usages for
            include_definitions: Include definition occurrences (default: False)

        Returns:
            List of usage occurrences
        """
        occs = self.get_references(symbol_id)
        if include_definitions:
            return occs
        return [o for o in occs if not o.is_definition()]

    def get_file_occurrences(self, file_path: str) -> list[Occurrence]:
        """
        Get all occurrences in a file (O(1)).

        Args:
            file_path: File to get occurrences for

        Returns:
            List of occurrences in file
        """
        occ_ids = self.by_file.get(file_path, [])
        return [self.by_id[oid] for oid in occ_ids if oid in self.by_id]

    def get_definitions_in_file(self, file_path: str) -> list[Occurrence]:
        """
        Get all definitions in a file.

        Useful for:
        - Outline view
        - Symbol list
        - File summary

        Args:
            file_path: File to get definitions for

        Returns:
            List of definition occurrences in file
        """
        occs = self.get_file_occurrences(file_path)
        return [o for o in occs if o.is_definition()]

    def get_by_role(self, role: SymbolRole) -> list[Occurrence]:
        """
        Get all occurrences with specific role.

        Args:
            role: Role to filter by

        Returns:
            List of occurrences with that role
        """
        occ_ids = self.by_role.get(role, [])
        return [self.by_id[oid] for oid in occ_ids if oid in self.by_id]

    def get_by_importance(self, min_score: float = 0.7) -> list[Occurrence]:
        """
        Get high-importance occurrences.

        Useful for:
        - Showing most relevant results first
        - Filtering noise (low-importance symbols)

        Args:
            min_score: Minimum importance score (0.0-1.0)

        Returns:
            List of occurrences with importance >= min_score, sorted by score
        """
        high_importance = [occ for occ in self.by_id.values() if occ.importance_score >= min_score]
        return sorted(high_importance, key=lambda o: o.importance_score, reverse=True)

    def get_stats(self) -> dict[str, Any]:
        """
        Get index statistics.

        Returns:
            Statistics dict with counts and breakdowns
        """
        return {
            "total_occurrences": self.total_occurrences,
            "definitions": self.definitions_count,
            "references": self.references_count,
            "unique_symbols": len(self.by_symbol),
            "files": len(self.by_file),
            "role_breakdown": {str(role): len(occs) for role, occs in self.by_role.items()},
        }

    def clear(self) -> None:
        """Clear all indexes"""
        self.by_symbol.clear()
        self.by_file.clear()
        self.by_role.clear()
        self.by_id.clear()
        self.total_occurrences = 0
        self.definitions_count = 0
        self.references_count = 0


def create_definition_occurrence(
    symbol_id: str,
    span: Span,
    file_path: str,
    importance_score: float = 0.5,
    **kwargs: Any,
) -> Occurrence:
    """
    Helper: Create a definition occurrence.

    Args:
        symbol_id: ID of defined symbol
        span: Location of definition
        file_path: File containing definition
        importance_score: Importance score (0.0-1.0)
        **kwargs: Additional fields (enclosing_range, parent_symbol_id, etc.)

    Returns:
        Definition occurrence
    """
    return Occurrence(
        id=f"occ:def:{symbol_id}",
        symbol_id=symbol_id,
        span=span,
        roles=SymbolRole.DEFINITION,
        file_path=file_path,
        importance_score=importance_score,
        **kwargs,
    )


def create_reference_occurrence(
    symbol_id: str,
    span: Span,
    file_path: str,
    parent_symbol_id: str | None = None,
    is_write: bool = False,
    **kwargs: Any,
) -> Occurrence:
    """
    Helper: Create a reference occurrence.

    Args:
        symbol_id: ID of referenced symbol
        span: Location of reference
        file_path: File containing reference
        parent_symbol_id: Enclosing symbol (scope context)
        is_write: True for write access, False for read access
        **kwargs: Additional fields

    Returns:
        Reference occurrence
    """
    role = SymbolRole.WRITE_ACCESS if is_write else SymbolRole.READ_ACCESS

    ref_id = f"occ:{'write' if is_write else 'ref'}:{symbol_id}:{span.start_line}:{span.start_col}"

    return Occurrence(
        id=ref_id,
        symbol_id=symbol_id,
        span=span,
        roles=role,
        file_path=file_path,
        parent_symbol_id=parent_symbol_id,
        importance_score=0.5,  # References have lower base importance
        **kwargs,
    )
