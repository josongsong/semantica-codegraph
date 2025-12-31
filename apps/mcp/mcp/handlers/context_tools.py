"""
Context Tools (SOTA MCP Protocol)

통합 컨텍스트 조회 도구.
LLM이 코드 컨텍스트를 효율적으로 가져올 수 있도록 지원.

Tools:
- get_context: 통합 컨텍스트 조회 (definition, usages, callers, etc.)
- get_definition: 심볼 정의 조회
- get_references: 참조 조회 (with pagination)
"""

import json
from typing import Any

from apps.mcp.mcp.config import get_context_config, get_tier_config
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

# Load configurations
CONTEXT_CONFIG = get_context_config()
TIER_0_CONFIG = get_tier_config(0)


async def get_context(arguments: dict[str, Any]) -> str:
    """
    통합 컨텍스트 조회 [RFC-053 Tier 0]

    여러 facet을 한 번에 조회하여 LLM 컨텍스트 구성.

    Args:
        arguments:
            - target: symbol_id | fqn | file:line
            - facets: list of facets to retrieve
                - definition: 심볼 정의
                - usages: 사용처
                - references: 참조
                - docstring: 문서
                - skeleton: 스켈레톤 (시그니처만)
                - tests: 관련 테스트
                - callers: 호출자
                - callees: 호출 대상
            - budget: 토큰 예산
                - max_chars: 최대 문자 수
                - max_items: 최대 아이템 수
                - max_files: 최대 파일 수

    Returns:
        JSON: {summary, facets: {definition, usages, ...}, items, meta}

    Performance (RFC-053):
        - Target: < 3s (p95)
        - Cost: Low
        - Tier: 0 (Primary entry point)
    """
    import time

    start_time = time.time()

    target = arguments.get("target")
    facets = arguments.get("facets", ["definition", "usages"])
    budget = arguments.get("budget", {})

    if not target:
        return json.dumps({"status": "error", "error": "target is required"})

    max_chars = budget.get("max_chars", CONTEXT_CONFIG.default_max_chars)
    max_items = budget.get("max_items", CONTEXT_CONFIG.default_max_items)

    result: dict[str, Any] = {
        "target": target,
        "facets": {},
        "summary": "",
        "items": [],
    }

    total_chars = 0

    # Resolve target
    target_info = await _resolve_target(target)
    if not target_info:
        return json.dumps({"status": "error", "error": f"Target not found: {target}"})

    # Fetch each facet
    for facet in facets:
        if total_chars >= max_chars:
            result["summary"] += " (budget exceeded, some facets skipped)"
            break

        facet_data = await _fetch_facet(target_info, facet, max_items)
        if facet_data:
            result["facets"][facet] = facet_data
            total_chars += len(json.dumps(facet_data))

            # Add to items for flattened access
            if isinstance(facet_data, list):
                result["items"].extend(facet_data[:5])  # Top 5 per facet
            elif isinstance(facet_data, dict):
                result["items"].append(facet_data)

    # Build summary
    facet_counts = {k: len(v) if isinstance(v, list) else 1 for k, v in result["facets"].items()}
    result["summary"] = f"Context for {target}: " + ", ".join(f"{k}({v})" for k, v in facet_counts.items())

    # RFC-053: Add metadata (from config)
    took_ms = int((time.time() - start_time) * 1000)
    result["meta"] = TIER_0_CONFIG.to_meta_dict(took_ms)

    return json.dumps(result)


async def get_definition(arguments: dict[str, Any]) -> str:
    """
    심볼 정의 조회

    Args:
        arguments:
            - symbol: 심볼 이름 또는 FQN
            - repo_id: 저장소 ID
            - snapshot_id: 스냅샷 ID
            - include_body: 본문 포함 여부 (기본 True)

    Returns:
        JSON: {found, name, file_path, line, code, type, fqn}
    """
    symbol = arguments.get("symbol")
    repo_id = arguments.get("repo_id", "")
    snapshot_id = arguments.get("snapshot_id", "main")
    include_body = arguments.get("include_body", True)

    if not symbol:
        return json.dumps({"status": "error", "error": "symbol is required"})

    try:
        from apps.orchestrator.orchestrator.adapters.context_adapter import ContextAdapter

        adapter = ContextAdapter()

        result = await adapter.get_symbol_definition(
            symbol_name=symbol,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
        )

        return json.dumps(result)

    except Exception as e:
        logger.warning("get_definition_fallback", symbol=symbol, error=str(e))

        # Fallback: use grep-based search
        return json.dumps(
            {
                "found": False,
                "name": symbol,
                "error": str(e),
            }
        )


async def get_references(arguments: dict[str, Any]) -> str:
    """
    참조 조회 (with pagination)

    Args:
        arguments:
            - symbol: 심볼 이름 또는 FQN
            - repo_id: 저장소 ID
            - snapshot_id: 스냅샷 ID
            - limit: 페이지당 최대 결과 수 (기본 50)
            - cursor: 페이지네이션 커서

    Returns:
        JSON: PagedResponse with references
    """
    symbol = arguments.get("symbol")
    repo_id = arguments.get("repo_id", "")
    snapshot_id = arguments.get("snapshot_id", "main")
    limit = arguments.get("limit", CONTEXT_CONFIG.default_limit)
    cursor = arguments.get("cursor")

    if not symbol:
        return json.dumps({"status": "error", "error": "symbol is required"})

    try:
        from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import CallGraphQueryBuilder

        query_builder = CallGraphQueryBuilder()

        # Get all references
        references = await query_builder.search_references(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            symbol_name=symbol,
            limit=limit * CONTEXT_CONFIG.reference_fetch_multiplier,
        )

        # Apply pagination
        offset = 0
        if cursor:
            from codegraph_engine.shared_kernel.contracts.pagination import decode_cursor

            offset, _ = decode_cursor(cursor)

        paginated = references[offset : offset + limit]

        # Build next cursor
        next_cursor = None
        if offset + limit < len(references):
            from codegraph_engine.shared_kernel.contracts.pagination import encode_cursor

            next_cursor = encode_cursor(offset + limit)

        # Build summary
        summary = f"Found {len(references)} references to {symbol}"
        if len(references) > limit:
            summary += f", showing {offset + 1}-{min(offset + limit, len(references))}"

        return json.dumps(
            {
                "items": paginated,
                "total": len(references),
                "limit": limit,
                "next_cursor": next_cursor,
                "summary": {"description": summary},
            }
        )

    except Exception as e:
        logger.warning("get_references_fallback", symbol=symbol, error=str(e))
        return json.dumps(
            {
                "items": [],
                "total": 0,
                "limit": limit,
                "next_cursor": None,
                "error": str(e),
            }
        )


# ============================================================
# Internal helpers
# ============================================================


async def _resolve_target(target: str) -> dict[str, Any] | None:
    """
    Resolve target to symbol info

    Formats:
    - symbol_id: "sym_abc123"
    - fqn: "module.ClassName.method_name"
    - file:line: "src/module.py:42"
    """
    if target.startswith("sym_"):
        # Symbol ID
        return {"type": "symbol_id", "id": target}

    elif ":" in target and target.rsplit(":", 1)[-1].isdigit():
        # file:line format
        parts = target.rsplit(":", 1)
        return {"type": "location", "file": parts[0], "line": int(parts[1])}

    else:
        # FQN
        return {"type": "fqn", "fqn": target}


async def _fetch_facet(target_info: dict, facet: str, max_items: int) -> Any:
    """Fetch a single facet for target"""

    try:
        if facet == "definition":
            return await _fetch_definition(target_info)
        elif facet == "usages":
            return await _fetch_usages(target_info, max_items)
        elif facet == "references":
            return await _fetch_references(target_info, max_items)
        elif facet == "callers":
            return await _fetch_callers(target_info, max_items)
        elif facet == "callees":
            return await _fetch_callees(target_info, max_items)
        elif facet == "docstring":
            return await _fetch_docstring(target_info)
        elif facet == "skeleton":
            return await _fetch_skeleton(target_info)
        elif facet == "tests":
            return await _fetch_tests(target_info, max_items)
        else:
            logger.warning("unknown_facet", facet=facet)
            return None

    except Exception as e:
        logger.warning("facet_fetch_failed", facet=facet, error=str(e))
        return {"error": str(e)}


async def _fetch_definition(target_info: dict) -> dict[str, Any]:
    """Fetch symbol definition"""
    try:
        from apps.orchestrator.orchestrator.adapters.context_adapter import ContextAdapter

        adapter = ContextAdapter()

        if target_info["type"] == "fqn":
            return await adapter.get_symbol_definition(
                symbol_name=target_info["fqn"],
                repo_id="",
                snapshot_id="main",
            )

        return {"error": "Unsupported target type for definition"}

    except Exception as e:
        return {"error": str(e)}


async def _fetch_usages(target_info: dict, max_items: int) -> list[dict]:
    """Fetch usages"""
    try:
        from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import CallGraphQueryBuilder

        query_builder = CallGraphQueryBuilder()

        if target_info["type"] == "fqn":
            return await query_builder.search_references(
                repo_id="",
                snapshot_id="main",
                symbol_name=target_info["fqn"],
                limit=max_items,
            )

        return []

    except Exception as e:
        return [{"error": str(e)}]


async def _fetch_references(target_info: dict, max_items: int) -> list[dict]:
    """Fetch references (same as usages for now)"""
    return await _fetch_usages(target_info, max_items)


async def _fetch_callers(target_info: dict, max_items: int) -> list[dict]:
    """Fetch callers"""
    try:
        from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import CallGraphQueryBuilder

        query_builder = CallGraphQueryBuilder()

        if target_info["type"] == "fqn":
            return await query_builder.search_callers(
                repo_id="",
                snapshot_id="main",
                symbol_name=target_info["fqn"],
                limit=max_items,
            )

        return []

    except Exception as e:
        return [{"error": str(e)}]


async def _fetch_callees(target_info: dict, max_items: int) -> list[dict]:
    """Fetch callees"""
    try:
        from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import CallGraphQueryBuilder

        query_builder = CallGraphQueryBuilder()

        if target_info["type"] == "fqn":
            return await query_builder.search_callees(
                repo_id="",
                snapshot_id="main",
                symbol_name=target_info["fqn"],
                limit=max_items,
            )

        return []

    except Exception as e:
        return [{"error": str(e)}]


async def _fetch_docstring(target_info: dict) -> dict[str, Any]:
    """Fetch docstring"""
    try:
        from apps.orchestrator.orchestrator.adapters.context_adapter import ContextAdapter

        adapter = ContextAdapter()

        if target_info["type"] == "fqn":
            # Get symbol definition which includes docstring
            result = await adapter.get_symbol_definition(
                symbol_name=target_info["fqn"],
                repo_id="",
                snapshot_id="main",
            )

            # Extract docstring from code if present
            code = result.get("code", "")
            docstring = _extract_docstring(code)

            return {"docstring": docstring, "found": bool(docstring)}

        return {"docstring": None, "found": False}

    except Exception as e:
        return {"docstring": None, "error": str(e)}


async def _fetch_skeleton(target_info: dict) -> dict[str, Any]:
    """Fetch skeleton (signatures only, no body)"""
    try:
        from apps.orchestrator.orchestrator.adapters.context_adapter import ContextAdapter

        adapter = ContextAdapter()

        if target_info["type"] == "fqn":
            result = await adapter.get_symbol_definition(
                symbol_name=target_info["fqn"],
                repo_id="",
                snapshot_id="main",
            )

            # Extract skeleton (first line = signature)
            code = result.get("code", "")
            skeleton = _extract_skeleton(code)

            return {
                "skeleton": skeleton,
                "file_path": result.get("file_path"),
                "line": result.get("line"),
            }

        return {"skeleton": None, "found": False}

    except Exception as e:
        return {"skeleton": None, "error": str(e)}


async def _fetch_tests(target_info: dict, max_items: int) -> list[dict]:
    """Fetch related tests"""
    try:
        from apps.orchestrator.orchestrator.adapters.context_adapter import ContextAdapter

        adapter = ContextAdapter()

        if target_info["type"] == "fqn":
            # Infer file path from FQN
            fqn = target_info["fqn"]
            # Convert module.Class.method to module.py
            parts = fqn.split(".")
            if parts:
                file_path = parts[0].replace(".", "/") + ".py"

                test_files = await adapter.get_related_tests(
                    file_path=file_path,
                    repo_id="",
                    snapshot_id="main",
                )

                return [{"file": f, "type": "test"} for f in test_files[:max_items]]

        return []

    except Exception as e:
        return [{"error": str(e)}]


# ============================================================
# String extraction helpers
# ============================================================


def _extract_docstring(code: str) -> str | None:
    """
    Extract docstring from code.

    Handles:
    - Triple-quoted strings (''' or \"\"\")
    - First docstring after def/class

    Args:
        code: Source code

    Returns:
        Docstring content or None
    """
    import re

    # Match triple-quoted docstring
    patterns = [
        r'"""(.*?)"""',  # Double quotes
        r"'''(.*?)'''",  # Single quotes
    ]

    for pattern in patterns:
        match = re.search(pattern, code, re.DOTALL)
        if match:
            docstring = match.group(1).strip()
            if docstring:
                return docstring

    return None


def _extract_skeleton(code: str) -> str | None:
    """
    Extract skeleton (signature only, no body).

    For functions: def name(args): ...
    For classes: class Name(bases): ...

    Args:
        code: Source code

    Returns:
        Signature line or None
    """
    if not code:
        return None

    lines = code.strip().split("\n")
    if not lines:
        return None

    # Get signature (first line)
    signature = lines[0].strip()

    # For multi-line signatures, collect until ':'
    if ":" not in signature:
        for i, line in enumerate(lines[1:], 1):
            signature += " " + line.strip()
            if ":" in line:
                break
            if i >= 5:  # Safety limit
                break

    # Truncate body indicator
    if signature.endswith(":"):
        signature += " ..."

    return signature
