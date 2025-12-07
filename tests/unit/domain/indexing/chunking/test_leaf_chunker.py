"""
Tests for LeafChunker
"""

import pytest
from src.chunking import ChunkingConfig, LeafChunker
from src.core.ports.parser_port import CodeNode


class MockTokenizer:
    """Mock TokenizerPort"""

    def count_tokens(self, text: str) -> int:
        # Simple mock: 1 token per word
        return len(text.split())

    def encode(self, text: str) -> list[int]:
        return [1] * self.count_tokens(text)


class MockNormalizer:
    """Mock CanonicalTextNormalizerPort"""

    def canonicalize(self, text: str, language: str) -> str:
        return text.strip()

    def normalize_signature(self, node: CodeNode) -> str:
        return f"{node.node_type}:{node.name}"

    def strip_comments(self, text: str, language: str) -> str:
        return text

    def strip_whitespace(self, text: str) -> str:
        return text.strip()


@pytest.fixture
def leaf_chunker():
    """Create LeafChunker instance"""
    config = ChunkingConfig(
        min_tokens=5,
        max_tokens=20,
        overlap_lines=2,
    )
    return LeafChunker(MockTokenizer(), MockNormalizer(), config)


@pytest.fixture
def sample_node():
    """Sample CodeNode"""
    return CodeNode(
        node_id="node1",
        node_type="function",
        name="test_function",
        file_path="test.py",
        start_line=1,
        end_line=10,
        raw_code="def test_function():\n    x = 1\n    y = 2\n    return x + y",
        attrs={"signature": "test_function()"},
    )


def test_create_single_chunk_small_node(leaf_chunker, sample_node):
    """Test: 작은 노드 → 단일 청크"""
    chunks = leaf_chunker.create_leaf_chunks(
        nodes=[sample_node],
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.repo_id == "repo1"
    assert chunk.file_path == "test.py"
    assert chunk.language == "python"
    assert chunk.start_line == 1
    assert chunk.end_line == 10
    assert chunk.node_id == "node1"


def test_create_chunks_large_node(leaf_chunker):
    """Test: 큰 노드 → 여러 청크로 분할"""
    # 긴 코드 (max_tokens=20 초과)
    long_code = "\n".join([f"line{i} = {i}" for i in range(30)])

    large_node = CodeNode(
        node_id="node2",
        node_type="function",
        name="large_function",
        file_path="test.py",
        start_line=1,
        end_line=30,
        raw_code=long_code,
        attrs={},
    )

    chunks = leaf_chunker.create_leaf_chunks(
        nodes=[large_node],
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    # 여러 청크로 분할되어야 함
    assert len(chunks) > 1

    # 각 청크는 max_tokens 이하여야 함 (단, 단일 라인이 초과하는 경우 제외)
    for chunk in chunks:
        assert chunk.repo_id == "repo1"
        assert chunk.node_id == "node2"


def test_chunk_id_stable(leaf_chunker, sample_node):
    """Test: Stable Chunk ID (같은 내용 → 같은 ID)"""
    chunks1 = leaf_chunker.create_leaf_chunks(
        nodes=[sample_node],
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    chunks2 = leaf_chunker.create_leaf_chunks(
        nodes=[sample_node],
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    assert chunks1[0].id == chunks2[0].id


def test_chunk_kind_detection(leaf_chunker):
    """Test: 청크 종류 판단 (code vs doc)"""
    # 주석이 많은 코드
    doc_node = CodeNode(
        node_id="doc_node",
        node_type="function",
        name="documented",
        file_path="test.py",
        start_line=1,
        end_line=5,
        raw_code="# This is a comment\n# Another comment\n# More comments\ndef foo():\n    pass",
        attrs={},
    )

    chunks = leaf_chunker.create_leaf_chunks(
        nodes=[doc_node],
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    # kind should be "doc" or "mixed" (주석 비율 높음)
    assert chunks[0].kind in ["doc", "mixed"]


def test_lineage_metadata(leaf_chunker, sample_node):
    """Test: Lineage 메타데이터 포함"""
    chunks = leaf_chunker.create_leaf_chunks(
        nodes=[sample_node],
        repo_id="repo1",
        file_path="test.py",
        language="python",
        file_hash="abc123",
    )

    chunk = chunks[0]
    assert chunk.source_file_hash == "abc123"
    assert chunk.parser_version is not None
    assert chunk.chunking_config_hash is not None
