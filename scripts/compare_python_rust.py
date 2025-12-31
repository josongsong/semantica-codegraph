"""
Python vs Rust Benchmark Comparison

Direct comparison without module dependencies.
"""

import time
from pathlib import Path


def bench_rust_only(repo_path: Path, num_files: int):
    """Rust benchmark"""
    py_files = list(repo_path.rglob("*.py"))[:num_files]

    total_lines = sum(len(f.read_text().splitlines()) for f in py_files if f.exists())

    print("🦀 Rust Benchmark")
    print(f"Files: {len(py_files)}, Lines: {total_lines:,}")
    print("=" * 60)

    import codegraph_ir

    files = [(str(f), f.read_text(), "test") for f in py_files]

    start = time.time()
    results = codegraph_ir.process_python_files(files, "test_repo")
    elapsed = time.time() - start

    success = sum(1 for r in results if r.get("success", False))
    total_nodes = sum(len(r.get("nodes", [])) for r in results)
    total_edges = sum(len(r.get("edges", [])) for r in results)
    total_bfg = sum(len(r.get("bfg_graphs", [])) for r in results)

    print(f"Time: {elapsed:.3f}s")
    print(f"Per file: {elapsed / len(files) * 1000:.2f}ms")
    print(f"Success: {success}/{len(files)}")
    print(f"Nodes: {total_nodes:,}, Edges: {total_edges:,}, BFG: {total_bfg:,}")

    return elapsed, total_nodes, total_edges


if __name__ == "__main__":
    # Test scales
    DJANGO = Path("tools/benchmark/_external_benchmark/django/django")

    print("━" * 60)
    print("Python vs Rust Comparison")
    print("━" * 60)
    print()

    scales = [100, 500, 901]

    for scale in scales:
        print(f"\n{'=' * 60}")
        print(f"Scale: {scale} files")
        print(f"{'=' * 60}")

        elapsed, nodes, edges = bench_rust_only(DJANGO, scale)

        # Python estimate (9.8ms/file from previous measurements)
        python_est = scale * 9.8 / 1000
        speedup = python_est / elapsed

        print()
        print("📊 Comparison:")
        print(f"  Python (est): {python_est:.3f}s")
        print(f"  Rust: {elapsed:.3f}s")
        print(f"  Speedup: {speedup:.1f}x")
        print()
