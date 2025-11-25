"""
Tool Input/Output Schemas

Defines Pydantic models for all agent tool inputs and outputs.
Clear JSON contracts for LLM interaction.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# ============================================================
# Code Search
# ============================================================


class CodeSearchInput(BaseModel):
    """Input schema for code_search tool."""

    query: str = Field(..., description="Search query (natural language or code snippet)")
    scope: str | None = Field(
        None, description="Optional scope filter (file path, directory, or symbol name)"
    )
    limit: int = Field(10, description="Maximum number of results", ge=1, le=50)
    search_type: Literal["semantic", "lexical", "symbol", "hybrid"] = Field(
        "hybrid", description="Type of search to perform"
    )


class SearchResult(BaseModel):
    """Single search result."""

    file_path: str = Field(..., description="Path to file containing the match")
    symbol_name: str | None = Field(None, description="Symbol name if applicable")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    score: float = Field(..., description="Relevance score (0-1)")
    snippet: str = Field(..., description="Code snippet preview")
    context: str | None = Field(None, description="Additional context (docstring, signature)")


class CodeSearchOutput(BaseModel):
    """Output schema for code_search tool."""

    success: bool = Field(..., description="Whether search succeeded")
    results: list[SearchResult] = Field(default_factory=list, description="Search results")
    total_found: int = Field(0, description="Total number of matches found")
    error: str | None = Field(None, description="Error message if search failed")


# ============================================================
# Symbol Search
# ============================================================


class SymbolSearchInput(BaseModel):
    """Input schema for symbol_search tool."""

    name: str = Field(..., description="Symbol name to search for")
    kind: Literal["function", "class", "variable", "any"] | None = Field(
        None, description="Type of symbol to find"
    )
    exact_match: bool = Field(False, description="Whether to require exact name match")


class SymbolInfo(BaseModel):
    """Symbol information."""

    symbol_id: str = Field(..., description="Unique symbol identifier")
    name: str = Field(..., description="Symbol name")
    kind: str = Field(..., description="Symbol kind (function, class, etc.)")
    file_path: str = Field(..., description="File containing the symbol")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    signature: str | None = Field(None, description="Function/method signature")
    docstring: str | None = Field(None, description="Docstring if available")


class SymbolSearchOutput(BaseModel):
    """Output schema for symbol_search tool."""

    success: bool = Field(..., description="Whether search succeeded")
    symbols: list[SymbolInfo] = Field(default_factory=list, description="Found symbols")
    error: str | None = Field(None, description="Error message if search failed")


# ============================================================
# File Operations
# ============================================================


class OpenFileInput(BaseModel):
    """Input schema for open_file tool."""

    path: str = Field(..., description="Path to file to open")
    start_line: int | None = Field(None, description="Optional start line (1-indexed)")
    end_line: int | None = Field(None, description="Optional end line (inclusive)")


class OpenFileOutput(BaseModel):
    """Output schema for open_file tool."""

    success: bool = Field(..., description="Whether file was opened successfully")
    path: str = Field(..., description="File path")
    content: str = Field("", description="File contents")
    start_line: int = Field(1, description="Start line of returned content")
    end_line: int = Field(1, description="End line of returned content")
    total_lines: int = Field(0, description="Total lines in file")
    language: str | None = Field(None, description="Detected programming language")
    error: str | None = Field(None, description="Error message if failed")


class GetSpanInput(BaseModel):
    """Input schema for get_span tool."""

    path: str = Field(..., description="Path to file")
    start_line: int = Field(..., description="Start line number (1-indexed)")
    end_line: int = Field(..., description="End line number (inclusive)")


class GetSpanOutput(BaseModel):
    """Output schema for get_span tool."""

    success: bool = Field(..., description="Whether span was retrieved successfully")
    path: str = Field(..., description="File path")
    content: str = Field("", description="Content of the span")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    error: str | None = Field(None, description="Error message if failed")


# ============================================================
# Patch Operations
# ============================================================


class ProposePatchInput(BaseModel):
    """Input schema for propose_patch tool."""

    path: str = Field(..., description="Path to file to modify")
    start_line: int = Field(..., description="Start line of section to replace (1-indexed)")
    end_line: int = Field(..., description="End line of section to replace (inclusive)")
    new_code: str = Field(..., description="New code to replace the section")
    description: str = Field(..., description="Description of what this patch does")


class ProposePatchOutput(BaseModel):
    """Output schema for propose_patch tool."""

    success: bool = Field(..., description="Whether patch was created successfully")
    patch_id: str | None = Field(None, description="Unique patch identifier")
    path: str = Field(..., description="File path")
    diff: str = Field("", description="Unified diff of the proposed change")
    validation: dict[str, Any] = Field(
        default_factory=dict, description="Validation results (syntax check, etc.)"
    )
    error: str | None = Field(None, description="Error message if failed")


class ApplyPatchInput(BaseModel):
    """Input schema for apply_patch tool."""

    patch_id: str = Field(..., description="Patch ID to apply")
    dry_run: bool = Field(True, description="Whether to do dry-run only (default: True)")


class ApplyPatchOutput(BaseModel):
    """Output schema for apply_patch tool."""

    success: bool = Field(..., description="Whether patch was applied successfully")
    patch_id: str = Field(..., description="Patch ID")
    applied: bool = Field(False, description="Whether patch was actually applied (not dry-run)")
    path: str = Field(..., description="File path")
    backup_path: str | None = Field(None, description="Backup file path if created")
    error: str | None = Field(None, description="Error message if failed")


# ============================================================
# Test Operations
# ============================================================


class RunTestsInput(BaseModel):
    """Input schema for run_tests tool."""

    scope: str | None = Field(None, description="Test scope (file, directory, or test name)")
    test_command: str | None = Field(None, description="Custom test command to run")
    timeout: int = Field(300, description="Timeout in seconds", ge=1, le=3600)


class TestResult(BaseModel):
    """Individual test result."""

    name: str = Field(..., description="Test name")
    status: Literal["passed", "failed", "skipped", "error"] = Field(..., description="Test status")
    duration: float = Field(..., description="Test duration in seconds")
    message: str | None = Field(None, description="Error message if failed")


class RunTestsOutput(BaseModel):
    """Output schema for run_tests tool."""

    success: bool = Field(..., description="Whether tests ran successfully (not if they passed)")
    passed: int = Field(0, description="Number of passed tests")
    failed: int = Field(0, description="Number of failed tests")
    skipped: int = Field(0, description="Number of skipped tests")
    total: int = Field(0, description="Total number of tests")
    duration: float = Field(0.0, description="Total test duration in seconds")
    results: list[TestResult] = Field(default_factory=list, description="Individual test results")
    output: str = Field("", description="Full test output")
    error: str | None = Field(None, description="Error message if tests failed to run")


# ============================================================
# Base Tool Result
# ============================================================


class ToolResult(BaseModel):
    """Generic tool result wrapper."""

    tool_name: str = Field(..., description="Name of tool that was executed")
    success: bool = Field(..., description="Whether tool execution succeeded")
    result: dict[str, Any] = Field(..., description="Tool-specific result data")
    error: str | None = Field(None, description="Error message if failed")
    execution_time: float = Field(..., description="Execution time in seconds")
