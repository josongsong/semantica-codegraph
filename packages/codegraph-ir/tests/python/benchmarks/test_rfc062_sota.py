"""
Benchmark for RFC-062 SOTA PyO3 #[pyclass] API

Tests the zero-overhead Python→Rust transfer using direct Rust class creation.
Expected: ~1.1M symbols/sec (vs 145K with old PyDict API)
"""

import time
import codegraph_ir


def test_new_api():
    """Test the new SOTA API with direct Rust class creation"""
    print("=" * 70)
    print("RFC-062 SOTA API Benchmark")
    print("=" * 70)

    # Create IRDocument objects using Rust classes (ZERO overhead!)
    num_files = 1000
    nodes_per_file = 100  # Total: 100K symbols

    print(f"\nGenerating {num_files} files × {nodes_per_file} symbols/file = {num_files * nodes_per_file:,} symbols...")

    ir_docs = []
    for i in range(num_files):
        file_path = f"src/module_{i}.py"

        # Create nodes using Rust classes directly (no dict conversion!)
        nodes = []
        for j in range(nodes_per_file):
            span = codegraph_ir.Span(1, 0, 10, 0)
            kind = codegraph_ir.NodeKind.Function
            node = codegraph_ir.Node(
                id=f"node_{i}_{j}",
                kind=kind,
                fqn=f"module_{i}.func_{j}",
                file_path=file_path,
                span=span,
            )
            nodes.append(node)

        # Create IRDocument using Rust class
        ir_doc = codegraph_ir.IRDocument(
            file_path=file_path,
            nodes=nodes,
            edges=[],
        )
        ir_docs.append(ir_doc)

    print(f"✅ Generated {len(ir_docs)} IRDocument objects")

    # Benchmark
    print("\n🚀 Running build_global_context_py...")
    start = time.perf_counter()
    result = codegraph_ir.build_global_context_py(ir_docs)
    duration = time.perf_counter() - start

    # Results
    total_symbols = result["total_symbols"]
    throughput = total_symbols / duration

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"Total symbols: {total_symbols:,}")
    print(f"Duration: {duration * 1000:.2f}ms")
    print(f"Throughput: {throughput:,.0f} symbols/sec")
    print()

    # Compare with targets
    old_throughput = 145_000  # Old PyDict API
    target_throughput = 450_000  # Target
    expected_throughput = 1_100_000  # Expected with SOTA

    speedup = throughput / old_throughput
    vs_target = throughput / target_throughput
    vs_expected = throughput / expected_throughput

    print(f"Speedup vs old API (145K): {speedup:.1f}x")
    print(f"vs Target (450K): {vs_target:.1f}x")
    print(f"vs Expected (1.1M): {vs_expected:.1f}x")
    print()

    # Verdict
    if throughput >= expected_throughput * 0.8:
        print("✅ EXCELLENT: Performance meets/exceeds expectations!")
    elif throughput >= target_throughput:
        print("✅ GOOD: Performance exceeds target (450K)")
    elif throughput >= old_throughput * 2:
        print("⚠️  OK: Some improvement but below target")
    else:
        print("❌ POOR: Performance regression")

    print("=" * 70)

    return result


if __name__ == "__main__":
    result = test_new_api()
