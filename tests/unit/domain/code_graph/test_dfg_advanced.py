"""
Test DFG Advanced Patterns (Phase 2)

Tests tuple destructuring, attribute access, subscript, and comprehensions.
"""

import pytest
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


def test_tuple_destructuring(python_generator, semantic_builder):
    """Test tuple destructuring: a, b = x, y"""

    code = '''
def swap(x: int, y: int) -> tuple:
    """Swap values"""
    a, b = y, x
    return a, b
'''

    source = SourceFile.from_content("src/swap.py", code, "python")
    ir_doc = python_generator.generate(source, "test:001")

    source_map = {source.file_path: source}
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc, source_map)

    dfg = semantic_snapshot.dfg_snapshot
    assert dfg is not None

    # Get variable names
    vars_by_name = {v.name: v for v in dfg.variables}
    print(f"\nVariables: {list(vars_by_name.keys())}")

    # Should detect parameters
    assert "x" in vars_by_name
    assert "y" in vars_by_name

    # Should detect tuple targets
    assert "a" in vars_by_name
    assert "b" in vars_by_name

    # Check events
    print("\nEvents:")
    for event in dfg.events:
        var_name = next((v.name for v in dfg.variables if v.id == event.variable_id), "?")
        print(f"  - {event.op_kind.upper():5s} {var_name}")

    # Should have READ events for x, y
    read_events = [e for e in dfg.events if e.op_kind == "read"]
    read_var_names = [next((v.name for v in dfg.variables if v.id == e.variable_id), "?") for e in read_events]
    assert "x" in read_var_names
    assert "y" in read_var_names

    # Should have WRITE events for a, b
    write_events = [e for e in dfg.events if e.op_kind == "write"]
    write_var_names = [next((v.name for v in dfg.variables if v.id == e.variable_id), "?") for e in write_events]
    assert "a" in write_var_names
    assert "b" in write_var_names

    print("\n✅ Tuple destructuring test passed!")


def test_attribute_access(python_generator, semantic_builder):
    """Test attribute access: result = obj.field"""

    code = '''
def get_field(obj) -> int:
    """Get field from object"""
    result = obj.value
    return result
'''

    source = SourceFile.from_content("src/attr.py", code, "python")
    ir_doc = python_generator.generate(source, "test:002")

    source_map = {source.file_path: source}
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc, source_map)

    dfg = semantic_snapshot.dfg_snapshot
    assert dfg is not None

    vars_by_name = {v.name: v for v in dfg.variables}
    print(f"\nVariables: {list(vars_by_name.keys())}")

    # Should have obj and result
    assert "obj" in vars_by_name
    assert "result" in vars_by_name

    # Should NOT have 'value' as a separate variable
    # (it's an attribute, not a standalone variable)
    assert "value" not in vars_by_name

    # Check events
    read_events = [e for e in dfg.events if e.op_kind == "read"]
    read_var_names = [next((v.name for v in dfg.variables if v.id == e.variable_id), "?") for e in read_events]

    # Should read obj (not obj.value)
    assert "obj" in read_var_names

    print("\n✅ Attribute access test passed!")


def test_subscript_access(python_generator, semantic_builder):
    """Test subscript: value = arr[i]"""

    code = '''
def get_item(arr, i: int):
    """Get item from array"""
    value = arr[i]
    return value
'''

    source = SourceFile.from_content("src/subscript.py", code, "python")
    ir_doc = python_generator.generate(source, "test:003")

    source_map = {source.file_path: source}
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc, source_map)

    dfg = semantic_snapshot.dfg_snapshot
    assert dfg is not None

    vars_by_name = {v.name: v for v in dfg.variables}
    print(f"\nVariables: {list(vars_by_name.keys())}")

    # Should have arr, i, value
    assert "arr" in vars_by_name
    assert "i" in vars_by_name
    assert "value" in vars_by_name

    # Check events
    read_events = [e for e in dfg.events if e.op_kind == "read"]
    read_var_names = [next((v.name for v in dfg.variables if v.id == e.variable_id), "?") for e in read_events]

    # Should read both arr and i
    assert "arr" in read_var_names
    assert "i" in read_var_names

    print("\n✅ Subscript access test passed!")


def test_list_comprehension(python_generator, semantic_builder):
    """Test list comprehension: [x*x for x in items]"""

    code = '''
def squares(items):
    """Calculate squares"""
    result = [x * x for x in items]
    return result
'''

    source = SourceFile.from_content("src/comp.py", code, "python")
    ir_doc = python_generator.generate(source, "test:004")

    source_map = {source.file_path: source}
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc, source_map)

    dfg = semantic_snapshot.dfg_snapshot
    assert dfg is not None

    vars_by_name = {v.name: v for v in dfg.variables}
    print(f"\nVariables: {list(vars_by_name.keys())}")

    # Should have items and result
    assert "items" in vars_by_name
    assert "result" in vars_by_name

    # Check events
    read_events = [e for e in dfg.events if e.op_kind == "read"]
    read_var_names = [next((v.name for v in dfg.variables if v.id == e.variable_id), "?") for e in read_events]

    # Should read items
    assert "items" in read_var_names

    # Note: 'x' is a comprehension loop variable
    # We may or may not track it depending on implementation
    # For now, we just verify that items is read

    print("\n✅ List comprehension test passed!")


def test_complex_pattern(python_generator, semantic_builder):
    """Test complex pattern combining multiple features"""

    code = '''
def process_data(data, index: int):
    """Complex data processing"""
    # Tuple destructuring
    key, value = data[index]

    # Attribute access
    result = value.count

    # Subscript with expression
    item = data[index + 1]

    return result, item
'''

    source = SourceFile.from_content("src/complex.py", code, "python")
    ir_doc = python_generator.generate(source, "test:005")

    source_map = {source.file_path: source}
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc, source_map)

    dfg = semantic_snapshot.dfg_snapshot
    assert dfg is not None

    vars_by_name = {v.name: v for v in dfg.variables}
    print(f"\nVariables: {list(vars_by_name.keys())}")

    # Should have parameters
    assert "data" in vars_by_name
    assert "index" in vars_by_name

    # Should have tuple targets
    assert "key" in vars_by_name
    assert "value" in vars_by_name

    # Should have result variables
    assert "result" in vars_by_name
    assert "item" in vars_by_name

    # Should NOT have attribute names as variables
    assert "count" not in vars_by_name

    print("\n✅ Complex pattern test passed!")


if __name__ == "__main__":
    gen = PythonIRGenerator(repo_id="test-repo")
    builder = DefaultSemanticIrBuilder()

    print("=" * 60)
    print("Test 1: Tuple Destructuring")
    print("=" * 60)
    test_tuple_destructuring(gen, builder)

    print("\n" + "=" * 60)
    print("Test 2: Attribute Access")
    print("=" * 60)
    test_attribute_access(gen, builder)

    print("\n" + "=" * 60)
    print("Test 3: Subscript Access")
    print("=" * 60)
    test_subscript_access(gen, builder)

    print("\n" + "=" * 60)
    print("Test 4: List Comprehension")
    print("=" * 60)
    test_list_comprehension(gen, builder)

    print("\n" + "=" * 60)
    print("Test 5: Complex Pattern")
    print("=" * 60)
    test_complex_pattern(gen, builder)

    print("\n" + "=" * 60)
    print("✅ All advanced DFG tests passed!")
    print("=" * 60)
