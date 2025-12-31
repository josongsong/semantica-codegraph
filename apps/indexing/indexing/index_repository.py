"""
Index Repository UseCase

BALANCED mode indexing:
- L1: Parse & build IR (LayeredIRBuilder)
- L2: Chunk & Vector indexing (검색 가능)
- L3: Lexical indexing (Tantivy)
"""

from pathlib import Path
from typing import Protocol

from src.application.indexing.types import SemanticMode  # ✅ ENUM types
from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig, SemanticTier
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
from codegraph_engine.multi_index.domain.ports import LexicalIndexPort  # ✅ Port (abstraction)


class IndexResult(Protocol):
    """Indexing result."""

    files_processed: int
    nodes_created: int
    edges_created: int
    chunks_created: int
    duration_seconds: float


async def index_repository(
    repo_path: str | Path,
    repo_id: str,
    snapshot_id: str = "main",
    semantic_mode: SemanticMode | str = SemanticMode.FULL,  # ✅ ENUM or string (backward compat)
    parallel_workers: int = 4,
    save_to_storage: bool = True,
    lexical_index: LexicalIndexPort | None = None,  # ✅ DI (Port)
) -> IndexResult:
    """
    Index a repository using LayeredIRBuilder.

    ✅ Hexagonal Architecture:
    - Application depends on Port (LexicalIndexPort), NOT Infrastructure
    - Infrastructure injected from outside (DI)
    - Backward compatible (creates index if not provided)

    ✅ Type Safety:
    - Accepts ENUM or string (validates string → ENUM)
    - Internal logic uses ENUM only

    Args:
        repo_path: Repository path
        repo_id: Repository ID
        snapshot_id: Snapshot ID
        semantic_mode: SemanticMode ENUM or "quick"/"full" string
        parallel_workers: Number of workers
        save_to_storage: Whether to save to storage
        lexical_index: Lexical index adapter (Port). If None, creates internally.

    Returns:
        IndexResult with statistics

    Raises:
        ValueError: If semantic_mode string is invalid
    """
    from datetime import datetime

    repo_path = Path(repo_path).resolve()
    start_time = datetime.now()

    # ✅ Convert string → ENUM (if needed)
    if isinstance(semantic_mode, str):
        semantic_mode = SemanticMode.from_string(semantic_mode)

    # Scan files
    files = list(repo_path.rglob("*.py"))
    exclude_patterns = ["venv", ".venv", "node_modules", ".git", "__pycache__", "build", "dist", "benchmark"]
    files = [f for f in files if not any(pattern in str(f) for pattern in exclude_patterns)]

    # ==================================================
    # L1: Build IR (LayeredIRBuilder)
    # ==================================================
    print(f"[L1] Building IR for {len(files)} files...")

    builder = LayeredIRBuilder(project_root=repo_path, profiler=None)

    # ✅ ENUM → SemanticTier mapping (type-safe)
    tier_mapping = {
        SemanticMode.QUICK: SemanticTier.BASE,
        SemanticMode.FULL: SemanticTier.FULL,
    }
    semantic_tier = tier_mapping[semantic_mode]

    config = BuildConfig(
        semantic_tier=semantic_tier,
        occurrences=True,
        cross_file=True,
        retrieval_index=True,
        parallel_workers=parallel_workers,
    )

    result = await builder.build(files=files, config=config)
    ir_documents = result.ir_documents

    total_nodes = sum(len(doc.nodes) for doc in ir_documents.values())
    total_edges = sum(len(doc.edges) for doc in ir_documents.values())

    print(f"[L1] ✅ IR: {len(ir_documents)} files, {total_nodes:,} nodes")

    # ==================================================
    # L2: Chunk & Vector Indexing (BALANCED mode)
    # ==================================================
    chunks_created = 0
    all_chunks = []

    if save_to_storage:
        print("[L2] Building chunks & indexing...")

        from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from codegraph_engine.code_foundation.infrastructure.chunk.id_generator import ChunkIdGenerator
        from codegraph_engine.code_foundation.infrastructure.chunk.store_auto import create_auto_chunk_store
        from codegraph_shared.infra.storage.sqlite import SQLiteStore

        db_store = SQLiteStore(db_path="data/codegraph.db")
        chunk_store = create_auto_chunk_store(db_store)
        chunk_builder = ChunkBuilder(id_generator=ChunkIdGenerator())

        # Create minimal graph_doc for chunking
        from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument

        graph_doc = GraphDocument(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            graph_nodes={},
            graph_edges=[],
        )

        repo_config = {}  # Empty config for now

        for file_path_str, ir_doc in ir_documents.items():
            file_path = Path(file_path_str)

            try:
                file_text = file_path.read_text().splitlines() if file_path.exists() else []

                chunks, _, _ = chunk_builder.build(
                    repo_id=repo_id,
                    ir_doc=ir_doc,
                    graph_doc=graph_doc,
                    file_text=file_text,
                    repo_config=repo_config,
                    snapshot_id=snapshot_id,
                )
                all_chunks.extend(chunks)
            except Exception as e:
                print(f"⚠️  Chunk build failed for {file_path.name}: {e}")

        # Save chunks
        await chunk_store.save_chunks(all_chunks)
        chunks_created = len(all_chunks)

        print(f"[L2] ✅ Chunks: {chunks_created:,} saved")

        # ==================================================
        # L3: Lexical Indexing (Tantivy) - SOTA Batch Mode
        # ✅ Hexagonal Architecture: Use injected Port or create internally
        # ==================================================
        print("[L3] Lexical indexing (Tantivy)...")

        try:
            # Import Port types (Domain Layer)
            from codegraph_engine.multi_index.domain.ports import (
                FileToIndex,
                IndexingMode,
            )

            # ✅ Use injected adapter (DI) or create internally (backward compat)
            index_adapter = lexical_index
            if index_adapter is None:
                # Fallback: Create Infrastructure implementation internally
                from codegraph_engine.multi_index.infrastructure.lexical.tantivy import TantivyCodeIndex

                index_adapter = TantivyCodeIndex(
                    index_dir="data/tantivy_index",
                    chunk_store=chunk_store,
                    mode=IndexingMode.AGGRESSIVE,  # SOTA performance
                    batch_size=100,  # 100 files per batch
                )

            # Collect unique files to index
            files_to_index: list[FileToIndex] = []
            indexed_file_paths = set()

            for chunk in all_chunks:
                if chunk.file_path and chunk.file_path not in indexed_file_paths:
                    file_path = Path(chunk.file_path)
                    if file_path.exists():
                        try:
                            content = file_path.read_text(errors="ignore")
                            files_to_index.append(
                                FileToIndex(
                                    repo_id=repo_id,
                                    file_path=str(file_path),
                                    content=content,
                                )
                            )
                            indexed_file_paths.add(chunk.file_path)
                        except Exception as e:
                            print(f"⚠️  Failed to read {file_path}: {e}")

            # Batch index all files
            if files_to_index:
                indexing_result = await index_adapter.index_files_batch(files_to_index, fail_fast=False)

                if indexing_result.failed_files:
                    print(f"⚠️  {len(indexing_result.failed_files)} files failed:")
                    for failed_path, error in indexing_result.failed_files[:5]:  # Show first 5
                        print(f"   - {failed_path}: {error}")

                print(
                    f"[L3] ✅ Lexical: {indexing_result.success_count}/{indexing_result.total_files} files indexed "
                    f"in {indexing_result.duration_seconds:.1f}s ({indexing_result.total_files / indexing_result.duration_seconds:.1f} files/s)"
                )
            else:
                print("[L3] ⚠️  No files to index")

        except Exception as e:
            print(f"[L3] ⚠️  Lexical indexing skipped: {e}")
    else:
        chunks_created = 0

    # Cleanup
    await builder.shutdown()

    # ✅ Close lexical index (resource cleanup)
    if lexical_index is not None:
        try:
            await lexical_index.close()
        except Exception as e:
            print(f"⚠️  Failed to close lexical index: {e}")

    duration = (datetime.now() - start_time).total_seconds()

    # Return result
    class Result:
        pass

    result_obj = Result()
    result_obj.files_processed = len(ir_documents)
    result_obj.nodes_created = total_nodes
    result_obj.edges_created = total_edges
    result_obj.chunks_created = chunks_created
    result_obj.duration_seconds = duration

    return result_obj
