"""
Test Chunk Boundary Validator
"""

import pytest
from src.foundation.chunk import BoundaryValidationError, Chunk, ChunkBoundaryValidator


def test_boundary_validator_valid_chunks():
    """Test boundary validation with valid chunks (no gaps/overlaps)"""
    validator = ChunkBoundaryValidator()

    chunks = [
        # File chunk
        Chunk(
            chunk_id="chunk:repo:file:test",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="file",
            fqn="test",
            start_line=1,
            end_line=20,
            original_start_line=1,
            original_end_line=20,
            content_hash="abc",
            parent_id="chunk:repo:module:root",
            children=["chunk1", "chunk2"],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
        # Function 1
        Chunk(
            chunk_id="chunk1",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="function",
            fqn="test.func1",
            start_line=1,
            end_line=10,
            original_start_line=1,
            original_end_line=10,
            content_hash="abc1",
            parent_id="chunk:repo:file:test",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
        # Function 2 (consecutive, no gap)
        Chunk(
            chunk_id="chunk2",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="function",
            fqn="test.func2",
            start_line=11,
            end_line=20,
            original_start_line=11,
            original_end_line=20,
            content_hash="abc2",
            parent_id="chunk:repo:file:test",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
    ]

    # Should not raise any errors
    validator.validate(chunks)
    print("✅ Valid chunks passed validation")


def test_boundary_validator_overlap_error():
    """Test boundary validation detects overlapping chunks"""
    validator = ChunkBoundaryValidator()

    chunks = [
        # Function 1
        Chunk(
            chunk_id="chunk1",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="function",
            fqn="test.func1",
            start_line=1,
            end_line=15,  # Overlaps with chunk2
            original_start_line=1,
            original_end_line=15,
            content_hash="abc1",
            parent_id="chunk:repo:file:test",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
        # Function 2 (overlaps with chunk1)
        Chunk(
            chunk_id="chunk2",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="function",
            fqn="test.func2",
            start_line=10,  # Starts before chunk1 ends
            end_line=20,
            original_start_line=10,
            original_end_line=20,
            content_hash="abc2",
            parent_id="chunk:repo:file:test",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
    ]

    # Should raise overlap error
    with pytest.raises(BoundaryValidationError, match="overlap"):
        validator.validate(chunks)

    print("✅ Overlap detection works")


def test_boundary_validator_gap_warning(caplog):
    """Test boundary validation detects gaps between chunks"""
    validator = ChunkBoundaryValidator(allow_gaps=True)

    chunks = [
        # Function 1
        Chunk(
            chunk_id="chunk1",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="function",
            fqn="test.func1",
            start_line=1,
            end_line=10,
            original_start_line=1,
            original_end_line=10,
            content_hash="abc1",
            parent_id="chunk:repo:file:test",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
        # Function 2 (gap: lines 11-14 missing)
        Chunk(
            chunk_id="chunk2",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="function",
            fqn="test.func2",
            start_line=15,  # Gap of 4 lines
            end_line=20,
            original_start_line=15,
            original_end_line=20,
            content_hash="abc2",
            parent_id="chunk:repo:file:test",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
    ]

    # Should log warning but not raise error
    validator.validate(chunks)

    # Check warning was logged
    assert any("Gap detected" in record.message for record in caplog.records)
    print("✅ Gap warning logged")


def test_boundary_validator_gap_error():
    """Test boundary validation can raise error on gaps"""
    validator = ChunkBoundaryValidator(allow_gaps=False)

    chunks = [
        Chunk(
            chunk_id="chunk1",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="function",
            fqn="test.func1",
            start_line=1,
            end_line=10,
            original_start_line=1,
            original_end_line=10,
            content_hash="abc1",
            parent_id="chunk:repo:file:test",
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
            chunk_id="chunk2",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="function",
            fqn="test.func2",
            start_line=15,
            end_line=20,
            original_start_line=15,
            original_end_line=20,
            content_hash="abc2",
            parent_id="chunk:repo:file:test",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
    ]

    # Should raise gap error when allow_gaps=False
    with pytest.raises(BoundaryValidationError, match="Gap detected"):
        validator.validate(chunks)

    print("✅ Gap error works")


def test_boundary_validator_invalid_line_range():
    """Test boundary validation detects invalid line ranges"""
    validator = ChunkBoundaryValidator()

    chunks = [
        Chunk(
            chunk_id="chunk1",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="function",
            fqn="test.func1",
            start_line=20,  # Invalid: start > end
            end_line=10,
            original_start_line=20,
            original_end_line=10,
            content_hash="abc1",
            parent_id="chunk:repo:file:test",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
    ]

    # Should raise error for invalid line range
    with pytest.raises(BoundaryValidationError, match="Invalid line range"):
        validator.validate(chunks)

    print("✅ Invalid line range detection works")


def test_boundary_validator_large_class_detection():
    """Test large class detection"""
    validator = ChunkBoundaryValidator(large_class_threshold=1000)

    chunks = [
        # Small class (should not trigger)
        Chunk(
            chunk_id="chunk:small",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="class",
            fqn="test.SmallClass",
            start_line=1,
            end_line=20,  # ~400 tokens
            original_start_line=1,
            original_end_line=20,
            content_hash="abc1",
            parent_id="chunk:repo:file:test",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
        # Large class (should trigger)
        Chunk(
            chunk_id="chunk:large",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path="test.py",
            kind="class",
            fqn="test.LargeClass",
            start_line=100,
            end_line=200,  # ~2000 tokens
            original_start_line=100,
            original_end_line=200,
            content_hash="abc2",
            parent_id="chunk:repo:file:test",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
    ]

    large_classes = validator.check_large_class_flatten(chunks)

    # Should detect the large class
    assert len(large_classes) == 1
    assert large_classes[0] == "chunk:large"

    print(f"✅ Large class detection works: {large_classes}")


def test_boundary_validator_no_line_ranges():
    """Test boundary validation handles chunks without line ranges"""
    validator = ChunkBoundaryValidator()

    chunks = [
        # Repo chunk (no lines)
        Chunk(
            chunk_id="chunk:repo",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id=None,
            module_path=None,
            file_path=None,
            kind="repo",
            fqn="repo",
            start_line=None,
            end_line=None,
            original_start_line=None,
            original_end_line=None,
            content_hash=None,
            parent_id=None,
            children=[],
            language=None,
            symbol_visibility=None,
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
        # Project chunk (no lines)
        Chunk(
            chunk_id="chunk:proj",
            repo_id="repo",
            snapshot_id="snap:001",
            project_id="proj",
            module_path=None,
            file_path=None,
            kind="project",
            fqn="proj",
            start_line=None,
            end_line=None,
            original_start_line=None,
            original_end_line=None,
            content_hash=None,
            parent_id="chunk:repo",
            children=[],
            language=None,
            symbol_visibility=None,
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        ),
    ]

    # Should not raise error for chunks without line ranges
    validator.validate(chunks)
    print("✅ No-line-range chunks handled correctly")


if __name__ == "__main__":
    print("=" * 60)
    print("Test 1: Valid Chunks")
    print("=" * 60)
    test_boundary_validator_valid_chunks()

    print("\n" + "=" * 60)
    print("Test 2: Overlap Detection")
    print("=" * 60)
    test_boundary_validator_overlap_error()

    print("\n" + "=" * 60)
    print("Test 3: Invalid Line Range")
    print("=" * 60)
    test_boundary_validator_invalid_line_range()

    print("\n" + "=" * 60)
    print("Test 7: No Line Ranges")
    print("=" * 60)
    test_boundary_validator_no_line_ranges()

    print("\n" + "=" * 60)
    print("✅ All Boundary Validation Tests Passed!")
    print("=" * 60)
