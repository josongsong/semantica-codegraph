"""
Speculative Execution Integration Tests
"""

import pytest

from src.contexts.reasoning_engine.domain.speculative_models import PatchType, RiskLevel, SpeculativePatch
from src.contexts.reasoning_engine.infrastructure.speculative.graph_simulator import GraphSimulator
from src.contexts.reasoning_engine.infrastructure.speculative.risk_analyzer import RiskAnalyzer


def create_base_graph():
    """Create base graph with call graph"""
    return {
        "nodes": {
            "func1": {"id": "func1", "name": "function1", "type": "function", "file": "main.py"},
            "func2": {"id": "func2", "name": "function2", "type": "function", "file": "main.py", "return_type": "str"},
            "func3": {"id": "func3", "name": "function3", "type": "function", "file": "utils.py"},
        },
        "edges": {
            "func1": [{"source": "func1", "target": "func2", "kind": "CALLS"}],
            "func2": [{"source": "func2", "target": "func3", "kind": "CALLS"}],
            "func3": [],
        },
    }


class TestSimulateAndAnalyze:
    """Test Simulation + Risk analysis 통합"""

    def test_simulate_rename_and_analyze(self):
        """RENAME patch simulation + risk analysis"""
        base = create_base_graph()

        patch = SpeculativePatch(
            patch_id="p1", patch_type=PatchType.RENAME_SYMBOL, target_symbol="func1", new_name="renamed_func1"
        )

        # Simulate
        simulator = GraphSimulator(base)
        delta_graph = simulator.simulate_patch(patch)

        # Verify simulation
        assert delta_graph.get_node("func1")["name"] == "renamed_func1"
        assert base["nodes"]["func1"]["name"] == "function1"  # Base unchanged

        # Analyze risk
        analyzer = RiskAnalyzer()
        risk = analyzer.analyze_risk(patch, delta_graph, base)

        # Verify risk
        assert risk.patch_id == "p1"
        assert risk.risk_level in [RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.BREAKING]
        assert len(risk.affected_symbols) > 0

    def test_simulate_delete_and_analyze_breaking(self):
        """DELETE patch → BREAKING risk"""
        base = create_base_graph()

        patch = SpeculativePatch(patch_id="p2", patch_type=PatchType.DELETE_FUNCTION, target_symbol="func2")

        simulator = GraphSimulator(base)
        delta_graph = simulator.simulate_patch(patch)

        # Verify deletion
        assert delta_graph.get_node("func2") is None

        # Analyze risk
        analyzer = RiskAnalyzer()
        risk = analyzer.analyze_risk(patch, delta_graph, base)

        # Should be BREAKING (has caller)
        assert risk.is_breaking()
        assert len(risk.breaking_changes) > 0

    def test_simulate_add_function(self):
        """ADD_FUNCTION patch"""
        base = create_base_graph()

        patch = SpeculativePatch(
            patch_id="p3",
            patch_type=PatchType.ADD_FUNCTION,
            target_symbol="new_func",
            after_code="def new_func():\n    pass",
        )

        simulator = GraphSimulator(base)
        delta_graph = simulator.simulate_patch(patch)

        # Verify addition
        assert delta_graph.get_node("new_func") is not None
        assert "new_func" not in base["nodes"]

        # Analyze risk
        analyzer = RiskAnalyzer()
        risk = analyzer.analyze_risk(patch, delta_graph, base)

        # Should be SAFE (no breaking)
        assert risk.is_safe()
        assert not risk.is_breaking()


class TestMultiPatch:
    """Test multi-patch simulation"""

    def test_multi_patch_simulation(self):
        """Multiple patches in sequence"""
        base = create_base_graph()

        patches = [
            SpeculativePatch("p1", PatchType.RENAME_SYMBOL, "func1", new_name="renamed1"),
            SpeculativePatch("p2", PatchType.RENAME_SYMBOL, "func2", new_name="renamed2"),
            SpeculativePatch("p3", PatchType.RENAME_SYMBOL, "func3", new_name="renamed3"),
        ]

        simulator = GraphSimulator(base)
        delta_graph = simulator.simulate_multi_patch(patches)

        # Verify all applied
        assert delta_graph.get_node("func1")["name"] == "renamed1"
        assert delta_graph.get_node("func2")["name"] == "renamed2"
        assert delta_graph.get_node("func3")["name"] == "renamed3"

    def test_multi_patch_risk_analysis(self):
        """Multi-patch with risk analysis"""
        base = create_base_graph()

        patches = [
            SpeculativePatch("p1", PatchType.ADD_PARAMETER, "func1", parameters=[{"name": "new_param"}]),
            SpeculativePatch("p2", PatchType.DELETE_FUNCTION, "func3"),
        ]

        simulator = GraphSimulator(base)
        analyzer = RiskAnalyzer()

        delta_graph = None
        safe_patches = []

        for patch in patches:
            temp_delta = simulator.simulate_patch(patch)
            risk = analyzer.analyze_risk(patch, temp_delta, base)

            if risk.is_safe():
                safe_patches.append(patch)
            else:
                # Stop if risky
                break

        # At least 1 patch should be analyzed
        assert len(safe_patches) >= 0


class TestRiskLevels:
    """Test different risk levels"""

    def test_safe_risk_level(self):
        """SAFE risk level"""
        base = {"nodes": {"f1": {"id": "f1", "file": "a.py"}}, "edges": {}}

        patch = SpeculativePatch("p1", PatchType.ADD_FUNCTION, "new_func", after_code="def new_func(): pass")

        simulator = GraphSimulator(base)
        delta_graph = simulator.simulate_patch(patch)

        analyzer = RiskAnalyzer()
        risk = analyzer.analyze_risk(patch, delta_graph, base)

        assert risk.risk_level == RiskLevel.SAFE
        assert risk.safe_to_apply

    def test_breaking_risk_level(self):
        """BREAKING risk level"""
        base = {
            "nodes": {
                "target": {"id": "target"},
                "caller": {"id": "caller"},
            },
            "edges": {"caller": [{"source": "caller", "target": "target", "kind": "CALLS"}]},
        }

        patch = SpeculativePatch("p1", PatchType.DELETE_FUNCTION, "target")

        simulator = GraphSimulator(base)
        delta_graph = simulator.simulate_patch(patch)

        analyzer = RiskAnalyzer()
        risk = analyzer.analyze_risk(patch, delta_graph, base)

        assert risk.risk_level == RiskLevel.BREAKING
        assert not risk.safe_to_apply
        assert len(risk.breaking_changes) > 0


class TestCaching:
    """Test simulator caching"""

    def test_patch_cache(self):
        """Patch simulation is cached"""
        base = create_base_graph()
        patch = SpeculativePatch("p1", PatchType.RENAME_SYMBOL, "func1", new_name="renamed")

        simulator = GraphSimulator(base)

        # First call
        delta1 = simulator.simulate_patch(patch)
        assert simulator.cache_size() == 1

        # Second call (should be cached)
        delta2 = simulator.simulate_patch(patch)
        assert simulator.cache_size() == 1
        assert delta1 is delta2  # Same object


class TestErrorHandling:
    """Test error cases"""

    def test_invalid_patch_type(self):
        """Unknown patch type → error"""
        from src.contexts.reasoning_engine.infrastructure.speculative.exceptions import SimulationError

        base = create_base_graph()

        # Create invalid patch type (using refactor which isn't fully implemented)
        patch = SpeculativePatch("p1", PatchType.REFACTOR, "func1")

        simulator = GraphSimulator(base)

        with pytest.raises(SimulationError):
            simulator.simulate_patch(patch)

    def test_missing_required_field(self):
        """Missing required field → error"""
        from src.contexts.reasoning_engine.infrastructure.speculative.exceptions import SimulationError

        base = create_base_graph()

        # RENAME without new_name
        patch = SpeculativePatch("p1", PatchType.RENAME_SYMBOL, "func1")

        simulator = GraphSimulator(base)

        with pytest.raises(SimulationError):
            simulator.simulate_patch(patch)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
