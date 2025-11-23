#!/usr/bin/env python3
"""저장소 전체 인덱싱 CLI"""

import asyncio
import sys
from pathlib import Path

from core.core.indexing import (
    FileParser,
    build_chunk_nodes,
    build_file_node,
    build_file_symbol_edges,
    build_hierarchical_chunks,
    compute_file_hash,
    get_default_config,
    persist_all,
    walk_repository,
)
from core.core.store.factory import create_all_stores
from infra.config.logging import setup_logging

setup_logging()


async def index_repository(repo_path: str):
    """저장소 인덱싱"""
    config = get_default_config()
    node_store, edge_store, vector_store = create_all_stores()

    all_nodes = []
    all_edges = []

    for file_path, language in walk_repository(repo_path, config):
        lang_config = config.get_language_config(language)
        if not lang_config:
            continue

        # 파일 읽기
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)
            continue

        # 파일 노드 생성
        file_hash = compute_file_hash(content)
        file_node = build_file_node(file_path, content, file_hash)
        all_nodes.append(file_node)

        # 파싱
        parser = FileParser(lang_config)
        symbol_nodes, symbol_edges = parser.parse(file_path, content)
        all_nodes.extend(symbol_nodes)
        all_edges.extend(symbol_edges)

        # 파일-심볼 엣지
        file_symbol_edges = build_file_symbol_edges(file_node, symbol_nodes)
        all_edges.extend(file_symbol_edges)

        # 청크 생성
        chunk_nodes = build_chunk_nodes(
            file_node.id, content, lang_config.chunk_size, lang_config.chunk_overlap
        )
        hierarchical_chunks = build_hierarchical_chunks(chunk_nodes)
        all_nodes.extend(hierarchical_chunks)

        # 파일-청크 엣지
        from core.core.indexing.build_edges import build_file_chunk_edges

        file_chunk_edges = build_file_chunk_edges(file_node, hierarchical_chunks)
        all_edges.extend(file_chunk_edges)

    # 저장
    await persist_all(all_nodes, all_edges, node_store, edge_store, vector_store)
    print(f"Indexed {len(all_nodes)} nodes and {len(all_edges)} edges")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: index_repo.py <repo_path>", file=sys.stderr)
        sys.exit(1)

    repo_path = sys.argv[1]
    asyncio.run(index_repository(repo_path))
