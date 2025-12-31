"""
QueryPlan Domain Model Tests

RFC-052: MCP Service Layer Architecture
Tests for QueryPlan IR canonical form.

Test Coverage:
- Happy path: Basic plan creation
- Immutability: Frozen dataclass
- Hashability: Stable hashing
- Validation: Invalid plans
- Factory methods: Convenience functions
- Serialization: to_dict/from_dict
"""

import pytest

from codegraph_engine.code_foundation.domain.query.query_plan import (
    Budget,
    PlanKind,
    QueryPattern,
    QueryPlan,
    SliceDirection,
    dataflow_plan,
    slice_plan,
    taint_proof_plan,
)


class TestQueryPattern:
    """QueryPattern tests"""

    def test_create_pattern(self):
        """Happy path: Create pattern"""
        pattern = QueryPattern(pattern="request.GET", pattern_type="symbol")

        assert pattern.pattern == "request.GET"
        assert pattern.pattern_type == "symbol"
        assert pattern.scope is None

    def test_pattern_with_scope(self):
        """Create pattern with scope"""
        pattern = QueryPattern(
            pattern="func",
            pattern_type="symbol",
            scope="module.py",
        )

        assert pattern.scope == "module.py"

    def test_pattern_hashable(self):
        """Patterns are hashable"""
        p1 = QueryPattern("func", "symbol")
        p2 = QueryPattern("func", "symbol")
        p3 = QueryPattern("other", "symbol")

        assert hash(p1) == hash(p2)
        assert hash(p1) != hash(p3)

        # Can use in set
        patterns = {p1, p2, p3}
        assert len(patterns) == 2


class TestBudget:
    """Budget tests"""

    def test_default_budget(self):
        """Happy path: Default budget"""
        budget = Budget.default()

        assert budget.max_nodes == 1000
        assert budget.max_edges == 5000
        assert budget.max_paths == 100
        assert budget.max_depth == 10
        assert budget.timeout_ms == 30000

    def test_light_budget(self):
        """Light budget for quick queries"""
        budget = Budget.light()

        assert budget.max_nodes == 100
        assert budget.max_depth == 5
        assert budget.timeout_ms == 5000

    def test_heavy_budget(self):
        """Heavy budget for deep analysis"""
        budget = Budget.heavy()

        assert budget.max_nodes == 10000
        assert budget.max_depth == 20
        assert budget.timeout_ms == 120000

    def test_budget_hashable(self):
        """Budgets are hashable"""
        b1 = Budget(max_nodes=100, max_edges=200, max_paths=50, max_depth=5, timeout_ms=1000)
        b2 = Budget(max_nodes=100, max_edges=200, max_paths=50, max_depth=5, timeout_ms=1000)

        assert hash(b1) == hash(b2)


class TestQueryPlan:
    """QueryPlan tests"""

    def test_create_slice_plan(self):
        """Happy path: Create slice plan"""
        plan = QueryPlan(
            kind=PlanKind.SLICE,
            patterns=(QueryPattern("main", "symbol"),),
            slice_direction=SliceDirection.BACKWARD,
        )

        assert plan.kind == PlanKind.SLICE
        assert len(plan.patterns) == 1
        assert plan.slice_direction == SliceDirection.BACKWARD

    def test_create_dataflow_plan(self):
        """Happy path: Create dataflow plan"""
        plan = QueryPlan(
            kind=PlanKind.DATAFLOW,
            patterns=(
                QueryPattern("source", "symbol"),
                QueryPattern("sink", "symbol"),
            ),
            edge_types=("DFG",),
        )

        assert plan.kind == PlanKind.DATAFLOW
        assert len(plan.patterns) == 2
        assert plan.edge_types == ("DFG",)

    def test_plan_immutable(self):
        """QueryPlan is immutable (frozen)"""
        plan = slice_plan("main")

        with pytest.raises(Exception):  # FrozenInstanceError
            plan.kind = PlanKind.DATAFLOW

    def test_plan_compute_hash(self):
        """QueryPlan hash is stable"""
        plan1 = slice_plan("main", SliceDirection.BACKWARD)
        plan2 = slice_plan("main", SliceDirection.BACKWARD)
        plan3 = slice_plan("main", SliceDirection.FORWARD)

        hash1 = plan1.compute_hash()
        hash2 = plan2.compute_hash()
        hash3 = plan3.compute_hash()

        # Same plan → same hash
        assert hash1 == hash2

        # Different plan → different hash
        assert hash1 != hash3

        # Hash is stable (16 chars)
        assert len(hash1) == 16

    def test_plan_with_budget(self):
        """Create plan with custom budget"""
        plan = slice_plan("main").with_budget(Budget.light())

        assert plan.budget.max_nodes == 100

    def test_plan_serialization(self):
        """Plan to_dict/from_dict roundtrip"""
        original = dataflow_plan("source", "sink", Budget.default())

        data = original.to_dict()
        restored = QueryPlan.from_dict(data)

        assert restored.kind == original.kind
        assert len(restored.patterns) == len(original.patterns)
        assert restored.budget.max_nodes == original.budget.max_nodes
        assert restored.compute_hash() == original.compute_hash()

    def test_plan_validation_no_patterns(self):
        """Validation: No patterns"""
        with pytest.raises(ValueError, match="at least one pattern"):
            QueryPlan(
                kind=PlanKind.SLICE,
                patterns=(),
            )

    def test_factory_slice_plan(self):
        """Factory: slice_plan()"""
        plan = slice_plan("main", SliceDirection.BACKWARD, Budget.light(), "test.py")

        assert plan.kind == PlanKind.SLICE
        assert plan.patterns[0].pattern == "main"
        assert plan.slice_direction == SliceDirection.BACKWARD
        assert plan.budget.max_nodes == 100
        assert plan.file_scope == "test.py"

    def test_factory_dataflow_plan(self):
        """Factory: dataflow_plan()"""
        plan = dataflow_plan("source", "sink", Budget.default(), "test.py")

        assert plan.kind == PlanKind.DATAFLOW
        assert len(plan.patterns) == 2
        assert plan.edge_types == ("DFG",)

    def test_factory_taint_proof_plan(self):
        """Factory: taint_proof_plan()"""
        plan = taint_proof_plan("source", "sink", "sql_injection")

        assert plan.kind == PlanKind.TAINT_PROOF
        assert plan.policy_id == "sql_injection"
        assert plan.edge_types == ("DFG",)

    def test_plan_post_init_default_direction(self):
        """Post-init sets default slice direction"""
        plan = QueryPlan(
            kind=PlanKind.SLICE,
            patterns=(QueryPattern("main"),),
            # slice_direction not set
        )

        # Should default to BACKWARD
        assert plan.slice_direction == SliceDirection.BACKWARD


# ============================================================
# Edge Cases
# ============================================================


class TestQueryPlanEdgeCases:
    """Edge cases and corner cases"""

    def test_empty_pattern_string(self):
        """Edge: Empty pattern string"""
        # Allowed (validation is UseCase responsibility)
        pattern = QueryPattern("")
        assert pattern.pattern == ""

    def test_very_long_pattern(self):
        """Edge: Very long pattern"""
        long_pattern = "Module." * 1000 + "func"
        pattern = QueryPattern(long_pattern)

        assert len(pattern.pattern) > 5000

    def test_budget_zero_values(self):
        """Edge: Budget with zero values"""
        # Allowed at Domain level (validation at Infrastructure)
        budget = Budget(max_nodes=0, max_edges=0, max_paths=0, max_depth=0, timeout_ms=0)

        assert budget.max_nodes == 0

    def test_budget_negative_values(self):
        """Edge: Budget with negative values"""
        # Allowed at Domain level (validation at Infrastructure)
        budget = Budget(max_nodes=-1, max_edges=-1, max_paths=-1, max_depth=-1, timeout_ms=-1)

        assert budget.max_nodes == -1

    def test_plan_hash_collision_resistant(self):
        """Edge: Hash collision resistance"""
        # Different plans should have different hashes
        plans = [slice_plan(f"func{i}") for i in range(100)]

        hashes = [p.compute_hash() for p in plans]

        # All unique (no collisions in small sample)
        assert len(set(hashes)) == 100

    def test_plan_metadata(self):
        """Edge: Plan with metadata"""
        plan = slice_plan("main")
        plan_with_meta = QueryPlan(
            kind=plan.kind,
            patterns=plan.patterns,
            metadata={"custom_key": "custom_value"},
        )

        assert plan_with_meta.metadata["custom_key"] == "custom_value"


# ============================================================
# Performance Tests
# ============================================================


class TestQueryPlanPerformance:
    """Performance tests"""

    def test_hash_performance(self):
        """Performance: Hashing is fast"""
        import time

        plan = dataflow_plan("source", "sink")

        start = time.time()
        for _ in range(1000):
            plan.compute_hash()
        elapsed = time.time() - start

        # Should be < 100ms for 1000 hashes
        assert elapsed < 0.1

    def test_serialization_performance(self):
        """Performance: Serialization is fast"""
        import time

        plan = dataflow_plan("source", "sink")

        start = time.time()
        for _ in range(1000):
            data = plan.to_dict()
            QueryPlan.from_dict(data)
        elapsed = time.time() - start

        # Should be < 500ms for 1000 roundtrips
        assert elapsed < 0.5
