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
    scope: str | None = Field(None, description="Optional scope filter (file path, directory, or symbol name)")
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
    kind: Literal["function", "class", "variable", "any"] | None = Field(None, description="Type of symbol to find")
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
    validation: dict[str, Any] = Field(default_factory=dict, description="Validation results (syntax check, etc.)")
    error: str | None = Field(None, description="Error message if failed")


class ApplyPatchInput(BaseModel):
    """Input schema for apply_patch tool."""

    patch_id: str = Field(..., description="Patch ID to apply")
    dry_run: bool = Field(True, description="Whether to do dry-run only (default: True)")
    conflict_strategy: Literal["ours", "theirs"] | None = Field(
        None, description="Conflict resolution strategy: 'ours' (keep current), 'theirs' (use patch)"
    )


class ConflictInfo(BaseModel):
    """Information about a merge conflict."""

    line_start: int = Field(..., description="Starting line of conflict")
    line_end: int = Field(..., description="Ending line of conflict")
    ours: str = Field(..., description="Current version content (truncated)")
    theirs: str = Field(..., description="Proposed version content (truncated)")


class ApplyPatchOutput(BaseModel):
    """Output schema for apply_patch tool."""

    success: bool = Field(..., description="Whether patch was applied successfully")
    patch_id: str = Field(..., description="Patch ID")
    applied: bool = Field(False, description="Whether patch was actually applied (not dry-run)")
    path: str = Field(..., description="File path")
    backup_path: str | None = Field(None, description="Backup file path if created")
    error: str | None = Field(None, description="Error message if failed")
    conflicts: list[ConflictInfo] = Field(
        default_factory=list, description="Conflict details if merge conflicts occurred"
    )


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
# Graph Query
# ============================================================


class GraphQueryInput(BaseModel):
    """Input schema for graph_query tool."""

    query_type: Literal["callers", "callees", "dependencies", "dependents", "flow_trace"] = Field(
        ..., description="Type of graph query to perform"
    )
    symbol_id: str = Field(..., description="Symbol/node ID to query")
    max_depth: int = Field(3, description="Maximum traversal depth", ge=1, le=10)
    include_transitive: bool = Field(False, description="Include transitive relationships")


class GraphRelation(BaseModel):
    """Single graph relationship."""

    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    relation_type: str = Field(..., description="Relationship type (CALLS, IMPORTS, etc.)")
    source_name: str | None = Field(None, description="Source symbol name")
    target_name: str | None = Field(None, description="Target symbol name")
    path: str | None = Field(None, description="File path")


class GraphQueryOutput(BaseModel):
    """Output schema for graph_query tool."""

    success: bool = Field(..., description="Whether query succeeded")
    query_type: str = Field(..., description="Query type executed")
    relations: list[GraphRelation] = Field(default_factory=list, description="Found relationships")
    total_found: int = Field(0, description="Total relationships found")
    error: str | None = Field(None, description="Error message if failed")


# ============================================================
# RepoMap Navigation
# ============================================================


class RepoMapNavigationInput(BaseModel):
    """Input schema for repomap_navigate tool."""

    query_type: Literal["top_nodes", "search_path", "get_children", "get_ancestors"] = Field(
        ..., description="Type of navigation query"
    )
    path: str | None = Field(None, description="File/directory path (for search_path)")
    node_id: str | None = Field(None, description="Node ID (for get_children/get_ancestors)")
    limit: int = Field(20, description="Maximum results", ge=1, le=100)
    min_importance: float = Field(0.0, description="Minimum importance score", ge=0.0, le=1.0)


class RepoMapNodeInfo(BaseModel):
    """RepoMap node information."""

    node_id: str = Field(..., description="Node ID")
    kind: str = Field(..., description="Node kind (file, class, function, etc.)")
    name: str = Field(..., description="Node name")
    path: str | None = Field(None, description="File path")
    importance_score: float = Field(..., description="Importance score (0-1)")
    summary: str | None = Field(None, description="Node summary")
    children_count: int = Field(0, description="Number of children")


class RepoMapNavigationOutput(BaseModel):
    """Output schema for repomap_navigate tool."""

    success: bool = Field(..., description="Whether navigation succeeded")
    nodes: list[RepoMapNodeInfo] = Field(default_factory=list, description="Found nodes")
    total_found: int = Field(0, description="Total nodes found")
    error: str | None = Field(None, description="Error message if failed")


# ============================================================
# Impact Analysis
# ============================================================


class ImpactAnalysisInput(BaseModel):
    """Input schema for impact_analysis tool."""

    changed_symbols: list[str] = Field(..., description="List of changed symbol IDs or paths")
    change_type: Literal["modified", "deleted", "signature_changed"] = Field("modified", description="Type of change")
    max_depth: int = Field(3, description="Maximum impact depth", ge=1, le=5)


class ImpactedSymbol(BaseModel):
    """Single impacted symbol."""

    symbol_id: str = Field(..., description="Symbol ID")
    symbol_name: str = Field(..., description="Symbol name")
    file_path: str = Field(..., description="File path")
    impact_type: Literal["direct", "transitive"] = Field(..., description="Impact type")
    distance: int = Field(..., description="Distance from changed symbol")


class ImpactAnalysisOutput(BaseModel):
    """Output schema for impact_analysis tool."""

    success: bool = Field(..., description="Whether analysis succeeded")
    direct_affected: list[ImpactedSymbol] = Field(default_factory=list, description="Directly affected symbols")
    transitive_affected: list[ImpactedSymbol] = Field(default_factory=list, description="Transitively affected symbols")
    affected_files: list[str] = Field(default_factory=list, description="Affected file paths")
    total_impact: int = Field(0, description="Total affected symbols")
    error: str | None = Field(None, description="Error message if failed")


# ============================================================
# Proposal Package
# ============================================================


class ProposalPackage(BaseModel):
    """Integrated proposal package for human approval."""

    proposal_id: str = Field(..., description="Unique proposal identifier")
    title: str = Field(..., description="Proposal title")
    description: str = Field(..., description="Detailed description")

    # Changes
    changes: list[dict[str, Any]] = Field(default_factory=list, description="Proposed changes")
    diff: str = Field("", description="Unified diff of all changes")

    # Impact analysis
    impact_summary: dict[str, Any] = Field(
        default_factory=dict, description="Impact analysis summary (affected symbols, files)"
    )

    # Test plan
    test_plan: dict[str, Any] = Field(
        default_factory=dict, description="Suggested test plan (tests to run, new tests needed)"
    )

    # Risk assessment
    risk_level: Literal["low", "medium", "high"] = Field("medium", description="Overall risk level")
    risks: list[dict[str, Any]] = Field(default_factory=list, description="Identified risks")

    # Metadata
    created_at: float = Field(..., description="Creation timestamp")
    requires_approval: bool = Field(True, description="Whether approval is required")


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
