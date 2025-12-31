#!/usr/bin/env python3
"""
Index a test repository for integration testing.

This script indexes a specified directory (typically src/retriever)
into all required indexes:
- Symbol index (Kuzu)
- Vector index (Qdrant)
- Lexical index (Zoekt)
- Graph store (Kuzu)

Usage:
    python scripts/index_test_repo.py <repo_path>

Example:
    python scripts/index_test_repo.py src/retriever
"""

import asyncio
import sys
from pathlib import Path

from src.container import Container
from src.foundation.chunk.git_loader import GitFileLoader
from src.foundation.chunk.models import Chunk


async def index_repository(
    repo_path: Path,
    repo_id: str = "test_repo",
) -> dict[str, int]:
    """
    Index a repository into all indexes.

    Args:
        repo_path: Path to the repository to index
        repo_id: Repository identifier

    Returns:
        Statistics: {chunks, symbols, vectors, lexical}
    """
    print(f"🚀 Starting indexing of {repo_path}")
    print(f"   Repository ID: {repo_id}")

    # Initialize DI container
    container = Container()
    container.wire(modules=[__name__])

    # Get services
    chunk_builder = container.chunk_builder()
    graph_builder = container.graph_builder()
    index_factory = container.index_factory()
    container.indexing_service()

    # Step 1: Load files from repository
    print(f"\n📂 Step 1: Loading files from {repo_path}")
    GitFileLoader(repo_path=str(repo_path))

    files = []
    for file_path in repo_path.rglob("*.py"):
        if "__pycache__" in str(file_path) or "test_" in file_path.name:
            continue  # Skip cache and test files

        rel_path = file_path.relative_to(repo_path)
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        files.append(
            {
                "file_path": str(rel_path),
                "content": content,
                "language": "python",
            }
        )

    print(f"   ✅ Loaded {len(files)} Python files")

    # Step 2: Build chunks
    print("\n🧩 Step 2: Building chunks")
    all_chunks: list[Chunk] = []

    for file_info in files:
        try:
            chunks = chunk_builder.build_chunks(
                file_path=file_info["file_path"],
                content=file_info["content"],
                language=file_info["language"],
                repo_id=repo_id,
            )
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"   ⚠️  Failed to chunk {file_info['file_path']}: {e}")
            continue

    print(f"   ✅ Built {len(all_chunks)} chunks")

    # Step 3: Build graph
    print("\n🕸️  Step 3: Building graph")
    try:
        graph = graph_builder.build_graph(chunks=all_chunks, repo_id=repo_id)
        print(f"   ✅ Built graph with {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    except Exception as e:
        print(f"   ⚠️  Failed to build graph: {e}")
        graph = None

    # Step 4: Index chunks into all indexes
    print("\n📇 Step 4: Indexing into all indexes")

    # Get index adapters
    symbol_index = index_factory.get_symbol_index()
    vector_index = index_factory.get_vector_index()
    lexical_index = index_factory.get_lexical_index()

    # Index symbols
    print("   📍 Indexing into symbol index...")
    symbol_count = 0
    for chunk in all_chunks:
        if chunk.symbol_id:
            try:
                await symbol_index.index_chunk(chunk)
                symbol_count += 1
            except Exception as e:
                print(f"      ⚠️  Failed to index symbol {chunk.symbol_id}: {e}")

    print(f"   ✅ Indexed {symbol_count} symbols")

    # Index vectors
    print("   🔢 Indexing into vector index...")
    vector_count = 0
    for chunk in all_chunks:
        try:
            await vector_index.index_chunk(chunk)
            vector_count += 1
        except Exception as e:
            print(f"      ⚠️  Failed to index vector for {chunk.chunk_id}: {e}")

    print(f"   ✅ Indexed {vector_count} vectors")

    # Index lexical
    print("   📝 Indexing into lexical index...")
    lexical_count = 0
    for chunk in all_chunks:
        try:
            await lexical_index.index_chunk(chunk)
            lexical_count += 1
        except Exception as e:
            print(f"      ⚠️  Failed to index lexical for {chunk.chunk_id}: {e}")

    print(f"   ✅ Indexed {lexical_count} lexical entries")

    # Index graph (if available)
    if graph:
        print("   🕸️  Indexing graph...")
        graph_store = container.graph_store()
        try:
            await graph_store.store_graph(graph, repo_id=repo_id)
            print(f"   ✅ Indexed graph ({len(graph.nodes)} nodes, {len(graph.edges)} edges)")
        except Exception as e:
            print(f"      ⚠️  Failed to index graph: {e}")

    # Step 5: Summary
    print("\n✅ Indexing complete!")
    print("\n📊 Summary:")
    print(f"   - Files: {len(files)}")
    print(f"   - Chunks: {len(all_chunks)}")
    print(f"   - Symbols: {symbol_count}")
    print(f"   - Vectors: {vector_count}")
    print(f"   - Lexical: {lexical_count}")
    if graph:
        print(f"   - Graph nodes: {len(graph.nodes)}")
        print(f"   - Graph edges: {len(graph.edges)}")

    return {
        "files": len(files),
        "chunks": len(all_chunks),
        "symbols": symbol_count,
        "vectors": vector_count,
        "lexical": lexical_count,
        "graph_nodes": len(graph.nodes) if graph else 0,
        "graph_edges": len(graph.edges) if graph else 0,
    }


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/index_test_repo.py <repo_path>")
        print("\nExample:")
        print("  python scripts/index_test_repo.py src/retriever")
        sys.exit(1)

    repo_path = Path(sys.argv[1])

    if not repo_path.exists():
        print(f"❌ Error: Repository path does not exist: {repo_path}")
        sys.exit(1)

    if not repo_path.is_dir():
        print(f"❌ Error: Not a directory: {repo_path}")
        sys.exit(1)

    try:
        await index_repository(repo_path)
        print(f"\n✅ Successfully indexed {repo_path}")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error during indexing: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
