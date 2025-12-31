"""
RFC-027/028 MCP Tools (4-Point Integration: MCP Server)

SOTA L11:
- Hexagonal Architecture (MCP = Adapter)
- SOLID (Single responsibility per tool)
- Error handling (Never raise to client)
- Schema strictness (Type hints)
"""

import traceback
from typing import Any

from mcp import types
from mcp.server import Server

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

# MCP Server instance (imported from main)
server = Server("semantica-rfc")


@server.call_tool()
async def rfc_analyze(
    template_id: str,
    repo_id: str,
    snapshot_id: str = "main",
    max_paths: int = 200,
) -> list[types.TextContent]:
    """
    RFC-027 분석 실행 (MCP tool).

    Args:
        template_id: Analysis template (sql_injection, xss, etc.)
        repo_id: Repository ID
        snapshot_id: Snapshot ID
        max_paths: Max paths to analyze

    Returns:
        ResultEnvelope as formatted text
    """
    try:
        from codegraph_runtime.llm_arbitration.application import ExecuteExecutor

        executor = ExecuteExecutor()

        spec = {
            "intent": "analyze",
            "template_id": template_id,
            "scope": {"repo_id": repo_id, "snapshot_id": snapshot_id},
            "limits": {"max_paths": max_paths, "timeout_ms": 30000},
        }

        envelope = await executor.execute(spec)

        # Format result
        result_text = f"""
🎯 RFC-027 Analysis Result

Request ID: {envelope.request_id}
Summary: {envelope.summary}

Claims: {len(envelope.claims)}
"""

        for claim in envelope.claims[:5]:  # First 5
            if not claim.suppressed:
                result_text += f"""
  - {claim.type} ({claim.severity})
    Confidence: {claim.confidence:.2%} ({claim.confidence_basis.value})
"""

        result_text += f"\nEvidences: {len(envelope.evidences)}\n"
        result_text += f"Replay: {envelope.replay_ref}\n"

        return [types.TextContent(type="text", text=result_text)]

    except Exception as e:
        logger.error("rfc_analyze_failed", error=str(e), exc_info=True)
        return [
            types.TextContent(
                type="text",
                text=f"❌ Analysis failed: {str(e)}\n{traceback.format_exc()}",
            )
        ]


@server.call_tool()
async def analyze_cost(
    function_fqn: str,
    repo_id: str,
    snapshot_id: str = "main",
) -> list[types.TextContent]:
    """
    RFC-028 성능 분석 (MCP tool).

    4-Point Integration (Point 4: MCP Server).

    Args:
        function_fqn: Function FQN (e.g., "module.process_data")
        repo_id: Repository ID
        snapshot_id: Snapshot ID

    Returns:
        CostResult with complexity, verdict, evidence
    """
    try:
        from codegraph_engine.code_foundation.infrastructure.analyzers.cost import (
            CostAnalyzer,
        )
        from codegraph_runtime.llm_arbitration.infrastructure.ir_loader import (
            ContainerIRLoader,
        )

        # 1. Load IR Document
        ir_loader = ContainerIRLoader()
        ir_doc = await ir_loader.load_ir(repo_id, snapshot_id)

        if not ir_doc:
            return [
                types.TextContent(
                    type="text",
                    text=f"❌ IR Document not found: {repo_id}:{snapshot_id}\nRun indexing first.",
                )
            ]

        # 2. Analyze cost (RFC-028)
        analyzer = CostAnalyzer()
        cost_result = analyzer.analyze_function(ir_doc, function_fqn, request_id=f"mcp_{repo_id}")

        # 3. Format result
        result_text = f"""
🎯 Cost Analysis Result (RFC-028)

Function: {cost_result.function_fqn}
Complexity: {cost_result.complexity.value}
Verdict: {cost_result.verdict}
Confidence: {cost_result.confidence:.2%}

Explanation: {cost_result.explanation}

Loop Bounds:
"""

        for lb in cost_result.loop_bounds:
            result_text += f"  - Loop {lb.loop_id}: {lb.bound} ({lb.method}, {lb.confidence:.2%})\n"

        result_text += f"\nHotspots: {len(cost_result.hotspots)} locations\n"

        if cost_result.is_slow():
            result_text += "\n⚠️  Performance Warning: >= O(n²) detected!\n"

        return [types.TextContent(type="text", text=result_text)]

    except Exception as e:
        logger.error("analyze_cost_failed", error=str(e), exc_info=True)
        return [
            types.TextContent(
                type="text",
                text=f"❌ Cost analysis failed: {str(e)}\n{traceback.format_exc()}",
            )
        ]


@server.call_tool()
async def rfc_validate(spec: dict[str, Any]) -> list[types.TextContent]:
    """
    RFC-027 Spec 검증 (MCP tool).

    Args:
        spec: RetrieveSpec | AnalyzeSpec | EditSpec

    Returns:
        Validation result
    """
    try:
        from codegraph_runtime.llm_arbitration.application import ValidateExecutor

        validator = ValidateExecutor()
        result = validator.validate_spec(spec)

        if result["valid"]:
            text = "✅ Spec is valid\n"
        else:
            text = "❌ Spec is invalid\n\nErrors:\n"
            for err in result.get("errors", []):
                text += f"  - {err.get('field')}: {err.get('message')}\n"

        if result.get("warnings"):
            text += "\nWarnings:\n"
            for warn in result["warnings"]:
                text += f"  - {warn.get('field')}: {warn.get('message')}\n"

        return [types.TextContent(type="text", text=text)]

    except Exception as e:
        return [
            types.TextContent(
                type="text",
                text=f"❌ Validation failed: {str(e)}",
            )
        ]
