import codegraph_ir
import msgpack

# Create comprehensive IR with multiple node types
ir_result = {
    "nodes": [
        # File node
        {"id": "file1", "kind": "File", "fqn": "test.py", "file_path": "test.py",
         "span": {"start_line": 1, "start_col": 0, "end_line": 100, "end_col": 0},
         "language": "python", "name": "test.py"},
        
        # Module node
        {"id": "module1", "kind": "Module", "fqn": "test", "file_path": "test.py",
         "span": {"start_line": 1, "start_col": 0, "end_line": 100, "end_col": 0},
         "language": "python", "name": "test"},
        
        # Class node
        {"id": "class1", "kind": "Class", "fqn": "test.Calculator", "file_path": "test.py",
         "span": {"start_line": 5, "start_col": 0, "end_line": 50, "end_col": 0},
         "language": "python", "name": "Calculator"},
        
        # Method nodes
        {"id": "method1", "kind": "Method", "fqn": "test.Calculator.add", "file_path": "test.py",
         "span": {"start_line": 10, "start_col": 4, "end_line": 15, "end_col": 0},
         "language": "python", "name": "add"},
        
        {"id": "method2", "kind": "Method", "fqn": "test.Calculator.subtract", "file_path": "test.py",
         "span": {"start_line": 17, "start_col": 4, "end_line": 20, "end_col": 0},
         "language": "python", "name": "subtract"},
        
        # Function node
        {"id": "func1", "kind": "Function", "fqn": "test.helper", "file_path": "test.py",
         "span": {"start_line": 60, "start_col": 0, "end_line": 65, "end_col": 0},
         "language": "python", "name": "helper"},
        
        # Variable node
        {"id": "var1", "kind": "Variable", "fqn": "test.CONSTANT", "file_path": "test.py",
         "span": {"start_line": 70, "start_col": 0, "end_line": 70, "end_col": 20},
         "language": "python", "name": "CONSTANT"},
        
        # Import node
        {"id": "import1", "kind": "Import", "fqn": "test.import.os", "file_path": "test.py",
         "span": {"start_line": 1, "start_col": 0, "end_line": 1, "end_col": 10},
         "language": "python", "name": "os"},
    ],
    "edges": []
}

ir_bytes = msgpack.packb(ir_result)

print("=" * 60)
print("COMPREHENSIVE PyGraphIndex TEST")
print("=" * 60)

# Build graph
graph_index = codegraph_ir.PyGraphIndex(ir_bytes)
print(f"\n✓ Built: {repr(graph_index)}")

# Test 1: Query all nodes
print("\n" + "=" * 60)
print("TEST 1: Query ALL nodes (no filter)")
print("=" * 60)
filter_all = codegraph_ir.NodeFilter()
result = msgpack.unpackb(graph_index.query_nodes(filter_all))
print(f"Count: {result['count']}")
print(f"Nodes: {[n['name'] for n in result['nodes']]}")
assert result['count'] == 8, f"Expected 8 nodes, got {result['count']}"
print("✓ PASS")

# Test 2: Filter by each kind
test_cases = [
    ("File", 1, ["test.py"]),
    ("Module", 1, ["test"]),
    ("Class", 1, ["Calculator"]),
    ("Method", 2, ["add", "subtract"]),
    ("Function", 1, ["helper"]),
    ("Variable", 1, ["CONSTANT"]),
    ("Import", 1, ["os"]),
]

for kind, expected_count, expected_names in test_cases:
    print("\n" + "=" * 60)
    print(f"TEST: Filter kind='{kind}'")
    print("=" * 60)
    filter_kind = codegraph_ir.NodeFilter(kind=kind)
    result = msgpack.unpackb(graph_index.query_nodes(filter_kind))
    actual_names = [n['name'] for n in result['nodes']]
    print(f"Count: {result['count']}")
    print(f"Nodes: {actual_names}")
    assert result['count'] == expected_count, f"Expected {expected_count}, got {result['count']}"
    assert sorted(actual_names) == sorted(expected_names), f"Expected {expected_names}, got {actual_names}"
    print("✓ PASS")

# Test 3: Name prefix filter
print("\n" + "=" * 60)
print("TEST: Filter name_prefix='C'")
print("=" * 60)
filter_prefix = codegraph_ir.NodeFilter(name_prefix="C")
result = msgpack.unpackb(graph_index.query_nodes(filter_prefix))
actual_names = [n['name'] for n in result['nodes']]
print(f"Count: {result['count']}")
print(f"Nodes: {actual_names}")
assert result['count'] == 2, f"Expected 2 (Calculator, CONSTANT), got {result['count']}"
print("✓ PASS")

# Test 4: Combined filters (kind + name_prefix)
print("\n" + "=" * 60)
print("TEST: Filter kind='Method' AND name_prefix='a'")
print("=" * 60)
filter_combined = codegraph_ir.NodeFilter(kind="Method", name_prefix="a")
result = msgpack.unpackb(graph_index.query_nodes(filter_combined))
actual_names = [n['name'] for n in result['nodes']]
print(f"Count: {result['count']}")
print(f"Nodes: {actual_names}")
assert result['count'] == 1, f"Expected 1 (add), got {result['count']}"
assert actual_names == ["add"], f"Expected ['add'], got {actual_names}"
print("✓ PASS")

# Test 5: FQN prefix filter
print("\n" + "=" * 60)
print("TEST: Filter fqn_prefix='test.Calculator'")
print("=" * 60)
filter_fqn = codegraph_ir.NodeFilter(fqn_prefix="test.Calculator")
result = msgpack.unpackb(graph_index.query_nodes(filter_fqn))
actual_names = [n['name'] for n in result['nodes']]
print(f"Count: {result['count']}")
print(f"Nodes: {actual_names}")
assert result['count'] >= 2, f"Expected at least 2 (Calculator, methods), got {result['count']}"
print("✓ PASS")

print("\n" + "=" * 60)
print("✅ ALL COMPREHENSIVE TESTS PASSED!")
print("=" * 60)
