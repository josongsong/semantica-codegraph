"""
Tests for IndexDocument Transformer

Verifies Chunk → IndexDocument transformation with RepoMap integration.
"""

from src.foundation.chunk.models import Chunk
from src.index.common.transformer import IndexDocumentTransformer
from src.repomap.models import (
    RepoMapMetrics,
    RepoMapNode,
    RepoMapSnapshot,
)


def create_test_chunk(**overrides):
    """Helper to create test Chunk with all required fields."""
    defaults = {
        "chunk_id": "chunk:test:1",
        "repo_id": "test_repo",
        "snapshot_id": "test_snapshot",
        "project_id": None,
        "module_path": None,
        "file_path": "src/test.py",
        "kind": "function",
        "fqn": "test_func",
        "start_line": 1,
        "end_line": 10,
        "original_start_line": 1,
        "original_end_line": 10,
        "content_hash": "abc123",
        "parent_id": None,
        "children": [],
        "language": "python",
        "symbol_visibility": "public",
        "symbol_id": None,
        "symbol_owner_id": None,
        "summary": None,
        "importance": None,
        "attrs": {},
    }
    defaults.update(overrides)
    return Chunk(**defaults)


def test_basic_transformation():
    """Test basic Chunk to IndexDocument transformation."""
    chunk = create_test_chunk(
        module_path="test.module",
        fqn="test.module.my_function",
        start_line=10,
        end_line=20,
        original_start_line=10,
        original_end_line=20,
        symbol_id="symbol:test.module.my_function",
        summary="A test function",
        attrs={"signature": "def my_function(x: int) -> int"},
    )

    transformer = IndexDocumentTransformer()
    doc = transformer.transform(chunk, snapshot_id="snapshot:123")

    assert doc.chunk_id == chunk.chunk_id
    assert doc.repo_id == chunk.repo_id
    assert doc.snapshot_id == "snapshot:123"
    assert doc.file_path == chunk.file_path
    assert doc.language == chunk.language
    assert doc.symbol_id == chunk.symbol_id
    assert doc.symbol_name == "my_function"

    # Check content structure
    assert "[SUMMARY]" in doc.content
    assert "[SIGNATURE]" in doc.content
    assert "[META]" in doc.content

    # Check identifiers
    assert "my_function" in doc.identifiers
    assert "test" in doc.identifiers
    assert "module" in doc.identifiers

    # Check tags
    assert doc.tags["kind"] == "function"
    assert doc.tags["module"] == "test.module"
    assert doc.tags["language"] == "python"


def test_transformation_with_repomap():
    """Test transformation with RepoMap importance scores."""
    # Create chunk
    chunk = create_test_chunk(
        file_path="src/main.py",
        fqn="main",
    )

    # Create RepoMap node
    repomap_node = RepoMapNode(
        id="repomap:test:1",
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        kind="function",
        name="main",
        chunk_ids=["chunk:test:1"],
        metrics=RepoMapMetrics(
            loc=50,
            symbol_count=1,
            pagerank=0.85,
            importance=0.92,
        ),
        is_entrypoint=True,
    )

    # Create RepoMap snapshot
    repomap_snapshot = RepoMapSnapshot(
        repo_id="test_repo",
        snapshot_id="snapshot:123",
        root_node_id="repomap:root",
        nodes=[repomap_node],
    )

    # Transform with RepoMap
    transformer = IndexDocumentTransformer(repomap_snapshot=repomap_snapshot)
    doc = transformer.transform(chunk, snapshot_id="snapshot:123")

    # Check RepoMap tags are included
    assert "repomap_score" in doc.tags
    assert doc.tags["repomap_score"] == "0.92"
    assert "pagerank_score" in doc.tags
    assert doc.tags["pagerank_score"] == "0.85"
    assert doc.tags["is_entrypoint"] == "true"
    assert doc.tags["loc"] == "50"


def test_transformation_with_source_code():
    """Test transformation with source code content."""
    chunk = create_test_chunk()

    source_code = """def test_func():
    return 42"""

    transformer = IndexDocumentTransformer()
    doc = transformer.transform(chunk, source_code=source_code, snapshot_id="snapshot:123")

    # Check code is included
    assert "[CODE]" in doc.content
    assert "def test_func():" in doc.content
    assert "return 42" in doc.content


def test_batch_transformation():
    """Test batch transformation of multiple chunks."""
    chunks = [
        create_test_chunk(
            chunk_id=f"chunk:test:{i}",
            file_path=f"src/file{i}.py",
            fqn=f"func{i}",
            content_hash=f"hash{i}",
        )
        for i in range(5)
    ]

    transformer = IndexDocumentTransformer()
    docs = transformer.transform_batch(chunks, snapshot_id="snapshot:123")

    assert len(docs) == 5
    for i, doc in enumerate(docs):
        assert doc.chunk_id == f"chunk:test:{i}"
        assert doc.file_path == f"src/file{i}.py"
        assert doc.snapshot_id == "snapshot:123"


def test_identifier_extraction():
    """Test identifier extraction from FQN and attributes."""
    chunk = create_test_chunk(
        fqn="my.package.MyClass.my_method",
        attrs={"identifiers": ["MyClass", "my_method", "arg1", "arg2"]},
    )

    transformer = IndexDocumentTransformer()
    doc = transformer.transform(chunk, snapshot_id="snapshot:123")

    # Check identifiers from FQN
    assert "my" in doc.identifiers
    assert "package" in doc.identifiers
    assert "myclass" in doc.identifiers
    assert "my_method" in doc.identifiers

    # Check identifiers from attrs
    assert "arg1" in doc.identifiers
    assert "arg2" in doc.identifiers


def test_parent_chunk_id_tag():
    """Test parent_chunk_id is included in tags."""
    chunk = create_test_chunk(
        parent_id="chunk:test:parent",
    )

    transformer = IndexDocumentTransformer()
    doc = transformer.transform(chunk, snapshot_id="snapshot:123")

    assert "parent_chunk_id" in doc.tags
    assert doc.tags["parent_chunk_id"] == "chunk:test:parent"
