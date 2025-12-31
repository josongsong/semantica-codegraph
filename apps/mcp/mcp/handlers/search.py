"""
Tier 0 Tool: search (Hybrid Search)

RFC-053 통합 검색 핸들러.
chunks + symbols 하이브리드 검색, mixed ranking 지원.

Architecture:
- Adapter Layer (MCP Handler)
- Delegates to MCPSearchService
- Returns JSON with mixed ranking

Performance:
- Target: < 2s (p95)
- Cost: Low
- Tier: 0 (Primary entry point)
"""

import asyncio
import json
import time
from enum import Enum
from typing import Any, TypedDict

from apps.mcp.mcp.adapters.mcp.services import MCPSearchService
from apps.mcp.mcp.config import get_search_config, get_tier_config
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

# Load configurations
SEARCH_CONFIG = get_search_config()
TIER_0_CONFIG = get_tier_config(0)


# ============================================================
# Domain Enums (Internal)
# ============================================================


class SearchType(Enum):
    """
    Search type enum (internal use).

    Values:
        CHUNKS: Search code chunks
        SYMBOLS: Search symbols (functions, classes)
        ALL: Search both chunks and symbols
    """

    CHUNKS = "chunks"
    SYMBOLS = "symbols"
    ALL = "all"


# ============================================================
# Response Schema (Type Safety)
# ============================================================


class SearchResponse(TypedDict):
    """
    Search response schema.

    Fields:
        query: Original query string
        results: Dict with chunks and/or symbols
        mixed_ranking: Unified ranked results
        took_ms: Execution time in milliseconds
        meta: Metadata (timeout, cost_hint)
    """

    query: str
    results: dict[str, list[dict]]
    mixed_ranking: list[dict]
    took_ms: int
    meta: dict[str, Any]


# ============================================================
# Handler
# ============================================================


async def search(service: MCPSearchService, arguments: dict) -> str:
    """
    Hybrid search handler (chunks + symbols).

    RFC-053 Tier 0 tool - primary entry point for code search.

    Args:
        service: MCPSearchService instance
        arguments: Tool arguments
            - query (str, required): Search query
            - types (list[str], optional): ["chunks", "symbols", "all"], default=["all"]
            - limit (int, optional): Max results, default=10
            - repo_id (str, optional): Repository ID
            - snapshot_id (str, optional): Snapshot ID

    Returns:
        JSON string with SearchResponse schema

    Raises:
        ValueError: If query is empty or invalid
        RuntimeError: If search fails

    Example:
        result = await search(service, {
            "query": "authentication logic",
            "types": ["all"],
            "limit": 10
        })

    Performance:
        - Target: < 2s (p95)
        - Timeout: 2s per search type
        - Fallback: Partial results if one type fails

    Schema:
        {
          "query": "authentication logic",
          "results": {
            "chunks": [{id, content, file_path, line, score}],
            "symbols": [{id, name, kind, file_path, line, score}]
          },
          "mixed_ranking": [{type, id, content, score, ...}],
          "took_ms": 1234,
          "meta": {
            "timeout_seconds": 2,
            "cost_hint": "low"
          }
        }
    """
    start_time = time.time()

    # ========================================
    # 1. Input Validation
    # ========================================
    query = arguments.get("query", "").strip()
    if not query:
        raise ValueError("Query parameter is required and cannot be empty")

    types_raw = arguments.get("types", ["all"])
    limit = arguments.get("limit", SEARCH_CONFIG.default_limit)
    repo_id = arguments.get("repo_id", "")
    snapshot_id = arguments.get("snapshot_id", "main")

    # Validate limit
    if not isinstance(limit, int) or limit < 1 or limit > SEARCH_CONFIG.max_limit:
        raise ValueError(f"Limit must be an integer between 1 and {SEARCH_CONFIG.max_limit}")

    # Parse search types (external string → internal enum)
    search_types = _parse_search_types(types_raw)

    # ========================================
    # 2. Execute Searches (Parallel)
    # ========================================
    results: dict[str, list[dict]] = {}

    try:
        # Determine what to search
        search_chunks = SearchType.ALL in search_types or SearchType.CHUNKS in search_types
        search_symbols = SearchType.ALL in search_types or SearchType.SYMBOLS in search_types

        # Parallel execution with timeout
        tasks = []
        if search_chunks:
            tasks.append(_search_chunks_safe(service, query, limit, repo_id, snapshot_id))
        if search_symbols:
            tasks.append(_search_symbols_safe(service, query, limit, repo_id, snapshot_id))

        # Execute with 2s timeout per task
        search_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        idx = 0
        if search_chunks:
            chunks_result = search_results[idx]
            idx += 1
            if isinstance(chunks_result, Exception):
                logger.warning(f"Chunks search failed: {chunks_result}")
                results["chunks"] = []
            else:
                results["chunks"] = chunks_result

        if search_symbols:
            symbols_result = search_results[idx]
            if isinstance(symbols_result, Exception):
                logger.warning(f"Symbols search failed: {symbols_result}")
                results["symbols"] = []
            else:
                results["symbols"] = symbols_result

    except Exception as e:
        logger.error(f"Search execution failed: {e}", query=query)
        # Graceful degradation: return empty results
        results = {"chunks": [], "symbols": []}

    # ========================================
    # 3. Mixed Ranking
    # ========================================
    mixed_ranking = _create_mixed_ranking(results, limit)

    # ========================================
    # 4. Build Response
    # ========================================
    took_ms = int((time.time() - start_time) * 1000)

    response: SearchResponse = {
        "query": query,
        "results": results,
        "mixed_ranking": mixed_ranking,
        "took_ms": took_ms,
        "meta": TIER_0_CONFIG.to_meta_dict(took_ms),  # ✅ No hardcoding
    }

    logger.info(
        f"search completed",
        query=query[:50],
        chunks_count=len(results.get("chunks", [])),
        symbols_count=len(results.get("symbols", [])),
        took_ms=took_ms,
    )

    return json.dumps(response, ensure_ascii=False, indent=2)


# ============================================================
# Internal Helpers
# ============================================================


def _parse_search_types(types_raw: Any) -> set[SearchType]:
    """
    Parse and validate search types.

    Args:
        types_raw: Raw types from arguments (list of strings)

    Returns:
        Set of SearchType enums

    Raises:
        ValueError: If invalid type provided
    """
    if not isinstance(types_raw, list):
        types_raw = ["all"]

    parsed = set()
    for t in types_raw:
        if not isinstance(t, str):
            continue

        t_lower = t.lower().strip()
        try:
            parsed.add(SearchType(t_lower))
        except ValueError:
            logger.warning(f"Invalid search type: {t}, ignoring")

    # Default to ALL if nothing valid
    if not parsed:
        parsed.add(SearchType.ALL)

    return parsed


async def _search_chunks_safe(
    service: MCPSearchService,
    query: str,
    limit: int,
    repo_id: str,
    snapshot_id: str,
) -> list[dict]:
    """
    Safe chunks search with timeout.

    Args:
        service: MCPSearchService
        query: Search query
        limit: Max results
        repo_id: Repository ID
        snapshot_id: Snapshot ID

    Returns:
        List of chunk dicts

    Raises:
        TimeoutError: If search exceeds configured timeout
        RuntimeError: If search fails
    """
    try:
        # Execute with configured timeout
        results = await asyncio.wait_for(
            service.search_chunks(query, limit, repo_id, snapshot_id),
            timeout=SEARCH_CONFIG.chunk_timeout,  # ✅ From config
        )

        # Convert SearchResult to dict
        return [r.to_dict() for r in results]

    except asyncio.TimeoutError:
        logger.warning(f"Chunks search timeout: {query}")
        raise TimeoutError("Chunks search exceeded 2s timeout")
    except Exception as e:
        logger.error(f"Chunks search failed: {e}")
        raise RuntimeError(f"Chunks search failed: {e}") from e


async def _search_symbols_safe(
    service: MCPSearchService,
    query: str,
    limit: int,
    repo_id: str,
    snapshot_id: str,
) -> list[dict]:
    """
    Safe symbols search with timeout.

    Args:
        service: MCPSearchService
        query: Search query
        limit: Max results
        repo_id: Repository ID
        snapshot_id: Snapshot ID

    Returns:
        List of symbol dicts

    Raises:
        TimeoutError: If search exceeds configured timeout
        RuntimeError: If search fails
    """
    try:
        # Execute with configured timeout
        results = await asyncio.wait_for(
            service.search_symbols(query, limit, repo_id, snapshot_id),
            timeout=SEARCH_CONFIG.symbol_timeout,  # ✅ From config
        )

        # Convert SearchResult to dict
        return [r.to_dict() for r in results]

    except asyncio.TimeoutError:
        logger.warning(f"Symbols search timeout: {query}")
        raise TimeoutError("Symbols search exceeded 2s timeout")
    except Exception as e:
        logger.error(f"Symbols search failed: {e}")
        raise RuntimeError(f"Symbols search failed: {e}") from e


def _create_mixed_ranking(results: dict[str, list[dict]], limit: int) -> list[dict]:
    """
    Create unified ranking from chunks and symbols.

    Algorithm:
    1. Collect all results with type marker
    2. Normalize scores to [0.0, 1.0]
    3. Sort by score DESC
    4. Deduplicate by (type, id)
    5. Limit to requested count

    Args:
        results: Dict with chunks and/or symbols
        limit: Max results in ranking

    Returns:
        List of ranked results with type field

    Example:
        Input: {
          "chunks": [{id: "c1", score: 0.9}],
          "symbols": [{id: "s1", score: 0.95}]
        }
        Output: [
          {type: "symbol", id: "s1", score: 0.95, ...},
          {type: "chunk", id: "c1", score: 0.9, ...}
        ]
    """
    all_results = []

    # Collect chunks
    for chunk in results.get("chunks", []):
        all_results.append(
            {
                "type": "chunk",
                **chunk,
            }
        )

    # Collect symbols
    for symbol in results.get("symbols", []):
        all_results.append(
            {
                "type": "symbol",
                **symbol,
            }
        )

    # Normalize scores (already in [0.0, 1.0] from service)
    # Sort by score DESC
    all_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    # Deduplicate by (type, id)
    seen = set()
    unique_results = []
    for result in all_results:
        key = (result.get("type"), result.get("id"))
        if key not in seen:
            seen.add(key)
            unique_results.append(result)

    # Limit
    return unique_results[:limit]
