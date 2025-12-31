"""
L1-L5 Rust Integration Test

Tests complete pipeline from Rust IR generation to QueryEngine.
"""

import pytest
from pathlib import Path


def test_rust_l1_l5_integration():
    """Test L1-L5 Rust integration with QueryEngine"""
    from codegraph_engine.code_foundation.infrastructure.generators.rust_adapter import RustIRAdapter
    from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

    # Test code with all L1-L5 features
    code = '''
def calculate(x: int, y: int) -> int:
    """Calculate sum with branching"""
    if x > 0:
        result = x + y
    else:
        result = 0
    return result

class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b
'''

    # Create mock source
    class MockSource:
        def __init__(self):
            self.file_path = "test.py"
            self.content = code
            self.language = "python"

    # Generate IR with Rust
    adapter = RustIRAdapter("test_repo", enable_rust=True)

    if not adapter.is_rust_available():
        pytest.skip("Rust not available")

    sources = [MockSource()]
    ir_docs, errors = adapter.generate_ir_batch(sources)

    # Verify no errors
    assert len(errors) == 0, f"Errors: {errors}"
    assert len(ir_docs) == 1, "Should have 1 IR document"

    ir_doc = ir_docs[0]

    # L1: Verify nodes
    assert len(ir_doc.nodes) > 0, "Should have nodes"
    function_nodes = [n for n in ir_doc.nodes if n.kind.value == "FUNCTION"]
    class_nodes = [n for n in ir_doc.nodes if n.kind.value == "CLASS"]
    assert len(function_nodes) >= 2, "Should have at least 2 functions"
    assert len(class_nodes) >= 1, "Should have at least 1 class"

    # L1: Verify edges
    assert len(ir_doc.edges) > 0, "Should have edges"

    # L2: Verify BFG
    assert hasattr(ir_doc, "bfg_graphs"), "Should have bfg_graphs"
    assert len(ir_doc.bfg_graphs) > 0, "Should have BFG graphs"

    # L2: Verify CFG
    assert hasattr(ir_doc, "cfg_edges"), "Should have cfg_edges"
    assert len(ir_doc.cfg_edges) > 0, "Should have CFG edges"

    # L3: Verify types
    assert hasattr(ir_doc, "type_entities"), "Should have type_entities"
    assert len(ir_doc.type_entities) > 0, "Should have type entities"

    # L4: Verify DFG
    assert hasattr(ir_doc, "dfg_graphs"), "Should have dfg_graphs"
    assert len(ir_doc.dfg_graphs) > 0, "Should have DFG graphs"

    # L5: Verify SSA
    assert hasattr(ir_doc, "ssa_graphs"), "Should have ssa_graphs"
    assert len(ir_doc.ssa_graphs) > 0, "Should have SSA graphs"

    print("✅ L1-L5 Rust integration verified!")

    # Query Engine test
    engine = QueryEngine(ir_doc)

    # Test basic query
    from codegraph_engine.code_foundation.domain.query.expressions import PathQuery

    # Find all functions
    functions = [n for n in ir_doc.nodes if n.kind.value == "FUNCTION"]
    assert len(functions) >= 2, "Should find functions"

    print(f"✅ QueryEngine initialized with {len(functions)} functions")
    print(f"✅ L1: {len(ir_doc.nodes)} nodes, {len(ir_doc.edges)} edges")
    print(f"✅ L2: {len(ir_doc.bfg_graphs)} BFG graphs, {len(ir_doc.cfg_edges)} CFG edges")
    print(f"✅ L3: {len(ir_doc.type_entities)} type entities")
    print(f"✅ L4: {len(ir_doc.dfg_graphs)} DFG graphs")
    print(f"✅ L5: {len(ir_doc.ssa_graphs)} SSA graphs")


def test_rust_edge_cases():
    """Test Rust integration with edge cases"""
    from codegraph_engine.code_foundation.infrastructure.generators.rust_adapter import RustIRAdapter

    adapter = RustIRAdapter("test_repo", enable_rust=True)

    if not adapter.is_rust_available():
        pytest.skip("Rust not available")

    # Edge case: Empty file
    class MockSource:
        def __init__(self, content):
            self.file_path = "test.py"
            self.content = content
            self.language = "python"

    # Test empty
    ir_docs, errors = adapter.generate_ir_batch([MockSource("")])
    assert len(ir_docs) == 1 or len(errors) == 1, "Should handle empty file"

    # Test simple
    ir_docs, errors = adapter.generate_ir_batch([MockSource("x = 1")])
    assert len(ir_docs) == 1, "Should handle simple code"

    print("✅ Edge cases handled correctly")


def test_rust_large_scale():
    """Test Rust integration with large code"""
    from codegraph_engine.code_foundation.infrastructure.generators.rust_adapter import RustIRAdapter

    adapter = RustIRAdapter("test_repo", enable_rust=True)

    if not adapter.is_rust_available():
        pytest.skip("Rust not available")

    # Generate large code
    code = "\n".join([f"def func_{i}(x: int) -> int:\n    return x + {i}" for i in range(100)])

    class MockSource:
        def __init__(self):
            self.file_path = "test.py"
            self.content = code
            self.language = "python"

    ir_docs, errors = adapter.generate_ir_batch([MockSource()])

    assert len(errors) == 0, f"Errors: {errors}"
    assert len(ir_docs) == 1, "Should have 1 IR document"

    ir_doc = ir_docs[0]
    function_nodes = [n for n in ir_doc.nodes if n.kind.value == "FUNCTION"]
    assert len(function_nodes) >= 100, f"Should have 100 functions, got {len(function_nodes)}"

    print(f"✅ Large scale: {len(function_nodes)} functions processed")
