"""
Run Indexing Performance Benchmark with Detailed IR Breakdown

Profiles the complete indexing pipeline with granular IR generation phases.
"""

import sys
import time
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


def process_file(profiler: IndexingProfiler, file_path: Path, repo_path: Path):
    """
    Process a single file through the indexing pipeline with detailed IR breakdown.

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
    parse_phase = f"parse:{relative_path}"

    # IR Generation sub-phases
    ir_ast_traverse_phase = f"ir_ast_traverse:{relative_path}"
    ir_call_analysis_phase = f"ir_call_analysis:{relative_path}"
    ir_variable_analysis_phase = f"ir_variable_analysis:{relative_path}"
    ir_signature_phase = f"ir_signature:{relative_path}"
    ir_other_phase = f"ir_other:{relative_path}"

    semantic_ir_phase = f"semantic_ir:{relative_path}"
    graph_build_phase = f"graph_build:{relative_path}"
    symbol_graph_phase = f"symbol_graph:{relative_path}"
    chunk_build_phase = f"chunk_build:{relative_path}"

    try:
        # Read source
        source_code = file_path.read_text(encoding="utf-8")
        loc = len(source_code.split("\n"))

        # Phase 1: Parse
        profiler.start_phase(parse_phase)
        parse_start = time.perf_counter()

        source_file = SourceFile.from_content(file_path=relative_path, content=source_code, language="python")
        ast_tree = AstTree.parse(source_file)

        parse_time_ms = (time.perf_counter() - parse_start) * 1000
        profiler.end_phase(parse_phase)

        # Phase 2: IR Generation with detailed breakdown
        # We'll instrument the IR generator
        ir_generator = PythonIRGenerator(repo_id=profiler.repo_id)

        # Monkey-patch to measure internal phases
        original_traverse = ir_generator._traverse_ast
        original_process_calls = None
        original_process_variables = None
        original_build_signature = None

        timings = {
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
            timings["ast_traverse"] += (time.perf_counter() - start) * 1000
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
                    timings["call_analysis"] += (time.perf_counter() - start) * 1000
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
                    timings["variable_analysis"] += (time.perf_counter() - start) * 1000
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
                    timings["signature"] += (time.perf_counter() - start) * 1000
                    return result

                sig_builder.build_signature = timed_build_signature

        # Generate IR
        ir_gen_start = time.perf_counter()
        ir_doc = ir_generator.generate(source_file, snapshot_id="bench-snapshot")
        ir_gen_time_ms = (time.perf_counter() - ir_gen_start) * 1000

        # Calculate "other" time (includes parsing inside generate)
        measured_time = sum(timings.values())
        timings["other"] = max(0, ir_gen_time_ms - measured_time)

        # Record IR sub-phases
        if timings["ast_traverse"] > 0:
            profiler.start_phase(ir_ast_traverse_phase)
            profiler.end_phase(ir_ast_traverse_phase)
            profiler._phase_stack[-1].duration_ms = timings["ast_traverse"]

        if timings["call_analysis"] > 0:
            profiler.start_phase(ir_call_analysis_phase)
            profiler.end_phase(ir_call_analysis_phase)
            profiler._phase_stack[-1].duration_ms = timings["call_analysis"]

        if timings["variable_analysis"] > 0:
            profiler.start_phase(ir_variable_analysis_phase)
            profiler.end_phase(ir_variable_analysis_phase)
            profiler._phase_stack[-1].duration_ms = timings["variable_analysis"]

        if timings["signature"] > 0:
            profiler.start_phase(ir_signature_phase)
            profiler.end_phase(ir_signature_phase)
            profiler._phase_stack[-1].duration_ms = timings["signature"]

        if timings["other"] > 0:
            profiler.start_phase(ir_other_phase)
            profiler.end_phase(ir_other_phase)
            profiler._phase_stack[-1].duration_ms = timings["other"]

        # Phase 3: Semantic IR
        profiler.start_phase(semantic_ir_phase)
        semantic_start = time.perf_counter()

        semantic_builder = DefaultSemanticIrBuilder()
        semantic_snapshot, _ = semantic_builder.build_full(ir_doc)

        semantic_time_ms = (time.perf_counter() - semantic_start) * 1000
        profiler.end_phase(semantic_ir_phase)

        # Phase 4: Graph Building
        profiler.start_phase(graph_build_phase)
        graph_start = time.perf_counter()

        graph_builder = GraphBuilder()
        graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

        graph_time_ms = (time.perf_counter() - graph_start) * 1000
        profiler.end_phase(graph_build_phase)

        # Phase 5: SymbolGraph Building
        profiler.start_phase(symbol_graph_phase)
        symbol_start = time.perf_counter()

        symbol_builder = SymbolGraphBuilder()
        symbol_graph = symbol_builder.build_from_graph(graph_doc)

        symbol_time_ms = (time.perf_counter() - symbol_start) * 1000
        profiler.end_phase(symbol_graph_phase)

        # Phase 6: Chunk Building
        profiler.start_phase(chunk_build_phase)
        chunk_start = time.perf_counter()

        id_generator = ChunkIdGenerator()
        chunk_builder = ChunkBuilder(id_generator)
        file_lines = source_code.split("\n")
        chunks, chunk_to_ir, chunk_to_graph = chunk_builder.build(
            repo_id=profiler.repo_id,
            ir_doc=ir_doc,
            graph_doc=graph_doc,
            symbol_graph=symbol_graph,
            file_text=file_lines,
            snapshot_id="bench-snapshot",
        )

        chunk_time_ms = (time.perf_counter() - chunk_start) * 1000
        profiler.end_phase(chunk_build_phase)

        # Total build time
        build_time_ms = ir_gen_time_ms + semantic_time_ms + graph_time_ms + symbol_time_ms + chunk_time_ms

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


def run_indexing_benchmark(repo_path: str, output_path: str | None = None):
    """
    Run complete indexing benchmark with detailed IR breakdown.

    Args:
        repo_path: Path to repository to index
        output_path: Optional output path for report
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

    print(f"Starting detailed indexing benchmark for: {repo_path}")
    print(f"Repository ID: {repo_id}")
    print(f"Output: {output_path}")
    print()

    # Initialize profiler
    profiler = IndexingProfiler(repo_id=repo_id, repo_path=str(repo_path))
    profiler.start()

    # Phase 1: Bootstrap
    profiler.start_phase("bootstrap")
    print("Phase 1: Bootstrap...")
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
    print("Phase 3: Processing files (with detailed IR tracking)...")

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


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run detailed indexing performance benchmark")
    parser.add_argument("repo_path", help="Path to repository to benchmark")
    parser.add_argument(
        "-o",
        "--output",
        help="Output file path for report",
        default=None,
    )

    args = parser.parse_args()

    run_indexing_benchmark(args.repo_path, args.output)


if __name__ == "__main__":
    main()
