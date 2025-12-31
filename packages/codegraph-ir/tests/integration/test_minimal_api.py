#!/usr/bin/env python3
"""
Test Minimal Python API
- E2E Pipeline
- Graph Query
"""

import sys
import tempfile
from pathlib import Path


def test_e2e_pipeline():
    """Test 1: E2E Pipeline Execution"""
    print("=" * 70)
    print("TEST 1: E2E Pipeline Execution")
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
                enable_points_to=False,  # Skip heavy analysis for quick test
                parallel_workers=2,
                file_paths=None,  # Process all files
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
        for key in required_keys:
            if key in result:
                print(f"  ✅ {key}: present")
            else:
                print(f"  ❌ {key}: missing")
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
            print(f"\n🔍 Sample Nodes (first 5):")
            for i, node in enumerate(result["nodes"][:5]):
                print(f"  {i + 1}. {node['kind']}: {node['name']} (FQN: {node['fqn']})")
                span = node["span"]
                print(f"     Location: L{span['start_line']}:{span['start_col']}")
                print(f"     File: {node['file_path']}")

        print("\n" + "=" * 70)
        print("✅ TEST 1 PASSED: E2E Pipeline")
        print("=" * 70)
        return True, result


def test_graph_query(result):
    """Test 2: Graph Query API"""
    print("\n" + "=" * 70)
    print("TEST 2: Graph Query API")
    print("=" * 70)

    try:
        import codegraph_ir
    except ImportError as e:
        print(f"❌ Failed to import codegraph_ir: {e}")
        return False

    if len(result["nodes"]) == 0:
        print("⚠️  No nodes to query")
        return True

    # Get nodes and edges from result
    # Need to convert dict nodes to Node objects
    print(f"\n🔄 Converting dict nodes to Node objects...")
    nodes = []
    for node_dict in result["nodes"]:
        try:
            node = codegraph_ir.Node(
                id=node_dict["id"],
                kind=node_dict["kind"],
                name=node_dict["name"],
                fqn=node_dict["fqn"],
                file_path=node_dict["file_path"],
                span=codegraph_ir.Span(
                    start_line=node_dict["span"]["start_line"],
                    start_col=node_dict["span"]["start_col"],
                    end_line=node_dict["span"]["end_line"],
                    end_col=node_dict["span"]["end_col"],
                ),
            )
            nodes.append(node)
        except Exception as e:
            print(f"  ⚠️  Failed to convert node {node_dict.get('id', 'unknown')}: {e}")
            continue

    edges = []
    for edge_dict in result["edges"]:
        try:
            edge = codegraph_ir.Edge(
                source_id=edge_dict["source_id"],
                target_id=edge_dict["target_id"],
                kind=edge_dict["kind"],
            )
            edges.append(edge)
        except Exception as e:
            print(f"  ⚠️  Failed to convert edge: {e}")
            continue

    print(f"  ✅ Converted {len(nodes)} nodes and {len(edges)} edges")

    print(f"\n📊 Building graph index...")
    print(f"  - Nodes: {len(nodes)}")
    print(f"  - Edges: {len(edges)}")

    # Build graph index
    try:
        index = codegraph_ir.PyGraphIndex(nodes, edges)
        print("✅ Graph index created successfully")
    except Exception as e:
        print(f"❌ Failed to create graph index: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 1: Get graph stats
    print(f"\n📈 Graph Statistics:")
    try:
        stats = index.get_stats()
        print(f"  - Total nodes: {stats['nodes_count']}")
        print(f"  - Total edges: {stats['edges_count']}")
        print(f"  - Node kinds:")
        for kind, count in stats["kind_counts"].items():
            print(f"    • {kind}: {count}")
        print("✅ get_stats() works")
    except Exception as e:
        print(f"❌ get_stats() failed: {e}")
        return False

    # Test 2: Query all functions
    print(f"\n🔍 Query Test 1: Find all functions")
    try:
        filter = codegraph_ir.NodeFilter(kind="function")
        functions = index.query_nodes(filter)
        print(f"  ✅ Found {len(functions)} functions")

        for i, func in enumerate(functions[:3]):
            print(f"  {i + 1}. {func.name} (FQN: {func.fqn})")
            print(f"     File: {func.file_path}")
            print(f"     Location: L{func.span.start_line}:{func.span.start_col}")
    except Exception as e:
        print(f"  ❌ Query failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 3: Query by name prefix
    print(f"\n🔍 Query Test 2: Find functions starting with 'hello'")
    try:
        filter = codegraph_ir.NodeFilter(kind="function", name_prefix="hello")
        matches = index.query_nodes(filter)
        print(f"  ✅ Found {len(matches)} matches")

        for i, func in enumerate(matches):
            print(f"  {i + 1}. {func.name} at L{func.span.start_line}")
    except Exception as e:
        print(f"  ❌ Query failed: {e}")
        return False

    # Test 4: Query by FQN prefix
    print(f"\n🔍 Query Test 3: Find nodes with specific FQN prefix")
    try:
        filter = codegraph_ir.NodeFilter(fqn_prefix="test.")
        matches = index.query_nodes(filter)
        print(f"  ✅ Found {len(matches)} matches with 'test.' prefix")

        for i, node in enumerate(matches[:5]):
            print(f"  {i + 1}. {node.kind}: {node.name} (FQN: {node.fqn})")
    except Exception as e:
        print(f"  ❌ Query failed: {e}")
        return False

    # Test 5: Query classes
    print(f"\n🔍 Query Test 4: Find all classes")
    try:
        filter = codegraph_ir.NodeFilter(kind="class")
        classes = index.query_nodes(filter)
        print(f"  ✅ Found {len(classes)} classes")

        for i, cls in enumerate(classes):
            print(f"  {i + 1}. {cls.name} at L{cls.span.start_line}")
    except Exception as e:
        print(f"  ❌ Query failed: {e}")
        return False

    # Test 6: Empty filter (all nodes)
    print(f"\n🔍 Query Test 5: Get all nodes (empty filter)")
    try:
        filter = codegraph_ir.NodeFilter()
        all_nodes = index.query_nodes(filter)
        print(f"  ✅ Retrieved {len(all_nodes)} nodes (all)")
    except Exception as e:
        print(f"  ❌ Query failed: {e}")
        return False

    print("\n" + "=" * 70)
    print("✅ TEST 2 PASSED: Graph Query")
    print("=" * 70)
    return True


def main():
    """Run all tests"""
    print("\n" + "🧪" * 35)
    print("MINIMAL PYTHON API TEST SUITE")
    print("🧪" * 35)

    # Test 1: E2E Pipeline
    success1, result = test_e2e_pipeline()
    if not success1:
        print("\n❌ TESTS FAILED: E2E Pipeline")
        sys.exit(1)

    # Test 2: Graph Query
    success2 = test_graph_query(result)
    if not success2:
        print("\n❌ TESTS FAILED: Graph Query")
        sys.exit(1)

    # Final summary
    print("\n" + "🎉" * 35)
    print("ALL TESTS PASSED!")
    print("🎉" * 35)
    print("\n✅ E2E Pipeline: Working")
    print("✅ Graph Query: Working")
    print("\nThe minimal Python API is fully functional! 🚀")
    print()


if __name__ == "__main__":
    main()
