#!/usr/bin/env python3
"""
Test E2E Pipeline API
"""

import sys
import tempfile
from pathlib import Path


def test_e2e_pipeline():
    """Test E2E Pipeline Execution"""
    print("=" * 70)
    print("TEST: E2E Pipeline Execution")
    print("=" * 70)

    try:
        import codegraph_ir

        print("✅ codegraph_ir imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import codegraph_ir: {e}")
        return False

    # Create a temporary test file
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("""
def hello_world():
    '''A simple hello world function'''
    print("Hello, World!")
    return "Hello"

class Greeter:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello, {self.name}!"

def main():
    greeter = Greeter("Claude")
    message = greeter.greet()
    hello_world()
    print(message)
""")

        print(f"\n📝 Test file created: {test_file}")
        print(f"📂 Repository root: {tmpdir}")

        # Run E2E pipeline
        print("\n🚀 Running E2E pipeline...")
        try:
            result = codegraph_ir.run_ir_indexing_pipeline(
                repo_root=tmpdir,
                repo_name="test-project",
                enable_chunking=True,
                enable_cross_file=True,
                enable_symbols=True,
                enable_points_to=False,  # Skip heavy analysis
                parallel_workers=2,
                file_paths=None,
            )
            print("✅ E2E pipeline completed successfully")
        except Exception as e:
            print(f"❌ E2E pipeline failed: {e}")
            import traceback

            traceback.print_exc()
            return False

        # Verify result structure
        print("\n📊 Checking result structure...")
        required_keys = ["nodes", "edges", "chunks", "symbols", "occurrences", "stats"]
        all_present = True
        for key in required_keys:
            if key in result:
                print(f"  ✅ {key}: present")
            else:
                print(f"  ❌ {key}: missing")
                all_present = False

        if not all_present:
            return False

        # Print stats
        stats = result["stats"]
        print(f"\n📈 Pipeline Stats:")
        print(f"  - Files processed: {stats['files_processed']}")
        print(f"  - Files cached: {stats['files_cached']}")
        print(f"  - Total LOC: {stats['total_loc']}")
        print(f"  - Speed: {stats['loc_per_second']:,.0f} LOC/s")
        print(f"  - Duration: {stats['total_duration_ms']:.2f} ms")
        print(f"  - Cache hit rate: {stats['cache_hit_rate']:.2%}")

        # Print analysis results
        print(f"\n📋 Analysis Results:")
        print(f"  - Nodes: {len(result['nodes'])}")
        print(f"  - Edges: {len(result['edges'])}")
        print(f"  - Chunks: {len(result['chunks'])}")
        print(f"  - Symbols: {len(result['symbols'])}")
        print(f"  - Occurrences: {len(result['occurrences'])}")

        # Show some nodes
        if len(result["nodes"]) > 0:
            print(f"\n🔍 Sample Nodes (first 10):")
            for i, node in enumerate(result["nodes"][:10]):
                span = node["span"]
                print(f"  {i + 1}. {node['kind']}: {node['name']}")
                print(f"     FQN: {node['fqn']}")
                print(f"     Location: {node['file_path']}:{span['start_line']}:{span['start_col']}")

        # Show some edges
        if len(result["edges"]) > 0:
            print(f"\n🔗 Sample Edges (first 5):")
            for i, edge in enumerate(result["edges"][:5]):
                print(f"  {i + 1}. {edge['kind']}: {edge['source_id']} → {edge['target_id']}")

        # Show some chunks
        if len(result["chunks"]) > 0:
            print(f"\n📦 Sample Chunks (first 5):")
            for i, chunk in enumerate(result["chunks"][:5]):
                print(f"  {i + 1}. {chunk['chunk_type']}: {chunk['id']}")
                print(f"     File: {chunk['file_path'] or '(root)'}")
                if chunk.get("symbol_id"):
                    print(f"     Symbol: {chunk['symbol_id']}")

        # Show symbols
        if len(result["symbols"]) > 0:
            print(f"\n🔖 Symbols:")
            for i, symbol in enumerate(result["symbols"]):
                definition = symbol.get("definition")
                if definition:
                    line, col = definition
                    print(f"  {i + 1}. {symbol['kind']}: {symbol['name']}")
                    print(f"     File: {symbol['file_path']}:{line}:{col}")

        # Test querying using Python (simple filtering)
        print(f"\n🔍 Python-side Queries (simple filtering):")

        # Find all functions
        functions = [n for n in result["nodes"] if n["kind"] == "Function"]
        print(f"  - Functions: {len(functions)}")
        for func in functions:
            print(f"    • {func['name']} ({func['fqn']})")

        # Find all classes
        classes = [n for n in result["nodes"] if n["kind"] == "Class"]
        print(f"  - Classes: {len(classes)}")
        for cls in classes:
            print(f"    • {cls['name']} ({cls['fqn']})")

        # Find all methods
        methods = [n for n in result["nodes"] if n["kind"] == "Method"]
        print(f"  - Methods: {len(methods)}")
        for method in methods:
            print(f"    • {method['name']} ({method['fqn']})")

        print("\n" + "=" * 70)
        print("✅ TEST PASSED: E2E Pipeline")
        print("=" * 70)
        return True


def main():
    """Run test"""
    print("\n" + "🧪" * 35)
    print("E2E PIPELINE API TEST")
    print("🧪" * 35)

    success = test_e2e_pipeline()

    if not success:
        print("\n❌ TEST FAILED")
        sys.exit(1)

    # Final summary
    print("\n" + "🎉" * 35)
    print("TEST PASSED!")
    print("🎉" * 35)
    print("\n✅ E2E Pipeline: Working perfectly!")
    print("\n📝 You can query results using Python:")
    print("   - Filter nodes/edges by kind, name, fqn, etc.")
    print("   - Use list comprehensions for simple queries")
    print("   - Process results as native Python dicts")
    print()


if __name__ == "__main__":
    main()
