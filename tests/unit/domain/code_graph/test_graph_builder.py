"""
Test Graph Builder

Tests the graph construction layer that converts IR + Semantic IR → GraphDocument.
"""

import pytest

from src.foundation.generators import PythonIRGenerator
from src.foundation.graph import GraphBuilder, GraphEdgeKind, GraphNodeKind
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


@pytest.fixture
def graph_builder():
    """Create graph builder"""
    return GraphBuilder()


def test_graph_builder_basic(python_generator, semantic_builder, graph_builder):
    """Test basic graph construction from IR + Semantic IR"""

    code = """
class DataPoint:
    \"\"\"A data point\"\"\"
    value: int

def process(count: int, point: DataPoint) -> DataPoint:
    \"\"\"Process data\"\"\"
    result = point
    return result
"""

    # Generate IR
    source = SourceFile.from_content("src/data.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")

    # Generate Semantic IR
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc)

    # Build Graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    print("\n  Graph Stats:")
    stats = graph_doc.stats()
    print(f"    - Total nodes: {stats['total_nodes']}")
    print(f"    - Total edges: {stats['total_edges']}")

    # Verify nodes
    assert stats["total_nodes"] > 0
    assert stats["total_edges"] > 0

    # Check node kinds
    assert "File" in stats["nodes_by_kind"]
    assert "Module" in stats["nodes_by_kind"]
    assert "Class" in stats["nodes_by_kind"]
    assert "Function" in stats["nodes_by_kind"]
    assert "Type" in stats["nodes_by_kind"]
    assert "Signature" in stats["nodes_by_kind"]
    assert "CfgBlock" in stats["nodes_by_kind"]

    # Check edge kinds
    assert "CONTAINS" in stats["edges_by_kind"]
    assert "REFERENCES_TYPE" in stats["edges_by_kind"]
    assert "CFG_NEXT" in stats["edges_by_kind"]

    print("\n✅ Basic graph construction test passed!")


def test_graph_indexes(python_generator, semantic_builder, graph_builder):
    """Test graph indexes for efficient queries"""

    code = """
class DataPoint:
    value: int

def process(point: DataPoint) -> int:
    return point.value
"""

    # Generate all layers
    source = SourceFile.from_content("src/data.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    print("\n  Index Stats:")
    print(f"    - contains_children: {len(graph_doc.indexes.contains_children)}")
    print(f"    - type_users: {len(graph_doc.indexes.type_users)}")
    print(f"    - outgoing: {len(graph_doc.indexes.outgoing)}")
    print(f"    - incoming: {len(graph_doc.indexes.incoming)}")

    # Test contains_children index
    file_nodes = graph_doc.get_nodes_by_kind(GraphNodeKind.FILE)
    assert len(file_nodes) == 1
    file_node = file_nodes[0]

    children = graph_doc.indexes.get_children(file_node.id)
    assert len(children) > 0
    print(f"    - File has {len(children)} children")

    # Test type_users index
    type_nodes = graph_doc.get_nodes_by_kind(GraphNodeKind.TYPE)
    if len(type_nodes) > 0:
        type_node = type_nodes[0]
        users = graph_doc.indexes.get_type_users(type_node.id)
        print(f"    - Type '{type_node.name}' has {len(users)} users")

    # Test adjacency indexes
    assert len(graph_doc.indexes.outgoing) > 0
    assert len(graph_doc.indexes.incoming) > 0

    print("\n✅ Graph indexes test passed!")


def test_graph_with_enhanced_cfg(python_generator, semantic_builder, graph_builder):
    """Test graph construction with enhanced CFG (branches and loops)"""

    code = """
def calculate(n: int) -> int:
    \"\"\"Calculate with branches and loops\"\"\"
    result = 0

    if n > 0:
        result = n
    else:
        result = -n

    for i in range(n):
        result += i

    return result
"""

    # Generate IR
    source = SourceFile.from_content("src/calc.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:002")

    # Generate Semantic IR WITH source map (enhanced CFG)
    source_map = {source.file_path: source}
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc, source_map)

    # Build Graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    stats = graph_doc.stats()
    print("\n  Enhanced CFG Graph:")
    print(f"    - Total nodes: {stats['total_nodes']}")
    print(f"    - Total edges: {stats['total_edges']}")
    print(f"    - CFG blocks: {stats['nodes_by_kind'].get('CfgBlock', 0)}")

    # Verify enhanced CFG edges
    edge_kinds = stats["edges_by_kind"]
    print("\n  Edge kinds:")
    for kind, count in sorted(edge_kinds.items()):
        print(f"    - {kind}: {count}")

    # Should have branch edges (from if/else)
    assert "CFG_BRANCH" in edge_kinds
    assert edge_kinds["CFG_BRANCH"] > 0

    # Should have loop edges (from for loop)
    assert "CFG_LOOP" in edge_kinds
    assert edge_kinds["CFG_LOOP"] > 0

    # Should have normal flow edges
    assert "CFG_NEXT" in edge_kinds

    print("\n✅ Enhanced CFG graph test passed!")


def test_graph_query_methods(python_generator, semantic_builder, graph_builder):
    """Test graph query methods"""

    code = """
class Point:
    x: int
    y: int

def distance(p: Point) -> float:
    return (p.x ** 2 + p.y ** 2) ** 0.5
"""

    # Build graph
    source = SourceFile.from_content("src/geometry.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    print("\n  Query Tests:")

    # Test get_node
    file_nodes = graph_doc.get_nodes_by_kind(GraphNodeKind.FILE)
    assert len(file_nodes) > 0
    file_node = file_nodes[0]

    retrieved = graph_doc.get_node(file_node.id)
    assert retrieved is not None
    assert retrieved.id == file_node.id
    print("    ✓ get_node() works")

    # Test get_nodes_by_kind
    class_nodes = graph_doc.get_nodes_by_kind(GraphNodeKind.CLASS)
    assert len(class_nodes) > 0
    print(f"    ✓ get_nodes_by_kind() found {len(class_nodes)} classes")

    # Test get_edges_by_kind
    contains_edges = graph_doc.get_edges_by_kind(GraphEdgeKind.CONTAINS)
    assert len(contains_edges) > 0
    print(f"    ✓ get_edges_by_kind() found {len(contains_edges)} CONTAINS edges")

    # Test get_edges_from / get_edges_to
    if len(contains_edges) > 0:
        edge = contains_edges[0]
        outgoing = graph_doc.get_edges_from(edge.source_id)
        incoming = graph_doc.get_edges_to(edge.target_id)
        print(f"    ✓ get_edges_from() found {len(outgoing)} outgoing edges")
        print(f"    ✓ get_edges_to() found {len(incoming)} incoming edges")

    print("\n✅ Graph query methods test passed!")


def test_module_node_generation(python_generator, semantic_builder, graph_builder):
    """Test auto-generation of MODULE nodes from file paths"""

    code = """
def hello():
    return "Hello"
"""

    # Use a deep path to generate multiple module nodes
    source = SourceFile.from_content("src/utils/helpers/text.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Check for module nodes
    module_nodes = graph_doc.get_nodes_by_kind(GraphNodeKind.MODULE)
    print(f"\n  Module Nodes: {len(module_nodes)}")
    for node in module_nodes:
        print(f"    - {node.fqn} (path: {node.path})")

    # Should have generated: src, src.utils, src.utils.helpers
    assert len(module_nodes) >= 1
    assert any(node.fqn == "src" for node in module_nodes)

    print("\n✅ Module node generation test passed!")


if __name__ == "__main__":
    gen = PythonIRGenerator(repo_id="test-repo")
    sem_builder = DefaultSemanticIrBuilder()
    g_builder = GraphBuilder()

    print("=" * 60)
    print("Test 1: Basic Graph Construction")
    print("=" * 60)
    test_graph_builder_basic(gen, sem_builder, g_builder)

    print("\n" + "=" * 60)
    print("Test 2: Graph Indexes")
    print("=" * 60)
    test_graph_indexes(gen, sem_builder, g_builder)

    print("\n" + "=" * 60)
    print("Test 3: Enhanced CFG")
    print("=" * 60)
    test_graph_with_enhanced_cfg(gen, sem_builder, g_builder)

    print("\n" + "=" * 60)
    print("Test 4: Graph Query Methods")
    print("=" * 60)
    test_graph_query_methods(gen, sem_builder, g_builder)

    print("\n" + "=" * 60)
    print("Test 5: Module Node Generation")
    print("=" * 60)
    test_module_node_generation(gen, sem_builder, g_builder)

    print("\n" + "=" * 60)
    print("✅ All graph builder tests passed!")
    print("=" * 60)
