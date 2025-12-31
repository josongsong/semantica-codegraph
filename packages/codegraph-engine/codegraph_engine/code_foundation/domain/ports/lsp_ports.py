"""
LSP Ports - Hexagonal Architecture

Port definitions for Language Server Protocol operations.
Enables parallel batch fetching of hover/definition data.

Design Principles:
1. Single Responsibility: One port per LSP operation category
2. Interface Segregation: Minimal, focused interfaces
3. Dependency Inversion: Domain depends on abstractions, not concrete LSP clients
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Protocol, runtime_checkable


class LSPOperationType(Enum):
    """Types of LSP operations supported by BatchLSPFetcher."""

    HOVER = auto()  # textDocument/hover - type information
    DEFINITION = auto()  # textDocument/definition - jump to definition


@dataclass(frozen=True)
class LSPPosition:
    """
    Immutable position in source code.

    Frozen for use as dict key in batch results.
    """

    line: int  # 1-indexed
    column: int  # 0-indexed

    def __hash__(self) -> int:
        return hash((self.line, self.column))


@dataclass
class LSPHoverResult:
    """
    Result of textDocument/hover operation.

    Attributes:
        type: Inferred type string (e.g., "str", "List[int]")
        documentation: Optional docstring/documentation
        raw: Original hover response for debugging
    """

    type: str | None = None
    documentation: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Whether hover returned useful type information."""
        return self.type is not None


@dataclass
class LSPDefinitionResult:
    """
    Result of textDocument/definition operation.

    Attributes:
        file: Path to definition file
        line: Line number of definition (1-indexed)
        column: Column number of definition (0-indexed)
        fqn: Fully qualified name (if available)
    """

    file: str | None = None
    line: int | None = None
    column: int | None = None
    fqn: str | None = None

    @property
    def success(self) -> bool:
        """Whether definition was found."""
        return self.file is not None and self.line is not None


@dataclass
class LSPBatchResult:
    """
    Combined result of batch LSP operations for a single position.

    Attributes:
        position: Source position
        hover: Hover result (if requested)
        definition: Definition result (if requested)
        error: Error message if operation failed
    """

    position: LSPPosition
    hover: LSPHoverResult | None = None
    definition: LSPDefinitionResult | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        """Whether at least one operation succeeded."""
        hover_ok = self.hover is not None and self.hover.success
        def_ok = self.definition is not None and self.definition.success
        return hover_ok or def_ok


@runtime_checkable
class IBatchLSPFetcher(Protocol):
    """
    Port: Batch LSP operations for parallel execution.

    Combines hover and definition calls into a single batch operation
    that can be executed in parallel for massive performance gains.

    Performance Characteristics:
        Sequential: 854 calls × 12ms = ~10 seconds
        Parallel (32 workers): ~0.3-0.5 seconds (20-30x speedup)

    Example:
        >>> fetcher = BatchLSPFetcher(lsp_client, max_workers=32)
        >>> results = fetcher.fetch_batch(
        ...     file_path=Path("src/main.py"),
        ...     positions=[LSPPosition(10, 5), LSPPosition(20, 10)],
        ...     operations={LSPOperationType.HOVER, LSPOperationType.DEFINITION}
        ... )
        >>> for pos, result in results.items():
        ...     print(f"{pos.line}:{pos.column} -> {result.hover.type}")
    """

    def fetch_batch(
        self,
        file_path: Path,
        positions: list[LSPPosition],
        operations: set[LSPOperationType] | None = None,
    ) -> dict[LSPPosition, LSPBatchResult]:
        """
        Fetch LSP data for multiple positions in parallel.

        Args:
            file_path: Source file path (absolute)
            positions: List of positions to query
            operations: Which operations to perform (default: both HOVER and DEFINITION)

        Returns:
            Dictionary mapping position to batch result
        """
        ...

    def fetch_hover_batch(
        self,
        file_path: Path,
        positions: list[LSPPosition],
    ) -> dict[LSPPosition, LSPHoverResult]:
        """
        Convenience: Fetch only hover information.

        Args:
            file_path: Source file path
            positions: List of positions to query

        Returns:
            Dictionary mapping position to hover result
        """
        ...

    def fetch_definition_batch(
        self,
        file_path: Path,
        positions: list[LSPPosition],
    ) -> dict[LSPPosition, LSPDefinitionResult]:
        """
        Convenience: Fetch only definition information.

        Args:
            file_path: Source file path
            positions: List of positions to query

        Returns:
            Dictionary mapping position to definition result
        """
        ...

    @property
    def stats(self) -> dict:
        """
        Get performance statistics.

        Returns:
            Dictionary with:
                - total_calls: Number of individual LSP calls made
                - batch_calls: Number of batch operations
                - avg_batch_size: Average positions per batch
                - total_time_ms: Total time spent in LSP calls
                - parallel_speedup: Estimated speedup vs sequential
        """
        ...


__all__ = [
    "LSPOperationType",
    "LSPPosition",
    "LSPHoverResult",
    "LSPDefinitionResult",
    "LSPBatchResult",
    "IBatchLSPFetcher",
]
