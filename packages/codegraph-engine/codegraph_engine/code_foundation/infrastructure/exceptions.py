"""
Custom exceptions for code_foundation infrastructure.

P1-2: Replace generic Exception catches with specific exceptions for better error tracking.

Hierarchy:
- CodeFoundationError (base)
  - AnalysisError (analysis failures)
    - TaintAnalysisError
    - PointsToError
    - MemorySafetyError
  - IRBuildError (IR construction failures)
  - LSPError (external LSP/analyzer failures)
  - StorageError (graph/database failures)
"""

from __future__ import annotations


class CodeFoundationError(Exception):
    """Base exception for all code_foundation errors."""

    def __init__(self, message: str, context: dict | None = None):
        super().__init__(message)
        self.context = context or {}

    def __str__(self) -> str:
        if self.context:
            ctx_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{super().__str__()} [{ctx_str}]"
        return super().__str__()


# ============================================================================
# Analysis Errors
# ============================================================================


class AnalysisError(CodeFoundationError):
    """Base class for analysis-related errors."""

    pass


class TaintAnalysisError(AnalysisError):
    """Error during taint analysis."""

    def __init__(
        self,
        message: str,
        function_name: str | None = None,
        source: str | None = None,
        sink: str | None = None,
    ):
        context = {}
        if function_name:
            context["function"] = function_name
        if source:
            context["source"] = source
        if sink:
            context["sink"] = sink
        super().__init__(message, context)
        self.function_name = function_name
        self.source = source
        self.sink = sink


class PointsToError(AnalysisError):
    """Error during points-to analysis."""

    def __init__(
        self,
        message: str,
        variable: str | None = None,
        constraint_type: str | None = None,
    ):
        context = {}
        if variable:
            context["variable"] = variable
        if constraint_type:
            context["constraint"] = constraint_type
        super().__init__(message, context)
        self.variable = variable
        self.constraint_type = constraint_type


class MemorySafetyError(AnalysisError):
    """Error during memory safety analysis (sep_logic)."""

    def __init__(
        self,
        message: str,
        location: str | None = None,
        issue_type: str | None = None,
    ):
        context = {}
        if location:
            context["location"] = location
        if issue_type:
            context["issue_type"] = issue_type
        super().__init__(message, context)
        self.location = location
        self.issue_type = issue_type


class CFGConstructionError(AnalysisError):
    """Error during CFG/DFG construction."""

    def __init__(
        self,
        message: str,
        function_name: str | None = None,
        stage: str | None = None,
    ):
        context = {}
        if function_name:
            context["function"] = function_name
        if stage:
            context["stage"] = stage
        super().__init__(message, context)
        self.function_name = function_name
        self.stage = stage


# ============================================================================
# IR Build Errors
# ============================================================================


class IRBuildError(CodeFoundationError):
    """Error during IR construction."""

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        stage: str | None = None,
    ):
        context = {}
        if file_path:
            context["file"] = file_path
        if stage:
            context["stage"] = stage
        super().__init__(message, context)
        self.file_path = file_path
        self.stage = stage


class ParsingError(IRBuildError):
    """Error during source code parsing."""

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        line: int | None = None,
        column: int | None = None,
    ):
        context = {"stage": "parsing"}
        if file_path:
            context["file"] = file_path
        if line:
            context["line"] = line
        if column:
            context["column"] = column
        super().__init__(message, file_path, "parsing")
        self.line = line
        self.column = column


class TypeEnrichmentError(IRBuildError):
    """Error during type enrichment via LSP."""

    pass


# ============================================================================
# External Service Errors
# ============================================================================


class LSPError(CodeFoundationError):
    """Error from external LSP servers."""

    def __init__(
        self,
        message: str,
        lsp_name: str | None = None,
        method: str | None = None,
    ):
        context = {}
        if lsp_name:
            context["lsp"] = lsp_name
        if method:
            context["method"] = method
        super().__init__(message, context)
        self.lsp_name = lsp_name
        self.method = method


class LSPConnectionError(LSPError):
    """LSP server connection failure."""

    pass


class LSPTimeoutError(LSPError):
    """LSP request timeout."""

    pass


# ============================================================================
# Storage Errors
# ============================================================================


class StorageError(CodeFoundationError):
    """Error from graph/database storage."""

    def __init__(
        self,
        message: str,
        backend: str | None = None,
        operation: str | None = None,
    ):
        context = {}
        if backend:
            context["backend"] = backend
        if operation:
            context["operation"] = operation
        super().__init__(message, context)
        self.backend = backend
        self.operation = operation


class GraphQueryError(StorageError):
    """Error executing graph query."""

    pass


class TransactionError(StorageError):
    """Error in database transaction."""

    pass


# ============================================================================
# Validation Errors
# ============================================================================


class ValidationError(CodeFoundationError):
    """Error during validation."""

    pass


class IRValidationError(ValidationError):
    """Invalid IR structure."""

    def __init__(
        self,
        message: str,
        expected: str | None = None,
        actual: str | None = None,
    ):
        context = {}
        if expected:
            context["expected"] = expected
        if actual:
            context["actual"] = actual
        super().__init__(message, context)
        self.expected = expected
        self.actual = actual
