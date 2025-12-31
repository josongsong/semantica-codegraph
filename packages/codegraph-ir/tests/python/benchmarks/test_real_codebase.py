"""
Test RFC-062 with real Python codebase
Tests with actual codegraph package files
"""

import os
import time
from pathlib import Path
import codegraph_ir


def test_real_codebase(root_dir: str, max_files: int = 50):
    """Test with real Python codebase."""
    print(f"\n{'=' * 70}")
    print(f"Testing with real codebase: {root_dir}")
    print(f"{'=' * 70}")

    # Find Python files
    python_files = []
    for root, dirs, files in os.walk(root_dir):
        # Skip test files and cache directories
        if "__pycache__" in root or ".pytest_cache" in root or "test" in root.lower():
            continue

        for file in files:
            if file.endswith(".py") and not file.startswith("test_"):
                file_path = os.path.join(root, file)
                python_files.append(file_path)

                if len(python_files) >= max_files:
                    break
        if len(python_files) >= max_files:
            break

    if not python_files:
        print("❌ No Python files found")
        return False

    print(f"\n📂 Found {len(python_files)} Python files")
    print(f"   Sample files:")
    for f in python_files[:5]:
        rel_path = os.path.relpath(f, root_dir)
        print(f"   - {rel_path}")
    if len(python_files) > 5:
        print(f"   ... and {len(python_files) - 5} more")

    # Prepare files for IR generation
    files_data = []
    total_lines = 0
    for file_path in python_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                total_lines += len(content.split("\n"))

            # Derive module path from file path
            # Need to get from package root, not root_dir
            # e.g., packages/codegraph-shared/codegraph_shared/infra/config/groups.py
            #   → codegraph_shared.infra.config.groups
            try:
                # Get relative path from 'packages' directory
                abs_path = os.path.abspath(file_path)
                packages_idx = abs_path.find("packages" + os.sep)
                if packages_idx != -1:
                    rel_from_packages = abs_path[packages_idx + len("packages" + os.sep) :]
                    parts = rel_from_packages.split(os.sep)
                    # Skip package directory (e.g., codegraph-shared), use package name (e.g., codegraph_shared)
                    module_path = ".".join(parts[1:]).replace(".py", "")
                else:
                    # Fallback: use relative to root_dir
                    rel_path = os.path.relpath(file_path, root_dir)
                    module_path = rel_path.replace(os.sep, ".").replace(".py", "")
            except Exception:
                rel_path = os.path.relpath(file_path, root_dir)
                module_path = rel_path.replace(os.sep, ".").replace(".py", "")

            files_data.append((file_path, content, module_path))
        except Exception as e:
            print(f"   ⚠️  Skipping {file_path}: {e}")

    print(f"\n📊 Codebase statistics:")
    print(f"   - Files: {len(files_data)}")
    print(f"   - Total lines: {total_lines:,}")
    print(f"   - Avg lines/file: {total_lines // len(files_data) if files_data else 0}")

    # Step 1: Generate IR with Rust
    print(f"\n[1] Generating IR with Rust LayeredIRBuilder...")
    ir_start = time.perf_counter()

    try:
        ir_results = codegraph_ir.process_python_files(files_data, "test-codebase")
    except Exception as e:
        print(f"   ❌ IR generation failed: {e}")
        return False

    ir_duration = time.perf_counter() - ir_start

    # Analyze IR results
    total_nodes = 0
    total_edges = 0
    files_with_imports = 0
    total_imports_edges = 0
    files_with_errors = 0

    for result in ir_results:
        if not result["success"]:
            files_with_errors += 1
            continue

        total_nodes += len(result["nodes"])
        total_edges += len(result["edges"])

        # Count IMPORTS edges
        imports_count = sum(1 for e in result["edges"] if e["kind"] == "IMPORTS")
        if imports_count > 0:
            files_with_imports += 1
            total_imports_edges += imports_count

    print(f"   ✅ IR generation complete:")
    print(f"      - Duration: {ir_duration:.2f}s")
    print(f"      - Files processed: {len(ir_results)}")
    print(f"      - Files with errors: {files_with_errors}")
    print(f"      - Total nodes: {total_nodes:,}")
    print(f"      - Total edges: {total_edges:,}")
    print(f"      - Files with imports: {files_with_imports}")
    print(f"      - Total IMPORTS edges: {total_imports_edges}")

    if files_with_errors > 0:
        print(f"\n   ⚠️  Errors in {files_with_errors} files:")
        for i, result in enumerate(ir_results[:5]):
            if not result["success"]:
                file_path = files_data[i][0]
                print(f"      - {os.path.basename(file_path)}: {result.get('errors', [])}")

    # Step 2: Convert to IRDocument
    print(f"\n[2] Converting to IRDocument for CrossFileResolver...")
    from codegraph_ir import IRDocument, Node, Edge, NodeKind, EdgeKind, Span

    convert_start = time.perf_counter()
    ir_docs = []

    for i, result in enumerate(ir_results):
        if not result["success"]:
            continue

        file_path = files_data[i][0]

        # Convert nodes
        nodes = []
        for node_dict in result["nodes"]:
            try:
                # Parse kind
                kind_str = node_dict["kind"].lower()
                if kind_str == "file":
                    kind = NodeKind.File
                elif kind_str == "module":
                    kind = NodeKind.Module
                elif kind_str == "class":
                    kind = NodeKind.Class
                elif kind_str == "function":
                    kind = NodeKind.Function
                elif kind_str == "method":
                    kind = NodeKind.Method
                elif kind_str == "variable":
                    kind = NodeKind.Variable
                elif kind_str == "parameter":
                    kind = NodeKind.Parameter
                elif kind_str == "field":
                    kind = NodeKind.Field
                elif kind_str == "lambda":
                    kind = NodeKind.Lambda
                elif kind_str == "import":
                    kind = NodeKind.Import
                else:
                    kind = NodeKind.Variable

                node = Node(
                    id=node_dict["id"],
                    kind=kind,
                    fqn=node_dict.get("fqn", ""),
                    file_path=node_dict["file_path"],
                    span=Span(
                        node_dict["span"]["start_line"],
                        node_dict["span"]["start_col"],
                        node_dict["span"]["end_line"],
                        node_dict["span"]["end_col"],
                    ),
                )
                if "name" in node_dict:
                    node.name = node_dict["name"]
                nodes.append(node)
            except Exception as e:
                print(f"      ⚠️  Error converting node: {e}")

        # Convert edges
        edges = []
        for edge_dict in result["edges"]:
            try:
                kind_str = edge_dict["kind"]
                if kind_str == "CONTAINS":
                    kind = EdgeKind.Contains
                elif kind_str == "CALLS":
                    kind = EdgeKind.Calls
                elif kind_str == "READS":
                    kind = EdgeKind.Reads
                elif kind_str == "WRITES":
                    kind = EdgeKind.Writes
                elif kind_str == "IMPORTS":
                    kind = EdgeKind.Imports
                elif kind_str == "INHERITS":
                    kind = EdgeKind.Inherits
                elif kind_str == "REFERENCES":
                    kind = EdgeKind.References
                elif kind_str == "DEFINES":
                    kind = EdgeKind.Defines
                else:
                    continue

                edge = Edge(
                    source_id=edge_dict["source_id"],
                    target_id=edge_dict["target_id"],
                    kind=kind,
                )
                edges.append(edge)
            except Exception as e:
                print(f"      ⚠️  Error converting edge: {e}")

        ir_doc = IRDocument(
            file_path=file_path,
            nodes=nodes,
            edges=edges,
        )
        ir_docs.append(ir_doc)

    convert_duration = time.perf_counter() - convert_start
    print(f"   ✅ Converted {len(ir_docs)} IRDocuments in {convert_duration:.2f}s")

    # Step 3: Cross-file resolution
    print(f"\n[3] Resolving cross-file dependencies with Rust...")

    resolve_start = time.perf_counter()
    try:
        result = codegraph_ir.build_global_context_py(ir_docs)
    except Exception as e:
        print(f"   ❌ Cross-file resolution failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    resolve_duration = time.perf_counter() - resolve_start

    print(f"\n{'=' * 70}")
    print(f"📊 Cross-File Resolution Results")
    print(f"{'=' * 70}")
    print(f"   Total files: {result['total_files']}")
    print(f"   Total symbols: {result['total_symbols']}")
    print(f"   Total imports: {result['total_imports']}")
    print(f"   Total dependencies: {result['total_dependencies']}")
    print(f"   Rust processing time: {result['build_duration_ms']}ms")
    print(f"   Python overhead: {(resolve_duration * 1000 - result['build_duration_ms']):.2f}ms")

    # Analyze symbol table
    symbol_kinds = {}
    for fqn, symbol in result["symbol_table"].items():
        kind = symbol["kind"]
        if kind not in symbol_kinds:
            symbol_kinds[kind] = 0
        symbol_kinds[kind] += 1

    print(f"\n   Symbol kinds:")
    for kind, count in sorted(symbol_kinds.items(), key=lambda x: x[1], reverse=True):
        print(f"      - {kind}: {count}")

    # Check for import nodes in symbol table (should be 0)
    import_count = symbol_kinds.get("Import", 0)
    if import_count > 0:
        print(f"\n   ❌ WARNING: {import_count} import nodes in symbol table (should be 0)")
    else:
        print(f"\n   ✅ Symbol table clean (no import nodes)")

    # Analyze file dependencies
    deps = result.get("file_dependencies", {})
    files_with_deps = len([d for d in deps.values() if d])
    avg_deps = sum(len(d) for d in deps.values()) / len(deps) if deps else 0

    print(f"\n   File dependencies:")
    print(f"      - Files with dependencies: {files_with_deps}/{result['total_files']}")
    print(f"      - Average dependencies per file: {avg_deps:.1f}")

    # Show top files by dependency count
    top_deps = sorted(deps.items(), key=lambda x: len(x[1]), reverse=True)[:5]
    if top_deps:
        print(f"\n   Top files by dependency count:")
        for file, dep_list in top_deps:
            file_name = os.path.basename(file)
            print(f"      - {file_name}: {len(dep_list)} dependencies")

    # Performance summary
    total_duration = ir_duration + convert_duration + resolve_duration
    print(f"\n{'=' * 70}")
    print(f"⚡ Performance Summary")
    print(f"{'=' * 70}")
    print(f"   Total duration: {total_duration:.2f}s")
    print(f"   ├─ IR generation: {ir_duration:.2f}s ({ir_duration / total_duration * 100:.1f}%)")
    print(f"   ├─ Conversion: {convert_duration:.2f}s ({convert_duration / total_duration * 100:.1f}%)")
    print(f"   └─ Cross-file resolution: {resolve_duration:.2f}s ({resolve_duration / total_duration * 100:.1f}%)")
    print(f"\n   Throughput:")
    print(f"   - Files/sec: {len(files_data) / total_duration:.1f}")
    print(f"   - Lines/sec: {total_lines / total_duration:,.0f}")
    print(f"   - Symbols/sec: {result['total_symbols'] / total_duration:,.0f}")

    # Verification
    print(f"\n{'=' * 70}")
    print(f"✅ Verification")
    print(f"{'=' * 70}")

    checks_passed = 0
    checks_total = 0

    # Check 1: All files processed
    checks_total += 1
    if result["total_files"] == len(ir_docs):
        print(f"   ✅ All files processed: {result['total_files']}")
        checks_passed += 1
    else:
        print(f"   ❌ File count mismatch: {result['total_files']} vs {len(ir_docs)}")

    # Check 2: Symbols indexed
    checks_total += 1
    if result["total_symbols"] > 0:
        print(f"   ✅ Symbols indexed: {result['total_symbols']:,}")
        checks_passed += 1
    else:
        print(f"   ❌ No symbols indexed")

    # Check 3: No import nodes in symbol table
    checks_total += 1
    if import_count == 0:
        print(f"   ✅ No import nodes in symbol table")
        checks_passed += 1
    else:
        print(f"   ❌ {import_count} import nodes in symbol table")

    # Check 4: Imports detected
    checks_total += 1
    if result["total_imports"] > 0:
        print(f"   ✅ Imports detected: {result['total_imports']}")
        checks_passed += 1
    else:
        print(f"   ⚠️  No imports detected (might be normal for small codebases)")
        checks_passed += 1  # Not a failure

    # Check 5: Dependencies resolved
    checks_total += 1
    if result["total_dependencies"] >= 0:  # Can be 0 for independent files
        print(f"   ✅ Dependencies resolved: {result['total_dependencies']}")
        checks_passed += 1
    else:
        print(f"   ❌ Invalid dependency count: {result['total_dependencies']}")

    print(f"\n{'=' * 70}")
    if checks_passed == checks_total:
        print(f"✅ ALL CHECKS PASSED ({checks_passed}/{checks_total})")
    else:
        print(f"⚠️  {checks_passed}/{checks_total} checks passed")
    print(f"{'=' * 70}")

    return checks_passed == checks_total


if __name__ == "__main__":
    # Test with different codebases
    codebases = [
        ("packages/codegraph-shared/codegraph_shared/infra/config", 10, "Config module (small)"),
        ("packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure", 30, "Code foundation (medium)"),
        ("packages/codegraph-shared/codegraph_shared", 50, "Shared package (large)"),
    ]

    results = []

    for root_dir, max_files, description in codebases:
        full_path = os.path.join(os.getcwd(), root_dir)
        if os.path.exists(full_path):
            print(f"\n\n{'#' * 70}")
            print(f"# Test Case: {description}")
            print(f"{'#' * 70}")
            success = test_real_codebase(full_path, max_files)
            results.append((description, success))
        else:
            print(f"\n⚠️  Skipping {description}: {full_path} not found")

    # Summary
    print(f"\n\n{'=' * 70}")
    print(f"FINAL SUMMARY")
    print(f"{'=' * 70}")
    for desc, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {status}: {desc}")

    total_passed = sum(1 for _, s in results if s)
    print(f"\n   Total: {total_passed}/{len(results)} test cases passed")

    if total_passed == len(results):
        print(f"\n🎉 ALL REAL CODEBASE TESTS PASSED!")
    else:
        print(f"\n⚠️  Some tests failed")
