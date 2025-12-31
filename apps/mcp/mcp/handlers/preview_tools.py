"""
Preview Tools (SOTA MCP Protocol)

경량 프리뷰 도구.
Heavy 분석 전에 빠르게 (1-2초) 존재성/대표 샘플을 확인.

Tools:
- preview_taint_path: Taint 경로 프리뷰
- preview_impact: Impact 프리뷰
- preview_callers: 호출자 프리뷰
"""

import json
from typing import Any

from apps.mcp.mcp.config import get_preview_config
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

# Load configuration
PREVIEW_CONFIG = get_preview_config()


async def preview_taint_path(arguments: dict[str, Any]) -> str:
    """
    Taint 경로 프리뷰

    Heavy taint 분석 전에 경로 존재 여부와 대표 샘플을 빠르게 확인.

    Args:
        arguments:
            - source_pattern: Source 패턴 (정규식 또는 FQN)
            - sink_pattern: Sink 패턴 (정규식 또는 FQN)
            - repo_id: 저장소 ID
            - snapshot_id: 스냅샷 ID
            - limit: 최대 경로 수 (기본 5)

    Returns:
        JSON: {exists, sample_paths, estimated_total, recommendation}

    Performance:
        Target: 1-2초 (정확도보다 속도 우선)
    """
    source_pattern = arguments.get("source_pattern")
    sink_pattern = arguments.get("sink_pattern")
    repo_id = arguments.get("repo_id", "")
    snapshot_id = arguments.get("snapshot_id", "main")
    limit = arguments.get("limit", PREVIEW_CONFIG.default_limit)

    if not source_pattern or not sink_pattern:
        return json.dumps(
            {
                "status": "error",
                "error": "source_pattern and sink_pattern are required",
            }
        )

    try:
        from codegraph_engine.reasoning_engine.application.reasoning_pipeline import ReasoningPipeline

        pipeline = ReasoningPipeline()

        # Fast mode: limited depth, early termination
        result = pipeline.analyze_taint_fast(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            sources=[source_pattern],
            sinks=[sink_pattern],
        )

        paths = result.get("paths", [])
        num_paths = len(paths)

        return json.dumps(
            {
                "exists": num_paths > 0,
                "sample_paths": paths[:limit],
                "estimated_total": num_paths,
                "performance_ms": result.get("performance", {}).get("total_time_ms", 0),
                "recommendation": _get_taint_recommendation(num_paths),
            }
        )

    except Exception as e:
        logger.warning("preview_taint_fallback", error=str(e))

        # Fallback: heuristic check
        return json.dumps(
            {
                "exists": None,  # Unknown
                "sample_paths": [],
                "estimated_total": None,
                "error": str(e),
                "recommendation": "Run full analysis to confirm",
            }
        )


async def preview_impact(arguments: dict[str, Any]) -> str:
    """
    Impact 프리뷰

    변경 영향도를 빠르게 근사.

    Args:
        arguments:
            - changed_symbols: 변경된 심볼 FQN 목록
            - repo_id: 저장소 ID
            - snapshot_id: 스냅샷 ID
            - top_k: 상위 영향 심볼 수 (기본 20)

    Returns:
        JSON: {affected_count, top_affected, risk_level, recommendation}

    Performance:
        Target: 1-2초 (콜그래프/의존 그래프 기반 근사)
    """
    changed_symbols = arguments.get("changed_symbols", [])
    repo_id = arguments.get("repo_id", "")
    snapshot_id = arguments.get("snapshot_id", "main")
    top_k = arguments.get("top_k", PREVIEW_CONFIG.default_top_k_callers)

    if not changed_symbols:
        return json.dumps(
            {
                "status": "error",
                "error": "changed_symbols is required",
            }
        )

    try:
        # Fast heuristic: count direct callers for each changed symbol
        from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import CallGraphQueryBuilder

        query_builder = CallGraphQueryBuilder()

        all_callers: list[dict] = []
        for symbol in changed_symbols:
            callers = await query_builder.search_callers(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                symbol_name=symbol,
                limit=top_k,
            )
            all_callers.extend(callers)

        # Deduplicate by file
        affected_files = set()
        for caller in all_callers:
            if "file_path" in caller:
                affected_files.add(caller["file_path"])

        # Risk assessment
        risk_level = _assess_risk(len(all_callers), len(affected_files))

        return json.dumps(
            {
                "affected_count": len(all_callers),
                "affected_files": len(affected_files),
                "top_affected": all_callers[:top_k],
                "risk_level": risk_level,
                "recommendation": _get_impact_recommendation(risk_level),
            }
        )

    except Exception as e:
        logger.warning("preview_impact_fallback", error=str(e))

        return json.dumps(
            {
                "affected_count": None,
                "top_affected": [],
                "risk_level": "unknown",
                "error": str(e),
                "recommendation": "Run full impact analysis",
            }
        )


async def preview_callers(arguments: dict[str, Any]) -> str:
    """
    호출자 프리뷰

    전체 콜그래프 탐색 전에 상위 호출자만 빠르게 조회.

    Args:
        arguments:
            - symbol: 심볼 FQN
            - depth: 탐색 깊이 (기본 2)
            - top_k: 상위 결과 수 (기본 50)
            - repo_id: 저장소 ID
            - snapshot_id: 스냅샷 ID

    Returns:
        JSON: {callers, by_module, estimated_total, has_more}

    Performance:
        Target: <1초
    """
    symbol = arguments.get("symbol")
    depth = arguments.get("depth", 2)
    top_k = arguments.get("top_k", PREVIEW_CONFIG.default_top_k_impact)
    repo_id = arguments.get("repo_id", "")
    snapshot_id = arguments.get("snapshot_id", "main")

    if not symbol:
        return json.dumps(
            {
                "status": "error",
                "error": "symbol is required",
            }
        )

    try:
        from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import CallGraphQueryBuilder

        query_builder = CallGraphQueryBuilder()

        callers = await query_builder.search_callers(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            symbol_name=symbol,
            limit=top_k * PREVIEW_CONFIG.fetch_multiplier,
        )

        # Group by module
        by_module: dict[str, int] = {}
        for caller in callers:
            module = caller.get("module", caller.get("file_path", "unknown").split("/")[0])
            by_module[module] = by_module.get(module, 0) + 1

        # Sort modules by count
        sorted_modules = sorted(by_module.items(), key=lambda x: x[1], reverse=True)

        has_more = len(callers) >= top_k * PREVIEW_CONFIG.fetch_multiplier

        return json.dumps(
            {
                "callers": callers[:top_k],
                "by_module": dict(sorted_modules[:10]),  # Top 10 modules
                "estimated_total": len(callers) if not has_more else f"{len(callers)}+",
                "has_more": has_more,
            }
        )

    except Exception as e:
        logger.warning("preview_callers_fallback", error=str(e))

        return json.dumps(
            {
                "callers": [],
                "by_module": {},
                "estimated_total": None,
                "error": str(e),
            }
        )


# ============================================================
# Internal helpers
# ============================================================


def _get_taint_recommendation(num_paths: int) -> str:
    """Get recommendation based on taint path count"""
    if num_paths == 0:
        return "No taint paths found. Safe to proceed."
    elif num_paths <= 5:
        return "Few paths found. Review manually."
    elif num_paths <= 20:
        return "Moderate paths. Run full analysis recommended."
    else:
        return "Many paths found. Critical review required."


def _assess_risk(caller_count: int, file_count: int) -> str:
    """Assess risk level based on impact"""
    if caller_count == 0:
        return "low"
    elif caller_count <= 10 and file_count <= 3:
        return "low"
    elif caller_count <= 50 and file_count <= 10:
        return "medium"
    elif caller_count <= 100:
        return "high"
    else:
        return "critical"


def _get_impact_recommendation(risk_level: str) -> str:
    """Get recommendation based on risk level"""
    recommendations = {
        "low": "Low impact. Safe to proceed with changes.",
        "medium": "Medium impact. Review affected files before proceeding.",
        "high": "High impact. Require careful review and testing.",
        "critical": "Critical impact. Consider breaking into smaller changes.",
        "unknown": "Run full impact analysis to assess risk.",
    }
    return recommendations.get(risk_level, recommendations["unknown"])
