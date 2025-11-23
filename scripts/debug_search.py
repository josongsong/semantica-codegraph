#!/usr/bin/env python3
"""검색 디버깅 CLI"""

import asyncio
import json
import sys

from core.core.schema.queries import SearchQuery, SearchType
from core.core.search.chunk_retriever import create_chunk_retriever
from core.core.search.symbol_retriever import create_symbol_retriever
from core.core.store.factory import create_all_stores
from infra.config.logging import setup_logging

setup_logging()


async def debug_search(query: str, search_type: str = "chunk"):
    """검색 디버깅"""
    node_store, edge_store, vector_store = create_all_stores()

    search_query = SearchQuery(
        query=query,
        search_type=SearchType.CHUNK if search_type == "chunk" else SearchType.SYMBOL,
        limit=10,
    )

    if search_type == "chunk":
        retriever = create_chunk_retriever(vector_store, edge_store)
    else:
        retriever = create_symbol_retriever(vector_store, edge_store)

    results = await retriever.search(search_query)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: debug_search.py <query> [chunk|symbol]", file=sys.stderr)
        sys.exit(1)

    query = sys.argv[1]
    search_type = sys.argv[2] if len(sys.argv) > 2 else "chunk"
    asyncio.run(debug_search(query, search_type))
