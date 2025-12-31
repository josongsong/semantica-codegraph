"""
MCP Handler: analyze_race (RFC-028 Phase 2)

Provides race detection via MCP protocol.

Architecture:
- MCP Layer (stdio protocol)
- Reuses: ExecuteExecutor (RFC-027)
- Reuses: AnalyzeSpec (race_detection template)

Design:
- Thin wrapper over ExecuteExecutor
- No business logic (delegates to API layer)
- Returns ResultEnvelope as JSON

Usage (MCP client):
    {
        "tool": "analyze_race",
        "arguments": {
            "repo_id": "repo:semantica",
            "snapshot_id": "snap:abc123",
            "functions": ["module.Class.async_method"]
        }
    }

Response:
    {
        "request_id": "req_abc123",
        "summary": "Found 2 race conditions",
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


async def analyze_race(service: Any, arguments: dict) -> dict:
    """
    Analyze race conditions (MCP handler)

    Args:
        service: MCP service (unused, for consistency)
        arguments: MCP arguments
            - repo_id: str (repository ID)
            - snapshot_id: str (snapshot ID)
            - functions: list[str] (async function FQNs)

    Returns:
        ResultEnvelope as dict (JSON-serializable)

    Raises:
        ValueError: If arguments invalid
        NotImplementedError: If IR loading not implemented

    Example:
        >>> result = await analyze_race(None, {
        ...     "repo_id": "repo:test",
        ...     "snapshot_id": "snap:abc123",
        ...     "functions": ["module.async_func"]
        ... })
        >>> result["summary"]
        'Found 1 race conditions'
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
        "mcp_analyze_race",
        repo_id=repo_id,
        snapshot_id=snapshot_id,
        functions=len(functions),
    )

    # Create AnalyzeSpec (RFC-027 standard)
    spec = AnalyzeSpec(
        intent="analyze",
        template_id="race_detection",
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
        "mcp_analyze_race_complete",
        request_id=result["request_id"],
        claims=len(result["claims"]),
    )

    return result
