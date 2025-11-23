"""
Basic test for Python IR Generator
"""

import pytest

from src.foundation.generators import PythonIRGenerator
from src.foundation.ir.models import NodeKind
from src.foundation.parsing import SourceFile


@pytest.fixture
def generator():
    """Create Python IR generator"""
    return PythonIRGenerator(repo_id="test-repo")


def test_simple_class_generation(generator):
    """Test generating IR from simple Python class"""

    # Simple Python code
    code = '''"""Module docstring"""

class Calculator:
    """A simple calculator class"""

    def add(self, a, b):
        """Add two numbers"""
        return a + b

    def multiply(self, a, b):
        """Multiply two numbers"""
        result = a * b
        return result
'''

    # Create source file
    source = SourceFile.from_content(
        file_path="src/calculator.py",
        content=code,
        language="python",
    )

    # Generate IR
    ir_doc = generator.generate(source, snapshot_id="test:001")

    # Verify IR document
    assert ir_doc.repo_id == "test-repo"
    assert ir_doc.snapshot_id == "test:001"
    assert ir_doc.schema_version == "4.1.0"

    # Verify nodes
    assert len(ir_doc.nodes) > 0

    # Find nodes by kind
    nodes_by_kind = {}
    for node in ir_doc.nodes:
        nodes_by_kind.setdefault(node.kind, []).append(node)

    # Should have 1 File node
    assert NodeKind.FILE in nodes_by_kind
    assert len(nodes_by_kind[NodeKind.FILE]) == 1

    file_node = nodes_by_kind[NodeKind.FILE][0]
    assert file_node.file_path == "src/calculator.py"
    assert file_node.fqn == "calculator"

    # Should have 1 Class node
    assert NodeKind.CLASS in nodes_by_kind
    assert len(nodes_by_kind[NodeKind.CLASS]) == 1

    class_node = nodes_by_kind[NodeKind.CLASS][0]
    assert class_node.name == "Calculator"
    assert class_node.fqn == "calculator.Calculator"
    assert class_node.docstring == "A simple calculator class"

    # Should have 2 Method nodes
    assert NodeKind.METHOD in nodes_by_kind
    assert len(nodes_by_kind[NodeKind.METHOD]) == 2

    method_names = {m.name for m in nodes_by_kind[NodeKind.METHOD]}
    assert "add" in method_names
    assert "multiply" in method_names

    # Verify control flow summary
    for method in nodes_by_kind[NodeKind.METHOD]:
        assert method.control_flow_summary is not None
        # Simple methods should have complexity 1
        assert method.control_flow_summary.cyclomatic_complexity >= 1

    # Should have Variable nodes (parameters + local variables)
    if NodeKind.VARIABLE in nodes_by_kind:
        var_nodes = nodes_by_kind[NodeKind.VARIABLE]
        print(f"\n  Variable nodes found: {len(var_nodes)}")
        for var in var_nodes:
            print(f"    - {var.name} ({var.attrs.get('var_kind', 'unknown')})")

    # Verify edges
    assert len(ir_doc.edges) > 0

    # All edges should be CONTAINS for now
    for edge in ir_doc.edges:
        assert edge.kind.value == "CONTAINS"

    print(f"\n✅ Generated {len(ir_doc.nodes)} nodes, {len(ir_doc.edges)} edges")
    for kind, nodes in nodes_by_kind.items():
        print(f"  - {kind.value}: {len(nodes)}")


def test_function_with_control_flow(generator):
    """Test control flow summary calculation"""

    code = '''
def complex_function(x):
    """Function with branches and loops"""
    if x > 0:
        result = 0
        for i in range(x):
            if i % 2 == 0:
                result += i
        return result
    elif x < 0:
        return -1
    else:
        return 0
'''

    source = SourceFile.from_content(
        file_path="src/utils.py",
        content=code,
        language="python",
    )

    ir_doc = generator.generate(source, snapshot_id="test:002")

    # Find function nodes (exclude external)
    func_nodes = [
        n for n in ir_doc.nodes
        if n.kind == NodeKind.FUNCTION and not n.attrs.get("is_external")
    ]
    assert len(func_nodes) == 1

    func = func_nodes[0]
    assert func.name == "complex_function"

    # Verify control flow summary
    cf = func.control_flow_summary
    assert cf is not None
    assert cf.has_loop is True  # Has for loop
    assert cf.cyclomatic_complexity > 1  # Has if/elif/else branches
    assert cf.branch_count >= 3  # if + nested if + elif

    print(f"\n✅ Control Flow Summary:")
    print(f"  - Cyclomatic Complexity: {cf.cyclomatic_complexity}")
    print(f"  - Has Loop: {cf.has_loop}")
    print(f"  - Branch Count: {cf.branch_count}")


def test_imports(generator):
    """Test import node generation"""

    code = '''
import os
import numpy as np
from typing import List, Dict
from pathlib import Path

def process_file(path: str) -> List[str]:
    """Process a file"""
    p = Path(path)
    return []
'''

    source = SourceFile.from_content(
        file_path="src/processor.py",
        content=code,
        language="python",
    )

    ir_doc = generator.generate(source, snapshot_id="test:003")

    # Find import nodes
    import_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.IMPORT]
    print(f"\n  Import nodes found: {len(import_nodes)}")
    for imp in import_nodes:
        attrs = imp.attrs
        print(f"    - {attrs.get('full_symbol')} as {attrs.get('alias')}")

    # Should have: os, numpy, typing.List, typing.Dict, pathlib.Path
    assert len(import_nodes) >= 4

    print(f"\n✅ Generated {len(ir_doc.nodes)} nodes with {len(import_nodes)} imports")


def test_function_calls(generator):
    """Test function call tracking (CALLS edges)"""

    code = '''
import os

def helper(x):
    """Helper function"""
    return x * 2

class Processor:
    """Data processor"""

    def process(self, data):
        """Process data"""
        result = helper(data)  # Call to local function
        result = self.validate(result)  # Call to own method
        path = os.path.join("tmp", "file.txt")  # Call to imported function
        print(result)  # Call to builtin
        return result

    def validate(self, value):
        """Validate value"""
        return value if value > 0 else 0
'''

    source = SourceFile.from_content(
        file_path="src/processor.py",
        content=code,
        language="python",
    )

    ir_doc = generator.generate(source, snapshot_id="test:004")

    # Find CALLS edges
    call_edges = [e for e in ir_doc.edges if e.kind.value == "CALLS"]
    print(f"\n  CALLS edges found: {len(call_edges)}")

    # Analyze calls
    for edge in call_edges:
        callee_name = edge.attrs.get("callee_name", "unknown")
        print(f"    - {edge.source_id.split(':')[-1]} → {callee_name}")

    # Should have at least 4 calls:
    # 1. helper() from process
    # 2. self.validate() from process
    # 3. os.path.join() from process
    # 4. print() from process
    assert len(call_edges) >= 4

    # Check external functions
    external_nodes = [n for n in ir_doc.nodes if n.attrs.get("is_external")]
    print(f"\n  External function nodes: {len(external_nodes)}")
    for ext in external_nodes:
        print(f"    - {ext.name}")

    print(f"\n✅ Generated {len(ir_doc.nodes)} nodes with {len(call_edges)} CALLS edges")


def test_type_resolution(generator):
    """Test type annotation resolution (BUILTIN/LOCAL)"""

    code = '''
class DataPoint:
    """A data point class"""
    pass

def process_data(
    count: int,
    name: str,
    items: list,
    point: DataPoint
) -> DataPoint:
    """Process data with typed parameters"""
    result = point
    return result
'''

    source = SourceFile.from_content(
        file_path="src/data.py",
        content=code,
        language="python",
    )

    ir_doc = generator.generate(source, snapshot_id="test:005")

    print(f"\n  Total nodes: {len(ir_doc.nodes)}")
    print(f"  Total types: {len(ir_doc.types)}")
    print(f"  Total signatures: {len(ir_doc.signatures)}")

    # Find the function
    func_nodes = [
        n for n in ir_doc.nodes
        if n.kind == NodeKind.FUNCTION and n.name == "process_data"
    ]
    assert len(func_nodes) == 1
    func = func_nodes[0]

    # Function should have signature
    assert func.signature_id is not None
    print(f"\n  Function signature_id: {func.signature_id}")

    # Find the signature entity
    signature = next((s for s in ir_doc.signatures if s.id == func.signature_id), None)
    assert signature is not None
    print(f"    - raw: {signature.raw}")
    print(f"    - parameter_type_ids: {len(signature.parameter_type_ids)}")
    print(f"    - return_type_id: {signature.return_type_id}")

    # Signature should have return type
    assert signature.return_type_id is not None

    # Find the return type entity
    return_type = next((t for t in ir_doc.types if t.id == signature.return_type_id), None)
    assert return_type is not None
    print(f"\n  Return type:")
    print(f"    - raw: {return_type.raw}")
    print(f"    - flavor: {return_type.flavor.value}")
    print(f"    - resolution_level: {return_type.resolution_level.value}")

    # Return type should be LOCAL (DataPoint class)
    assert return_type.raw == "DataPoint"
    assert return_type.resolution_level.value == "local"

    # Find parameters
    param_nodes = [
        n for n in ir_doc.nodes
        if n.kind == NodeKind.VARIABLE
        and n.attrs.get("var_kind") == "parameter"
        and n.name in ("count", "name", "items", "point")
    ]

    print(f"\n  Parameters with types:")
    for param in param_nodes:
        type_id = param.declared_type_id
        if type_id:
            type_entity = next((t for t in ir_doc.types if t.id == type_id), None)
            if type_entity:
                print(f"    - {param.name}: {type_entity.raw} ({type_entity.resolution_level.value})")

    # Should have 4 parameters: count, name, items, point
    assert len(param_nodes) == 4

    # Signature should have 4 parameter types
    assert len(signature.parameter_type_ids) == 4

    # Verify each parameter has correct type
    param_types = {}
    for param in param_nodes:
        if param.declared_type_id:
            type_entity = next((t for t in ir_doc.types if t.id == param.declared_type_id), None)
            param_types[param.name] = type_entity

    # count: int (BUILTIN)
    assert "count" in param_types
    assert param_types["count"].raw == "int"
    assert param_types["count"].resolution_level.value == "builtin"

    # name: str (BUILTIN)
    assert "name" in param_types
    assert param_types["name"].raw == "str"
    assert param_types["name"].resolution_level.value == "builtin"

    # items: list (BUILTIN)
    assert "items" in param_types
    assert param_types["items"].raw == "list"
    assert param_types["items"].resolution_level.value == "builtin"

    # point: DataPoint (LOCAL)
    assert "point" in param_types
    assert param_types["point"].raw == "DataPoint"
    assert param_types["point"].resolution_level.value == "local"
    # Should resolve to the class node
    assert param_types["point"].resolved_target is not None

    print(f"\n✅ Type resolution test passed!")
    print(f"   - BUILTIN types: int, str, list")
    print(f"   - LOCAL type: DataPoint (resolved to class)")
    print(f"   - Signature: {signature.raw}")


if __name__ == "__main__":
    # Run tests
    gen = PythonIRGenerator(repo_id="test-repo")

    print("=" * 60)
    print("Test 1: Simple Class Generation")
    print("=" * 60)
    test_simple_class_generation(gen)

    print("\n" + "=" * 60)
    print("Test 2: Control Flow Analysis")
    print("=" * 60)
    test_function_with_control_flow(gen)

    print("\n" + "=" * 60)
    print("Test 3: Import Nodes")
    print("=" * 60)
    test_imports(gen)

    print("\n" + "=" * 60)
    print("Test 4: Function Calls (CALLS edges)")
    print("=" * 60)
    test_function_calls(gen)

    print("\n" + "=" * 60)
    print("Test 5: Type Resolution (BUILTIN/LOCAL)")
    print("=" * 60)
    test_type_resolution(gen)

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
