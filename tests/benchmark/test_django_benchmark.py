"""
Real-world Benchmark: Django Repository

Tests Rust implementation on actual Django codebase (3684 files).

VALIDATION:
- No mock/fake data
- Real Python code
- Actual complexity
- Production-grade verification
"""

import time
from pathlib import Path
from collections import Counter


def test_django_benchmark():
    """Benchmark on real Django repository"""
    try:
        import codegraph_ast
    except ImportError:
        print("⚠️  Rust module not installed")
        return

    print("\n" + "=" * 70)
    print("🐍 Django Repository Benchmark")
    print("=" * 70)

    # Find Django repo
    django_path = Path("tools/benchmark/_external_benchmark/django/django")

    if not django_path.exists():
        print("⚠️  Django repo not found")
        return

    # Collect all Python files
    py_files = list(django_path.rglob("*.py"))

    print(f"\n📁 Repository:")
    print(f"  Path: {django_path}")
    print(f"  Total files: {len(py_files)}")

    # Load files
    files = []
    total_size = 0
    load_errors = 0

    for fpath in py_files:
        try:
            content = fpath.read_text(encoding="utf-8")
            total_size += len(content)

            # Generate module path
            rel_path = fpath.relative_to(django_path.parent)
            module = str(rel_path).replace("/", ".").replace(".py", "")

            files.append((str(fpath), content, module))
        except Exception as e:
            load_errors += 1

    print(f"  Loaded: {len(files)}")
    print(f"  Load errors: {load_errors}")
    print(f"  Total size: {total_size:,} bytes ({total_size / 1024 / 1024:.1f} MB)")
    print(f"  Avg size: {total_size / len(files):,.0f} bytes/file")

    # Process with Rust
    print(f"\n⚡ Processing with Rust...")

    start = time.perf_counter()
    results = codegraph_ast.process_python_files(files, "django")
    elapsed = time.perf_counter() - start

    print(f"  ✅ Completed in {elapsed:.3f}s")

    # Analyze results
    success_count = sum(1 for r in results if r["success"])
    total_nodes = sum(len(r["nodes"]) for r in results)
    total_edges = sum(len(r["edges"]) for r in results)

    print(f"\n📊 Results:")
    print(f"  Success rate: {success_count}/{len(results)} ({success_count / len(results) * 100:.1f}%)")
    print(f"  Total nodes: {total_nodes:,}")
    print(f"  Total edges: {total_edges:,}")
    print(f"  Avg nodes/file: {total_nodes / len(files):.1f}")
    print(f"  Avg edges/file: {total_edges / len(files):.1f}")

    # Performance metrics
    per_file_ms = (elapsed / len(files)) * 1000
    throughput = len(files) / elapsed

    print(f"\n⚡ Performance:")
    print(f"  Total time: {elapsed:.3f}s")
    print(f"  Per file: {per_file_ms:.2f}ms")
    print(f"  Throughput: {throughput:.0f} files/sec")
    print(f"  MB/sec: {(total_size / 1024 / 1024) / elapsed:.1f}")

    # Node type distribution
    node_kinds = Counter()
    for r in results:
        for node in r["nodes"]:
            node_kinds[node["kind"]] += 1

    print(f"\n📦 Node Distribution:")
    for kind, count in node_kinds.most_common():
        pct = (count / total_nodes) * 100
        print(f"  {kind:12s}: {count:6,} ({pct:5.1f}%)")

    # Edge type distribution
    edge_kinds = Counter()
    for r in results:
        for edge in r["edges"]:
            edge_kinds[edge["kind"]] += 1

    print(f"\n🔗 Edge Distribution:")
    for kind, count in edge_kinds.most_common():
        pct = (count / total_edges) * 100
        print(f"  {kind:12s}: {count:6,} ({pct:5.1f}%)")

    # Error analysis
    error_files = [r for r in results if not r["success"]]
    if error_files:
        print(f"\n⚠️  Errors: {len(error_files)}")
        for r in error_files[:5]:
            print(f"  - File {r['file_index']}: {r.get('errors', 'Unknown')}")

    # Sample validation (check for fake data)
    print(f"\n🔍 Data Validation (Mock check):")

    # Check 10 random nodes
    import random

    random.seed(42)

    all_nodes = []
    for r in results:
        all_nodes.extend(r["nodes"])

    if len(all_nodes) > 10:
        samples = random.sample(all_nodes, 10)

        # Validate Node IDs are unique
        node_ids = [n["id"] for n in samples]
        print(f"  Node IDs unique: {len(set(node_ids)) == len(node_ids)}")

        # Validate IDs are proper hashes
        all_hex = all(all(c in "0123456789abcdef" for c in nid) for nid in node_ids)
        print(f"  Node IDs are hex: {all_hex}")

        # Validate ID length
        all_32 = all(len(nid) == 32 for nid in node_ids)
        print(f"  Node IDs are 32 chars: {all_32}")

        # Validate FQNs are real
        fqns = [n["fqn"] for n in samples]
        has_django = any("django" in fqn.lower() for fqn in fqns)
        print(f"  FQNs contain 'django': {has_django}")

        # Validate content hashes
        hashes = [n.get("content_hash", "") for n in samples if "content_hash" in n]
        all_64 = all(len(h) == 64 for h in hashes)
        print(f"  Content hashes are 64 chars: {all_64}")

        print(f"\n  Sample FQNs:")
        for fqn in fqns[:3]:
            print(f"    - {fqn}")

    # Compare with target
    print(f"\n🎯 Target Comparison:")
    print(f"  Current: {elapsed:.3f}s ({len(files)} files)")
    print(f"  Python estimate: ~{len(files) * 0.0098:.1f}s (9.8ms/file)")
    print(f"  Speedup: {(len(files) * 0.0098) / elapsed:.1f}x")

    # Assertions
    assert success_count == len(results), f"Some files failed: {len(results) - success_count}"
    assert total_nodes > 0, "No nodes generated!"
    assert total_edges > 0, "No edges generated!"

    print(f"\n✅ Django benchmark completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    test_django_benchmark()
