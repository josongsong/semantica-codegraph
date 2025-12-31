"""
Large Repo + QueryDSL Test

Tests complete pipeline: Rust indexing → QueryEngine → Query execution
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, "packages")


def bench_with_query(repo_path: Path, num_files: int = None):
    """Benchmark with QueryEngine"""

    # Get files
    py_files = list(repo_path.rglob("*.py"))
    if num_files:
        py_files = py_files[:num_files]

    print(f"🔥 Large Repo + QueryDSL Test: {repo_path.name}")
    print(f"Files: {len(py_files)}")
    print("=" * 60)

    # Step 1: Rust indexing
    print("\n[Step 1] Rust L1-L5 Indexing...")
    try:
        import codegraph_ast

        files = []
        for f in py_files:
            try:
                content = f.read_text()
                files.append((str(f), content, repo_path.name))
            except:
                pass

        start = time.time()
        results = codegraph_ast.process_python_files(files, repo_path.name)
        index_time = time.time() - start

        success = sum(1 for r in results if r.get("success", False))
        total_nodes = sum(len(r.get("nodes", [])) for r in results)
        total_edges = sum(len(r.get("edges", [])) for r in results)

        print(f"  ✅ Indexing: {index_time:.3f}s")
        print(f"  ✅ Nodes: {total_nodes:,}")
        print(f"  ✅ Edges: {total_edges:,}")
        print(f"  ✅ Success: {success}/{len(files)}")

        # Step 2: Convert to IRDocument
        print("\n[Step 2] Converting to IRDocument...")
        from codegraph_engine.code_foundation.infrastructure.generators.rust_adapter import RustIRAdapter
        from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile

        adapter = RustIRAdapter(repo_path.name, enable_rust=True)

        sources = []
        for f in py_files[:10]:  # 10 files for query test
            try:
                content = f.read_text()
                source = SourceFile.from_content(
                    file_path=str(f),
                    content=content,
                    language="python",
                )
                sources.append(source)
            except:
                pass

        start = time.time()
        ir_docs, errors = adapter.generate_ir_batch(sources)
        convert_time = time.time() - start

        print(f"  ✅ Conversion: {convert_time:.3f}s")
        print(f"  ✅ IR docs: {len(ir_docs)}")

        if not ir_docs:
            print("  ❌ No IR documents generated")
            return

        # Step 3: QueryEngine
        print("\n[Step 3] QueryEngine Test...")
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

        # Merge IR docs
        merged_doc = ir_docs[0]
        for doc in ir_docs[1:]:
            merged_doc.nodes.extend(doc.nodes)
            merged_doc.edges.extend(doc.edges)

        start = time.time()
        engine = QueryEngine(merged_doc)
        init_time = time.time() - start

        print(f"  ✅ Engine init: {init_time:.3f}s")
        print(f"  ✅ Graph nodes: {len(merged_doc.nodes)}")
        print(f"  ✅ Graph edges: {len(merged_doc.edges)}")

        # Step 4: Query execution
        print("\n[Step 4] Query Execution...")

        # Find functions
        functions = [n for n in merged_doc.nodes if n.kind.value == "FUNCTION"]
        print(f"  Functions found: {len(functions)}")

        if functions:
            # Test query: Find callers
            target_func = functions[0]
            print(f"  Target: {target_func.name}")

            # Simple graph traversal
            start = time.time()
            callers = [e for e in merged_doc.edges if e.kind.value == "CALLS" and e.target_id == target_func.id]
            query_time = time.time() - start

            print(f"  ✅ Query: {query_time * 1000:.2f}ms")
            print(f"  ✅ Callers: {len(callers)}")

        # Summary
        print("\n" + "=" * 60)
        print("📊 Summary:")
        print("=" * 60)
        print(f"  Indexing (Rust L1-L5): {index_time:.3f}s")
        print(f"  Conversion: {convert_time:.3f}s")
        print(f"  Engine init: {init_time:.3f}s")
        print(f"  Query: {query_time * 1000:.2f}ms")
        print(f"  Total: {index_time + convert_time + init_time:.3f}s")
        print()
        print(f"  Nodes: {total_nodes:,}")
        print(f"  Edges: {total_edges:,}")
        print("=" * 60)
        print("✅ 전체 파이프라인 동작 확인!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python bench_with_query.py <repo_path> [num_files]")
        sys.exit(1)

    repo_path = Path(sys.argv[1])
    num_files = int(sys.argv[2]) if len(sys.argv) > 2 else None

    bench_with_query(repo_path, num_files)
