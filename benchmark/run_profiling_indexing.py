#!/usr/bin/env python3
"""
Run Indexing Performance Benchmark with Detailed IR Breakdown

Profiles the complete indexing pipeline with granular IR generation phases.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.profiler import IndexingProfiler
from benchmark.report_generator import ReportGenerator


def scan_repository(profiler: IndexingProfiler, repo_path: Path):
    """
    Scan repository for files.

    Args:
        profiler: Profiler instance
        repo_path: Path to repository
    """
    profiler.start_phase("scan_files")

    # Simple file scanner
    python_files = list(repo_path.rglob("*.py"))

    # Filter out common exclude patterns
    exclude_patterns = ["venv", ".venv", "node_modules", ".git", "__pycache__", "build", "dist"]
    python_files = [f for f in python_files if not any(pattern in str(f) for pattern in exclude_patterns)]

    profiler.record_counter("files_found", len(python_files))
    profiler.end_phase("scan_files")

    return python_files


async def process_file(
    profiler: IndexingProfiler,
    file_path: Path,
    repo_path: Path,
    container,
    skip_storage: bool = False,
    skip_ir_detail: bool = False,
    skip_embedding: bool = False,
    storage_errors: dict = None,
):
    """
    Process a single file through the complete indexing pipeline.

    Args:
        profiler: Profiler instance
        file_path: Path to file
        repo_path: Repository root path
        container: DI Container for infrastructure access
        skip_storage: Skip storage phases
        skip_ir_detail: Skip detailed IR profiling

    Returns:
        dict: Timing information for each phase
    """
    import time

    from src.contexts.code_foundation.infrastructure.chunk.builder import ChunkBuilder
    from src.contexts.code_foundation.infrastructure.chunk.id_generator import ChunkIdGenerator
    from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
    from src.contexts.code_foundation.infrastructure.graph.builder import GraphBuilder
    from src.contexts.code_foundation.infrastructure.parsing.ast_tree import AstTree
    from src.contexts.code_foundation.infrastructure.parsing.source_file import SourceFile
    from src.contexts.code_foundation.infrastructure.semantic_ir import DefaultSemanticIrBuilder
    from src.contexts.code_foundation.infrastructure.symbol_graph import SymbolGraphBuilder

    relative_path = str(file_path.relative_to(repo_path))

    # Track timings for this file
    timings = {
        "parse": 0.0,
        "ir_generation": 0.0,
        "semantic_ir": 0.0,
        "graph_build": 0.0,
        "symbol_graph": 0.0,
        "chunk_build": 0.0,
        "chunk_store": 0.0,
        "graph_store": 0.0,
        "vector_store": 0.0,
        "lexical_store": 0.0,
        "symbol_store": 0.0,
    }

    try:
        # Read source
        source_code = file_path.read_text(encoding="utf-8")
        loc = len(source_code.split("\n"))

        # Phase 1: Parse
        parse_start = time.perf_counter()

        source_file = SourceFile.from_content(file_path=relative_path, content=source_code, language="python")
        AstTree.parse(source_file)

        parse_time_ms = (time.perf_counter() - parse_start) * 1000
        timings["parse"] = parse_time_ms

        # Phase 2: IR Generation
        ir_gen_start = time.perf_counter()
        ir_generator = PythonIRGenerator(repo_id=profiler.repo_id)

        if not skip_ir_detail:
            # Detailed IR profiling with instrumentation
            original_traverse = ir_generator._traverse_ast

            ir_timings = {
                "ast_traverse": 0,
                "call_analysis": 0,
                "variable_analysis": 0,
                "signature": 0,
                "other": 0,
            }

            # Wrap _traverse_ast
            def timed_traverse(node):
                start = time.perf_counter()
                result = original_traverse(node)
                ir_timings["ast_traverse"] += (time.perf_counter() - start) * 1000
                return result

            ir_generator._traverse_ast = timed_traverse

            # Try to wrap call analyzer if available
            if hasattr(ir_generator, "_call_analyzer"):
                call_analyzer = ir_generator._call_analyzer
                if hasattr(call_analyzer, "process_calls_in_block"):
                    original_process_calls = call_analyzer.process_calls_in_block

                    def timed_process_calls(*args, **kwargs):
                        start = time.perf_counter()
                        result = original_process_calls(*args, **kwargs)
                        ir_timings["call_analysis"] += (time.perf_counter() - start) * 1000
                        return result

                    call_analyzer.process_calls_in_block = timed_process_calls

            # Try to wrap variable analyzer
            if hasattr(ir_generator, "_variable_analyzer"):
                var_analyzer = ir_generator._variable_analyzer
                if hasattr(var_analyzer, "process_variables_in_block"):
                    original_process_variables = var_analyzer.process_variables_in_block

                    def timed_process_variables(*args, **kwargs):
                        start = time.perf_counter()
                        result = original_process_variables(*args, **kwargs)
                        ir_timings["variable_analysis"] += (time.perf_counter() - start) * 1000
                        return result

                    var_analyzer.process_variables_in_block = timed_process_variables

            # Try to wrap signature builder
            if hasattr(ir_generator, "_signature_builder"):
                sig_builder = ir_generator._signature_builder
                if hasattr(sig_builder, "build_signature"):
                    original_build_signature = sig_builder.build_signature

                    def timed_build_signature(*args, **kwargs):
                        start = time.perf_counter()
                        result = original_build_signature(*args, **kwargs)
                        ir_timings["signature"] += (time.perf_counter() - start) * 1000
                        return result

                    sig_builder.build_signature = timed_build_signature

        # Generate IR
        ir_doc = ir_generator.generate(source_file, snapshot_id="bench-snapshot")
        ir_gen_time_ms = (time.perf_counter() - ir_gen_start) * 1000
        timings["ir_generation"] = ir_gen_time_ms

        if not skip_ir_detail:
            # Calculate "other" time (includes parsing inside generate)
            measured_time = sum(ir_timings.values())
            ir_timings["other"] = max(0, ir_gen_time_ms - measured_time)

            # Record IR sub-phases as counters
            profiler.record_counter(f"ir_ast_traverse_ms:{relative_path}", ir_timings["ast_traverse"])
            profiler.record_counter(f"ir_call_analysis_ms:{relative_path}", ir_timings["call_analysis"])
            profiler.record_counter(f"ir_variable_analysis_ms:{relative_path}", ir_timings["variable_analysis"])
            profiler.record_counter(f"ir_signature_ms:{relative_path}", ir_timings["signature"])
            profiler.record_counter(f"ir_other_ms:{relative_path}", ir_timings["other"])

        # Phase 3: Semantic IR
        semantic_start = time.perf_counter()

        semantic_builder = DefaultSemanticIrBuilder()
        semantic_snapshot, _ = semantic_builder.build_full(ir_doc)

        semantic_time_ms = (time.perf_counter() - semantic_start) * 1000
        timings["semantic_ir"] = semantic_time_ms

        # Phase 4: Graph Building
        graph_start = time.perf_counter()

        graph_builder = GraphBuilder()
        graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

        graph_time_ms = (time.perf_counter() - graph_start) * 1000
        timings["graph_build"] = graph_time_ms

        # Phase 5: SymbolGraph Building
        symbol_start = time.perf_counter()

        symbol_builder = SymbolGraphBuilder()
        symbol_graph = symbol_builder.build_from_graph(graph_doc)

        symbol_time_ms = (time.perf_counter() - symbol_start) * 1000
        timings["symbol_graph"] = symbol_time_ms

        # Phase 6: Chunk Building
        chunk_start = time.perf_counter()

        id_generator = ChunkIdGenerator()
        chunk_builder = ChunkBuilder(id_generator)
        file_lines = source_code.split("\n")
        chunks, chunk_to_ir, chunk_to_graph = chunk_builder.build(
            repo_id=profiler.repo_id,
            ir_doc=ir_doc,
            graph_doc=graph_doc,
            file_text=file_lines,
            repo_config={},
            snapshot_id="bench-snapshot",
        )

        chunk_time_ms = (time.perf_counter() - chunk_start) * 1000
        timings["chunk_build"] = chunk_time_ms

        # Storage phases (skip if requested)
        chunk_store_time_ms = 0
        graph_store_time_ms = 0
        vector_store_time_ms = 0
        lexical_store_time_ms = 0
        symbol_store_time_ms = 0

        if not skip_storage:
            # Phase 7: Store Chunks (PostgreSQL)
            chunk_store_start = time.perf_counter()

            try:
                await container.chunk_store.save_chunks(chunks)
                chunk_store_time_ms = (time.perf_counter() - chunk_store_start) * 1000
                profiler.increment_counter("chunk_store_success", 1)
            except Exception as e:
                error_msg = str(e)
                print(f"  ✗ Chunk store failed for {relative_path}: {error_msg}")
                chunk_store_time_ms = 0
                profiler.increment_counter("chunk_store_failed", 1)
                if storage_errors is not None and "chunk_store" not in storage_errors:
                    storage_errors["chunk_store"] = error_msg

            timings["chunk_store"] = chunk_store_time_ms

            # Phase 8: Store Graph (Memgraph)
            graph_store_start = time.perf_counter()

            try:
                # Use save_graph instead of individual upsert calls
                await container.graph_store.save_graph(graph_doc, mode="upsert")

                graph_store_time_ms = (time.perf_counter() - graph_store_start) * 1000
                profiler.increment_counter("graph_store_success", 1)
                profiler.increment_counter("graph_nodes_stored", len(graph_doc.graph_nodes))
                profiler.increment_counter("graph_edges_stored", len(graph_doc.graph_edges))
            except Exception as e:
                error_msg = str(e)
                print(f"  ✗ Graph store failed for {relative_path}: {error_msg}")
                graph_store_time_ms = 0
                profiler.increment_counter("graph_store_failed", 1)
                if storage_errors is not None and "graph_store" not in storage_errors:
                    storage_errors["graph_store"] = error_msg

            timings["graph_store"] = graph_store_time_ms

            # Phase 9: Generate Embeddings & Store Vectors (Qdrant) - SKIPPED
            # TODO: Fix import path and implement proper vector indexing
            vector_store_time_ms = 0
            timings["vector_store"] = vector_store_time_ms

            # Phase 10: Index Lexical (Zoekt) - SKIPPED
            # TODO: Implement proper lexical indexing API
            lexical_store_time_ms = 0
            timings["lexical_store"] = lexical_store_time_ms

            # Phase 11: Index Symbols (Memgraph) - SKIPPED
            # TODO: Implement proper symbol indexing API
            symbol_store_time_ms = 0
            timings["symbol_store"] = symbol_store_time_ms

        # Total build time
        build_time_ms = ir_gen_time_ms + semantic_time_ms + graph_time_ms + symbol_time_ms + chunk_time_ms

        # Total store time
        store_time_ms = (
            chunk_store_time_ms
            + graph_store_time_ms
            + vector_store_time_ms
            + lexical_store_time_ms
            + symbol_store_time_ms
        )

        # Record file metrics
        profiler.record_file(
            file_path=relative_path,
            language="python",
            loc=loc,
            parse_time_ms=parse_time_ms,
            build_time_ms=build_time_ms,
            store_time_ms=store_time_ms,
            nodes=len(ir_doc.nodes),
            edges=len(ir_doc.edges),
            chunks=len(chunks),
            symbols=symbol_graph.symbol_count,
        )

        # Update global counters
        profiler.increment_counter("files_parsed", 1)
        profiler.increment_counter("nodes_created", len(ir_doc.nodes))
        profiler.increment_counter("edges_created", len(ir_doc.edges))
        profiler.increment_counter("chunks_created", len(chunks))
        profiler.increment_counter("symbols_created", symbol_graph.symbol_count)
        profiler.increment_counter("chunks_stored", len(chunks))
        profiler.increment_counter("vectors_stored", len(chunks))

        # Store phase timings
        if not hasattr(profiler, "_store_timings"):
            profiler._store_timings = {
                "chunk_store": [],
                "graph_store": [],
                "vector_store": [],
                "lexical_store": [],
                "symbol_store": [],
            }

        profiler._store_timings["chunk_store"].append(chunk_store_time_ms)
        profiler._store_timings["graph_store"].append(graph_store_time_ms)
        profiler._store_timings["vector_store"].append(vector_store_time_ms)
        profiler._store_timings["lexical_store"].append(lexical_store_time_ms)
        profiler._store_timings["symbol_store"].append(symbol_store_time_ms)

    except Exception as e:
        import traceback as tb

        error_type = "unknown_error"
        phase = "unknown"

        if "parse" in str(e).lower():
            error_type = "parsing_error"
            phase = "parse"
        else:
            error_type = "build_error"
            phase = "build"

        profiler.record_failed_file(
            file_path=relative_path,
            error_type=error_type,
            error_message=str(e),
            phase=phase,
            traceback=tb.format_exc(),
        )

        print(f"Error processing {relative_path}: [{error_type}] {e}")
        profiler.increment_counter("files_failed", 1)

        return None

    return timings


async def run_indexing_benchmark(
    repo_path: str,
    output_path: str | None = None,
    skip_health_check: bool = False,
    skip_storage: bool = False,
    skip_repomap: bool = False,
    skip_ir_detail: bool = False,
    skip_embedding: bool = False,
):
    """
    Run complete indexing benchmark with detailed IR breakdown.

    Args:
        repo_path: Path to repository to index
        output_path: Optional output path for report
        skip_health_check: Skip infrastructure health check
        skip_storage: Skip storage phases (PostgreSQL, Qdrant, etc.)
        skip_repomap: Skip RepoMap building
        skip_ir_detail: Skip detailed IR profiling (faster but less detailed)
    """
    import time
    from datetime import datetime

    repo_path = Path(repo_path).resolve()
    repo_id = repo_path.name

    # Auto-generate output path if not provided
    if output_path is None:
        timestamp = time.strftime("%H%M%S")
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_dir = Path("benchmark/reports") / repo_id / date_str
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{timestamp}_detailed_report.txt")

    # Print benchmark profile
    print("=" * 80)
    print("벤치마크 프로필".center(80))
    print("=" * 80)
    print(f"Repository: {repo_path}")
    print(f"Repository ID: {repo_id}")
    print(f"Output: {output_path}")
    print()

    print("프로파일링 대상:")
    print("  ✓ Parse (AST)")
    print("  ✓ IR Generation")
    if not skip_ir_detail:
        print("    - AST Traverse (상세)")
        print("    - Call Analysis (상세)")
        print("    - Variable Analysis (상세)")
        print("    - Signature Building (상세)")
    else:
        print("    - 전체 (통합)")
    print("  ✓ Semantic IR")
    print("  ✓ Graph Build")
    print("  ✓ SymbolGraph Build")
    print("  ✓ Chunk Build")

    if not skip_storage:
        print("  ✓ Storage Phases:")
        print("    - Chunk Store (PostgreSQL)")
        print("    - Graph Store (Memgraph)")
        if not skip_embedding:
            print("    - Vector Store (Qdrant)")
        else:
            print("    - Vector Store (Qdrant) ⊗ SKIPPED")
        print("    - Lexical Index (Zoekt)")
        print("    - Symbol Index (Memgraph)")
    else:
        print("  ⊗ Storage Phases (SKIPPED)")

    if not skip_repomap:
        print("  ✓ RepoMap Build")
    else:
        print("  ⊗ RepoMap Build (SKIPPED)")

    print()
    print("인프라 설정:")
    if not skip_health_check:
        print("  ✓ Health Check 활성화")
    else:
        print("  ⊗ Health Check 스킵")

    if not skip_storage:
        print("  ✓ 실제 인프라 사용 (PostgreSQL, Redis, Qdrant, Memgraph)")
    else:
        print("  ⊗ 메모리 내 처리만 (인프라 미사용)")

    print()
    print("=" * 80)
    print()

    # Initialize profiler
    profiler = IndexingProfiler(repo_id=repo_id, repo_path=str(repo_path))
    profiler.start()

    # Phase 1: Bootstrap - Initialize DI Container
    profiler.start_phase("bootstrap")
    print("Phase 1: Bootstrap - Initializing DI Container...")

    from src.container import Container

    container = Container()

    # Health check infrastructure components
    if not skip_health_check:
        print("  Infrastructure Health Check:")
        health_ok = True

        # Parallel health checks
        async def check_redis():
            try:
                await container.redis.ping()
                return ("Redis", True, None)
            except Exception as e:
                return ("Redis", False, str(e))

        async def check_postgres():
            try:
                await container.postgres.fetchval("SELECT 1")
                return ("PostgreSQL", True, None)
            except Exception as e:
                return ("PostgreSQL", False, str(e))

        async def check_qdrant():
            try:
                await container.qdrant.healthcheck()
                return ("Qdrant", True, None)
            except Exception as e:
                return ("Qdrant", False, str(e))

        async def check_memgraph():
            try:
                # Memgraph health check
                return ("Memgraph", True, None)
            except Exception as e:
                return ("Memgraph", False, str(e))

        # Run all checks in parallel
        import asyncio

        results = await asyncio.gather(
            check_redis(),
            check_postgres(),
            check_qdrant(),
            check_memgraph(),
        )

        for name, success, error in results:
            if success:
                print(f"    {name:11} ✓ OK")
            else:
                print(f"    {name:11} ✗ FAIL ({error})")
                health_ok = False

        if not health_ok and not skip_storage:
            print("\n  ⚠️  Warning: 일부 인프라가 실패했지만 계속 진행합니다.")
            print("     Storage 단계에서 에러가 발생할 수 있습니다.")

        print()
    else:
        print("  Health Check: ⊗ SKIPPED")
        print()

    profiler.end_phase("bootstrap")

    # Phase 2: Scan files
    profiler.start_phase("repo_scan")
    print("Phase 2: Scanning repository...")
    files = scan_repository(profiler, repo_path)
    print(f"  Found {len(files)} Python files")

    # Validation: Check if files were found
    if len(files) == 0:
        print(f"\n  ⚠️  WARNING: No Python files found in {repo_path}")
        print(f"     Please check if the path is correct.")
        print(f"     Expected: actual repository path (e.g., benchmark/repo-test/small/typer)")
        print(f"     Got: {repo_path}")
        print(f"\n  Continuing anyway for profiling purposes...\n")

    profiler.end_phase("repo_scan")

    # Phase 3: Process files
    profiler.start_phase("indexing_core")
    print("Phase 3: Processing files (with detailed IR tracking + persistence)...")

    # Track storage errors
    storage_errors = {}

    # Accumulate timing for each phase type
    phase_timings = {
        "parse": 0.0,
        "ir_generation": 0.0,
        "semantic_ir": 0.0,
        "graph_build": 0.0,
        "symbol_graph": 0.0,
        "chunk_build": 0.0,
        "chunk_store": 0.0,
        "graph_store": 0.0,
        "vector_store": 0.0,
        "lexical_store": 0.0,
        "symbol_store": 0.0,
    }

    for idx, file_path in enumerate(files, 1):
        if idx % 10 == 0:
            print(f"  Progress: {idx}/{len(files)} files...")
        file_timings = await process_file(
            profiler,
            file_path,
            repo_path,
            container,
            skip_storage=skip_storage,
            skip_ir_detail=skip_ir_detail,
            skip_embedding=skip_embedding,
            storage_errors=storage_errors,
        )

        # Accumulate timings
        if file_timings:
            for key, value in file_timings.items():
                if key in phase_timings:
                    phase_timings[key] += value

    # Add aggregated phase timings as child phases for waterfall display
    print(f"\n세부 영역별 통합 시간:")
    print(f"  Parse:         {phase_timings['parse']:.1f}ms")
    print(f"  IR Generation: {phase_timings['ir_generation']:.1f}ms")
    print(f"  Semantic IR:   {phase_timings['semantic_ir']:.1f}ms")
    print(f"  Graph Build:   {phase_timings['graph_build']:.1f}ms")
    print(f"  Symbol Graph:  {phase_timings['symbol_graph']:.1f}ms")
    print(f"  Chunk Build:   {phase_timings['chunk_build']:.1f}ms")

    # Add child phases to indexing_core for waterfall visualization
    if profiler._phase_stack:
        profiler.add_child_phase("parse_all", phase_timings["parse"])
        profiler.add_child_phase("ir_generation_all", phase_timings["ir_generation"])
        profiler.add_child_phase("semantic_ir_all", phase_timings["semantic_ir"])
        profiler.add_child_phase("graph_build_all", phase_timings["graph_build"])
        profiler.add_child_phase("symbol_graph_all", phase_timings["symbol_graph"])
        profiler.add_child_phase("chunk_build_all", phase_timings["chunk_build"])

    if not skip_storage and profiler._phase_stack:
        print(f"  Chunk Store:   {phase_timings['chunk_store']:.1f}ms")
        print(f"  Graph Store:   {phase_timings['graph_store']:.1f}ms")
        print(f"  Vector Store:  {phase_timings['vector_store']:.1f}ms")
        print(f"  Lexical Store: {phase_timings['lexical_store']:.1f}ms")
        print(f"  Symbol Store:  {phase_timings['symbol_store']:.1f}ms")

        # Add storage phases as children
        profiler.add_child_phase("chunk_store_all", phase_timings["chunk_store"])
        profiler.add_child_phase("graph_store_all", phase_timings["graph_store"])
        if not skip_embedding:
            profiler.add_child_phase("vector_store_all", phase_timings["vector_store"])
        profiler.add_child_phase("lexical_store_all", phase_timings["lexical_store"])
        profiler.add_child_phase("symbol_store_all", phase_timings["symbol_store"])

    print()

    profiler.end_phase("indexing_core")

    # ========================================================================
    # VALIDATION: Verify indexing results
    # ========================================================================
    print("=" * 80)
    print("INDEXING VALIDATION")
    print("=" * 80)

    files_parsed = profiler.get_counter("files_parsed") or 0
    files_failed = profiler.get_counter("files_failed") or 0
    chunks_created = profiler.get_counter("chunks_created") or 0
    chunks_stored = profiler.get_counter("chunks_stored") or 0
    nodes_created = profiler.get_counter("nodes_created") or 0
    edges_created = profiler.get_counter("edges_created") or 0
    symbols_created = profiler.get_counter("symbols_created") or 0

    print(f"\n1. File Processing:")
    print(f"   - Total files found:  {len(files)}")
    print(f"   - Successfully parsed: {files_parsed}")
    print(f"   - Failed:             {files_failed}")
    print(f"   - Success rate:       {files_parsed / max(len(files), 1) * 100:.1f}%")

    print(f"\n2. In-Memory Build:")
    print(f"   - Nodes created:   {nodes_created}")
    print(f"   - Edges created:   {edges_created}")
    print(f"   - Chunks created:  {chunks_created}")
    print(f"   - Symbols created: {symbols_created}")

    if not skip_storage:
        print(f"\n3. Storage Verification:")

        # Check chunk store
        try:
            # Use counter-based verification instead of querying
            chunk_store_success = profiler.get_counter("chunk_store_success") or 0
            if chunk_store_success > 0:
                print(f"   ✓ Chunk Store (PostgreSQL):  {chunk_store_success} files stored")
            else:
                print(f"   ⚠️  Chunk Store: No successful stores")
        except Exception as e:
            print(f"   ✗ Chunk Store failed: {e}")

        # Check graph store
        try:
            graph_store_success = profiler.get_counter("graph_store_success") or 0
            graph_nodes_stored = profiler.get_counter("graph_nodes_stored") or 0
            if graph_store_success > 0:
                print(f"   ✓ Graph Store (Memgraph):    {graph_nodes_stored} nodes from {graph_store_success} files")
            else:
                print(f"   ⚠️  Graph Store: No successful stores")
        except Exception as e:
            print(f"   ✗ Graph Store check failed: {e}")

        # Check vector store (if not skipped)
        vector_count = 0
        if not skip_embedding:
            try:
                vector_store_success = profiler.get_counter("vector_store_success") or 0
                vectors_stored_actual = profiler.get_counter("vectors_stored_actual") or 0
                if vector_store_success > 0:
                    print(
                        f"   ✓ Vector Store (Qdrant):     {vectors_stored_actual} vectors from {vector_store_success} files"
                    )
                else:
                    print(f"   ⚠️  Vector Store: No successful stores")
            except Exception as e:
                print(f"   ✗ Vector Store check failed: {e}")

        # Storage phase statistics with error samples
        print(f"\n4. Storage Success/Failure:")
        storage_phases = [
            ("Chunk Store", "chunk_store_success", "chunk_store_failed", "chunk_store"),
            ("Graph Store", "graph_store_success", "graph_store_failed", "graph_store"),
            ("Vector Store", "vector_store_success", "vector_store_failed", "vector_store"),
            ("Lexical Store", "lexical_store_success", "lexical_store_failed", "lexical_store"),
            ("Symbol Store", "symbol_store_success", "symbol_store_failed", "symbol_store"),
        ]

        for phase_name, success_key, failed_key, error_key in storage_phases:
            success_count = profiler.get_counter(success_key) or 0
            failed_count = profiler.get_counter(failed_key) or 0
            total = success_count + failed_count

            if total > 0:
                success_rate = success_count / total * 100
                status = "✓" if failed_count == 0 else "⚠️"
                print(
                    f"   {status} {phase_name:15s}: {success_count:3d} OK, {failed_count:3d} FAIL ({success_rate:.1f}%)"
                )

                # Show error reason for failed phases
                if failed_count > 0 and error_key in storage_errors:
                    print(f"      → {storage_errors[error_key]}")

        # Additional storage metrics
        graph_nodes_stored = profiler.get_counter("graph_nodes_stored") or 0
        graph_edges_stored = profiler.get_counter("graph_edges_stored") or 0
        vectors_stored_actual = profiler.get_counter("vectors_stored_actual") or 0
        symbols_stored_actual = profiler.get_counter("symbols_stored_actual") or 0

        if graph_nodes_stored > 0 or graph_edges_stored > 0:
            print(f"\n   Detailed counts:")
            print(f"     - Graph nodes stored: {graph_nodes_stored}")
            print(f"     - Graph edges stored: {graph_edges_stored}")
        if not skip_embedding and vectors_stored_actual > 0:
            print(f"     - Vectors stored:     {vectors_stored_actual}")
        if symbols_stored_actual > 0:
            print(f"     - Symbols indexed:    {symbols_stored_actual}")

        if hasattr(profiler, "_store_timings"):
            print(f"\n5. Storage Performance:")
            for store_name, timings_list in profiler._store_timings.items():
                if timings_list:
                    successes = sum(1 for t in timings_list if t > 0)
                    failures = len(timings_list) - successes
                    avg_time = sum(timings_list) / len(timings_list) if timings_list else 0
                    print(f"   {store_name:20s}: avg {avg_time:6.1f}ms per file")

    print(f"\n6. Overall Status:")
    if len(files) == 0:
        print(f"   ⚠️  No files to index (check repository path)")
    elif files_parsed == 0:
        print(f"   ✗ FAILED: No files successfully parsed")
    elif files_failed > 0:
        print(f"   ⚠️  PARTIAL: {files_failed} files failed")
    else:
        print(f"   ✓ SUCCESS: All files indexed successfully")

    print("=" * 80)
    print()

    # Phase 4: Build RepoMap (if applicable)
    if not skip_repomap and not skip_storage:
        profiler.start_phase("repomap_build")
        print("Phase 4: Building RepoMap...")
        repomap_start = time.time()

        try:
            # Build RepoMap using container
            repomap_builder = container.repomap_builder

            # Get all chunks for RepoMap
            all_chunks = await container.chunk_store.get_chunks_by_repo(repo_id=repo_id, snapshot_id="bench-snapshot")

            if all_chunks:
                # Build RepoMap tree
                repomap = await repomap_builder.build(
                    repo_id=repo_id,
                    chunks=all_chunks,
                )

                print(f"  RepoMap built: {len(repomap.nodes) if hasattr(repomap, 'nodes') else 0} nodes")
        except Exception as e:
            print(f"  Warning: RepoMap build failed: {e}")

        repomap_time = time.time() - repomap_start
        profiler.end_phase("repomap_build")
    else:
        repomap_time = 0
        if skip_repomap:
            print("Phase 4: RepoMap Build ⊗ SKIPPED")
        else:
            print("Phase 4: RepoMap Build ⊗ SKIPPED (storage disabled)")

    # Phase 5: Finalize & Metadata
    profiler.start_phase("finalize")
    print("Phase 5: Finalizing & saving metadata...")

    # Record metadata
    profiler.record_counter("total_files", len(files))
    profiler.record_counter("repomap_time_s", repomap_time)

    time.sleep(0.1)
    profiler.end_phase("finalize")

    # End profiling
    profiler.end()

    print()
    print(f"Benchmark complete! Total time: {profiler.total_duration_s:.2f}s")
    print()

    # Print detailed storage timing breakdown
    if hasattr(profiler, "_store_timings"):
        print("=" * 70)
        print("Storage Timing Breakdown (Average per file)")
        print("=" * 70)

        for store_type, timings in profiler._store_timings.items():
            if timings:
                avg_time = sum(timings) / len(timings)
                total_time = sum(timings)
                print(f"  {store_type:20s} {avg_time:8.3f} ms/file (total: {total_time:8.1f} ms)")

        print("=" * 70)
        print()

    # Generate report
    print("Generating detailed report...")
    generator = ReportGenerator(profiler)
    report = generator.generate()

    # Print to console
    print(report)

    # Save to file
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        generator.save(output_path)
        print()
        print(f"Detailed report saved to: {output_path}")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run detailed indexing performance benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 전체 벤치마크 (모든 단계 포함)
  python benchmark/run_profiling_indexing.py /path/to/repo

  # Storage 스킵 (메모리 내 처리만)
  python benchmark/run_profiling_indexing.py /path/to/repo --skip-storage

  # IR 상세 프로파일링 스킵 (더 빠름)
  python benchmark/run_profiling_indexing.py /path/to/repo --skip-ir-detail

  # 임베딩만 스킵 (Vector Store 제외)
  python benchmark/run_profiling_indexing.py /path/to/repo --skip-embedding

  # 여러 옵션 조합
  python benchmark/run_profiling_indexing.py /path/to/repo \\
      --skip-health-check --skip-repomap --skip-ir-detail --skip-embedding
        """,
    )

    parser.add_argument("repo_path", help="Path to repository to benchmark")
    parser.add_argument(
        "-o",
        "--output",
        help="Output file path for report",
        default=None,
    )
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="Skip infrastructure health check",
    )
    parser.add_argument(
        "--skip-storage",
        action="store_true",
        help="Skip storage phases (PostgreSQL, Qdrant, Memgraph, Zoekt)",
    )
    parser.add_argument(
        "--skip-repomap",
        action="store_true",
        help="Skip RepoMap building phase",
    )
    parser.add_argument(
        "--skip-ir-detail",
        action="store_true",
        help="Skip detailed IR profiling (faster, less detailed)",
    )
    parser.add_argument(
        "--skip-embedding",
        action="store_true",
        help="Skip embedding generation (Vector Store)",
    )

    args = parser.parse_args()

    await run_indexing_benchmark(
        args.repo_path,
        args.output,
        skip_health_check=args.skip_health_check,
        skip_storage=args.skip_storage,
        skip_repomap=args.skip_repomap,
        skip_ir_detail=args.skip_ir_detail,
        skip_embedding=args.skip_embedding,
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
