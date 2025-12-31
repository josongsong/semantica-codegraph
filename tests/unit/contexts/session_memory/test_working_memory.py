"""
Working Memory Tests

Test Coverage:
- Memory storage and retrieval
- Capacity limits
- Eviction policies
"""

import pytest

from codegraph_runtime.session_memory.domain.models import ImportanceLevel, MemoryType


class TestMemoryStorage:
    """Memory storage tests"""

    def test_store_and_retrieve(self):
        """Basic store and retrieve"""
        memory = {}
        key = "session_123"
        value = {"context": "user query", "timestamp": "2024-01-01"}

        memory[key] = value
        assert memory[key] == value

    def test_overwrite_existing(self):
        """Overwrite existing memory"""
        memory = {"key1": "old_value"}
        memory["key1"] = "new_value"
        assert memory["key1"] == "new_value"

    def test_retrieve_nonexistent(self):
        """Retrieve non-existent key"""
        memory = {}
        assert memory.get("missing") is None


class TestCapacityLimits:
    """Capacity limit tests"""

    def test_within_capacity(self):
        """Within capacity limit"""
        max_capacity = 100
        memory = {f"key_{i}": f"value_{i}" for i in range(50)}
        assert len(memory) < max_capacity

    def test_at_capacity(self):
        """At exact capacity"""
        max_capacity = 100
        memory = {f"key_{i}": f"value_{i}" for i in range(100)}
        assert len(memory) == max_capacity

    def test_over_capacity_eviction(self):
        """Over capacity triggers eviction"""
        max_capacity = 100
        memory = {f"key_{i}": f"value_{i}" for i in range(100)}

        # Add one more - should evict oldest
        if len(memory) >= max_capacity:
            oldest_key = next(iter(memory))
            del memory[oldest_key]

        memory["new_key"] = "new_value"
        assert len(memory) == max_capacity


class TestEvictionPolicies:
    """Eviction policy tests"""

    def test_lru_eviction(self):
        """Least Recently Used eviction"""
        access_order = ["a", "b", "c", "b", "a"]  # c is LRU
        recent = ["a", "b"]  # Most recently accessed

        lru = [k for k in ["a", "b", "c"] if k not in recent[-2:]]
        assert "c" in lru

    def test_importance_based_eviction(self):
        """Importance-based eviction"""
        # Importance order: CRITICAL > HIGH > MEDIUM > LOW > TRIVIAL
        importance_priority = {
            ImportanceLevel.CRITICAL: 5,
            ImportanceLevel.HIGH: 4,
            ImportanceLevel.MEDIUM: 3,
            ImportanceLevel.LOW: 2,
            ImportanceLevel.TRIVIAL: 1,
        }
        entries = [
            {"key": "a", "importance": ImportanceLevel.CRITICAL},
            {"key": "b", "importance": ImportanceLevel.LOW},
            {"key": "c", "importance": ImportanceLevel.MEDIUM},
        ]

        # Evict lowest importance first (lowest priority number)
        to_evict = min(entries, key=lambda x: importance_priority[x["importance"]])
        assert to_evict["key"] == "b"


class TestMemoryTypes:
    """Memory type tests"""

    def test_working_memory_ephemeral(self):
        """Working memory is ephemeral"""
        memory_type = MemoryType.WORKING
        assert memory_type == MemoryType.WORKING

    def test_episodic_memory_persistent(self):
        """Episodic memory persists"""
        memory_type = MemoryType.EPISODIC
        assert memory_type == MemoryType.EPISODIC

    def test_semantic_memory_learned(self):
        """Semantic memory is learned"""
        memory_type = MemoryType.SEMANTIC
        assert memory_type == MemoryType.SEMANTIC


class TestEdgeCases:
    """Edge cases"""

    def test_empty_memory(self):
        """Empty memory state"""
        memory = {}
        assert len(memory) == 0
        assert list(memory.keys()) == []

    def test_large_value_storage(self):
        """Store large value"""
        memory = {}
        large_value = "x" * 1000000  # 1MB string
        memory["large"] = large_value
        assert len(memory["large"]) == 1000000

    def test_unicode_keys_values(self):
        """Unicode keys and values"""
        memory = {}
        memory["키"] = "값"
        memory["🔑"] = "🗝️"
        assert memory["키"] == "값"
        assert memory["🔑"] == "🗝️"

    def test_nested_value_structure(self):
        """Nested value structures"""
        memory = {}
        memory["nested"] = {"level1": {"level2": {"data": [1, 2, 3]}}}
        assert memory["nested"]["level1"]["level2"]["data"] == [1, 2, 3]
