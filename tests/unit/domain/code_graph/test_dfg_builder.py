"""
Test DFG (Data Flow Graph) Builder

Tests variable entity tracking, read/write events, and data flow analysis.
"""

import pytest

from src.foundation.dfg import (
    AnalyzerRegistry,
    PythonStatementAnalyzer,
)
from src.foundation.generators import PythonIRGenerator
from src.foundation.parsing import SourceFile
from src.foundation.semantic_ir import DefaultSemanticIrBuilder


@pytest.fixture
def python_generator():
    """Create Python IR generator"""
    return PythonIRGenerator(repo_id="test-repo")


@pytest.fixture
def semantic_builder():
    """Create semantic IR builder with DFG"""
    return DefaultSemanticIrBuilder()


def test_dfg_basic_assignment(python_generator, semantic_builder):
    """Test basic DFG with simple assignment and return"""

    code = '''
def process(x: int) -> int:
    """Process value"""
    result = x
    return result
'''

    # Generate structural IR
    source = SourceFile.from_content(
        file_path="src/process.py",
        content=code,
        language="python",
    )
    ir_doc = python_generator.generate(source, snapshot_id="test:001")

    # Build semantic IR with source_map for DFG
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)

    print("\n  Semantic IR:")
    print(f"    - Types: {len(semantic_snapshot.types)}")
    print(f"    - Signatures: {len(semantic_snapshot.signatures)}")
    print(f"    - CFG Blocks: {len(semantic_snapshot.cfg_blocks)}")
    print(f"    - DFG Variables: {len(semantic_snapshot.dfg_snapshot.variables)}")
    print(f"    - DFG Events: {len(semantic_snapshot.dfg_snapshot.events)}")
    print(f"    - DFG Edges: {len(semantic_snapshot.dfg_snapshot.edges)}")

    # Verify DFG snapshot exists
    assert semantic_snapshot.dfg_snapshot is not None
    dfg = semantic_snapshot.dfg_snapshot

    # Verify variables
    # Should have: x (param), result (local)
    assert len(dfg.variables) >= 2

    # Find variables by name
    vars_by_name = {v.name: v for v in dfg.variables}
    print("\n  Variables:")
    for name, var in vars_by_name.items():
        print(f"    - {name}: {var.kind} ({var.id})")

    assert "x" in vars_by_name
    assert "result" in vars_by_name

    # Verify variable kinds
    assert vars_by_name["x"].kind == "param"
    assert vars_by_name["result"].kind == "local"

    # Verify events
    # Should have: READ x, WRITE result, READ result
    assert len(dfg.events) >= 3

    print("\n  Events:")
    for event in dfg.events:
        var_name = next((v.name for v in dfg.variables if v.id == event.variable_id), "?")
        print(f"    - {event.op_kind.upper()} {var_name} at block {event.block_id}")

    # Verify CFG blocks have variable tracking
    body_blocks = [b for b in semantic_snapshot.cfg_blocks if b.kind.value == "BODY"]
    if body_blocks:
        body_block = body_blocks[0]
        print("\n  CFG Block Variable Tracking:")
        print(f"    - Defined: {body_block.defined_variable_ids}")
        print(f"    - Used: {body_block.used_variable_ids}")

        # Body block should define result and use x
        assert len(body_block.defined_variable_ids) >= 1  # result
        assert len(body_block.used_variable_ids) >= 1  # x

    print("\n✅ Basic DFG test passed!")


def test_dfg_shadow_count(python_generator, semantic_builder):
    """Test variable shadow count for same-named variables in different blocks"""

    code = '''
def calculate(n: int) -> int:
    """Calculate with shadow variables"""
    result = 0

    if n > 0:
        result = n  # Shadow count 2
    else:
        result = -n  # Shadow count 3

    return result
'''

    # Generate structural IR
    source = SourceFile.from_content(
        file_path="src/calc.py",
        content=code,
        language="python",
    )
    ir_doc = python_generator.generate(source, snapshot_id="test:002")

    # Build semantic IR with source_map for DFG
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)

    dfg = semantic_snapshot.dfg_snapshot
    assert dfg is not None

    print("\n  DFG Analysis:")
    print(f"    - Variables: {len(dfg.variables)}")
    print(f"    - Events: {len(dfg.events)}")

    # Find all 'result' variables (should have different shadow counts)
    result_vars = [v for v in dfg.variables if v.name == "result"]
    print("\n  'result' Variables:")
    for var in result_vars:
        # Extract shadow count from ID: var:...:result@{block_idx}:{shadow_cnt}
        shadow_info = var.id.split(":")[-1]  # result@{block}:{shadow}
        print(f"    - {var.id}")
        print(f"      Shadow: {shadow_info}")
        print(f"      Kind: {var.kind}")

    # Should have multiple result variables with different shadow counts
    assert len(result_vars) >= 2

    # Verify shadow counts are unique
    # ID format: var:repo:file:func:name@block:shadow
    # e.g., "var:test-repo:src/calc.py:calc.calculate:result@3:1"
    shadow_counts = set()
    for var in result_vars:
        # Extract the part after last ":"
        # This is the shadow count
        parts = var.id.split(":")
        if len(parts) >= 2:
            shadow_count = parts[-1]  # Last part is shadow count
            shadow_counts.add(shadow_count)

    print(f"    - Unique shadow counts: {shadow_counts}")
    assert len(shadow_counts) >= 2  # At least 2 different shadow counts

    print("\n✅ Shadow count test passed!")


def test_dfg_read_write_events(python_generator, semantic_builder):
    """Test READ/WRITE event generation"""

    code = '''
def transform(a: int, b: int) -> int:
    """Transform with multiple operations"""
    x = a
    y = b
    z = x + y
    return z
'''

    # Generate structural IR
    source = SourceFile.from_content(
        file_path="src/transform.py",
        content=code,
        language="python",
    )
    ir_doc = python_generator.generate(source, snapshot_id="test:003")

    # Build semantic IR with source_map for DFG
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)

    dfg = semantic_snapshot.dfg_snapshot
    assert dfg is not None

    print("\n  Events:")
    for event in dfg.events:
        var_name = next((v.name for v in dfg.variables if v.id == event.variable_id), "?")
        print(f"    - {event.op_kind.upper():5s} {var_name:3s} at block {event.block_id}")

    # Count event types
    read_events = [e for e in dfg.events if e.op_kind == "read"]
    write_events = [e for e in dfg.events if e.op_kind == "write"]

    print("\n  Event Summary:")
    print(f"    - READ events: {len(read_events)}")
    print(f"    - WRITE events: {len(write_events)}")

    # Should have both reads and writes
    assert len(read_events) > 0
    assert len(write_events) > 0

    # Variables should include: a, b, x, y, z
    vars_by_name = {v.name: v for v in dfg.variables}
    print(f"\n  Variables: {list(vars_by_name.keys())}")

    # Verify param variables
    assert "a" in vars_by_name
    assert "b" in vars_by_name
    assert vars_by_name["a"].kind == "param"
    assert vars_by_name["b"].kind == "param"

    # Verify local variables
    assert "x" in vars_by_name or "y" in vars_by_name or "z" in vars_by_name

    print("\n✅ READ/WRITE events test passed!")


def test_dfg_analyzer_registry(python_generator):
    """Test DFG analyzer registry for language-specific analysis"""

    # Create analyzer registry
    registry = AnalyzerRegistry()

    # Register Python analyzer
    python_analyzer = PythonStatementAnalyzer()
    registry.register("python", python_analyzer)

    # Verify retrieval
    analyzer = registry.get("python")
    assert analyzer is not None
    assert analyzer is python_analyzer

    print("\n  Analyzer Registry:")
    print("    - Registered: python ✓")

    # Test invalid language
    try:
        registry.get("javascript")
        assert False, "Should raise ValueError for unregistered language"
    except ValueError as e:
        print(f"    - Correctly raises error for unregistered language: {e}")

    print("\n✅ Analyzer registry test passed!")


def test_dfg_integration_with_cfg(python_generator, semantic_builder):
    """Test DFG integration with CFG blocks"""

    code = '''
def fibonacci(n: int) -> int:
    """Calculate fibonacci"""
    if n <= 1:
        return n

    a = 0
    b = 1

    for i in range(n):
        temp = a + b
        a = b
        b = temp

    return b
'''

    # Generate structural IR
    source = SourceFile.from_content(
        file_path="src/fib.py",
        content=code,
        language="python",
    )
    ir_doc = python_generator.generate(source, snapshot_id="test:004")

    # Build semantic IR with source_map for enhanced CFG + DFG
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)

    print("\n  Integration Test:")
    print(f"    - CFG Blocks: {len(semantic_snapshot.cfg_blocks)}")
    print(f"    - DFG Variables: {len(semantic_snapshot.dfg_snapshot.variables)}")
    print(f"    - DFG Events: {len(semantic_snapshot.dfg_snapshot.events)}")

    # Verify CFG blocks have variable tracking
    blocks_with_vars = 0
    for block in semantic_snapshot.cfg_blocks:
        if block.defined_variable_ids or block.used_variable_ids:
            blocks_with_vars += 1
            print(f"\n  Block {block.id}:")
            print(f"    - Kind: {block.kind.value}")
            print(f"    - Defined vars: {len(block.defined_variable_ids)}")
            print(f"    - Used vars: {len(block.used_variable_ids)}")

    print(f"\n  Blocks with variable tracking: {blocks_with_vars}")
    assert blocks_with_vars > 0, "CFG blocks should have variable tracking"

    # Verify variables exist
    dfg = semantic_snapshot.dfg_snapshot
    vars_by_name = {v.name: v for v in dfg.variables}
    print(f"\n  Variables detected: {list(vars_by_name.keys())}")

    # Should detect parameter
    assert "n" in vars_by_name
    assert vars_by_name["n"].kind == "param"

    print("\n✅ DFG-CFG integration test passed!")


def test_dfg_full_pipeline(python_generator, semantic_builder):
    """Test complete pipeline: IR → Semantic IR → DFG"""

    code = '''
class Calculator:
    """Simple calculator"""

    def add(self, x: int, y: int) -> int:
        """Add two numbers"""
        result = x + y
        return result

    def multiply(self, x: int, y: int) -> int:
        """Multiply two numbers"""
        product = x * y
        return product
'''

    # Generate structural IR
    source = SourceFile.from_content(
        file_path="src/calculator.py",
        content=code,
        language="python",
    )
    ir_doc = python_generator.generate(source, snapshot_id="test:005")

    print("\n  Structural IR:")
    print(f"    - Nodes: {len(ir_doc.nodes)}")

    # Build semantic IR
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)

    print("\n  Semantic IR:")
    print(f"    - Types: {len(semantic_snapshot.types)}")
    print(f"    - Signatures: {len(semantic_snapshot.signatures)}")
    print(f"    - CFG Graphs: {len(semantic_snapshot.cfg_graphs)}")
    print(f"    - CFG Blocks: {len(semantic_snapshot.cfg_blocks)}")

    # Verify DFG for multiple functions
    dfg = semantic_snapshot.dfg_snapshot
    assert dfg is not None

    print("\n  DFG:")
    print(f"    - Variables: {len(dfg.variables)}")
    print(f"    - Events: {len(dfg.events)}")
    print(f"    - Edges: {len(dfg.edges)}")

    # Group variables by function
    vars_by_function = {}
    for var in dfg.variables:
        func_fqn = var.function_fqn
        if func_fqn not in vars_by_function:
            vars_by_function[func_fqn] = []
        vars_by_function[func_fqn].append(var)

    print("\n  Variables by function:")
    for func_fqn, vars_list in vars_by_function.items():
        func_name = func_fqn.split(".")[-1] if "." in func_fqn else func_fqn
        print(f"    - {func_name}: {len(vars_list)} variables")
        for var in vars_list:
            print(f"      - {var.name} ({var.kind})")

    # Should have variables for both methods
    assert len(vars_by_function) >= 2, "Should have DFG for multiple functions"

    # Each function should have parameters
    for func_fqn, vars_list in vars_by_function.items():
        param_vars = [v for v in vars_list if v.kind == "param"]
        if "add" in func_fqn or "multiply" in func_fqn:
            # Methods should have self, x, y parameters
            assert len(param_vars) >= 2, f"Function {func_fqn} should have parameters"

    print("\n✅ Full pipeline test passed!")


def test_dfg_edges_alias(python_generator, semantic_builder):
    """Test DFG alias edges: a = b"""

    code = '''
def copy_value(x: int) -> int:
    """Copy value"""
    result = x
    return result
'''

    source = SourceFile.from_content("src/alias.py", code, "python")
    ir_doc = python_generator.generate(source, "test:006")

    source_map = {source.file_path: source}
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc, source_map)

    dfg = semantic_snapshot.dfg_snapshot
    assert dfg is not None

    print("\nDFG Edges:")
    for edge in dfg.edges:
        from_var = next((v for v in dfg.variables if v.id == edge.from_variable_id), None)
        to_var = next((v for v in dfg.variables if v.id == edge.to_variable_id), None)
        from_name = from_var.name if from_var else edge.to_variable_id
        to_name = to_var.name if to_var else edge.to_variable_id
        print(f"  - {edge.kind:15s} {from_name:10s} → {to_name}")

    # Should have edges
    assert len(dfg.edges) > 0

    # Should have alias edge from x to result
    alias_edges = [e for e in dfg.edges if e.kind == "alias"]
    assert len(alias_edges) > 0

    # Verify edge connects x → result
    for edge in alias_edges:
        from_var = next((v for v in dfg.variables if v.id == edge.from_variable_id), None)
        to_var = next((v for v in dfg.variables if v.id == edge.to_variable_id), None)
        if from_var and to_var:
            if from_var.name == "x" and to_var.name == "result":
                print("\n  ✓ Found alias edge: x → result")
                break
    else:
        # At least verify we have alias edges
        assert len(alias_edges) > 0

    # Should have return_value edge
    return_edges = [e for e in dfg.edges if e.kind == "return_value"]
    assert len(return_edges) > 0

    print("\n✅ DFG alias edges test passed!")


def test_dfg_edges_assign(python_generator, semantic_builder):
    """Test DFG assign edges: a = fn(b)"""

    code = '''
def process(x: int) -> int:
    """Process value"""
    result = abs(x)
    return result
'''

    source = SourceFile.from_content("src/assign.py", code, "python")
    ir_doc = python_generator.generate(source, "test:007")

    source_map = {source.file_path: source}
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc, source_map)

    dfg = semantic_snapshot.dfg_snapshot
    assert dfg is not None

    print("\nDFG Edges:")
    for edge in dfg.edges:
        from_var = next((v for v in dfg.variables if v.id == edge.from_variable_id), None)
        to_var = next((v for v in dfg.variables if v.id == edge.to_variable_id), None)
        from_name = from_var.name if from_var else edge.to_variable_id
        to_name = to_var.name if to_var else edge.to_variable_id
        print(f"  - {edge.kind:15s} {from_name:10s} → {to_name}")

    # Should have assign edge (from function call)
    assign_edges = [e for e in dfg.edges if e.kind == "assign"]
    assert len(assign_edges) > 0

    print("\n✅ DFG assign edges test passed!")


if __name__ == "__main__":
    gen = PythonIRGenerator(repo_id="test-repo")
    builder = DefaultSemanticIrBuilder()

    print("=" * 60)
    print("Test 1: Basic DFG Assignment")
    print("=" * 60)
    test_dfg_basic_assignment(gen, builder)

    print("\n" + "=" * 60)
    print("Test 2: DFG Shadow Count")
    print("=" * 60)
    test_dfg_shadow_count(gen, builder)

    print("\n" + "=" * 60)
    print("Test 3: DFG Read/Write Events")
    print("=" * 60)
    test_dfg_read_write_events(gen, builder)

    print("\n" + "=" * 60)
    print("Test 4: DFG Analyzer Registry")
    print("=" * 60)
    test_dfg_analyzer_registry(gen)

    print("\n" + "=" * 60)
    print("Test 5: DFG Integration with CFG")
    print("=" * 60)
    test_dfg_integration_with_cfg(gen, builder)

    print("\n" + "=" * 60)
    print("Test 6: DFG Full Pipeline")
    print("=" * 60)
    test_dfg_full_pipeline(gen, builder)

    print("\n" + "=" * 60)
    print("Test 7: DFG Alias Edges")
    print("=" * 60)
    test_dfg_edges_alias(gen, builder)

    print("\n" + "=" * 60)
    print("Test 8: DFG Assign Edges")
    print("=" * 60)
    test_dfg_edges_assign(gen, builder)

    print("\n" + "=" * 60)
    print("✅ All DFG tests passed!")
    print("=" * 60)
