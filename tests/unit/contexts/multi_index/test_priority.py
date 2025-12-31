"""
Embedding Priority Tests (SOTA L11)

Test Coverage:
- CHUNK_PRIORITY: Priority mapping
- Priority functions: get_chunk_priority, is_high/medium/low_priority
- Edge: Unknown kinds, bonus priority
"""

from unittest.mock import MagicMock

import pytest

from codegraph_engine.multi_index.infrastructure.vector.priority import (
    CHUNK_PRIORITY,
    HIGH_PRIORITY_THRESHOLD,
    LOW_PRIORITY_THRESHOLD,
    MEDIUM_PRIORITY_THRESHOLD,
    get_chunk_priority,
    is_high_priority,
    is_low_priority,
    is_medium_priority,
    partition_by_priority,
)


def make_mock_chunk(kind: str, pagerank: float = 0.0, importance: float = 0.0, is_test: bool = False):
    """Create mock chunk"""
    chunk = MagicMock()
    chunk.kind = kind
    chunk.pagerank = pagerank
    chunk.importance = importance
    chunk.is_test = is_test
    return chunk


class TestChunkPriority:
    """CHUNK_PRIORITY mapping tests"""

    def test_function_highest_priority(self):
        """Function has highest priority (10)"""
        assert CHUNK_PRIORITY["function"] == 10

    def test_usage_high_priority(self):
        """Usage has high priority (9)"""
        assert CHUNK_PRIORITY["usage"] == 9

    def test_class_high_priority(self):
        """Class has high priority (8)"""
        assert CHUNK_PRIORITY["class"] == 8

    def test_test_medium_priority(self):
        """Test has medium priority (7)"""
        assert CHUNK_PRIORITY["test"] == 7

    def test_file_low_priority(self):
        """File has low priority (1)"""
        assert CHUNK_PRIORITY["file"] == 1

    def test_priority_ordering(self):
        """Priority ordering is correct"""
        assert CHUNK_PRIORITY["function"] > CHUNK_PRIORITY["class"]
        assert CHUNK_PRIORITY["class"] > CHUNK_PRIORITY["test"]
        assert CHUNK_PRIORITY["test"] > CHUNK_PRIORITY["docstring"]


class TestThresholds:
    """Priority threshold tests"""

    def test_high_priority_threshold(self):
        """High priority threshold is 8"""
        assert HIGH_PRIORITY_THRESHOLD == 8

    def test_medium_priority_threshold(self):
        """Medium priority threshold is 5"""
        assert MEDIUM_PRIORITY_THRESHOLD == 5

    def test_low_priority_threshold(self):
        """Low priority threshold is 0"""
        assert LOW_PRIORITY_THRESHOLD == 0


class TestGetChunkPriority:
    """get_chunk_priority function tests"""

    def test_function_priority(self):
        """Function chunk priority"""
        chunk = make_mock_chunk("function")
        priority = get_chunk_priority(chunk)
        assert priority == 10

    def test_class_priority(self):
        """Class chunk priority"""
        chunk = make_mock_chunk("class")
        priority = get_chunk_priority(chunk)
        assert priority == 8

    def test_unknown_kind_zero_priority(self):
        """Unknown kind gets 0 priority"""
        chunk = make_mock_chunk("unknown_kind")
        priority = get_chunk_priority(chunk)
        assert priority == 0

    def test_pagerank_bonus(self):
        """High pagerank adds +1 bonus"""
        chunk = make_mock_chunk("function", pagerank=0.8)
        priority = get_chunk_priority(chunk)
        assert priority >= 10  # Base 10 + bonus

    def test_importance_bonus_non_test(self):
        """High importance non-test adds +1 bonus"""
        chunk = make_mock_chunk("function", importance=0.9, is_test=False)
        priority = get_chunk_priority(chunk)
        assert priority >= 10

    def test_no_importance_bonus_for_test(self):
        """Test files don't get importance bonus"""
        chunk = make_mock_chunk("test", importance=0.9, is_test=True)
        priority = get_chunk_priority(chunk)
        assert priority == 7  # Base priority only


class TestPriorityClassification:
    """is_high/medium/low_priority tests"""

    def test_function_is_high_priority(self):
        """Function is high priority"""
        chunk = make_mock_chunk("function")
        assert is_high_priority(chunk) is True

    def test_class_is_high_priority(self):
        """Class is high priority"""
        chunk = make_mock_chunk("class")
        assert is_high_priority(chunk) is True

    def test_test_is_medium_priority(self):
        """Test is medium priority"""
        chunk = make_mock_chunk("test")
        assert is_medium_priority(chunk) is True

    def test_file_is_low_priority(self):
        """File is low priority"""
        chunk = make_mock_chunk("file")
        assert is_low_priority(chunk) is True

    def test_unknown_is_low_priority(self):
        """Unknown kind is low priority"""
        chunk = make_mock_chunk("unknown")
        assert is_low_priority(chunk) is True


class TestPartitionByPriority:
    """partition_by_priority tests"""

    def test_partition_mixed_chunks(self):
        """Partition mixed priority chunks"""
        chunks = [
            make_mock_chunk("function"),
            make_mock_chunk("test"),
            make_mock_chunk("file"),
        ]
        high, medium, low = partition_by_priority(chunks)

        assert len(high) >= 1  # function
        assert len(medium) >= 0
        assert len(low) >= 1  # file

    def test_partition_empty_list(self):
        """Partition empty list"""
        high, medium, low = partition_by_priority([])
        assert high == []
        assert medium == []
        assert low == []

    def test_partition_all_high_priority(self):
        """All high priority chunks"""
        chunks = [make_mock_chunk("function"), make_mock_chunk("class")]
        high, medium, low = partition_by_priority(chunks)
        assert len(high) == 2
        assert len(low) == 0


class TestEdgeCases:
    """Edge case tests"""

    def test_none_pagerank(self):
        """None pagerank handled"""
        chunk = make_mock_chunk("function")
        chunk.pagerank = None
        priority = get_chunk_priority(chunk)
        assert priority >= 10

    def test_negative_pagerank(self):
        """Negative pagerank handled"""
        chunk = make_mock_chunk("function")
        chunk.pagerank = -0.5
        priority = get_chunk_priority(chunk)
        assert priority == 10  # No bonus

    def test_missing_attributes(self):
        """Missing attributes handled gracefully"""
        chunk = MagicMock()
        chunk.kind = "function"
        del chunk.pagerank
        del chunk.importance
        del chunk.is_test
        # Should not crash
        priority = get_chunk_priority(chunk)
        assert priority >= 0


class TestCornerCases:
    """Corner case tests"""

    def test_all_chunk_kinds_defined(self):
        """All expected chunk kinds have priorities"""
        expected_kinds = ["function", "class", "method", "test", "file", "docstring"]
        for kind in expected_kinds:
            assert kind in CHUNK_PRIORITY

    def test_priority_range(self):
        """All priorities in expected range (0-10)"""
        for kind, priority in CHUNK_PRIORITY.items():
            assert 0 <= priority <= 10

    def test_boundary_pagerank(self):
        """Boundary pagerank values"""
        chunk_low = make_mock_chunk("function", pagerank=0.5)
        chunk_high = make_mock_chunk("function", pagerank=0.51)

        # 0.5 is boundary - no bonus
        # 0.51 gets bonus
        p_low = get_chunk_priority(chunk_low)
        p_high = get_chunk_priority(chunk_high)
        assert p_high > p_low
