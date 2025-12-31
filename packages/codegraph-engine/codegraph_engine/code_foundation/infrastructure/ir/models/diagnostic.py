"""
Diagnostic Models (SCIP-compatible)

Represents linter errors, warnings, type errors, etc.

SCIP reference: https://github.com/sourcegraph/scip/blob/main/scip.proto#L200
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span


class DiagnosticSeverity(IntEnum):
    """
    SCIP-compatible diagnostic severity.

    Lower values = more severe.
    """

    ERROR = 1  # Compilation/type error
    WARNING = 2  # Potential issue
    INFORMATION = 3  # Informational message
    HINT = 4  # Subtle suggestion


@dataclass(slots=True)
class Diagnostic:
    """
    Single diagnostic (error, warning, etc.).

    SCIP-compatible diagnostic representation.
    Can come from:
    - LSP servers (Pyright, tsserver, etc.)
    - Linters (pylint, eslint, etc.)
    - Type checkers (mypy, pyright, etc.)

    Example:
        Diagnostic(
            id="diag:error:src/calc.py:10",
            file_path="src/calc.py",
            span=Span(10, 8, 10, 20),
            severity=DiagnosticSeverity.ERROR,
            message="Type 'str' cannot be assigned to 'int'",
            source="pyright",
            code="typeAssignmentMismatch",
        )
    """

    # Core fields
    id: str  # Unique diagnostic ID
    file_path: str
    span: Span
    severity: DiagnosticSeverity
    message: str

    # Source info
    source: str  # "pyright", "eslint", "mypy", etc.
    code: str | int | None = None  # Error code (e.g., "E501", "TS2322")

    # Related locations (for "referenced here" messages)
    related_locations: list[tuple[Span, str]] = field(default_factory=list)

    # Tags
    tags: list[str] = field(default_factory=list)  # ["deprecated", "unnecessary"]

    # Extensibility
    attrs: dict[str, Any] = field(default_factory=dict)

    def is_error(self) -> bool:
        """Check if this is an error"""
        return self.severity == DiagnosticSeverity.ERROR

    def is_warning(self) -> bool:
        """Check if this is a warning"""
        return self.severity == DiagnosticSeverity.WARNING

    def __str__(self) -> str:
        severity_str = {
            DiagnosticSeverity.ERROR: "ERROR",
            DiagnosticSeverity.WARNING: "WARN",
            DiagnosticSeverity.INFORMATION: "INFO",
            DiagnosticSeverity.HINT: "HINT",
        }[self.severity]

        code_str = f" [{self.code}]" if self.code else ""
        return f"{severity_str}{code_str}: {self.message} @ {self.file_path}:{self.span.start_line}"


@dataclass
class DiagnosticIndex:
    """
    Fast lookup indexes for diagnostics.

    Optimized for queries like:
    - "Get all errors in file X"
    - "Get all diagnostics by severity"
    - "Get diagnostics from source Y"
    """

    # Primary indexes
    by_file: dict[str, list[str]] = field(default_factory=dict)  # file_path → [diagnostic_id]
    by_severity: dict[DiagnosticSeverity, list[str]] = field(default_factory=dict)
    by_source: dict[str, list[str]] = field(default_factory=dict)  # "pyright" → [diagnostic_id]

    # Storage
    by_id: dict[str, Diagnostic] = field(default_factory=dict)

    # Stats
    total_diagnostics: int = 0
    error_count: int = 0
    warning_count: int = 0

    def add(self, diagnostic: Diagnostic) -> None:
        """Add diagnostic to indexes"""
        diag_id = diagnostic.id

        # Store
        self.by_id[diag_id] = diagnostic

        # Index by file
        self.by_file.setdefault(diagnostic.file_path, []).append(diag_id)

        # Index by severity
        self.by_severity.setdefault(diagnostic.severity, []).append(diag_id)

        # Index by source
        self.by_source.setdefault(diagnostic.source, []).append(diag_id)

        # Update stats
        self.total_diagnostics += 1
        if diagnostic.is_error():
            self.error_count += 1
        elif diagnostic.is_warning():
            self.warning_count += 1

    def get(self, diagnostic_id: str) -> Diagnostic | None:
        """Get diagnostic by ID"""
        return self.by_id.get(diagnostic_id)

    def get_file_diagnostics(self, file_path: str) -> list[Diagnostic]:
        """Get all diagnostics in a file"""
        diag_ids = self.by_file.get(file_path, [])
        return [self.by_id[did] for did in diag_ids if did in self.by_id]

    def get_file_errors(self, file_path: str) -> list[Diagnostic]:
        """Get only errors in a file"""
        diags = self.get_file_diagnostics(file_path)
        return [d for d in diags if d.is_error()]

    def get_by_severity(self, severity: DiagnosticSeverity) -> list[Diagnostic]:
        """Get all diagnostics with specific severity"""
        diag_ids = self.by_severity.get(severity, [])
        return [self.by_id[did] for did in diag_ids if did in self.by_id]

    def get_by_source(self, source: str) -> list[Diagnostic]:
        """Get all diagnostics from specific source (e.g., 'pyright')"""
        diag_ids = self.by_source.get(source, [])
        return [self.by_id[did] for did in diag_ids if did in self.by_id]

    def get_stats(self) -> dict[str, Any]:
        """Get diagnostic statistics"""
        return {
            "total": self.total_diagnostics,
            "errors": self.error_count,
            "warnings": self.warning_count,
            "by_severity": {str(sev): len(diags) for sev, diags in self.by_severity.items()},
            "by_source": {src: len(diags) for src, diags in self.by_source.items()},
            "files_with_diagnostics": len(self.by_file),
        }

    def clear(self) -> None:
        """Clear all indexes"""
        self.by_file.clear()
        self.by_severity.clear()
        self.by_source.clear()
        self.by_id.clear()
        self.total_diagnostics = 0
        self.error_count = 0
        self.warning_count = 0


def create_diagnostic(
    file_path: str,
    span: Span,
    severity: DiagnosticSeverity,
    message: str,
    source: str,
    code: str | int | None = None,
) -> Diagnostic:
    """
    Helper: Create a diagnostic.

    Args:
        file_path: File containing the issue
        span: Location of the issue
        severity: Error, warning, etc.
        message: Human-readable message
        source: Source of diagnostic (e.g., "pyright")
        code: Error code (optional)

    Returns:
        Diagnostic
    """
    diag_id = f"diag:{severity.name.lower()}:{file_path}:{span.start_line}:{span.start_col}"

    return Diagnostic(
        id=diag_id,
        file_path=file_path,
        span=span,
        severity=severity,
        message=message,
        source=source,
        code=code,
    )
