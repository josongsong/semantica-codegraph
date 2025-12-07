"""
Test Kuzu Graph Store

Tests GraphDocument → Kuzu persistence and querying.
"""

import tempfile
from pathlib import Path

import pytest
from src.foundation.generators import PythonIRGenerator
from src.foundation.graph import GraphBuilder
from src.foundation.graph.models import GraphEdgeKind
from src.foundation.parsing import SourceFile
from src.foundation.semantic_ir import DefaultSemanticIrBuilder

# Try to import kuzu
try:
    import kuzu
    from src.foundation.storage.kuzu import KuzuGraphStore, KuzuSchema

    KUZU_AVAILABLE = True
except ImportError:
    KUZU_AVAILABLE = False


pytestmark = pytest.mark.skipif(not KUZU_AVAILABLE, reason="kuzu not installed (pip install kuzu)")


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


@pytest.fixture
def temp_db():
    """Create temporary Kuzu database"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_kuzu.db"


def test_kuzu_schema_initialization(temp_db):
    """Test Kuzu schema creation"""
    import kuzu

    db = kuzu.Database(str(temp_db))

    # Initialize schema
    KuzuSchema.initialize(db, include_framework_rels=False)

    # Verify node table exists
    conn = kuzu.Connection(db)
    # Kuzu doesn't have a direct way to check table existence,
    # so we'll try to query it
    result = conn.execute("MATCH (n:graph_node) RETURN count(*)")
    count = result.get_all()[0][0]
    assert count == 0  # No nodes yet

    print("\n✅ Kuzu schema initialization test passed!")


def test_kuzu_store_save_and_query(temp_db, python_generator, semantic_builder, graph_builder):
    """Test saving GraphDocument to Kuzu and querying"""

    code = '''
def caller():
    """Caller function"""
    result = callee()
    return result

def callee():
    """Callee function"""
    return 42
'''

    # Generate full pipeline
    source = SourceFile.from_content("src/example.py", code, "python")
    ir_doc = python_generator.generate(source, "test:001")

    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    print("\n📊 Graph Statistics:")
    print(f"  Nodes: {len(graph_doc.graph_nodes)}")
    print(f"  Edges: {len(graph_doc.graph_edges)}")

    # Create Kuzu store and save
    store = KuzuGraphStore(temp_db)
    store.save_graph(graph_doc)

    print(f"\n✅ Saved {len(graph_doc.graph_nodes)} nodes to Kuzu")
    print(f"✅ Saved {len(graph_doc.graph_edges)} edges to Kuzu")

    # Test querying
    # Find CONTAINS relationships
    file_nodes = [n for n in graph_doc.graph_nodes.values() if n.kind.value == "FILE"]
    if file_nodes:
        file_node = file_nodes[0]
        children = store.query_contains_children(file_node.id)
        print(f"\n📋 File {file_node.name} contains {len(children)} children")
        assert len(children) > 0  # Should have function children

    print("\n✅ Kuzu store save and query test passed!")


def test_kuzu_dfg_reads_writes(temp_db, python_generator, semantic_builder, graph_builder):
    """Test DFG READS/WRITES edges in Kuzu"""

    code = '''
def process(data):
    """Process data"""
    result = data * 2
    return result
'''

    # Generate full pipeline
    source = SourceFile.from_content("src/process.py", code, "python")
    ir_doc = python_generator.generate(source, "test:002")

    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Save to Kuzu
    store = KuzuGraphStore(temp_db)
    store.save_graph(graph_doc)

    # Find READS and WRITES edges
    reads_edges = [e for e in graph_doc.graph_edges if e.kind == GraphEdgeKind.READS]
    writes_edges = [e for e in graph_doc.graph_edges if e.kind == GraphEdgeKind.WRITES]

    print("\n📊 DFG Edges in Graph:")
    print(f"  READS: {len(reads_edges)}")
    print(f"  WRITES: {len(writes_edges)}")

    # Query READS edges from Kuzu
    if reads_edges:
        # Pick first read variable
        var_id = reads_edges[0].target_id
        blocks = store.query_reads_variable(var_id)
        print(f"\n📋 Variable {var_id} is read by {len(blocks)} blocks")
        assert len(blocks) > 0

    # Query WRITES edges from Kuzu
    if writes_edges:
        var_id = writes_edges[0].target_id
        blocks = store.query_writes_variable(var_id)
        print(f"📋 Variable {var_id} is written by {len(blocks)} blocks")
        assert len(blocks) > 0

    print("\n✅ Kuzu DFG test passed!")


def test_kuzu_cfg_edges(temp_db, python_generator, semantic_builder, graph_builder):
    """Test CFG edges in Kuzu"""

    code = '''
def check(x: int) -> bool:
    """Check value"""
    if x > 0:
        return True
    else:
        return False
'''

    # Generate full pipeline
    source = SourceFile.from_content("src/check.py", code, "python")
    ir_doc = python_generator.generate(source, "test:003")

    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Save to Kuzu
    store = KuzuGraphStore(temp_db)
    store.save_graph(graph_doc)

    # Count CFG edges
    cfg_edges = [e for e in graph_doc.graph_edges if e.kind.value.startswith("CFG_")]

    print(f"\n📊 CFG Edges: {len(cfg_edges)}")

    # Query CFG successors
    cfg_blocks = [n for n in graph_doc.graph_nodes.values() if n.kind.value == "CFG_BLOCK"]
    if cfg_blocks:
        block = cfg_blocks[0]
        successors = store.query_cfg_successors(block.id)
        print(f"\n📋 Block {block.id} has {len(successors)} successors")

    print("\n✅ Kuzu CFG test passed!")


def test_kuzu_query_node_by_id(temp_db, python_generator, semantic_builder, graph_builder):
    """Test querying node by ID"""

    code = '''
def example():
    """Example function"""
    return 42
'''

    # Generate full pipeline
    source = SourceFile.from_content("src/example.py", code, "python")
    ir_doc = python_generator.generate(source, "test:004")

    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Save to Kuzu
    store = KuzuGraphStore(temp_db)
    store.save_graph(graph_doc)

    # Query a node
    nodes = list(graph_doc.graph_nodes.values())
    if nodes:
        test_node = nodes[0]
        result = store.query_node_by_id(test_node.id)

        assert result is not None
        assert result["node_id"] == test_node.id
        assert result["repo_id"] == test_node.repo_id
        assert result["kind"] == test_node.kind.value
        assert result["fqn"] == test_node.fqn

        print(f"\n📋 Queried node: {result['kind']} - {result['fqn']}")

    print("\n✅ Kuzu query node by ID test passed!")


def test_kuzu_delete_nodes(temp_db, python_generator, semantic_builder, graph_builder):
    """Test deleting nodes by IDs"""

    code = '''
def function_a():
    """Function A"""
    return 1

def function_b():
    """Function B"""
    return 2
'''

    # Generate full pipeline
    source = SourceFile.from_content("src/functions.py", code, "python")
    ir_doc = python_generator.generate(source, "test:005")

    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Save to Kuzu
    store = KuzuGraphStore(temp_db)
    store.save_graph(graph_doc)

    initial_count = len(graph_doc.graph_nodes)
    print(f"\n📊 Initial node count: {initial_count}")

    # Delete first node
    nodes = list(graph_doc.graph_nodes.values())
    if nodes:
        node_to_delete = nodes[0]
        deleted = store.delete_nodes([node_to_delete.id])
        print(f"\n🗑️  Deleted {deleted} node(s)")
        assert deleted == 1

        # Verify deletion
        result = store.query_node_by_id(node_to_delete.id)
        assert result is None
        print(f"✅ Node {node_to_delete.id} successfully deleted")

    print("\n✅ Kuzu delete nodes test passed!")


def test_kuzu_delete_repo(temp_db, python_generator, semantic_builder, graph_builder):
    """Test deleting entire repository"""

    code = '''
def example():
    """Example function"""
    return 42
'''

    # Generate full pipeline
    source = SourceFile.from_content("src/example.py", code, "python")
    ir_doc = python_generator.generate(source, "test:006")

    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Save to Kuzu
    store = KuzuGraphStore(temp_db)
    store.save_graph(graph_doc)

    initial_count = len(graph_doc.graph_nodes)
    print(f"\n📊 Initial node count: {initial_count}")

    # Delete entire repo
    result = store.delete_repo(graph_doc.repo_id)
    print(f"\n🗑️  Deleted repo: {result}")
    assert result["nodes"] == initial_count

    # Verify all nodes are gone
    nodes = list(graph_doc.graph_nodes.values())
    if nodes:
        remaining = store.query_node_by_id(nodes[0].id)
        assert remaining is None
        print(f"✅ All nodes for repo '{graph_doc.repo_id}' successfully deleted")

    print("\n✅ Kuzu delete repo test passed!")


def test_kuzu_delete_snapshot(temp_db, python_generator, semantic_builder, graph_builder):
    """Test deleting specific snapshot"""

    code_1 = '''
def example():
    """Example function"""
    return 42
'''

    code_2 = '''
def different_function():
    """Different function"""
    return 100
'''

    # Generate two snapshots with different code
    source_1 = SourceFile.from_content("src/example1.py", code_1, "python")
    source_2 = SourceFile.from_content("src/example2.py", code_2, "python")

    # Snapshot 1
    ir_doc_1 = python_generator.generate(source_1, "snapshot:001")
    source_map_1 = {source_1.file_path: source_1}
    semantic_snapshot_1, _ = semantic_builder.build_full(ir_doc_1, source_map_1)
    graph_doc_1 = graph_builder.build_full(ir_doc_1, semantic_snapshot_1)

    # Snapshot 2
    ir_doc_2 = python_generator.generate(source_2, "snapshot:002")
    source_map_2 = {source_2.file_path: source_2}
    semantic_snapshot_2, _ = semantic_builder.build_full(ir_doc_2, source_map_2)
    graph_doc_2 = graph_builder.build_full(ir_doc_2, semantic_snapshot_2)

    # Save both snapshots
    store = KuzuGraphStore(temp_db)
    store.save_graph(graph_doc_1)
    store.save_graph(graph_doc_2)

    count_1 = len(graph_doc_1.graph_nodes)
    count_2 = len(graph_doc_2.graph_nodes)
    print(f"\n📊 Snapshot 1 nodes: {count_1}")
    print(f"📊 Snapshot 2 nodes: {count_2}")

    # Delete only snapshot 1
    result = store.delete_snapshot(graph_doc_1.repo_id, "snapshot:001")
    print(f"\n🗑️  Deleted snapshot 001: {result}")
    # Note: Some nodes (e.g., EXTERNAL nodes) may have NULL snapshot_id
    # so the deleted count might be less than total nodes
    assert result["nodes"] > 0
    assert result["nodes"] <= count_1

    # Verify snapshot 1 is gone
    nodes_1 = list(graph_doc_1.graph_nodes.values())
    if nodes_1:
        remaining = store.query_node_by_id(nodes_1[0].id)
        assert remaining is None
        print("✅ Snapshot 001 successfully deleted")

    # Verify snapshot 2 still exists
    nodes_2 = list(graph_doc_2.graph_nodes.values())
    if nodes_2:
        still_exists = store.query_node_by_id(nodes_2[0].id)
        assert still_exists is not None
        print("✅ Snapshot 002 still exists")

    print("\n✅ Kuzu delete snapshot test passed!")


def test_kuzu_delete_by_filter(temp_db, python_generator, semantic_builder, graph_builder):
    """Test deleting nodes by filter"""

    code = '''
class MyClass:
    """Example class"""
    pass

def my_function():
    """Example function"""
    return 42
'''

    # Generate full pipeline
    source = SourceFile.from_content("src/mixed.py", code, "python")
    ir_doc = python_generator.generate(source, "test:007")

    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Save to Kuzu
    store = KuzuGraphStore(temp_db)
    store.save_graph(graph_doc)

    # Count function nodes
    function_nodes = [n for n in graph_doc.graph_nodes.values() if n.kind.value == "Function"]
    print(f"\n📊 Function nodes: {len(function_nodes)}")

    # Delete only function nodes
    deleted = store.delete_nodes_by_filter(
        repo_id=graph_doc.repo_id, snapshot_id=graph_doc.snapshot_id, kind="Function"
    )
    print(f"\n🗑️  Deleted {deleted} function node(s)")
    assert deleted == len(function_nodes)

    # Verify functions are gone
    if function_nodes:
        remaining = store.query_node_by_id(function_nodes[0].id)
        assert remaining is None
        print("✅ Function nodes successfully deleted")

    # Verify other nodes still exist
    class_nodes = [n for n in graph_doc.graph_nodes.values() if n.kind.value == "Class"]
    if class_nodes:
        still_exists = store.query_node_by_id(class_nodes[0].id)
        assert still_exists is not None
        print("✅ Class nodes still exist")

    print("\n✅ Kuzu delete by filter test passed!")


if __name__ == "__main__":
    if not KUZU_AVAILABLE:
        print("⚠️  Kuzu not installed. Install with: pip install kuzu")
        print("Skipping tests...")
    else:
        import tempfile

        gen = PythonIRGenerator(repo_id="test-repo")
        sem_builder = DefaultSemanticIrBuilder()
        graph_builder = GraphBuilder()

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_db = Path(tmpdir) / "test_kuzu.db"

            print("=" * 60)
            print("Test 1: Kuzu Schema Initialization")
            print("=" * 60)
            test_kuzu_schema_initialization(temp_db)

            print("\n" + "=" * 60)
            print("Test 2: Kuzu Store Save and Query")
            print("=" * 60)
            test_kuzu_store_save_and_query(temp_db, gen, sem_builder, graph_builder)

            print("\n" + "=" * 60)
            print("Test 3: Kuzu DFG READS/WRITES")
            print("=" * 60)
            test_kuzu_dfg_reads_writes(temp_db, gen, sem_builder, graph_builder)

            print("\n" + "=" * 60)
            print("Test 4: Kuzu CFG Edges")
            print("=" * 60)
            test_kuzu_cfg_edges(temp_db, gen, sem_builder, graph_builder)

            print("\n" + "=" * 60)
            print("Test 5: Kuzu Query Node by ID")
            print("=" * 60)
            test_kuzu_query_node_by_id(temp_db, gen, sem_builder, graph_builder)

            print("\n" + "=" * 60)
            print("✅ All Kuzu tests passed!")
            print("=" * 60)
