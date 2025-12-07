"""
Tests for ParentChunker
"""

import pytest
from src.chunking import ChunkingConfig, LeafChunk, ParentChunker
from src.core.ports.parser_port import CodeNode


class MockTokenizer:
    """Mock TokenizerPort"""

    def count_tokens(self, text: str) -> int:
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
def parent_chunker():
    """Create ParentChunker instance"""
    config = ChunkingConfig(
        min_tokens=5,
        max_tokens=20,
        enable_adaptive_sizing=True,
    )
    return ParentChunker(MockTokenizer(), MockNormalizer(), config)


@pytest.fixture
def sample_nodes():
    """Sample CodeNodes"""
    return [
        CodeNode(
            node_id="func1",
            node_type="function",
            name="foo",
            file_path="test.py",
            start_line=1,
            end_line=10,
            raw_code="def foo():\n    pass",
            attrs={"signature": "foo()", "modifiers": ["public"]},
        ),
        CodeNode(
            node_id="class1",
            node_type="class",
            name="MyClass",
            file_path="test.py",
            start_line=12,
            end_line=20,
            raw_code="class MyClass:\n    pass",
            attrs={"signature": "MyClass"},
        ),
        CodeNode(
            node_id="var1",
            node_type="variable",
            name="x",
            file_path="test.py",
            start_line=22,
            end_line=22,
            raw_code="x = 1",
            attrs={},
        ),
    ]


@pytest.fixture
def sample_leaf_chunks():
    """Sample LeafChunks"""
    return [
        LeafChunk(
            id="leaf1",
            repo_id="repo1",
            file_path="test.py",
            language="python",
            kind="code",
            parent_id=None,
            node_id="func1",
            start_line=1,
            end_line=10,
            text="def foo():\n    pass",
            token_count=5,
        ),
        LeafChunk(
            id="leaf2",
            repo_id="repo1",
            file_path="test.py",
            language="python",
            kind="code",
            parent_id=None,
            node_id="class1",
            start_line=12,
            end_line=20,
            text="class MyClass:\n    pass",
            token_count=5,
        ),
    ]


def test_create_parent_chunks_structure_only(parent_chunker, sample_nodes, sample_leaf_chunks):
    """Test: 구조 노드(function, class)만 ParentChunk 생성"""
    chunks = parent_chunker.create_parent_chunks(
        nodes=sample_nodes,
        leaf_chunks=sample_leaf_chunks,
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    # function(1) + class(1) + file-level(1) = 3
    assert len(chunks) == 3

    # 타입 확인
    kinds = {chunk.kind for chunk in chunks}
    assert "function" in kinds
    assert "class" in kinds
    assert "file" in kinds


def test_file_level_chunk_always_created(parent_chunker, sample_nodes, sample_leaf_chunks):
    """Test: File-level ParentChunk는 반드시 1개 생성"""
    chunks = parent_chunker.create_parent_chunks(
        nodes=sample_nodes,
        leaf_chunks=sample_leaf_chunks,
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    file_chunks = [c for c in chunks if c.kind == "file"]
    assert len(file_chunks) == 1

    file_chunk = file_chunks[0]
    assert file_chunk.title == "test.py"
    assert file_chunk.node_id is None  # 파일 레벨은 node_id 없음


def test_importance_score_calculation(parent_chunker, sample_nodes, sample_leaf_chunks):
    """Test: 초기 중요도 계산 (heuristic)"""
    chunks = parent_chunker.create_parent_chunks(
        nodes=sample_nodes,
        leaf_chunks=sample_leaf_chunks,
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    # public 함수는 중요도가 높아야 함
    func_chunk = next(c for c in chunks if c.kind == "function")
    assert func_chunk.importance_score > 0.0
    assert func_chunk.importance_score <= 0.5  # Chunking Layer: 최대 0.5


def test_adaptive_chunking_suggested_tokens(parent_chunker, sample_nodes, sample_leaf_chunks):
    """Test: Adaptive chunking - suggested_max_tokens 계산"""
    chunks = parent_chunker.create_parent_chunks(
        nodes=sample_nodes,
        leaf_chunks=sample_leaf_chunks,
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    # 중요도에 따라 suggested_max_tokens가 설정되어야 함
    func_chunk = next(c for c in chunks if c.kind == "function")
    assert func_chunk.suggested_max_tokens is not None
    assert func_chunk.suggested_max_tokens > 0


def test_leaf_chunk_association(parent_chunker, sample_nodes, sample_leaf_chunks):
    """Test: ParentChunk와 LeafChunk 연결"""
    chunks = parent_chunker.create_parent_chunks(
        nodes=sample_nodes,
        leaf_chunks=sample_leaf_chunks,
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    func_chunk = next(c for c in chunks if c.kind == "function")

    # leaf_ids에 연결된 LeafChunk ID가 있어야 함
    assert len(func_chunk.leaf_ids) > 0
    assert "leaf1" in func_chunk.leaf_ids


def test_parent_chunk_id_stable(parent_chunker, sample_nodes, sample_leaf_chunks):
    """Test: Stable ParentChunk ID (같은 signature → 같은 ID)"""
    chunks1 = parent_chunker.create_parent_chunks(
        nodes=sample_nodes,
        leaf_chunks=sample_leaf_chunks,
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    chunks2 = parent_chunker.create_parent_chunks(
        nodes=sample_nodes,
        leaf_chunks=sample_leaf_chunks,
        repo_id="repo1",
        file_path="test.py",
        language="python",
    )

    # 같은 노드 → 같은 ID
    func1 = next(c for c in chunks1 if c.kind == "function")
    func2 = next(c for c in chunks2 if c.kind == "function")
    assert func1.id == func2.id
