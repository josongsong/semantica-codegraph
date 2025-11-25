"""
Test Chunk Builder End-to-End

Tests complete chunking pipeline: IR → Graph → Chunks
"""

import pytest

from src.foundation.chunk import ChunkBuilder, ChunkIdGenerator
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


def test_chunk_builder_basic(python_generator, semantic_builder, graph_builder, chunk_builder):
    """Test basic chunk hierarchy generation"""

    code = '''
"""Example module"""

def top_level_function():
    """Top-level function"""
    return 42

class Calculator:
    """Calculator class"""

    def add(self, a: int, b: int) -> int:
        """Add two numbers"""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        """Subtract two numbers"""
        return a - b
'''

    # Generate IR
    source = SourceFile.from_content("backend/math/calculator.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")

    # Generate semantic IR
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)

    # Generate graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Generate chunks
    file_text = code.split("\n")
    repo_config = {"project_name": "default", "root": "/test"}
    chunks, chunk_to_ir, chunk_to_graph = chunk_builder.build(
        repo_id="test-repo",
        ir_doc=ir_doc,
        graph_doc=graph_doc,
        file_text=file_text,
        repo_config=repo_config,
    )

    # Verify chunk hierarchy
    print(f"\n📊 Generated {len(chunks)} chunks:")

    # Verify chunk kinds
    chunk_by_kind = {}
    for chunk in chunks:
        chunk_by_kind.setdefault(chunk.kind, []).append(chunk)
        print(f"  - {chunk.kind:10s}: {chunk.fqn}")

    # Expected hierarchy levels
    assert "repo" in chunk_by_kind
    assert "project" in chunk_by_kind
    assert "module" in chunk_by_kind
    assert "file" in chunk_by_kind
    assert "class" in chunk_by_kind
    assert "function" in chunk_by_kind

    # Verify counts
    assert len(chunk_by_kind["repo"]) == 1
    assert len(chunk_by_kind["project"]) == 1
    assert len(chunk_by_kind["module"]) == 2  # backend, backend.math
    assert len(chunk_by_kind["file"]) == 1
    assert len(chunk_by_kind["class"]) == 1  # Calculator
    assert len(chunk_by_kind["function"]) == 3  # top_level + add + subtract

    print("\n✅ Chunk hierarchy test passed!")


def test_chunk_parent_child_links(python_generator, semantic_builder, graph_builder, chunk_builder):
    """Test parent-child relationships in chunk hierarchy"""

    code = """
class MyClass:
    def method1(self):
        return 1

    def method2(self):
        return 2
"""

    # Generate full pipeline
    source = SourceFile.from_content("src/example.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Generate chunks
    file_text = code.split("\n")
    repo_config = {"project_name": "default"}
    chunks, chunk_to_ir, chunk_to_graph = chunk_builder.build(
        repo_id="test-repo",
        ir_doc=ir_doc,
        graph_doc=graph_doc,
        file_text=file_text,
        repo_config=repo_config,
    )

    # Build chunk lookup
    chunk_map = {c.chunk_id: c for c in chunks}

    # Verify parent-child links
    print("\n📋 Verifying parent-child links:")

    for chunk in chunks:
        print(f"\n{chunk.kind}: {chunk.fqn}")
        print(f"  Parent: {chunk.parent_id}")
        print(f"  Children: {len(chunk.children)}")

        # Verify children reference valid chunks
        for child_id in chunk.children:
            assert child_id in chunk_map, f"Invalid child ID: {child_id}"
            child = chunk_map[child_id]
            print(f"    - {child.kind}: {child.fqn}")

            # Verify back-reference
            assert (
                child.parent_id == chunk.chunk_id
            ), f"Child {child.chunk_id} doesn't reference parent {chunk.chunk_id}"

    print("\n✅ Parent-child link test passed!")


def test_chunk_line_ranges(python_generator, semantic_builder, graph_builder, chunk_builder):
    """Test chunk line range assignments"""

    code = """
class MyClass:
    def method(self):
        x = 1
        y = 2
        return x + y
"""

    # Generate full pipeline
    source = SourceFile.from_content("src/test.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Generate chunks
    file_text = code.split("\n")
    repo_config = {"project_name": "default"}
    chunks, chunk_to_ir, chunk_to_graph = chunk_builder.build(
        repo_id="test-repo",
        ir_doc=ir_doc,
        graph_doc=graph_doc,
        file_text=file_text,
        repo_config=repo_config,
    )

    # Verify line ranges
    print("\n📋 Chunk line ranges:")

    for chunk in chunks:
        if chunk.start_line is not None:
            print(f"  {chunk.kind:10s} {chunk.fqn:30s} lines {chunk.start_line}-{chunk.end_line}")
            assert chunk.start_line <= chunk.end_line, f"Invalid line range for {chunk.chunk_id}"
            assert chunk.start_line == chunk.original_start_line
            assert chunk.end_line == chunk.original_end_line
        else:
            print(f"  {chunk.kind:10s} {chunk.fqn:30s} (no line range)")

    print("\n✅ Line range test passed!")


def test_chunk_content_hash(python_generator, semantic_builder, graph_builder, chunk_builder):
    """Test chunk content hash generation"""

    code = """
def example():
    return 42
"""

    # Generate full pipeline
    source = SourceFile.from_content("src/example.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")
    source_map = {source.file_path: source}
    semantic_snapshot, semantic_index = semantic_builder.build_full(ir_doc, source_map)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Generate chunks
    file_text = code.split("\n")
    repo_config = {"project_name": "default"}
    chunks, chunk_to_ir, chunk_to_graph = chunk_builder.build(
        repo_id="test-repo",
        ir_doc=ir_doc,
        graph_doc=graph_doc,
        file_text=file_text,
        repo_config=repo_config,
    )

    # Verify content hashes
    print("\n📋 Content hashes:")

    for chunk in chunks:
        if chunk.content_hash:
            print(f"  {chunk.kind:10s} {chunk.fqn:30s} → {chunk.content_hash[:16]}...")
            assert len(chunk.content_hash) == 32  # MD5 hash length
        else:
            print(f"  {chunk.kind:10s} {chunk.fqn:30s} (no hash)")

    print("\n✅ Content hash test passed!")


if __name__ == "__main__":
    from src.foundation.generators import PythonIRGenerator
    from src.foundation.graph import GraphBuilder
    from src.foundation.semantic_ir import DefaultSemanticIrBuilder

    gen = PythonIRGenerator(repo_id="test-repo")
    sem_builder = DefaultSemanticIrBuilder()
    g_builder = GraphBuilder()
    c_builder = ChunkBuilder(ChunkIdGenerator())

    print("=" * 60)
    print("Test 1: Basic Chunk Hierarchy")
    print("=" * 60)
    test_chunk_builder_basic(gen, sem_builder, g_builder, c_builder)

    print("\n" + "=" * 60)
    print("Test 2: Parent-Child Links")
    print("=" * 60)
    test_chunk_parent_child_links(gen, sem_builder, g_builder, c_builder)

    print("\n" + "=" * 60)
    print("Test 3: Line Ranges")
    print("=" * 60)
    test_chunk_line_ranges(gen, sem_builder, g_builder, c_builder)

    print("\n" + "=" * 60)
    print("Test 4: Content Hashes")
    print("=" * 60)
    test_chunk_content_hash(gen, sem_builder, g_builder, c_builder)

    print("\n" + "=" * 60)
    print("✅ All Chunk Builder Tests Passed!")
    print("=" * 60)
