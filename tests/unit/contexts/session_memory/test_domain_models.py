"""
Session Memory Domain Models Tests

Test Coverage:
- Enums: MemoryType, TaskType, TaskStatus, ImportanceLevel
- Value Objects: EmbeddingVector
- Edge cases: Validation, immutability
"""

import pytest

from codegraph_runtime.session_memory.domain.models import (
    EmbeddingVector,
    ImportanceLevel,
    MemoryType,
    PatternCategory,
    TaskStatus,
    TaskType,
)


class TestMemoryType:
    """MemoryType enum tests"""

    def test_all_types_defined(self):
        """All memory types exist"""
        assert MemoryType.WORKING.value == "working"
        assert MemoryType.EPISODIC.value == "episodic"
        assert MemoryType.SEMANTIC.value == "semantic"
        assert MemoryType.PROFILE.value == "profile"
        assert MemoryType.NONE.value == "none"

    def test_enum_count(self):
        """Expected number of memory types"""
        assert len(MemoryType) == 7


class TestTaskType:
    """TaskType enum tests"""

    def test_core_types_defined(self):
        """Core task types exist"""
        assert TaskType.SEARCH.value == "search"
        assert TaskType.IMPLEMENT.value == "implement"
        assert TaskType.DEBUG.value == "debug"
        assert TaskType.TEST.value == "test"
        assert TaskType.REFACTOR.value == "refactor"

    def test_all_types_are_strings(self):
        """All task types are string enums"""
        for task_type in TaskType:
            assert isinstance(task_type.value, str)


class TestTaskStatus:
    """TaskStatus enum tests"""

    def test_lifecycle_statuses(self):
        """Task lifecycle statuses exist"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.SUCCESS.value == "success"
        assert TaskStatus.FAILURE.value == "failure"

    def test_terminal_statuses(self):
        """Terminal statuses identified"""
        terminal = {TaskStatus.SUCCESS, TaskStatus.FAILURE, TaskStatus.CANCELLED}
        for status in terminal:
            assert status in TaskStatus


class TestImportanceLevel:
    """ImportanceLevel enum tests"""

    def test_levels_ordered(self):
        """Importance levels defined"""
        levels = [
            ImportanceLevel.CRITICAL,
            ImportanceLevel.HIGH,
            ImportanceLevel.MEDIUM,
            ImportanceLevel.LOW,
            ImportanceLevel.TRIVIAL,
        ]
        assert len(levels) == 5

    def test_level_values(self):
        """Level values are strings"""
        assert ImportanceLevel.CRITICAL.value == "critical"
        assert ImportanceLevel.TRIVIAL.value == "trivial"


class TestPatternCategory:
    """PatternCategory enum tests"""

    def test_security_categories(self):
        """Security-related categories exist"""
        assert PatternCategory.SECURITY.value == "security"
        assert PatternCategory.NULL_SAFETY.value == "null_safety"
        assert PatternCategory.ERROR_HANDLING.value == "error_handling"


class TestEmbeddingVector:
    """EmbeddingVector value object tests"""

    def test_create_vector(self):
        """Create embedding vector"""
        values = (0.1, 0.2, 0.3, 0.4, 0.5)
        vector = EmbeddingVector(values=values)
        assert vector.values == values
        assert len(vector.values) == 5

    def test_vector_immutable(self):
        """Vector is frozen (immutable)"""
        vector = EmbeddingVector(values=(1.0, 2.0, 3.0))
        with pytest.raises(AttributeError):
            vector.values = (4.0, 5.0, 6.0)  # type: ignore

    def test_empty_vector(self):
        """Empty vector creation"""
        vector = EmbeddingVector(values=())
        assert len(vector.values) == 0

    def test_high_dimension_vector(self):
        """High-dimensional vector (e.g., 768 for BERT)"""
        values = tuple([0.01 * i for i in range(768)])
        vector = EmbeddingVector(values=values)
        assert len(vector.values) == 768

    def test_vector_equality(self):
        """Vectors with same values are equal"""
        v1 = EmbeddingVector(values=(1.0, 2.0, 3.0))
        v2 = EmbeddingVector(values=(1.0, 2.0, 3.0))
        assert v1 == v2

    def test_vector_hash(self):
        """Vectors can be hashed (for use in sets/dicts)"""
        v1 = EmbeddingVector(values=(1.0, 2.0, 3.0))
        v2 = EmbeddingVector(values=(1.0, 2.0, 3.0))
        assert hash(v1) == hash(v2)
        assert len({v1, v2}) == 1  # Same hash, same set entry


class TestEdgeCases:
    """Edge case tests"""

    def test_negative_embedding_values(self):
        """Negative values in embeddings"""
        vector = EmbeddingVector(values=(-0.5, 0.0, 0.5))
        assert vector.values[0] < 0

    def test_very_small_values(self):
        """Very small floating point values"""
        vector = EmbeddingVector(values=(1e-10, 1e-15, 1e-20))
        assert all(v > 0 for v in vector.values)

    def test_enum_string_comparison(self):
        """Enum values can be compared to strings"""
        assert MemoryType.WORKING.value == "working"
        assert str(MemoryType.WORKING.value) == "working"
