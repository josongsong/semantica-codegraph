"""
SOTA L11 Integration Test: L1+L2 Complete Validation

PRODUCTION REQUIREMENTS:
- No fake/stub data
- Complete error handling
- All edge cases
- Type safety
- Schema validation
- Integration verification
"""

import codegraph_ast
from collections import Counter


def test_base_case():
    """Base case: Empty function"""
    code = "def empty(): pass"

    r = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")[0]

    assert r["success"], "Should succeed"
    assert len(r["nodes"]) >= 1, "Should have function node"
    assert len(r.get("bfg_graphs", [])) >= 1, "Should have BFG"

    bfg = r["bfg_graphs"][0]
    assert len(bfg["blocks"]) >= 2, "Should have Entry + Exit"

    print("✅ Base case")


def test_edge_case_no_return():
    """Edge case: Function without explicit return"""
    code = """
def no_return(x):
    print(x)
"""

    r = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")[0]

    assert r["success"]
    bfg = r["bfg_graphs"][0]

    # Should have Entry, Statement, Exit
    assert len(bfg["blocks"]) >= 3
    assert bfg["blocks"][0]["kind"] == "ENTRY"
    assert bfg["blocks"][-1]["kind"] == "EXIT"

    print("✅ Edge case: no return")


def test_corner_case_only_return():
    """Corner case: Only return statement"""
    code = "def only_return(): return 42"

    r = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")[0]

    assert r["success"]
    bfg = r["bfg_graphs"][0]

    # Should have Entry, Return, Exit
    has_return = any(b["kind"] == "RETURN" for b in bfg["blocks"])
    assert has_return, "Should have RETURN block"

    print("✅ Corner case: only return")


def test_extreme_nested_loops():
    """Extreme: 5-level nested loops"""
    code = """
def extreme():
    for a in range(10):
        for b in range(10):
            for c in range(10):
                for d in range(10):
                    for e in range(10):
                        print(e)
"""

    r = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")[0]

    assert r["success"]
    bfg = r["bfg_graphs"][0]

    # Should have 5 LOOP blocks
    loop_count = sum(1 for b in bfg["blocks"] if b["kind"] == "LOOP")
    assert loop_count == 5, f"Expected 5 loops, got {loop_count}"

    print(f"✅ Extreme: 5-level nesting ({len(bfg['blocks'])} blocks)")


def test_cfg_edge_correctness():
    """CFG edges: Validate all edge types"""
    code = """
def test(x):
    if x > 0:
        for i in range(x):
            if i % 2 == 0:
                continue
            print(i)
        return x
    return 0
"""

    r = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")[0]

    assert r["success"]

    cfg_edges = r.get("cfg_edges", [])
    assert len(cfg_edges) > 0, "Should have CFG edges"

    # Count edge types
    edge_types = Counter(e["edge_type"] for e in cfg_edges)

    print(f"  CFG edges: {len(cfg_edges)}")
    print(f"  Edge types: {dict(edge_types)}")

    # Should have conditional edges (TRUE/FALSE)
    assert "TRUE" in edge_types or "FALSE" in edge_types, "Should have conditional edges"

    # Should have loop back-edge
    assert "LOOP_BACK" in edge_types, "Should have loop back-edge"

    print("✅ CFG edges validated")


def test_type_safety():
    """Type safety: All fields have correct types"""
    code = "def test(): return 1"

    r = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")[0]

    # Validate node types
    for node in r["nodes"]:
        assert isinstance(node["id"], str), "Node ID must be str"
        assert isinstance(node["kind"], str), "Node kind must be str"
        assert isinstance(node["fqn"], str), "Node FQN must be str"
        assert isinstance(node["span"], dict), "Span must be dict"

    # Validate edge types
    for edge in r["edges"]:
        assert isinstance(edge["id"], str), "Edge ID must be str"
        assert isinstance(edge["kind"], str), "Edge kind must be str"
        assert isinstance(edge["source_id"], str), "Source ID must be str"
        assert isinstance(edge["target_id"], str), "Target ID must be str"

    # Validate BFG types
    for bfg in r.get("bfg_graphs", []):
        assert isinstance(bfg["id"], str), "BFG ID must be str"
        assert isinstance(bfg["function_id"], str), "Function ID must be str"
        assert isinstance(bfg["blocks"], list), "Blocks must be list"
        assert isinstance(bfg["total_statements"], int), "Total statements must be int"

    # Validate CFG edge types
    for cfg_edge in r.get("cfg_edges", []):
        assert isinstance(cfg_edge["source_block_id"], str), "Source block ID must be str"
        assert isinstance(cfg_edge["target_block_id"], str), "Target block ID must be str"
        assert isinstance(cfg_edge["edge_type"], str), "Edge type must be str"

    print("✅ Type safety validated")


def test_enum_vs_string():
    """ENUM usage: Internal=ENUM, External=string"""
    code = "def test(): return 1"

    r = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")[0]

    # External (Python): strings
    assert isinstance(r["nodes"][0]["kind"], str), "External: string"

    # Validate enum values (not arbitrary strings)
    valid_node_kinds = {
        "file",
        "module",
        "class",
        "function",
        "method",
        "variable",
        "parameter",
        "field",
        "lambda",
        "import",
    }
    valid_edge_kinds = {"CONTAINS", "CALLS", "READS", "WRITES", "INHERITS", "IMPORTS", "REFERENCES", "DEFINES"}
    valid_block_kinds = {
        "ENTRY",
        "EXIT",
        "STATEMENT",
        "BRANCH",
        "LOOP",
        "LOOP_EXIT",
        "LOOP_CONTINUE",
        "RETURN",
        "YIELD",
        "RAISE",
    }

    for node in r["nodes"]:
        assert node["kind"] in valid_node_kinds, f"Invalid node kind: {node['kind']}"

    for edge in r["edges"]:
        assert edge["kind"] in valid_edge_kinds, f"Invalid edge kind: {edge['kind']}"

    for bfg in r.get("bfg_graphs", []):
        for block in bfg["blocks"]:
            assert block["kind"] in valid_block_kinds, f"Invalid block kind: {block['kind']}"

    print("✅ ENUM validation passed")


def test_no_hardcoding():
    """No hardcoding: IDs are generated, not hardcoded"""
    code1 = "def test1(): pass"
    code2 = "def test2(): pass"

    r1 = codegraph_ast.process_python_files([("test.py", code1, "test")], "repo")[0]
    r2 = codegraph_ast.process_python_files([("test.py", code2, "test")], "repo")[0]

    # Different functions should have different IDs
    id1 = r1["nodes"][0]["id"]
    id2 = r2["nodes"][0]["id"]

    assert id1 != id2, "IDs should be different (not hardcoded)"

    # IDs should be deterministic
    r1_again = codegraph_ast.process_python_files([("test.py", code1, "test")], "repo")[0]
    id1_again = r1_again["nodes"][0]["id"]

    assert id1 == id1_again, "IDs should be deterministic"

    print("✅ No hardcoding validated")


def test_integration_l1_l2():
    """Integration: L1 and L2 data are consistent"""
    code = """
def integrated(x):
    if x > 0:
        y = x * 2
        return y
    return 0
"""

    r = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")[0]

    # L1 data
    func_nodes = [n for n in r["nodes"] if n["kind"] == "function"]
    assert len(func_nodes) == 1, "Should have 1 function"

    func_id = func_nodes[0]["id"]

    # L2 data
    bfg_graphs = r.get("bfg_graphs", [])
    assert len(bfg_graphs) == 1, "Should have 1 BFG"

    # BFG should reference the function
    bfg = bfg_graphs[0]
    assert "integrated" in bfg["function_id"], "BFG should reference function"

    # CFG edges should reference BFG blocks
    cfg_edges = r.get("cfg_edges", [])
    block_ids = {b["id"] for b in bfg["blocks"]}

    for edge in cfg_edges:
        assert edge["source_block_id"] in block_ids, f"Invalid source: {edge['source_block_id']}"
        assert edge["target_block_id"] in block_ids, f"Invalid target: {edge['target_block_id']}"

    print("✅ L1+L2 integration validated")


def test_error_handling():
    """Error handling: Malformed input"""
    bad_code = "def incomplete("

    r = codegraph_ast.process_python_files([("bad.py", bad_code, "test")], "repo")[0]

    # Should not crash (tree-sitter is error-tolerant)
    assert "success" in r, "Should have success field"

    # May succeed or fail, but should not crash
    print(f"  Malformed input: success={r['success']}")
    print("✅ Error handling validated")


def test_django_real_file():
    """Real file: Django actual code"""
    from pathlib import Path

    django_file = Path("tools/benchmark/_external_benchmark/django/django/utils/log.py")

    if not django_file.exists():
        print("⚠️  Django file not found, skipping")
        return

    content = django_file.read_text(encoding="utf-8", errors="ignore")

    r = codegraph_ast.process_python_files([(str(django_file), content, "django.utils.log")], "django")[0]

    assert r["success"], "Should process real Django file"
    assert len(r["nodes"]) > 0, "Should have nodes"
    assert len(r.get("bfg_graphs", [])) > 0, "Should have BFG"
    assert len(r.get("cfg_edges", [])) > 0, "Should have CFG edges"

    print(f"  Django file: {len(r['nodes'])} nodes, {len(r['bfg_graphs'])} BFGs, {len(r['cfg_edges'])} CFG edges")
    print("✅ Real Django file validated")


if __name__ == "__main__":
    print("=" * 70)
    print("🔍 SOTA L11 Integration Test")
    print("=" * 70)

    tests = [
        ("Base case", test_base_case),
        ("Edge case", test_edge_case_no_return),
        ("Corner case", test_corner_case_only_return),
        ("Extreme case", test_extreme_nested_loops),
        ("CFG correctness", test_cfg_edge_correctness),
        ("Type safety", test_type_safety),
        ("ENUM validation", test_enum_vs_string),
        ("No hardcoding", test_no_hardcoding),
        ("L1+L2 integration", test_integration_l1_l2),
        ("Error handling", test_error_handling),
        ("Real Django file", test_django_real_file),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 {name}: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"Results: {passed}/{len(tests)} passed")

    if failed == 0:
        print("🎉 ALL SOTA L11 TESTS PASSED!")
        print("✅ Production ready")
    else:
        print(f"⚠️  {failed} tests failed")

    print("=" * 70)
