"""
Tests for DeltaCalculator
"""

import pytest

from src.chunking import (
    ChunkDelta,
    ChunkDeltaOperation,
    DeltaCalculator,
    LeafChunk,
)


class MockNormalizer:
    """Mock CanonicalTextNormalizerPort for testing"""

    def canonicalize(self, text: str, language: str) -> str:
        # Simple mock: just strip whitespace
        return text.strip()


@pytest.fixture
def delta_calculator():
    """Create DeltaCalculator instance"""
    normalizer = MockNormalizer()
    return DeltaCalculator(normalizer)


@pytest.fixture
def sample_leaf_chunks():
    """Sample LeafChunk for testing"""
    return [
        LeafChunk(
            id="chunk1",
            repo_id="repo1",
            file_path="test.py",
            language="python",
            kind="code",
            start_line=1,
            end_line=10,
            text="def foo():\n    pass",
            token_count=10,
        ),
        LeafChunk(
            id="chunk2",
            repo_id="repo1",
            file_path="test.py",
            language="python",
            kind="code",
            start_line=11,
            end_line=20,
            text="def bar():\n    pass",
            token_count=10,
        ),
    ]


def test_calculate_leaf_deltas_all_insert(delta_calculator, sample_leaf_chunks):
    """Test: 이전 상태 없음 → 전체 INSERT"""
    deltas = delta_calculator.calculate_leaf_deltas(
        old_chunks=None,
        new_chunks=sample_leaf_chunks,
    )

    assert len(deltas) == 2
    assert all(delta.operation == ChunkDeltaOperation.INSERT for delta in deltas)
    assert all(delta.old_hash is None for delta in deltas)
    assert all(delta.new_hash is not None for delta in deltas)


def test_calculate_leaf_deltas_no_change(delta_calculator, sample_leaf_chunks):
    """Test: 변경 없음 → NOOP"""
    deltas = delta_calculator.calculate_leaf_deltas(
        old_chunks=sample_leaf_chunks,
        new_chunks=sample_leaf_chunks,
    )

    assert len(deltas) == 2
    assert all(delta.operation == ChunkDeltaOperation.NOOP for delta in deltas)


def test_calculate_leaf_deltas_update(delta_calculator, sample_leaf_chunks):
    """Test: 내용 변경 → UPDATE"""
    old_chunks = sample_leaf_chunks
    new_chunks = [
        LeafChunk(
            id="chunk1",
            repo_id="repo1",
            file_path="test.py",
            language="python",
            kind="code",
            start_line=1,
            end_line=10,
            text="def foo():\n    return 42",  # Changed
            token_count=12,
        ),
        sample_leaf_chunks[1],  # No change
    ]

    deltas = delta_calculator.calculate_leaf_deltas(
        old_chunks=old_chunks,
        new_chunks=new_chunks,
    )

    assert len(deltas) == 2
    assert deltas[0].operation == ChunkDeltaOperation.UPDATE
    assert deltas[1].operation == ChunkDeltaOperation.NOOP


def test_calculate_leaf_deltas_delete(delta_calculator, sample_leaf_chunks):
    """Test: 청크 삭제 → DELETE"""
    old_chunks = sample_leaf_chunks
    new_chunks = [sample_leaf_chunks[0]]  # chunk2 deleted

    deltas = delta_calculator.calculate_leaf_deltas(
        old_chunks=old_chunks,
        new_chunks=new_chunks,
    )

    # chunk1: NOOP, chunk2: DELETE
    assert len(deltas) == 2
    noop_delta = next(d for d in deltas if d.chunk_id == "chunk1")
    delete_delta = next(d for d in deltas if d.chunk_id == "chunk2")

    assert noop_delta.operation == ChunkDeltaOperation.NOOP
    assert delete_delta.operation == ChunkDeltaOperation.DELETE
    assert delete_delta.new_hash is None


def test_filter_actionable_deltas(delta_calculator):
    """Test: NOOP 필터링"""
    deltas = [
        ChunkDelta(
            chunk_id="1",
            kind="leaf",
            operation=ChunkDeltaOperation.INSERT,
            old_hash=None,
            new_hash="abc",
            ref_type="leaf",
            ref_id="1",
        ),
        ChunkDelta(
            chunk_id="2",
            kind="leaf",
            operation=ChunkDeltaOperation.NOOP,
            old_hash="def",
            new_hash="def",
            ref_type="leaf",
            ref_id="2",
        ),
        ChunkDelta(
            chunk_id="3",
            kind="leaf",
            operation=ChunkDeltaOperation.UPDATE,
            old_hash="ghi",
            new_hash="jkl",
            ref_type="leaf",
            ref_id="3",
        ),
    ]

    actionable = delta_calculator.filter_actionable_deltas(deltas)

    assert len(actionable) == 2  # INSERT + UPDATE
    assert all(d.operation != ChunkDeltaOperation.NOOP for d in actionable)
