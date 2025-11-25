"""
Run Indexing Performance Benchmark

Profiles the complete indexing pipeline and generates a detailed report.
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

    # Simple file scanner (you can replace with actual implementation)
    python_files = list(repo_path.rglob("*.py"))

    # Filter out common exclude patterns
    exclude_patterns = ["venv", ".venv", "node_modules", ".git", "__pycache__", "build", "dist"]
    python_files = [
        f
        for f in python_files
        if not any(pattern in str(f) for pattern in exclude_patterns)
    ]

    profiler.record_counter("files_found", len(python_files))
    profiler.end_phase("scan_files")

    return python_files


def process_file(profiler: IndexingProfiler, file_path: Path, repo_path: Path):
    """
    Process a single file through the indexing pipeline.

    Args:
        profiler: Profiler instance
        file_path: Path to file
        repo_path: Repository root path
    """
    import time

    from src.foundation.chunk.builder import ChunkBuilder
    from src.foundation.chunk.id_generator import ChunkIdGenerator
    from src.foundation.generators.python_generator import PythonIRGenerator
    from src.foundation.graph.builder import GraphBuilder
    from src.foundation.parsing.ast_tree import AstTree
    from src.foundation.parsing.source_file import SourceFile
    from src.foundation.semantic_ir import DefaultSemanticIrBuilder
    from src.foundation.symbol_graph import SymbolGraphBuilder

    relative_path = str(file_path.relative_to(repo_path))

    # Define phase names for granular profiling
    parse_phase_name = f"parse:{relative_path}"
    ir_gen_phase_name = f"ir_gen:{relative_path}"
    semantic_ir_phase_name = f"semantic_ir:{relative_path}"
    graph_build_phase_name = f"graph_build:{relative_path}"
    symbol_graph_phase_name = f"symbol_graph:{relative_path}"
    chunk_build_phase_name = f"chunk_build:{relative_path}"

    try:
        # Read source
        source_code = file_path.read_text(encoding="utf-8")
        loc = len(source_code.split("\n"))

        # Phase 1: Parse (only once!)
        profiler.start_phase(parse_phase_name)
        parse_start = time.time()

        source_file = SourceFile.from_content(
            file_path=relative_path, content=source_code, language="python"
        )
        ast_tree = AstTree.parse(source_file)

        parse_time_ms = (time.time() - parse_start) * 1000
        profiler.end_phase(parse_phase_name)

        # Phase 2: IR Generation (reuse parsed AST - no re-parsing!)
        # OPTIMIZATION: Pass pre-parsed AST to avoid duplicate parsing
        profiler.start_phase(ir_gen_phase_name)
        ir_gen_start = time.time()

        ir_generator = PythonIRGenerator(repo_id=profiler.repo_id)
        ir_doc = ir_generator.generate(
            source_file, snapshot_id="bench-snapshot", ast=ast_tree  # ← Reuse AST!
        )

        # Get IR generation timing breakdown
        ir_timing = ir_generator.get_timing_breakdown()

        ir_gen_time_ms = (time.perf_counter() - ir_gen_start) * 1000
        profiler.end_phase(ir_gen_phase_name)

        # Store IR timing in profiler for aggregation
        if not hasattr(profiler, "_ir_timings"):
            profiler._ir_timings = []
        profiler._ir_timings.append(ir_timing)

        # Phase 3: Semantic IR
        profiler.start_phase(semantic_ir_phase_name)
        semantic_start = time.time()

        semantic_builder = DefaultSemanticIrBuilder()
        semantic_snapshot, _ = semantic_builder.build_full(ir_doc)

        semantic_time_ms = (time.time() - semantic_start) * 1000
        profiler.end_phase(semantic_ir_phase_name)

        # Phase 4: Graph Building
        profiler.start_phase(graph_build_phase_name)
        graph_start = time.time()

        graph_builder = GraphBuilder()
        graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

        graph_time_ms = (time.time() - graph_start) * 1000
        profiler.end_phase(graph_build_phase_name)

        # Phase 5: SymbolGraph Building
        profiler.start_phase(symbol_graph_phase_name)
        symbol_start = time.time()

        symbol_builder = SymbolGraphBuilder()
        symbol_graph = symbol_builder.build_from_graph(graph_doc)

        symbol_time_ms = (time.time() - symbol_start) * 1000
        profiler.end_phase(symbol_graph_phase_name)

        # Phase 6: Chunk Building
        profiler.start_phase(chunk_build_phase_name)
        chunk_start = time.time()

        id_generator = ChunkIdGenerator()
        chunk_builder = ChunkBuilder(id_generator)
        file_lines = source_code.split("\n")
        chunks, chunk_to_ir, chunk_to_graph = chunk_builder.build(
            repo_id=profiler.repo_id,
            ir_doc=ir_doc,
            graph_doc=graph_doc,  # Required by internal mapping logic
            symbol_graph=symbol_graph,
            file_text=file_lines,
            snapshot_id="bench-snapshot",
        )

        chunk_time_ms = (time.time() - chunk_start) * 1000
        profiler.end_phase(chunk_build_phase_name)

        # Total build time (for backward compatibility)
        build_time_ms = (
            ir_gen_time_ms
            + semantic_time_ms
            + graph_time_ms
            + symbol_time_ms
            + chunk_time_ms
        )

        # Record file metrics
        profiler.record_file(
            file_path=relative_path,
            language="python",
            loc=loc,
            parse_time_ms=parse_time_ms,
            build_time_ms=build_time_ms,
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

    except Exception as e:
        import traceback as tb

        # Determine phase and error type
        phase = "unknown"
        error_type = "unknown_error"

        if profiler._phase_stack:
            current_phase = profiler._phase_stack[-1].name
            if current_phase == parse_phase_name:
                phase = "parse"
                error_type = "parsing_error"
            elif current_phase == build_phase_name:
                phase = "build"
                # Classify build errors
                error_msg = str(e).lower()
                if "substring not found" in error_msg or "type" in error_msg:
                    error_type = "type_resolution_error"
                elif "encoding" in error_msg or "decode" in error_msg:
                    error_type = "encoding_error"
                else:
                    error_type = "build_error"

        # Record failed file with detailed info
        profiler.record_failed_file(
            file_path=relative_path,
            error_type=error_type,
            error_message=str(e),
            phase=phase,
            traceback=tb.format_exc(),
        )

        # Make sure to end any open phases
        while profiler._phase_stack:
            phase_obj = profiler._phase_stack[-1]
            if phase_obj.name in (parse_phase_name, build_phase_name):
                profiler.end_phase()
            else:
                break

        print(f"Error processing {relative_path}: [{error_type}] {e}")
        profiler.increment_counter("files_failed", 1)


def run_indexing_benchmark(repo_path: str, output_path: str | None = None):
    """
    Run complete indexing benchmark.

    Args:
        repo_path: Path to repository to index
        output_path: Optional output path for report. If None, auto-generates path as:
                    benchmark/reports/{repo_id}/{date}/{timestamp}_report.txt
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
        output_path = str(output_dir / f"{timestamp}_report.txt")

    print(f"Starting indexing benchmark for: {repo_path}")
    print(f"Repository ID: {repo_id}")
    print(f"Output: {output_path}")
    print()

    # Initialize profiler
    profiler = IndexingProfiler(repo_id=repo_id, repo_path=str(repo_path))
    profiler.start()

    # Phase 1: Bootstrap
    profiler.start_phase("bootstrap")
    print("Phase 1: Bootstrap...")
    # Simulate bootstrap time
    import time

    time.sleep(0.1)
    profiler.end_phase("bootstrap")

    # Phase 2: Scan files
    profiler.start_phase("repo_scan")
    print("Phase 2: Scanning repository...")
    files = scan_repository(profiler, repo_path)
    print(f"  Found {len(files)} Python files")
    profiler.end_phase("repo_scan")

    # Phase 3: Process files
    profiler.start_phase("indexing_core")
    print("Phase 3: Processing files...")

    for idx, file_path in enumerate(files, 1):
        if idx % 10 == 0:
            print(f"  Progress: {idx}/{len(files)} files...")
        process_file(profiler, file_path, repo_path)

    profiler.end_phase("indexing_core")

    # Phase 4: Finalize
    profiler.start_phase("finalize")
    print("Phase 4: Finalizing...")
    time.sleep(0.1)
    profiler.end_phase("finalize")

    # End profiling
    profiler.end()

    print()
    print(f"Benchmark complete! Total time: {profiler.total_duration_s:.2f}s")
    print()

    # Print IR timing breakdown
    if hasattr(profiler, "_ir_timings") and profiler._ir_timings:
        print("=" * 70)
        print("IR Generation Timing Breakdown (Average across all files)")
        print("=" * 70)

        # Aggregate timings
        timing_keys = profiler._ir_timings[0].keys()
        timing_totals = {key: sum(t.get(key, 0) for t in profiler._ir_timings) for key in timing_keys}
        num_files = len(profiler._ir_timings)

        # Calculate averages
        timing_avgs = {key: total / num_files for key, total in timing_totals.items()}

        # Sort by time (descending)
        sorted_timings = sorted(timing_avgs.items(), key=lambda x: x[1], reverse=True)

        # Calculate total
        total_avg = sum(timing_avgs.values())

        # Print breakdown
        for key, avg_ms in sorted_timings:
            if avg_ms > 0:  # Only show non-zero items
                pct = (avg_ms / total_avg * 100) if total_avg > 0 else 0
                print(f"  {key:30s} {avg_ms:8.3f} ms/file ({pct:5.1f}%)")

        print("=" * 70)
        print(f"  {'Total (average)':30s} {total_avg:8.3f} ms/file (100.0%)")
        print("=" * 70)
        print()
        print("Note:")
        print("  - function_process_ms: All functions (includes call/variable/signature)")
        print("  - class_process_ms: Class overhead only (excludes methods)")
        print("  - other_ms: AST traversal overhead + file node + misc")
        print()

    # Generate report
    print("Generating report...")
    generator = ReportGenerator(profiler)
    report = generator.generate()

    # Print to console
    print(report)

    # Save to file if specified
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        generator.save(output_path)
        print()
        print(f"Report saved to: {output_path}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run indexing performance benchmark")
    parser.add_argument("repo_path", help="Path to repository to benchmark")
    parser.add_argument(
        "-o",
        "--output",
        help="Output file path for report. If not specified, auto-generates as: "
        "benchmark/reports/{repo_id}/{date}/{timestamp}_report.txt",
        default=None,
    )

    args = parser.parse_args()

    run_indexing_benchmark(args.repo_path, args.output)


if __name__ == "__main__":
    main()
