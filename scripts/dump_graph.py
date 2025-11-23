#!/usr/bin/env python3
"""그래프 덤프 CLI"""

import asyncio
import json
import sys

from core.core.graph.call_graph import CallGraph
from core.core.schema.queries import CalleesQuery, CallersQuery
from core.core.store.factory import create_all_stores
from infra.config.logging import setup_logging

setup_logging()


async def dump_call_graph(symbol_id: str, direction: str = "both"):
    """호출 그래프 덤프"""
    node_store, edge_store, vector_store = create_all_stores()
    call_graph = CallGraph(node_store, edge_store)

    results = {}
    if direction in ["both", "in"]:
        callers_query = CallersQuery(node_id=symbol_id, depth=2)
        callers = await call_graph.get_callers(callers_query)
        results["callers"] = [
            {"node": r["node"].id, "edge": r["edge"].id} for r in callers
        ]

    if direction in ["both", "out"]:
        callees_query = CalleesQuery(node_id=symbol_id, depth=2)
        callees = await call_graph.get_callees(callees_query)
        results["callees"] = [
            {"node": r["node"].id, "edge": r["edge"].id} for r in callees
        ]

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: dump_graph.py <symbol_id> [in|out|both]", file=sys.stderr)
        sys.exit(1)

    symbol_id = sys.argv[1]
    direction = sys.argv[2] if len(sys.argv) > 2 else "both"
    asyncio.run(dump_call_graph(symbol_id, direction))

