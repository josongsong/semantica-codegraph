"""
Test Chunk Models and ID Generator
"""

from src.foundation.chunk import Chunk, ChunkIdContext, ChunkIdGenerator


def test_chunk_model_creation():
    """Test basic Chunk model creation"""
    chunk = Chunk(
        chunk_id="chunk:repo:function:main.foo",
        repo_id="repo",
        snapshot_id="snap:001",
        project_id=None,
        module_path="main",
        file_path="main.py",
        kind="function",
        fqn="main.foo",
        start_line=10,
        end_line=20,
        original_start_line=10,
        original_end_line=20,
        content_hash="abc123",
        parent_id="chunk:repo:file:main",
        children=[],
        language="python",
        symbol_visibility="public",
        symbol_id="func:repo:main.py:main.foo",
        symbol_owner_id="func:repo:main.py:main.foo",
        summary="Test function",
        importance=0.8,
        attrs={},
    )

    assert chunk.chunk_id == "chunk:repo:function:main.foo"
    assert chunk.kind == "function"
    assert chunk.fqn == "main.foo"
    assert chunk.start_line == 10
    assert chunk.end_line == 20
    print(f"✅ Chunk model created: {chunk.chunk_id}")


def test_chunk_id_generator_basic():
    """Test basic chunk ID generation without collisions"""
    gen = ChunkIdGenerator()

    ctx1 = ChunkIdContext(repo_id="myrepo", kind="function", fqn="main.foo", content_hash="abc123")
    chunk_id1 = gen.generate(ctx1)

    ctx2 = ChunkIdContext(repo_id="myrepo", kind="class", fqn="main.Bar", content_hash="def456")
    chunk_id2 = gen.generate(ctx2)

    assert chunk_id1 == "chunk:myrepo:function:main.foo"
    assert chunk_id2 == "chunk:myrepo:class:main.Bar"
    print(f"✅ Generated IDs: {chunk_id1}, {chunk_id2}")


def test_chunk_id_generator_collision():
    """Test chunk ID generation with collision handling"""
    gen = ChunkIdGenerator()

    # First generation - no collision
    ctx1 = ChunkIdContext(repo_id="myrepo", kind="function", fqn="main.foo", content_hash="abc12345")
    chunk_id1 = gen.generate(ctx1)
    assert chunk_id1 == "chunk:myrepo:function:main.foo"

    # Second generation - collision, should append hash
    ctx2 = ChunkIdContext(repo_id="myrepo", kind="function", fqn="main.foo", content_hash="def67890")
    chunk_id2 = gen.generate(ctx2)
    assert chunk_id2 == "chunk:myrepo:function:main.foo:def67890"
    print(f"✅ Collision handled: {chunk_id1} -> {chunk_id2}")


def test_chunk_id_generator_reset():
    """Test chunk ID generator reset functionality"""
    gen = ChunkIdGenerator()

    ctx = ChunkIdContext(repo_id="myrepo", kind="function", fqn="main.foo", content_hash="abc123")

    # First generation
    chunk_id1 = gen.generate(ctx)
    assert chunk_id1 == "chunk:myrepo:function:main.foo"

    # Reset and generate again - should get same ID
    gen.reset()
    chunk_id2 = gen.generate(ctx)
    assert chunk_id2 == "chunk:myrepo:function:main.foo"
    print(f"✅ Reset works: {chunk_id1} == {chunk_id2}")


def test_chunk_hierarchy_levels():
    """Test all chunk hierarchy levels"""
    gen = ChunkIdGenerator()

    levels = [
        ("repo", "myrepo", "chunk:myrepo:repo:myrepo"),
        ("project", "backend", "chunk:myrepo:project:backend"),
        ("module", "backend.search", "chunk:myrepo:module:backend.search"),
        ("file", "backend.search.retriever", "chunk:myrepo:file:backend.search.retriever"),
        (
            "class",
            "backend.search.retriever.Retriever",
            "chunk:myrepo:class:backend.search.retriever.Retriever",
        ),
        (
            "function",
            "backend.search.retriever.Retriever.search",
            "chunk:myrepo:function:backend.search.retriever.Retriever.search",
        ),
    ]

    for kind, fqn, expected_id in levels:
        ctx = ChunkIdContext(repo_id="myrepo", kind=kind, fqn=fqn)
        chunk_id = gen.generate(ctx)
        assert chunk_id == expected_id
        print(f"  ✅ {kind:10s} -> {chunk_id}")

    print("✅ All hierarchy levels tested")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Test 1: Chunk Model Creation")
    print("=" * 60)
    test_chunk_model_creation()

    print("\n" + "=" * 60)
    print("Test 2: Chunk ID Generator - Basic")
    print("=" * 60)
    test_chunk_id_generator_basic()

    print("\n" + "=" * 60)
    print("Test 3: Chunk ID Generator - Collision")
    print("=" * 60)
    test_chunk_id_generator_collision()

    print("\n" + "=" * 60)
    print("Test 4: Chunk ID Generator - Reset")
    print("=" * 60)
    test_chunk_id_generator_reset()

    print("\n" + "=" * 60)
    print("Test 5: Chunk Hierarchy Levels")
    print("=" * 60)
    test_chunk_hierarchy_levels()

    print("\n" + "=" * 60)
    print("✅ All Chunk Model Tests Passed!")
    print("=" * 60)
