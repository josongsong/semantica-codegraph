"""
SymbolGraph Performance Benchmark

Tests memory usage and query performance of SymbolGraph vs GraphDocument.
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.foundation.graph.builder import GraphBuilder
from src.foundation.parsing.ast_tree import AstTree
from src.foundation.parsing.source_file import SourceFile
from src.foundation.symbol_graph import SymbolGraphBuilder


def get_memory_usage():
    """Get current memory usage in MB"""
    import tracemalloc

    current, peak = tracemalloc.get_traced_memory()
    return current / 1024 / 1024, peak / 1024 / 1024


def benchmark_file(file_path: str, repo_id: str = "test-repo"):
    """
    Benchmark a single file.

    Returns:
        Dict with benchmark results
    """
    import tracemalloc

    tracemalloc.start()

    print(f"\n{'='*60}")
    print(f"Benchmarking: {file_path}")
    print(f"{'='*60}")

    # Read source file
    with open(file_path) as f:
        source_code = f.read()

    source_lines = source_code.split("\n")
    print(f"Lines of code: {len(source_lines)}")

    # Step 1: Parse AST
    print("\n[1/5] Parsing AST...")
    start = time.time()
    source_file = SourceFile.from_content(
        file_path=file_path, content=source_code, language="python"
    )
    ast_tree = AstTree.parse(source_file)
    parse_time = time.time() - start
    print(f"  ✓ Parse time: {parse_time*1000:.2f}ms")

    mem_after_parse = get_memory_usage()
    print(f"  Memory: {mem_after_parse[0]:.2f}MB (peak: {mem_after_parse[1]:.2f}MB)")

    # Step 2: Build IR
    print("\n[2/5] Building IR...")
    start = time.time()
    from src.foundation.generators.python_generator import PythonIRGenerator

    ir_generator = PythonIRGenerator(repo_id)
    ir_doc = ir_generator.generate(source_file, snapshot_id="bench-snapshot")
    ir_time = time.time() - start
    print(f"  ✓ IR generation time: {ir_time*1000:.2f}ms")
    print(f"  IR nodes: {len(ir_doc.nodes)}")

    mem_after_ir = get_memory_usage()
    print(f"  Memory: {mem_after_ir[0]:.2f}MB (peak: {mem_after_ir[1]:.2f}MB)")

    # Step 3: Build Semantic IR
    print("\n[3/5] Building Semantic IR...")
    start = time.time()
    from src.foundation.semantic_ir import DefaultSemanticIrBuilder

    semantic_builder = DefaultSemanticIrBuilder()
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc)
    semantic_time = time.time() - start
    print(f"  ✓ Semantic IR build time: {semantic_time*1000:.2f}ms")

    mem_after_semantic = get_memory_usage()
    print(f"  Memory: {mem_after_semantic[0]:.2f}MB (peak: {mem_after_semantic[1]:.2f}MB)")

    # Step 4: Build GraphDocument
    print("\n[4/5] Building GraphDocument...")
    start = time.time()
    graph_builder = GraphBuilder()
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)
    graph_time = time.time() - start
    print(f"  ✓ Graph build time: {graph_time*1000:.2f}ms")
    print(f"  Graph nodes: {len(graph_doc.graph_nodes)}")
    print(f"  Graph edges: {len(graph_doc.graph_edges)}")

    mem_after_graph = get_memory_usage()
    graph_memory = mem_after_graph[0] - mem_after_ir[0]
    print(f"  Memory: {mem_after_graph[0]:.2f}MB (peak: {mem_after_graph[1]:.2f}MB)")
    print(f"  GraphDocument memory: ~{graph_memory:.2f}MB")

    # Step 5: Build SymbolGraph
    print("\n[5/6] Building SymbolGraph...")
    start = time.time()
    symbol_builder = SymbolGraphBuilder()
    symbol_graph = symbol_builder.build_from_graph(graph_doc)
    symbol_time = time.time() - start
    print(f"  ✓ SymbolGraph build time: {symbol_time*1000:.2f}ms")
    print(f"  Symbols: {symbol_graph.symbol_count}")
    print(f"  Relations: {symbol_graph.relation_count}")

    mem_after_symbol = get_memory_usage()
    symbol_memory = mem_after_symbol[0] - mem_after_graph[0]
    print(f"  Memory: {mem_after_symbol[0]:.2f}MB (peak: {mem_after_symbol[1]:.2f}MB)")
    print(f"  SymbolGraph memory: ~{symbol_memory:.2f}MB")

    if graph_memory > 0:
        reduction = (1 - symbol_memory / graph_memory) * 100
        print(f"  Memory reduction: {reduction:.1f}%")

    # Step 6: Query Performance
    print("\n[6/6] Testing Query Performance...")

    # Get all symbol IDs
    symbol_ids = list(symbol_graph.symbols.keys())
    if symbol_ids:
        test_symbol_id = symbol_ids[len(symbol_ids) // 2]  # Pick middle one

        # Test get_symbol (dict lookup)
        start = time.perf_counter()
        for _ in range(1000):
            symbol = symbol_graph.get_symbol(test_symbol_id)
        get_symbol_time = (time.perf_counter() - start) / 1000
        print(f"  get_symbol() avg: {get_symbol_time*1_000_000:.2f}μs (1000 iterations)")

        # Test get_children (index lookup)
        start = time.perf_counter()
        for _ in range(1000):
            children = symbol_graph.indexes.get_children(test_symbol_id)
        get_children_time = (time.perf_counter() - start) / 1000
        print(f"  get_children() avg: {get_children_time*1_000_000:.2f}μs (1000 iterations)")

        # Test get_callers (index lookup)
        start = time.perf_counter()
        for _ in range(1000):
            callers = symbol_graph.indexes.get_callers(test_symbol_id)
        get_callers_time = (time.perf_counter() - start) / 1000
        print(f"  get_callers() avg: {get_callers_time*1_000_000:.2f}μs (1000 iterations)")

        # Test get_symbols_by_kind (filter)
        from src.foundation.symbol_graph.models import SymbolKind

        start = time.perf_counter()
        for _ in range(100):
            funcs = symbol_graph.get_symbols_by_kind(SymbolKind.FUNCTION)
        get_by_kind_time = (time.perf_counter() - start) / 100
        print(f"  get_symbols_by_kind() avg: {get_by_kind_time*1000:.2f}ms (100 iterations)")
        print(f"  Found {len(funcs)} functions")

    tracemalloc.stop()

    # Return results
    return {
        "file": file_path,
        "loc": len(source_lines),
        "ir_nodes": len(ir_doc.nodes),
        "graph_nodes": len(graph_doc.graph_nodes),
        "graph_edges": len(graph_doc.graph_edges),
        "symbols": symbol_graph.symbol_count,
        "relations": symbol_graph.relation_count,
        "parse_time_ms": parse_time * 1000,
        "ir_time_ms": ir_time * 1000,
        "graph_time_ms": graph_time * 1000,
        "symbol_time_ms": symbol_time * 1000,
        "graph_memory_mb": graph_memory,
        "symbol_memory_mb": symbol_memory,
        "memory_reduction_pct": (1 - symbol_memory / graph_memory) * 100 if graph_memory > 0 else 0,
        "get_symbol_us": get_symbol_time * 1_000_000 if symbol_ids else 0,
        "get_children_us": get_children_time * 1_000_000 if symbol_ids else 0,
        "get_callers_us": get_callers_time * 1_000_000 if symbol_ids else 0,
    }


def main():
    """Run benchmark on sample files"""
    print("SymbolGraph Performance Benchmark")
    print("=" * 60)

    # Sample files from the project
    sample_files = [
        "src/foundation/symbol_graph/models.py",
        "src/foundation/symbol_graph/builder.py",
        "src/foundation/search_index/models.py",
        "src/foundation/search_index/builder.py",
        "src/foundation/chunk/builder.py",
    ]

    results = []
    for file_path in sample_files:
        full_path = Path(__file__).parent.parent / file_path
        if full_path.exists():
            try:
                result = benchmark_file(str(full_path))
                results.append(result)
            except Exception as e:
                print(f"\n❌ Error benchmarking {file_path}: {e}")
                import traceback

                traceback.print_exc()
        else:
            print(f"\n⚠️  File not found: {file_path}")

    # Summary
    if results:
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        total_loc = sum(r["loc"] for r in results)
        total_symbols = sum(r["symbols"] for r in results)
        total_relations = sum(r["relations"] for r in results)
        avg_graph_mem = sum(r["graph_memory_mb"] for r in results) / len(results)
        avg_symbol_mem = sum(r["symbol_memory_mb"] for r in results) / len(results)
        avg_reduction = sum(r["memory_reduction_pct"] for r in results) / len(results)
        avg_get_symbol = sum(r["get_symbol_us"] for r in results) / len(results)
        avg_get_children = sum(r["get_children_us"] for r in results) / len(results)

        print(f"\nFiles tested: {len(results)}")
        print(f"Total LOC: {total_loc:,}")
        print(f"Total symbols: {total_symbols:,}")
        print(f"Total relations: {total_relations:,}")
        print(f"\nAverage GraphDocument memory: {avg_graph_mem:.2f}MB")
        print(f"Average SymbolGraph memory: {avg_symbol_mem:.2f}MB")
        print(f"Average memory reduction: {avg_reduction:.1f}%")
        print("\nAverage query performance:")
        print(f"  get_symbol(): {avg_get_symbol:.2f}μs")
        print(f"  get_children(): {avg_get_children:.2f}μs")

        print(f"\n{'File':<50} {'Symbols':<10} {'Reduction':<12} {'Query μs':<10}")
        print("-" * 85)
        for r in results:
            file_name = Path(r["file"]).name
            print(
                f"{file_name:<50} {r['symbols']:<10} {r['memory_reduction_pct']:>10.1f}% {r['get_symbol_us']:>10.2f}"
            )


if __name__ == "__main__":
    main()
