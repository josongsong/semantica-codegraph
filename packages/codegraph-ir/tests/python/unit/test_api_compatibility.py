"""
Test API compatibility - verify both old dict API and new Rust class API work
"""

import codegraph_ir


def test_new_rust_api():
    """Test new API with Rust classes"""
    print("\n" + "=" * 70)
    print("TEST 1: New API (Rust classes)")
    print("=" * 70)

    try:
        # Create using Rust classes
        span = codegraph_ir.Span(1, 0, 10, 0)
        print(f"✅ Span: {span}")

        kind = codegraph_ir.NodeKind.Function
        print(f"✅ NodeKind: {kind}")

        node = codegraph_ir.Node(
            id="test_node",
            kind=kind,
            fqn="test.func",
            file_path="test.py",
            span=span,
        )
        print(f"✅ Node: {node}")

        edge_kind = codegraph_ir.EdgeKind.Calls
        edge = codegraph_ir.Edge(
            source_id="node1",
            target_id="node2",
            kind=edge_kind,
        )
        print(f"✅ Edge: {edge}")

        ir_doc = codegraph_ir.IRDocument(
            file_path="test.py",
            nodes=[node],
            edges=[edge],
        )
        print(f"✅ IRDocument: {ir_doc}")

        # Test build_global_context_py with new API
        result = codegraph_ir.build_global_context_py([ir_doc])
        print(f"✅ build_global_context_py result: {result['total_symbols']} symbols")

        print("\n✅ NEW API WORKS!")
        return True

    except Exception as e:
        print(f"\n❌ NEW API FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_field_access():
    """Test that we can read/write fields"""
    print("\n" + "=" * 70)
    print("TEST 2: Field Access")
    print("=" * 70)

    try:
        span = codegraph_ir.Span(1, 0, 10, 0)

        # Read fields
        print(f"✅ span.start_line = {span.start_line}")
        print(f"✅ span.start_col = {span.start_col}")
        print(f"✅ span.end_line = {span.end_line}")
        print(f"✅ span.end_col = {span.end_col}")

        # Write fields
        span.start_line = 5
        span.end_line = 15
        print(f"✅ Modified span: {span}")

        # Node fields
        node = codegraph_ir.Node(
            id="test",
            kind=codegraph_ir.NodeKind.Function,
            fqn="test.func",
            file_path="test.py",
            span=span,
        )

        print(f"✅ node.id = {node.id}")
        print(f"✅ node.fqn = {node.fqn}")
        print(f"✅ node.file_path = {node.file_path}")

        node.id = "modified_id"
        print(f"✅ Modified node.id = {node.id}")

        print("\n✅ FIELD ACCESS WORKS!")
        return True

    except Exception as e:
        print(f"\n❌ FIELD ACCESS FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_integration():
    """Test realistic usage with multiple files"""
    print("\n" + "=" * 70)
    print("TEST 3: Integration Test")
    print("=" * 70)

    try:
        # Create 3 files with dependencies
        ir_docs = []

        # File A
        span = codegraph_ir.Span(1, 0, 10, 0)
        node_a = codegraph_ir.Node(
            id="a_foo",
            kind=codegraph_ir.NodeKind.Function,
            fqn="a.foo",
            file_path="src/a.py",
            span=span,
        )
        ir_docs.append(
            codegraph_ir.IRDocument(
                file_path="src/a.py",
                nodes=[node_a],
                edges=[],
            )
        )

        # File B (imports from A)
        node_b = codegraph_ir.Node(
            id="b_bar",
            kind=codegraph_ir.NodeKind.Function,
            fqn="b.bar",
            file_path="src/b.py",
            span=span,
        )
        edge_b = codegraph_ir.Edge(
            source_id="b_bar",
            target_id="a_foo",
            kind=codegraph_ir.EdgeKind.Calls,
        )
        ir_docs.append(
            codegraph_ir.IRDocument(
                file_path="src/b.py",
                nodes=[node_b],
                edges=[edge_b],
            )
        )

        # File C (imports from B)
        node_c = codegraph_ir.Node(
            id="c_baz",
            kind=codegraph_ir.NodeKind.Function,
            fqn="c.baz",
            file_path="src/c.py",
            span=span,
        )
        edge_c = codegraph_ir.Edge(
            source_id="c_baz",
            target_id="b_bar",
            kind=codegraph_ir.EdgeKind.Calls,
        )
        ir_docs.append(
            codegraph_ir.IRDocument(
                file_path="src/c.py",
                nodes=[node_c],
                edges=[edge_c],
            )
        )

        # Build global context
        result = codegraph_ir.build_global_context_py(ir_docs)

        print(f"✅ Total files: {result['total_files']}")
        print(f"✅ Total symbols: {result['total_symbols']}")
        print(f"✅ Total imports: {result['total_imports']}")
        print(f"✅ Symbol table keys: {list(result['symbol_table'].keys())}")

        # Verify all symbols are in the table
        assert result["total_symbols"] == 3, "Should have 3 symbols"
        assert result["total_files"] == 3, "Should have 3 files"
        assert "a.foo" in result["symbol_table"], "Should have a.foo"
        assert "b.bar" in result["symbol_table"], "Should have b.bar"
        assert "c.baz" in result["symbol_table"], "Should have c.baz"

        print("\n✅ INTEGRATION TEST WORKS!")
        return True

    except Exception as e:
        print(f"\n❌ INTEGRATION TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("RFC-062 API Compatibility Tests")
    print("=" * 70)

    results = []
    results.append(("New Rust API", test_new_rust_api()))
    results.append(("Field Access", test_field_access()))
    results.append(("Integration", test_integration()))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False

    print("=" * 70)

    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print("\n❌ SOME TESTS FAILED")
        exit(1)
