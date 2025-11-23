"""
Test Semantic IR Builder

Tests the semantic IR builder that converts Structural IR → Semantic IR.
"""

import pytest

from src.foundation.generators import PythonIRGenerator
from src.foundation.ir.models import NodeKind
from src.foundation.parsing import SourceFile
from src.foundation.semantic_ir import DefaultSemanticIrBuilder


@pytest.fixture
def python_generator():
    """Create Python IR generator"""
    return PythonIRGenerator(repo_id="test-repo")


@pytest.fixture
def semantic_builder():
    """Create semantic IR builder"""
    return DefaultSemanticIrBuilder()


def test_semantic_ir_builder_basic(python_generator, semantic_builder):
    """Test basic semantic IR building from structural IR"""

    code = '''
class DataPoint:
    """A data point"""
    pass

def process(count: int, point: DataPoint) -> DataPoint:
    """Process data"""
    result = point
    return result
'''

    # Generate structural IR
    source = SourceFile.from_content(
        file_path="src/data.py",
        content=code,
        language="python",
    )
    ir_doc = python_generator.generate(source, snapshot_id="test:001")

    print(f"\n  Structural IR:")
    print(f"    - Nodes: {len(ir_doc.nodes)}")
    print(f"    - Types: {len(ir_doc.types)}")
    print(f"    - Signatures: {len(ir_doc.signatures)}")

    # Build semantic IR without source_map (simplified CFG)
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc)

    print(f"\n  Semantic IR (without source_map):")
    print(f"    - Types: {len(semantic_snapshot.types)}")
    print(f"    - Signatures: {len(semantic_snapshot.signatures)}")
    print(f"    - CFG Graphs: {len(semantic_snapshot.cfg_graphs)}")
    print(f"    - CFG Blocks: {len(semantic_snapshot.cfg_blocks)}")
    print(f"    - CFG Edges: {len(semantic_snapshot.cfg_edges)}")

    # Verify types (types are deduplicated by ID)
    assert len(semantic_snapshot.types) == 2  # int, DataPoint (reused)

    # Verify signatures
    assert len(semantic_snapshot.signatures) == 1  # process function

    # Verify CFG (simplified - no source_map)
    assert len(semantic_snapshot.cfg_graphs) == 1  # 1 function
    assert len(semantic_snapshot.cfg_blocks) == 3  # Entry, Body, Exit
    assert len(semantic_snapshot.cfg_edges) == 2  # Entry->Body, Body->Exit

    cfg_graph = semantic_snapshot.cfg_graphs[0]
    print(f"\n  CFG Graph:")
    print(f"    - ID: {cfg_graph.id}")
    print(f"    - Entry: {cfg_graph.entry_block_id}")
    print(f"    - Exit: {cfg_graph.exit_block_id}")
    print(f"    - Blocks: {len(cfg_graph.blocks)}")
    print(f"    - Edges: {len(cfg_graph.edges)}")

    # Find process function
    func_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FUNCTION and n.name == "process"]
    assert len(func_nodes) == 1
    func_node = func_nodes[0]

    # Verify type index
    print(f"\n  Type Index:")
    print(f"    - function_to_param_type_ids: {len(semantic_index.type_index.function_to_param_type_ids)}")
    print(f"    - function_to_return_type_id: {len(semantic_index.type_index.function_to_return_type_id)}")
    print(f"    - variable_to_type_id: {len(semantic_index.type_index.variable_to_type_id)}")

    assert func_node.id in semantic_index.type_index.function_to_param_type_ids
    assert len(semantic_index.type_index.function_to_param_type_ids[func_node.id]) == 2  # count, point

    assert func_node.id in semantic_index.type_index.function_to_return_type_id
    assert semantic_index.type_index.function_to_return_type_id[func_node.id] is not None

    # Verify signature index
    print(f"\n  Signature Index:")
    print(f"    - function_to_signature: {len(semantic_index.signature_index.function_to_signature)}")

    assert func_node.id in semantic_index.signature_index.function_to_signature
    signature_id = semantic_index.signature_index.function_to_signature[func_node.id]

    # Find signature
    signature = next((s for s in semantic_snapshot.signatures if s.id == signature_id), None)
    assert signature is not None
    print(f"    - Signature: {signature.raw}")

    # Verify signature details
    assert signature.name == "process"
    assert len(signature.parameter_type_ids) == 2
    assert signature.return_type_id is not None

    print(f"\n✅ Semantic IR builder test passed!")


def test_semantic_index_merge(semantic_builder):
    """Test semantic index merge functionality"""

    code1 = '''
def func1(x: int) -> int:
    return x + 1
'''

    code2 = '''
def func2(y: str) -> str:
    return y.upper()
'''

    # Generate two IR documents
    gen = PythonIRGenerator(repo_id="test-repo")

    source1 = SourceFile.from_content("src/a.py", code1, "python")
    ir_doc1 = gen.generate(source1, "snap:1")

    source2 = SourceFile.from_content("src/b.py", code2, "python")
    ir_doc2 = gen.generate(source2, "snap:2")

    # Build semantic IR for each
    _, index1 = semantic_builder.build_full(ir_doc1)
    _, index2 = semantic_builder.build_full(ir_doc2)

    # Merge indexes
    merged = index1.merge(index2)

    print(f"\n  Index Merge:")
    print(f"    - Index1 functions: {len(index1.signature_index.function_to_signature)}")
    print(f"    - Index2 functions: {len(index2.signature_index.function_to_signature)}")
    print(f"    - Merged functions: {len(merged.signature_index.function_to_signature)}")

    # Verify merge
    assert len(merged.signature_index.function_to_signature) == 2
    assert len(merged.type_index.function_to_param_type_ids) == 2

    print(f"\n✅ Semantic index merge test passed!")


def test_enhanced_cfg_with_branches_and_loops(python_generator, semantic_builder):
    """Test enhanced CFG with branch and loop analysis"""

    code = '''
def calculate(n: int) -> int:
    """Calculate with branches and loops"""
    result = 0

    # Branch
    if n > 0:
        result = n
    else:
        result = -n

    # Loop
    for i in range(n):
        result += i

    return result
'''

    # Generate structural IR
    source = SourceFile.from_content(
        file_path="src/calc.py",
        content=code,
        language="python",
    )
    ir_doc = python_generator.generate(source, snapshot_id="test:002")

    # Build semantic IR WITH source_map (enhanced CFG)
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)

    print(f"\n  Enhanced CFG Analysis:")
    print(f"    - CFG Graphs: {len(semantic_snapshot.cfg_graphs)}")
    print(f"    - CFG Blocks: {len(semantic_snapshot.cfg_blocks)}")
    print(f"    - CFG Edges: {len(semantic_snapshot.cfg_edges)}")

    # Find the calculate function's CFG (filter out external functions)
    calculate_cfg = None
    for cfg in semantic_snapshot.cfg_graphs:
        if "calculate" in cfg.function_node_id and "<external>" not in cfg.function_node_id:
            calculate_cfg = cfg
            break

    assert calculate_cfg is not None, "Could not find calculate function CFG"

    # Verify CFG has more blocks than simplified version
    assert len(calculate_cfg.blocks) > 3  # More than Entry, Body, Exit

    cfg_graph = calculate_cfg
    print(f"\n  CFG Details:")
    print(f"    - Entry: {cfg_graph.entry_block_id}")
    print(f"    - Exit: {cfg_graph.exit_block_id}")

    # Print block kinds
    from src.foundation.semantic_ir.cfg.models import CFGBlockKind
    block_kinds = {}
    for block in cfg_graph.blocks:
        kind = block.kind.value
        block_kinds[kind] = block_kinds.get(kind, 0) + 1

    print(f"    - Block kinds:")
    for kind, count in block_kinds.items():
        print(f"      - {kind}: {count}")

    # Print edge kinds
    from src.foundation.semantic_ir.cfg.models import CFGEdgeKind
    edge_kinds = {}
    for edge in cfg_graph.edges:
        kind = edge.kind.value
        edge_kinds[kind] = edge_kinds.get(kind, 0) + 1

    print(f"    - Edge kinds:")
    for kind, count in edge_kinds.items():
        print(f"      - {kind}: {count}")

    # Verify we have CONDITION blocks (from if statement)
    assert CFGBlockKind.CONDITION.value in block_kinds
    assert block_kinds[CFGBlockKind.CONDITION.value] >= 1

    # Verify we have LOOP_HEADER blocks (from for loop)
    assert CFGBlockKind.LOOP_HEADER.value in block_kinds
    assert block_kinds[CFGBlockKind.LOOP_HEADER.value] >= 1

    # Verify we have TRUE_BRANCH and FALSE_BRANCH edges
    assert CFGEdgeKind.TRUE_BRANCH.value in edge_kinds
    assert CFGEdgeKind.FALSE_BRANCH.value in edge_kinds

    # Verify we have LOOP_BACK edges
    assert CFGEdgeKind.LOOP_BACK.value in edge_kinds

    print(f"\n✅ Enhanced CFG test passed!")


if __name__ == "__main__":
    gen = PythonIRGenerator(repo_id="test-repo")
    builder = DefaultSemanticIrBuilder()

    print("=" * 60)
    print("Test 1: Basic Semantic IR Builder")
    print("=" * 60)
    test_semantic_ir_builder_basic(gen, builder)

    print("\n" + "=" * 60)
    print("Test 2: Semantic Index Merge")
    print("=" * 60)
    test_semantic_index_merge(builder)

    print("\n" + "=" * 60)
    print("Test 3: Enhanced CFG with Branches and Loops")
    print("=" * 60)
    test_enhanced_cfg_with_branches_and_loops(gen, builder)

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
