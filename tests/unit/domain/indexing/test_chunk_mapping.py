"""
Test Chunk ↔ IR/Graph Mapping

Tests chunk mapping to IR nodes and graph nodes.
"""

import pytest
from src.foundation.chunk import (
    ChunkBuilder,
    ChunkIdGenerator,
    ChunkMapper,
    GraphNodeFilter,
)
from src.foundation.generators import PythonIRGenerator
from src.foundation.graph import GraphBuilder
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


@pytest.fixture
def chunk_builder():
    """Create chunk builder"""
    return ChunkBuilder(ChunkIdGenerator())


def test_chunk_ir_mapping_basic(python_generator, semantic_builder, graph_builder, chunk_builder):
    """Test basic chunk → IR node mapping"""

    code = '''
def func1():
    """Function 1"""
    return 1

def func2():
    """Function 2"""
    return 2
'''

    # Generate IR
    source = SourceFile.from_content("test.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")

    print(f"\n📋 IR Document: {len(ir_doc.nodes)} nodes")
    for node in ir_doc.nodes:
        print(f"  {node.kind.value:15s} {node.fqn}")

    # Generate semantic IR
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)

    # Generate graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Generate chunks with mappings
    file_text = code.split("\n")
    repo_config = {"project_name": "default"}
    chunks, chunk_to_ir, chunk_to_graph = chunk_builder.build(
        repo_id="test-repo",
        ir_doc=ir_doc,
        graph_doc=graph_doc,
        file_text=file_text,
        repo_config=repo_config,
    )

    print(f"\n📊 Generated {len(chunks)} chunks:")
    for chunk in chunks:
        print(f"  {chunk.kind:10s} {chunk.fqn}")

    print("\n📊 Chunk → IR Mapping:")
    for chunk in chunks:
        ir_nodes = chunk_to_ir.get(chunk.chunk_id, set())
        if ir_nodes:
            print(f"  {chunk.kind:10s} {chunk.fqn:30s} → {len(ir_nodes)} IR nodes")

    # Verify mappings exist
    assert len(chunk_to_ir) == len(chunks)

    # Find function chunks
    func_chunks = [c for c in chunks if c.kind == "function"]
    print(f"\n📊 Found {len(func_chunks)} function chunks (expected 2)")
    assert len(func_chunks) == 2

    # Each function chunk should map to IR nodes
    for func_chunk in func_chunks:
        ir_nodes = chunk_to_ir[func_chunk.chunk_id]
        assert len(ir_nodes) > 0, f"Function chunk {func_chunk.fqn} has no IR nodes"

    print("✅ Chunk → IR mapping works")


def test_chunk_graph_mapping_basic(python_generator, semantic_builder, graph_builder, chunk_builder):
    """Test basic chunk → graph node mapping"""

    code = '''
class Calculator:
    """Calculator class"""

    def add(self, a: int, b: int) -> int:
        """Add two numbers"""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        """Subtract two numbers"""
        return a - b
'''

    # Generate full pipeline
    source = SourceFile.from_content("calc.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Generate chunks with mappings
    file_text = code.split("\n")
    repo_config = {"project_name": "default"}
    chunks, chunk_to_ir, chunk_to_graph = chunk_builder.build(
        repo_id="test-repo",
        ir_doc=ir_doc,
        graph_doc=graph_doc,
        file_text=file_text,
        repo_config=repo_config,
    )

    print("\n📊 Chunk → Graph Mapping:")
    for chunk in chunks:
        graph_nodes = chunk_to_graph.get(chunk.chunk_id, set())
        if graph_nodes:
            print(f"  {chunk.kind:10s} {chunk.fqn:30s} → {len(graph_nodes)} graph nodes")

    # Verify mappings exist
    assert len(chunk_to_graph) == len(chunks)

    # Find class chunk
    class_chunks = [c for c in chunks if c.kind == "class"]
    assert len(class_chunks) == 1

    class_chunk = class_chunks[0]
    graph_nodes = chunk_to_graph[class_chunk.chunk_id]

    # Class chunk should map to class symbol + method symbols
    assert len(graph_nodes) > 0, "Class chunk has no graph nodes"

    print(f"  Class chunk '{class_chunk.fqn}' maps to {len(graph_nodes)} graph nodes")
    print("✅ Chunk → Graph mapping works")


def test_graph_node_filter():
    """Test graph node filter"""
    from src.foundation.graph.models import GraphNode, GraphNodeKind

    filter = GraphNodeFilter()

    # Test cases
    test_nodes = [
        (GraphNodeKind.FUNCTION, True, "Function should be included"),
        (GraphNodeKind.CLASS, True, "Class should be included"),
        (GraphNodeKind.METHOD, True, "Method should be included"),
        (GraphNodeKind.TYPE, True, "Type should be included"),
        (GraphNodeKind.VARIABLE, False, "Variable should be excluded"),
        (GraphNodeKind.FIELD, False, "Field should be excluded"),
        (GraphNodeKind.CFG_BLOCK, False, "CfgBlock should be excluded"),
    ]

    print("\n🔍 Graph Node Filter:")
    for kind, should_include, description in test_nodes:
        node = GraphNode(
            id=f"test:{kind.value}",
            kind=kind,
            repo_id="test",
            snapshot_id="snap:001",
            fqn=f"test.{kind.value}",
            name=kind.value,
        )

        result = filter.include(node)
        print(f"  {kind.value:20s} → {'INCLUDE' if result else 'EXCLUDE'}")

        assert result == should_include, f"{description}: expected {should_include}, got {result}"

    print("✅ Graph node filter works correctly")


def test_chunk_mapper_line_containment():
    """Test chunk mapper line containment logic"""
    from src.foundation.chunk.models import Chunk
    from src.foundation.ir.models import IRDocument, Node, NodeKind, Span

    # Create test chunks
    chunks = [
        Chunk(
            chunk_id="chunk:file",
            repo_id="test",
            snapshot_id="snap:001",
            project_id=None,
            module_path=None,
            file_path="test.py",
            kind="file",
            fqn="test",
            start_line=1,
            end_line=20,
            original_start_line=1,
            original_end_line=20,
            content_hash="abc",
            parent_id=None,
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
        Chunk(
            chunk_id="chunk:func1",
            repo_id="test",
            snapshot_id="snap:001",
            project_id=None,
            module_path=None,
            file_path="test.py",
            kind="function",
            fqn="test.func1",
            start_line=1,
            end_line=10,
            original_start_line=1,
            original_end_line=10,
            content_hash="def1",
            parent_id="chunk:file",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id="func:test:test.py:func1",
            symbol_owner_id="func:test:test.py:func1",
            summary=None,
            importance=None,
            attrs={},
        ),
        Chunk(
            chunk_id="chunk:func2",
            repo_id="test",
            snapshot_id="snap:001",
            project_id=None,
            module_path=None,
            file_path="test.py",
            kind="function",
            fqn="test.func2",
            start_line=11,
            end_line=20,
            original_start_line=11,
            original_end_line=20,
            content_hash="def2",
            parent_id="chunk:file",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id="func:test:test.py:func2",
            symbol_owner_id="func:test:test.py:func2",
            summary=None,
            importance=None,
            attrs={},
        ),
    ]

    # Create test IR nodes
    ir_nodes = [
        Node(
            id="node:1",
            kind=NodeKind.FUNCTION,
            fqn="test.func1",
            file_path="test.py",
            span=Span(start_line=1, end_line=10, start_col=0, end_col=0),
            language="python",
            name="func1",
        ),
        Node(
            id="node:2",
            kind=NodeKind.FUNCTION,
            fqn="test.func2",
            file_path="test.py",
            span=Span(start_line=11, end_line=20, start_col=0, end_col=0),
            language="python",
            name="func2",
        ),
    ]

    ir_doc = IRDocument(
        repo_id="test",
        snapshot_id="snap:001",
        schema_version="4.1.0",
        nodes=ir_nodes,
        edges=[],
    )

    # Test mapping
    mapper = ChunkMapper()
    chunk_to_ir = mapper.map_ir(chunks, ir_doc)

    print("\n📋 Chunk → IR Line Containment:")
    for chunk in chunks:
        ir_node_ids = chunk_to_ir[chunk.chunk_id]
        print(f"  {chunk.kind:10s} (lines {chunk.start_line}-{chunk.end_line}) → {len(ir_node_ids)} IR nodes")

    # Verify func1 chunk contains node:1
    func1_ir = chunk_to_ir["chunk:func1"]
    assert "node:1" in func1_ir, "func1 chunk should contain node:1"
    assert "node:2" not in func1_ir, "func1 chunk should not contain node:2"

    # Verify func2 chunk contains node:2
    func2_ir = chunk_to_ir["chunk:func2"]
    assert "node:2" in func2_ir, "func2 chunk should contain node:2"
    assert "node:1" not in func2_ir, "func2 chunk should not contain node:1"

    # Verify file chunk contains both nodes
    file_ir = chunk_to_ir["chunk:file"]
    assert "node:1" in file_ir, "file chunk should contain node:1"
    assert "node:2" in file_ir, "file chunk should contain node:2"

    print("✅ Line containment logic works correctly")


if __name__ == "__main__":
    from src.foundation.generators import PythonIRGenerator
    from src.foundation.graph import GraphBuilder
    from src.foundation.semantic_ir import DefaultSemanticIrBuilder

    gen = PythonIRGenerator(repo_id="test-repo")
    sem_builder = DefaultSemanticIrBuilder()
    g_builder = GraphBuilder()
    c_builder = ChunkBuilder(ChunkIdGenerator())

    print("=" * 60)
    print("Test 1: Chunk → IR Mapping")
    print("=" * 60)
    test_chunk_ir_mapping_basic(gen, sem_builder, g_builder, c_builder)

    print("\n" + "=" * 60)
    print("Test 2: Chunk → Graph Mapping")
    print("=" * 60)
    test_chunk_graph_mapping_basic(gen, sem_builder, g_builder, c_builder)

    print("\n" + "=" * 60)
    print("Test 3: Graph Node Filter")
    print("=" * 60)
    test_graph_node_filter()

    print("\n" + "=" * 60)
    print("Test 4: Line Containment Logic")
    print("=" * 60)
    test_chunk_mapper_line_containment()

    print("\n" + "=" * 60)
    print("✅ All Chunk Mapping Tests Passed!")
    print("=" * 60)
