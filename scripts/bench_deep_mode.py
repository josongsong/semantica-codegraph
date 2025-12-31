"""
Deep Mode Benchmark (No LSP, Rust Type Resolver)

Tests L1-L5 with Rust type resolver (no LSP).
"""

import time
from pathlib import Path


def bench_deep_mode(repo_path: Path, repo_name: str):
    """Benchmark deep mode with Rust type resolver"""

    # Get Python files
    py_files = list(repo_path.rglob("*.py"))

    # Count lines
    total_lines = 0
    for f in py_files:
        try:
            total_lines += len(f.read_text().splitlines())
        except:
            pass

    print("━" * 60)
    print(f"🔥 Deep Mode Benchmark: {repo_name}")
    print("━" * 60)
    print(f"Files: {len(py_files)}")
    print(f"Lines: {total_lines:,}")
    print()

    try:
        import codegraph_ast

        # Prepare data
        files = []
        for f in py_files:
            try:
                content = f.read_text()
                files.append((str(f), content, repo_name))
            except:
                pass

        print(f"Loaded: {len(files)} files")
        print()

        # Benchmark
        print("Processing with Rust L1-L5 (Deep Mode)...")
        start = time.time()
        results = codegraph_ast.process_python_files(files, repo_name)
        elapsed = time.time() - start

        # Results
        success = sum(1 for r in results if r.get("success", False))

        print()
        print("✅ Results:")
        print(f"  Time: {elapsed:.3f}s")
        print(f"  Per file: {elapsed / len(files) * 1000:.2f}ms")
        print(f"  Per 1k lines: {elapsed / (total_lines / 1000):.2f}s")
        print(f"  Success: {success}/{len(files)} ({success / len(files) * 100:.1f}%)")
        print(f"  Throughput: {len(files) / elapsed:.0f} files/sec")

        # L1-L5 data
        total_nodes = sum(len(r.get("nodes", [])) for r in results)
        total_edges = sum(len(r.get("edges", [])) for r in results)
        total_bfg = sum(len(r.get("bfg_graphs", [])) for r in results)
        total_cfg = sum(len(r.get("cfg_edges", [])) for r in results)
        total_types = sum(len(r.get("type_entities", [])) for r in results)
        total_dfg = sum(len(r.get("dfg_graphs", [])) for r in results)
        total_ssa = sum(len(r.get("ssa_graphs", [])) for r in results)

        print()
        print("📊 L1-L5 Data Generated:")
        print(f"  L1 Nodes: {total_nodes:,}")
        print(f"  L1 Edges: {total_edges:,}")
        print(f"  L2 BFG: {total_bfg:,}")
        print(f"  L2 CFG: {total_cfg:,}")
        print(f"  L3 Types: {total_types:,} (Rust TypeResolver)")
        print(f"  L4 DFG: {total_dfg:,}")
        print(f"  L5 SSA: {total_ssa:,}")

        print()
        print(f"🚀 Deep Mode: {elapsed:.3f}s for {total_lines:,} lines")
        print(f"   Per 1k lines: {elapsed / (total_lines / 1000) * 1000:.1f}ms")

        return elapsed

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Test medium repos
    repos = [
        ("httpx", Path("tools/benchmark/repo-test/medium/httpx")),
        ("rich", Path("tools/benchmark/repo-test/medium/rich")),
    ]

    for name, path in repos:
        if path.exists():
            bench_deep_mode(path, name)
            print()
