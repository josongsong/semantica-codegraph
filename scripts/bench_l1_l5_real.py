"""
Real L1-L5 Benchmark (No Sampling)

Tests actual performance with all layers.
"""

import sys
import time
from pathlib import Path

# Test files
DJANGO_PATH = Path("tools/benchmark/_external_benchmark/django/django")


def bench_rust():
    """Benchmark Rust implementation"""
    try:
        import codegraph_ast

        # Get 100 Django files
        py_files = list(DJANGO_PATH.rglob("*.py"))[:100]
        print(f"Testing {len(py_files)} files...")

        # Prepare data
        files = []
        for f in py_files:
            try:
                content = f.read_text()
                files.append((str(f), content, "django"))
            except:
                pass

        print(f"Loaded {len(files)} files")

        # Benchmark
        start = time.time()
        results = codegraph_ast.process_python_files(files, "test_repo")
        elapsed = time.time() - start

        # Analyze results
        success_count = sum(1 for r in results if r.get("success", False))

        print(f"\n✅ Rust Results:")
        print(f"  Time: {elapsed:.3f}s")
        print(f"  Per file: {elapsed / len(files) * 1000:.2f}ms")
        print(f"  Success: {success_count}/{len(files)}")

        # Check L1-L5 data
        if results:
            r = results[0]
            print(f"\n📊 L1-L5 Data:")
            print(f"  L1 Nodes: {len(r.get('nodes', []))}")
            print(f"  L1 Edges: {len(r.get('edges', []))}")
            print(f"  L2 BFG: {len(r.get('bfg_graphs', []))}")
            print(f"  L2 CFG: {len(r.get('cfg_edges', []))}")
            print(f"  L3 Types: {len(r.get('type_entities', []))}")
            print(f"  L4 DFG: {len(r.get('dfg_graphs', []))}")
            print(f"  L5 SSA: {len(r.get('ssa_graphs', []))}")

        return elapsed

    except ImportError as e:
        print(f"❌ Rust not available: {e}")
        return None


if __name__ == "__main__":
    bench_rust()
