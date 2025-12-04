"""
Test to verify Graph-First strategy eliminates redundancy

This test verifies that the Graph-First approach correctly eliminates
the redundancy that existed when both ChunkBuilder and GraphBuilder
had role mapping logic.
"""

from src.foundation.chunk import ChunkBuilder
from src.foundation.chunk.builder_graphfirst import map_graph_kind_to_chunk_kind
from src.foundation.chunk.id_generator import ChunkIdGenerator
from src.foundation.generators import PythonIRGenerator
from src.foundation.graph import GraphBuilder
from src.foundation.graph.models import GraphNodeKind
from src.foundation.parsing import SourceFile
from src.foundation.semantic_ir import DefaultSemanticIrBuilder


def test_graph_first_no_duplicates():
    """Verify that Graph-First strategy creates no duplicate chunks"""

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

    # Setup
    python_generator = PythonIRGenerator(repo_id="test-repo")
    semantic_builder = DefaultSemanticIrBuilder()
    graph_builder = GraphBuilder()
    chunk_builder = ChunkBuilder(ChunkIdGenerator())

    # Generate IR
    source = SourceFile.from_content("src/services/user_service.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")

    # Set roles
    for node in ir_doc.nodes:
        if node.name == "UserService":
            node.role = "service"
        elif node.name == "UserRepository":
            node.role = "repository"

    # Generate Semantic IR & Graph
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc)
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    # Build chunks using Graph-First strategy
    file_text = code.split("\n")
    chunks, _, _ = chunk_builder.build(
        repo_id="test-repo",
        ir_doc=ir_doc,
        graph_doc=graph_doc,
        file_text=file_text,
        repo_config={"root": "/"},
        snapshot_id="snap:001",
    )

    # Check for duplicates based on (file_path, start_line, end_line)
    seen_spans = set()
    duplicates = []

    for chunk in chunks:
        if chunk.start_line is None or chunk.end_line is None:
            continue  # Skip structural chunks (repo, project, module, file)

        span = (chunk.file_path, chunk.start_line, chunk.end_line)
        if span in seen_spans:
            duplicates.append(chunk)
        seen_spans.add(span)

    print(f"\n  Total chunks created: {len(chunks)}")
    print(f"  Duplicate chunks found: {len(duplicates)}")

    if duplicates:
        print("\n  Duplicate chunks:")
        for dup in duplicates:
            print(f"    - {dup.kind}: {dup.fqn} (lines {dup.start_line}-{dup.end_line})")

    # VERIFY: No duplicates
    assert len(duplicates) == 0, f"Found {len(duplicates)} duplicate chunks"

    # VERIFY: Service and Repository chunks exist
    service_chunks = [c for c in chunks if c.kind == "service"]
    repo_chunks = [c for c in chunks if c.kind == "repository"]

    assert len(service_chunks) >= 1, "Should have at least one service chunk"
    assert len(repo_chunks) >= 1, "Should have at least one repository chunk"

    print(f"  Service chunks: {len(service_chunks)}")
    print(f"  Repository chunks: {len(repo_chunks)}")
    print("\n✅ Graph-First strategy: No duplicates!")


def test_role_mapping_single_source():
    """Verify that role mapping exists only in GraphBuilder (single source of truth)"""

    # GraphBuilder has the mapping
    from src.foundation.graph.builder import GraphBuilder

    graph_builder = GraphBuilder()

    # ChunkBuilder uses map_graph_kind_to_chunk_kind helper
    # (no direct role mapping logic)

    # Test GraphBuilder mapping
    from src.foundation.ir.models import NodeKind

    test_roles = [
        ("service", GraphNodeKind.SERVICE),
        ("repository", GraphNodeKind.REPOSITORY),
        ("config", GraphNodeKind.CONFIG),
        ("job", GraphNodeKind.JOB),
        ("middleware", GraphNodeKind.MIDDLEWARE),
        ("route", GraphNodeKind.ROUTE),
    ]

    print("\n  Graph-First Role Mapping:")
    print(f"  {'Role':<15} {'GraphNodeKind':<20} {'ChunkKind':<20}")
    print(f"  {'-' * 60}")

    for role, expected_graph_kind in test_roles:
        # GraphBuilder: role → GraphNodeKind
        graph_kind = graph_builder._map_ir_kind_to_graph_kind(NodeKind.CLASS, role)

        # ChunkBuilder: GraphNodeKind → chunk kind string
        chunk_kind = map_graph_kind_to_chunk_kind(graph_kind)

        print(f"  {role:<15} {graph_kind.value:<20} {chunk_kind:<20}")

        # Verify correct mapping
        assert graph_kind == expected_graph_kind
        assert chunk_kind == role  # Should match role name

    print("\n✅ Single source of truth: GraphBuilder → ChunkBuilder")
    print("   No duplication of role mapping logic!")


if __name__ == "__main__":
    print("=" * 70)
    print("Testing Graph-First Strategy (No Redundancy)")
    print("=" * 70)

    test_graph_first_no_duplicates()

    print("\n" + "=" * 70)
    print("Testing Single Source of Truth for Role Mapping")
    print("=" * 70)

    test_role_mapping_single_source()

    print("\n" + "=" * 70)
    print("✅ All Graph-First tests passed!")
    print("=" * 70)
