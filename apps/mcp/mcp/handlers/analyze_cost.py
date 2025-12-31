"""
MCP Handler: analyze_cost (RFC-028 Week 1 Point 4)

Provides cost analysis via MCP protocol.

Architecture:
- MCP Layer (stdio protocol)
- Reuses: ExecuteExecutor (RFC-027)
- Reuses: AnalyzeSpec (cost_complexity template)

Design:
- Thin wrapper over ExecuteExecutor
- No business logic (delegates to API layer)
- Returns ResultEnvelope as JSON

Usage (MCP client):
    {
        "tool": "analyze_cost",
        "arguments": {
            "repo_id": "repo:semantica",
            "snapshot_id": "snap:abc123",
            "functions": ["module.Class.method", "module.func"]
        }
    }

Response:
    {
        "request_id": "req_abc123",
        "summary": "Found 2 high-cost functions",
        "claims": [...],
        "evidences": [...],
        ...
    }
"""

from typing import Any

from apps.orchestrator.orchestrator.domain.rfc_specs import AnalyzeSpec, Scope
from codegraph_shared.common.observability import get_logger
from codegraph_runtime.llm_arbitration.application import ExecuteExecutor

logger = get_logger(__name__)


async def analyze_cost(service: Any, arguments: dict) -> dict:
    """
    Analyze cost complexity (MCP handler)

    Args:
        service: MCP service (unused, for consistency with other handlers)
        arguments: MCP arguments
            - repo_id: str (repository ID)
            - snapshot_id: str (snapshot ID)
            - functions: list[str] (function FQNs)

    Returns:
        ResultEnvelope as dict (JSON-serializable)

    Raises:
        ValueError: If arguments invalid
        NotImplementedError: If IR loading not implemented

    Example:
        >>> result = await analyze_cost(None, {
        ...     "repo_id": "repo:test",
        ...     "snapshot_id": "snap:abc123",
        ...     "functions": ["module.func"]
        ... })
        >>> result["summary"]
        'Analyzed 1 functions'
    """
    # Extract arguments
    repo_id = arguments.get("repo_id")
    snapshot_id = arguments.get("snapshot_id")
    functions = arguments.get("functions", [])

    # Validate
    if not repo_id:
        raise ValueError("repo_id is required")

    if not snapshot_id:
        raise ValueError("snapshot_id is required")

    if not functions:
        raise ValueError("functions is required (non-empty list)")

    if not isinstance(functions, list):
        raise ValueError(f"functions must be list, got {type(functions)}")

    logger.info(
        "mcp_analyze_cost",
        repo_id=repo_id,
        snapshot_id=snapshot_id,
        functions=len(functions),
    )

    # Create AnalyzeSpec (RFC-027 standard)
    spec = AnalyzeSpec(
        intent="analyze",
        template_id="cost_complexity",
        scope=Scope(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
        ),
        params={
            "functions": functions,
        },
    )

    # Execute via ExecuteExecutor (reuse API layer!)
    executor = ExecuteExecutor()
    envelope = await executor.execute(spec.model_dump())

    # Convert to dict (JSON-serializable)
    result = envelope.to_dict()

    logger.info(
        "mcp_analyze_cost_complete",
        request_id=result["request_id"],
        claims=len(result["claims"]),
    )

    return result
