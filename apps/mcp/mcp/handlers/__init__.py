"""
MCP Server Handlers

SOTA MCP Protocol 도구들 (RFC-SEM-022 + RFC-052).

RFC-052: Clean Architecture with UseCases.
All graph semantics tools use RFC-052 implementation.
"""

# New SOTA tools (no external dependencies)
from .admin_tools import force_reindex
from .analyze_cost import analyze_cost
from .analyze_race import analyze_race
from .context_tools import get_context, get_definition, get_references
from .graph_semantics_tools import graph_dataflow, graph_slice
from .job_tools import job_cancel, job_result, job_status, job_submit
from .preview_tools import preview_callers, preview_impact, preview_taint_path
from .search import search  # RFC-053 Tier 0
from .verify_tools import (
    verify_finding_resolved,
    verify_no_new_findings_introduced,
    verify_patch_compile,
)

# Legacy tools removed - now handled via service layer in main.py


__all__ = [
    # RFC-053 Tier 0
    "search",  # Hybrid search (chunks + symbols)
    # Admin (Tier 2)
    "force_reindex",
    # Job (Async)
    "job_submit",
    "job_status",
    "job_result",
    "job_cancel",
    # Context
    "get_context",
    "get_definition",
    "get_references",
    # Graph Semantics (RFC-SEM-022)
    "graph_slice",
    "graph_dataflow",
    # Preview
    "preview_taint_path",
    "preview_impact",
    "preview_callers",
    # Verify (RFC-SEM-022 Verification Loop)
    "verify_patch_compile",
    "verify_finding_resolved",
    "verify_no_new_findings_introduced",
    # Analysis
    "analyze_cost",
    "analyze_race",
]
