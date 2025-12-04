"""
Agent Tools

Tool-based interface for LLM agents to interact with code.

Tools:
- code_search: Search code using Semantica's multi-index system
- symbol_search: Find symbols (functions, classes) by name
- open_file: Read file contents
- get_span: Get specific line range from file
- propose_patch: Create code modification proposal
- apply_patch: Apply a proposed patch
- run_tests: Execute tests
- git: Git operations (status, diff, commit, branch, log)
- test_runner: Run pytest tests with structured results
- graph_query: Query code graph for relationships (NEW)
- repomap_navigate: Navigate repository structure (NEW)
- impact_analysis: Analyze change impact (NEW)

Architecture:
- Each tool is a self-contained class inheriting from BaseTool
- Tools use Pydantic schemas for input/output validation
- Tools integrate with Semantica Codegraph for powerful code analysis
"""

from src.contexts.agent_automation.infrastructure.tools.base import BaseTool, ToolExecutionError
from src.contexts.agent_automation.infrastructure.tools.code_search import CodeSearchTool
from src.contexts.agent_automation.infrastructure.tools.file_ops import GetSpanTool, OpenFileTool
from src.contexts.agent_automation.infrastructure.tools.git_tool import GitTool
from src.contexts.agent_automation.infrastructure.tools.graph_query_tool import GraphQueryTool
from src.contexts.agent_automation.infrastructure.tools.impact_analysis_tool import ImpactAnalysisTool
from src.contexts.agent_automation.infrastructure.tools.patch_tools import ApplyPatchTool, ProposePatchTool
from src.contexts.agent_automation.infrastructure.tools.proposal_builder import ProposalBuilder
from src.contexts.agent_automation.infrastructure.tools.repomap_navigation_tool import RepoMapNavigationTool
from src.contexts.agent_automation.infrastructure.tools.symbol_search import SymbolSearchTool
from src.contexts.agent_automation.infrastructure.tools.test_runner_tool import TestRunnerTool

__all__ = [
    "BaseTool",
    "ToolExecutionError",
    "CodeSearchTool",
    "SymbolSearchTool",
    "OpenFileTool",
    "GetSpanTool",
    "GitTool",
    "TestRunnerTool",
    "GraphQueryTool",
    "RepoMapNavigationTool",
    "ImpactAnalysisTool",
    "ProposePatchTool",
    "ApplyPatchTool",
    "ProposalBuilder",
]
