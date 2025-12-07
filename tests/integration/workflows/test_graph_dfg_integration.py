"""
Test Graph Layer DFG Integration

Verifies that DFG data flows correctly to GraphDocument:
- CFG blocks populated with defined_variable_ids and used_variable_ids
- GraphBuilder generates READS/WRITES edges
- Graph indexes track variable access patterns
"""

import pytest

from src.foundation.generators import PythonIRGenerator
from src.foundation.graph import GraphBuilder
from src.foundation.graph.models import GraphEdgeKind
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


def test_graph_dfg_reads_writes_edges(python_generator, semantic_builder, graph_builder):
    """Test that READS/WRITES edges are generated in graph layer"""

    code = '''
def calculate(x: int, y: int) -> int:
    """Calculate result"""
    result = x + y
    return result
'''

    # Generate IR
    source = SourceFile.from_content("src/calc.py", code, "python")
    ir_doc = python_generator.generate(source, "test:001")

    # Build Semantic IR (includes DFG)
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)

    # Build Graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Verify graph has edges
    assert len(graph_doc.graph_edges) > 0

    # Find READS and WRITES edges
    reads_edges = [e for e in graph_doc.graph_edges if e.kind == GraphEdgeKind.READS]
    writes_edges = [e for e in graph_doc.graph_edges if e.kind == GraphEdgeKind.WRITES]

    print("\n📊 Graph Statistics:")
    print(f"  Total edges: {len(graph_doc.graph_edges)}")
    print(f"  READS edges: {len(reads_edges)}")
    print(f"  WRITES edges: {len(writes_edges)}")

    # Should have at least some READS and WRITES edges
    assert len(reads_edges) > 0, "Should have READS edges"
    assert len(writes_edges) > 0, "Should have WRITES edges"

    # Verify edge structure
    for edge in reads_edges[:3]:  # Check first 3
        print(f"\n  READS: {edge.source_id} → {edge.target_id}")
        assert edge.source_id.startswith("cfg:")  # CFG block reads variable
        assert "function_node_id" in edge.attrs

    for edge in writes_edges[:3]:  # Check first 3
        print(f"  WRITES: {edge.source_id} → {edge.target_id}")
        assert edge.source_id.startswith("cfg:")  # CFG block writes variable
        assert "function_node_id" in edge.attrs

    print("\n✅ Graph DFG integration test passed!")


def test_graph_dfg_variable_tracking(python_generator, semantic_builder, graph_builder):
    """Test variable tracking in graph indexes"""

    code = '''
def process(data):
    """Process data"""
    temp = data
    result = temp * 2
    return result
'''

    # Generate IR
    source = SourceFile.from_content("src/process.py", code, "python")
    ir_doc = python_generator.generate(source, "test:002")

    # Build Semantic IR
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)

    # Build Graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Verify indexes were built
    assert graph_doc.indexes is not None
    assert graph_doc.indexes.reads_by is not None
    assert graph_doc.indexes.writes_by is not None

    print("\n📊 Graph Indexes:")
    print(f"  Variables read by blocks: {len(graph_doc.indexes.reads_by)}")
    print(f"  Variables written by blocks: {len(graph_doc.indexes.writes_by)}")

    # Should have some indexed variables
    assert len(graph_doc.indexes.reads_by) > 0, "Should have read variables indexed"
    assert len(graph_doc.indexes.writes_by) > 0, "Should have write variables indexed"

    # Print sample indexes
    for var_id, block_ids in list(graph_doc.indexes.reads_by.items())[:3]:
        print(f"\n  Variable {var_id} read by {len(block_ids)} blocks")

    for var_id, block_ids in list(graph_doc.indexes.writes_by.items())[:3]:
        print(f"  Variable {var_id} written by {len(block_ids)} blocks")

    print("\n✅ Graph variable tracking test passed!")


def test_full_pipeline_ir_to_graph(python_generator, semantic_builder, graph_builder):
    """Test complete pipeline: IR → Semantic IR → Graph"""

    code = '''
def swap(a: int, b: int) -> tuple:
    """Swap two values"""
    x, y = b, a
    return x, y
'''

    # Step 1: Generate IR
    source = SourceFile.from_content("src/swap.py", code, "python")
    ir_doc = python_generator.generate(source, "test:003")

    print("\n📋 Step 1: IR Generated")
    print(f"  Nodes: {len(ir_doc.nodes)}")
    print(f"  Edges: {len(ir_doc.edges)}")

    # Step 2: Build Semantic IR (includes CFG + DFG)
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)

    print("\n📋 Step 2: Semantic IR Built")
    print(f"  Types: {len(semantic_snapshot.types)}")
    print(f"  Signatures: {len(semantic_snapshot.signatures)}")
    print(f"  CFG Blocks: {len(semantic_snapshot.cfg_blocks)}")
    print(f"  CFG Edges: {len(semantic_snapshot.cfg_edges)}")

    # Verify DFG was built
    dfg = semantic_snapshot.dfg_snapshot
    assert dfg is not None, "DFG should be built"
    print(f"  DFG Variables: {len(dfg.variables)}")
    print(f"  DFG Events: {len(dfg.events)}")
    print(f"  DFG Edges: {len(dfg.edges)}")

    # Step 3: Build Graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    print("\n📋 Step 3: Graph Built")
    print(f"  Graph Nodes: {len(graph_doc.graph_nodes)}")
    print(f"  Graph Edges: {len(graph_doc.graph_edges)}")

    # Count edge types
    edge_counts = {}
    for edge in graph_doc.graph_edges:
        kind = edge.kind.value
        edge_counts[kind] = edge_counts.get(kind, 0) + 1

    print("\n📊 Edge Type Distribution:")
    for kind, count in sorted(edge_counts.items()):
        print(f"  {kind}: {count}")

    # Verify critical edge types exist
    assert GraphEdgeKind.CONTAINS.value in edge_counts, "Should have CONTAINS edges"
    assert GraphEdgeKind.READS.value in edge_counts, "Should have READS edges"
    assert GraphEdgeKind.WRITES.value in edge_counts, "Should have WRITES edges"

    # Verify indexes
    assert len(graph_doc.indexes.outgoing) > 0, "Should have outgoing index"
    assert len(graph_doc.indexes.incoming) > 0, "Should have incoming index"

    print("\n✅ Full pipeline test passed!")


def test_graph_dfg_complex_flow(python_generator, semantic_builder, graph_builder):
    """Test complex data flow patterns in graph"""

    code = '''
def analyze(data, threshold: int):
    """Complex analysis"""
    # Multiple reads and writes
    filtered = [x for x in data if x > threshold]
    count = len(filtered)

    # Attribute access
    result = count * threshold

    return result, count
'''

    # Generate full pipeline
    source = SourceFile.from_content("src/analyze.py", code, "python")
    ir_doc = python_generator.generate(source, "test:004")

    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Verify DFG data
    dfg = semantic_snapshot.dfg_snapshot
    vars_by_name = {v.name: v for v in dfg.variables}

    print("\n📊 Variables in DFG:")
    for name in sorted(vars_by_name.keys()):
        print(f"  - {name}")

    # Should detect key variables
    assert "data" in vars_by_name, "Should have data parameter"
    assert "threshold" in vars_by_name, "Should have threshold parameter"
    assert "filtered" in vars_by_name, "Should have filtered variable"
    assert "count" in vars_by_name, "Should have count variable"
    assert "result" in vars_by_name, "Should have result variable"

    # Verify graph has corresponding edges
    reads_edges = [e for e in graph_doc.graph_edges if e.kind == GraphEdgeKind.READS]
    writes_edges = [e for e in graph_doc.graph_edges if e.kind == GraphEdgeKind.WRITES]

    print("\n📊 Graph Data Flow:")
    print(f"  READS edges: {len(reads_edges)}")
    print(f"  WRITES edges: {len(writes_edges)}")

    # Should have substantial data flow
    assert len(reads_edges) >= 3, "Should have multiple reads"
    assert len(writes_edges) >= 3, "Should have multiple writes"

    print("\n✅ Complex flow test passed!")


if __name__ == "__main__":
    gen = PythonIRGenerator(repo_id="test-repo")
    sem_builder = DefaultSemanticIrBuilder()
    graph_builder = GraphBuilder()

    print("=" * 60)
    print("Test 1: Graph DFG READS/WRITES Edges")
    print("=" * 60)
    test_graph_dfg_reads_writes_edges(gen, sem_builder, graph_builder)

    print("\n" + "=" * 60)
    print("Test 2: Graph Variable Tracking")
    print("=" * 60)
    test_graph_dfg_variable_tracking(gen, sem_builder, graph_builder)

    print("\n" + "=" * 60)
    print("Test 3: Full Pipeline (IR → Semantic IR → Graph)")
    print("=" * 60)
    test_full_pipeline_ir_to_graph(gen, sem_builder, graph_builder)

    print("\n" + "=" * 60)
    print("Test 4: Complex Data Flow")
    print("=" * 60)
    test_graph_dfg_complex_flow(gen, sem_builder, graph_builder)

    print("\n" + "=" * 60)
    print("✅ All graph DFG integration tests passed!")
    print("=" * 60)
