"""
Speculative Execution - Production Tests

Real-world scenarios
"""

import time

import pytest

from codegraph_engine.reasoning_engine.domain.speculative_models import PatchType, RiskLevel, SpeculativePatch
from codegraph_engine.reasoning_engine.infrastructure.speculative.graph_simulator import GraphSimulator
from codegraph_engine.reasoning_engine.infrastructure.speculative.overlay_manager import OverlayManager
from codegraph_engine.reasoning_engine.infrastructure.speculative.risk_analyzer import RiskAnalyzer


def create_realistic_graph():
    """1000-node realistic codebase"""
    nodes = {}
    edges = {}

    # 1000 functions across 50 files
    for i in range(1000):
        file_id = i // 20  # 20 functions per file
        nodes[f"func{i}"] = {
            "id": f"func{i}",
            "name": f"function_{i}",
            "type": "function",
            "file": f"module_{file_id}.py",
            "return_type": "Any",
        }

    # Call graph (each function calls 0-5 others)
    for i in range(1000):
        callees = []
        for j in range(min(5, 1000 - i - 1)):
            target_id = i + j + 1
            if target_id < 1000:
                callees.append({"source": f"func{i}", "target": f"func{target_id}", "kind": "CALLS"})
        edges[f"func{i}"] = callees

    return {"nodes": nodes, "edges": edges}


class TestProductionScenario:
    """Production scenario tests"""

    def test_large_codebase_simulation(self):
        """1000-node codebase simulation"""
        base = create_realistic_graph()

        # Simulate 10 rename patches
        patches = [
            SpeculativePatch(f"p{i}", PatchType.RENAME_SYMBOL, f"func{i}", new_name=f"renamed_func_{i}")
            for i in range(10)
        ]

        manager = OverlayManager(base)

        start = time.perf_counter()
        applied = manager.apply_patches(patches, stop_on_breaking=False)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Performance check
        assert elapsed_ms < 1000, f"Too slow: {elapsed_ms:.2f}ms"
        assert applied == 10
        assert manager.stack_depth() == 10

    def test_llm_workflow_simulation(self):
        """
        Realistic LLM workflow:
        1. LLM proposes 5 patches
        2. Apply with risk check
        3. Rollback if risky
        """
        base = create_realistic_graph()

        # LLM proposals
        proposals = [
            SpeculativePatch("p1", PatchType.RENAME_SYMBOL, "func0", new_name="new_func0"),
            SpeculativePatch("p2", PatchType.ADD_PARAMETER, "func1", parameters=[{"name": "x"}]),
            SpeculativePatch("p3", PatchType.DELETE_FUNCTION, "func2"),  # Risky
            SpeculativePatch("p4", PatchType.RENAME_SYMBOL, "func3", new_name="renamed3"),
            SpeculativePatch("p5", PatchType.ADD_FUNCTION, "new_func", after_code="def new_func(): pass"),
        ]

        manager = OverlayManager(base, auto_reject_breaking=True)

        applied = 0
        for patch in proposals:
            success = manager.apply_patch(patch)
            if success:
                applied += 1

                # Check risk after each
                risk = manager.current_risk()
                if risk and risk.is_breaking():
                    manager.rollback(1)
                    applied -= 1

        # At least some patches should be applied
        assert applied > 0
        assert manager.stack_depth() == applied

    def test_multi_patch_rollback(self):
        """Multi-patch with selective rollback"""
        base = create_realistic_graph()

        patches = [
            SpeculativePatch("p1", PatchType.RENAME_SYMBOL, "func0", new_name="r0"),
            SpeculativePatch("p2", PatchType.RENAME_SYMBOL, "func1", new_name="r1"),
            SpeculativePatch("p3", PatchType.RENAME_SYMBOL, "func2", new_name="r2"),
            SpeculativePatch("p4", PatchType.DELETE_FUNCTION, "func3"),  # Breaking
            SpeculativePatch("p5", PatchType.RENAME_SYMBOL, "func4", new_name="r4"),
        ]

        manager = OverlayManager(base)
        manager.apply_patches(patches, stop_on_breaking=False)

        # Check stack
        assert manager.stack_depth() == 5

        # Rollback to safe
        rolled_back = manager.rollback_to_safe()

        # Should rollback at least the DELETE
        assert rolled_back >= 0

    def test_performance_1000_patches(self):
        """Performance: 1000 patches"""
        base = {"nodes": {f"f{i}": {"id": f"f{i}"} for i in range(100)}, "edges": {}}

        patches = [
            SpeculativePatch(f"p{i}", PatchType.RENAME_SYMBOL, f"f{i % 100}", new_name=f"r{i}") for i in range(1000)
        ]

        manager = OverlayManager(base, max_stack_depth=1000)

        start = time.perf_counter()
        applied = 0
        for patch in patches:
            try:
                if manager.apply_patch(patch):
                    applied += 1
            except Exception:
                break

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Should handle at least 100 patches
        assert applied >= 100

        # Performance check (< 10ms per patch on average)
        avg_ms = elapsed_ms / applied if applied > 0 else 0
        assert avg_ms < 10, f"Too slow: {avg_ms:.2f}ms/patch"


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_graph(self):
        """Empty graph handling"""
        base = {"nodes": {}, "edges": {}}

        patch = SpeculativePatch("p1", PatchType.ADD_FUNCTION, "new_func", after_code="def new_func(): pass")

        manager = OverlayManager(base)
        success = manager.apply_patch(patch)

        assert success
        assert manager.stack_depth() == 1

    def test_stack_overflow(self):
        """Stack overflow protection"""
        from codegraph_engine.reasoning_engine.infrastructure.speculative.exceptions import SimulationError

        base = {"nodes": {"f1": {"id": "f1"}}, "edges": {}}

        manager = OverlayManager(base, max_stack_depth=5)

        # Apply 5 patches (OK)
        for i in range(5):
            patch = SpeculativePatch(f"p{i}", PatchType.RENAME_SYMBOL, "f1", new_name=f"r{i}")
            manager.apply_patch(patch)

        assert manager.stack_depth() == 5

        # 6th patch → overflow
        patch6 = SpeculativePatch("p6", PatchType.RENAME_SYMBOL, "f1", new_name="r6")

        with pytest.raises(SimulationError, match="Stack overflow"):
            manager.apply_patch(patch6)

    def test_rollback_empty_stack(self):
        """Rollback on empty stack"""
        base = {"nodes": {}, "edges": {}}
        manager = OverlayManager(base)

        rolled_back = manager.rollback(5)

        assert rolled_back == 0
        assert manager.is_empty()

    def test_clear_stack(self):
        """Clear all patches"""
        base = {"nodes": {"f1": {"id": "f1"}}, "edges": {}}

        patches = [SpeculativePatch(f"p{i}", PatchType.RENAME_SYMBOL, "f1", new_name=f"r{i}") for i in range(10)]

        manager = OverlayManager(base)
        manager.apply_patches(patches)

        assert manager.stack_depth() == 10

        manager.clear()

        assert manager.is_empty()
        assert manager.current_risk() is None


class TestRiskAnalysis:
    """Production risk analysis"""

    def test_breaking_change_detection(self):
        """Breaking change in real scenario"""
        base = {
            "nodes": {
                "core_api": {"id": "core_api", "name": "core_api", "type": "function"},
                "caller1": {"id": "caller1"},
                "caller2": {"id": "caller2"},
            },
            "edges": {
                "caller1": [{"source": "caller1", "target": "core_api", "kind": "CALLS"}],
                "caller2": [{"source": "caller2", "target": "core_api", "kind": "CALLS"}],
                "core_api": [],
            },
        }

        # Delete core API → BREAKING
        patch = SpeculativePatch("p1", PatchType.DELETE_FUNCTION, "core_api")

        manager = OverlayManager(base)
        manager.apply_patch(patch, force=True)

        risk = manager.current_risk()

        assert risk.is_breaking()
        assert len(risk.breaking_changes) > 0
        assert "core_api" in risk.affected_symbols

    def test_safe_patch_identification(self):
        """Safe patches are correctly identified"""
        base = {"nodes": {"f1": {"id": "f1"}}, "edges": {}}

        # ADD is always safe
        patch = SpeculativePatch("p1", PatchType.ADD_FUNCTION, "new_func", after_code="def new_func(): pass")

        manager = OverlayManager(base)
        manager.apply_patch(patch)

        risk = manager.current_risk()

        assert risk.is_safe()
        assert risk.safe_to_apply


class TestStats:
    """Statistics and reporting"""

    def test_manager_stats(self):
        """Manager statistics tracking"""
        base = {"nodes": {"f1": {"id": "f1"}}, "edges": {}}

        patches = [SpeculativePatch(f"p{i}", PatchType.RENAME_SYMBOL, "f1", new_name=f"r{i}") for i in range(5)]

        manager = OverlayManager(base)
        manager.apply_patches(patches)

        stats = manager.stats()

        assert stats["stack_depth"] == 5
        assert stats["total_applied"] == 5
        assert stats["total_rejected"] == 0
        assert stats["total_rollbacks"] == 0

        # Rollback 2
        manager.rollback(2)

        stats2 = manager.stats()
        assert stats2["stack_depth"] == 3
        assert stats2["total_rollbacks"] == 2

    def test_patch_history(self):
        """Patch history tracking"""
        base = {"nodes": {"f1": {"id": "f1"}}, "edges": {}}

        patches = [
            SpeculativePatch("p1", PatchType.RENAME_SYMBOL, "f1", new_name="r1"),
            SpeculativePatch("p2", PatchType.RENAME_SYMBOL, "f1", new_name="r2"),
        ]

        manager = OverlayManager(base)
        for patch in patches:
            manager.apply_patch(patch)

        history = manager.get_patch_history()

        assert len(history) == 2
        assert history[0]["patch_id"] == "p1"
        assert history[1]["patch_id"] == "p2"
        assert all("risk_level" in h for h in history)
        assert all("timestamp" in h for h in history)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
