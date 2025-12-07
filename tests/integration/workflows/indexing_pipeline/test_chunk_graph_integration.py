"""
Test Chunk + Graph Integration (Phase 3 + Phase 4)

Tests that extended CodeGraph node types (Route, Service, Repository)
are properly converted to Chunks.
"""

import pytest
from src.foundation.chunk import ChunkBuilder
from src.foundation.chunk.id_generator import ChunkIdGenerator
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


def test_extended_chunks_from_graph(python_generator, semantic_builder, graph_builder, chunk_builder):
    """Test that Service/Repository nodes are converted to chunks"""

    code = """
class UserService:
    \"\"\"Service for user operations\"\"\"
    def get_user(self, user_id: int):
        return user_id

class UserRepository:
    \"\"\"Repository for user data\"\"\"
    def find_by_id(self, user_id: int):
        return user_id
"""

    # Generate IR
    source = SourceFile.from_content("src/services/user_service.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")

    # Set roles (normally done by role tagger)
    for node in ir_doc.nodes:
        if node.name == "UserService":
            node.role = "service"
        elif node.name == "UserRepository":
            node.role = "repository"

    # Generate Semantic IR
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc)

    # Build Graph (Phase 3 - creates Service/Repository nodes)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Build Chunks (Phase 4 - should create service/repository chunks)
    file_text = code.split("\n")
    chunks, chunk_to_ir, chunk_to_graph = chunk_builder.build(
        repo_id="test-repo",
        ir_doc=ir_doc,
        graph_doc=graph_doc,
        file_text=file_text,
        repo_config={"root": "/"},
    )

    print(f"\n  Total chunks created: {len(chunks)}")

    # Count chunk types
    chunk_kinds = {}
    for chunk in chunks:
        chunk_kinds[chunk.kind] = chunk_kinds.get(chunk.kind, 0) + 1

    print(f"  Chunk distribution: {chunk_kinds}")

    # Verify extended chunks were created
    assert "service" in chunk_kinds, "Service chunks should be created"
    assert "repository" in chunk_kinds, "Repository chunks should be created"

    # Find specific chunks
    service_chunks = [c for c in chunks if c.kind == "service"]
    repository_chunks = [c for c in chunks if c.kind == "repository"]

    print(f"\n  Service chunks: {[c.fqn for c in service_chunks]}")
    print(f"  Repository chunks: {[c.fqn for c in repository_chunks]}")

    assert len(service_chunks) >= 1
    assert len(repository_chunks) >= 1

    # Verify chunk properties
    for chunk in service_chunks + repository_chunks:
        assert chunk.symbol_id is not None, "Extended chunks should have symbol_id"
        assert chunk.parent_id is not None, "Extended chunks should have parent"
        assert chunk.attrs.get("role") is not None, "Extended chunks should have role"
        # graph_node_kind is only set for GraphDocument-exclusive nodes
        # Role-based chunks from IR have "role" attr instead

    print("\n✅ Extended chunks test passed!")


def test_chunk_kind_mapping():
    """Test that all Phase 3 extended kinds are supported in Chunk model"""

    from src.foundation.chunk.models import Chunk

    # Test that all extended kinds are valid
    extended_kinds = ["route", "service", "repository", "config", "job", "middleware"]

    for kind in extended_kinds:
        # This should not raise a validation error
        chunk = Chunk(
            chunk_id=f"chunk:test:{kind}:test.Foo",
            repo_id="test",
            snapshot_id="snap:001",
            project_id=None,
            module_path=None,
            file_path="test.py",
            kind=kind,  # type: ignore
            fqn="test.Foo",
            start_line=1,
            end_line=10,
            original_start_line=1,
            original_end_line=10,
            content_hash="abc123",
            parent_id="parent",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id="id123",
            symbol_owner_id="id123",
            summary=None,
            importance=None,
            attrs={},
        )

        assert chunk.kind == kind

    print("\n  Extended chunk kinds supported:")
    for kind in extended_kinds:
        print(f"    - {kind}: ✓")

    print("\n✅ Chunk kind mapping test passed!")


def test_chunk_to_graph_mapping_extended(python_generator, semantic_builder, graph_builder, chunk_builder):
    """Test that ChunkToGraph mapping includes extended node types"""

    code = """
class PaymentService:
    def process_payment(self, amount: float):
        return True
"""

    # Generate IR
    source = SourceFile.from_content("src/payment/service.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")

    # Set role
    for node in ir_doc.nodes:
        if "PaymentService" in str(node.name):
            node.role = "service"

    # Generate Semantic IR
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc)

    # Build Graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Build Chunks
    file_text = code.split("\n")
    chunks, chunk_to_ir, chunk_to_graph = chunk_builder.build(
        repo_id="test-repo",
        ir_doc=ir_doc,
        graph_doc=graph_doc,
        file_text=file_text,
        repo_config={"root": "/"},
    )

    # Find service chunk
    service_chunks = [c for c in chunks if c.kind == "service"]
    assert len(service_chunks) >= 1

    service_chunk = service_chunks[0]

    # Verify chunk is mapped to graph nodes
    assert service_chunk.chunk_id in chunk_to_graph
    mapped_nodes = chunk_to_graph[service_chunk.chunk_id]

    print(f"\n  Service chunk: {service_chunk.fqn}")
    print(f"  Mapped graph nodes: {len(mapped_nodes)}")

    assert len(mapped_nodes) > 0, "Service chunk should be mapped to graph nodes"

    print("\n✅ ChunkToGraph mapping test passed!")


if __name__ == "__main__":
    gen = PythonIRGenerator(repo_id="test-repo")
    sem_builder = DefaultSemanticIrBuilder()
    g_builder = GraphBuilder()
    c_builder = ChunkBuilder(ChunkIdGenerator())

    print("=" * 60)
    print("Phase 3+4 Integration Tests")
    print("=" * 60)

    print("\n" + "=" * 60)
    print("Test 1: Extended Chunks from Graph")
    print("=" * 60)
    test_extended_chunks_from_graph(gen, sem_builder, g_builder, c_builder)

    print("\n" + "=" * 60)
    print("Test 2: Chunk Kind Mapping")
    print("=" * 60)
    test_chunk_kind_mapping()

    print("\n" + "=" * 60)
    print("Test 3: ChunkToGraph Mapping")
    print("=" * 60)
    test_chunk_to_graph_mapping_extended(gen, sem_builder, g_builder, c_builder)

    print("\n" + "=" * 60)
    print("✅ All Phase 3+4 integration tests passed!")
    print("=" * 60)
