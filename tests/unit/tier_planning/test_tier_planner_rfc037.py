"""
RFC-037 Phase 1: TierPlanner Tests

Tests for automatic tier selection based on agent intent and query type.

Test Categories:
1. Query-driven tier selection (15 tests)
2. Intent-driven tier selection (12 tests)
3. Priority rules (5 tests)
4. Edge cases (8 tests)
5. Observability (3 tests)
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.build_config import SemanticTier
from codegraph_engine.code_foundation.infrastructure.tier_planning import (
    AgentIntent,
    QueryType,
    Scope,
    TierPlanner,
)


# ============================================================
# Test 1: Query-Driven Tier Selection
# ============================================================


class TestQueryDrivenTierSelection:
    """Test tier selection based on query type."""

    def test_slice_query_requires_full(self):
        """SLICE query → FULL tier (PDG needed)."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.SLICE)

        assert result.tier == SemanticTier.FULL
        assert "SSA/PDG" in result.reason

    def test_path_sensitive_requires_full(self):
        """PATH_SENSITIVE query → FULL tier."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.PATH_SENSITIVE)

        assert result.tier == SemanticTier.FULL

    def test_reaching_defs_requires_full(self):
        """REACHING_DEFS query → FULL tier."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.REACHING_DEFS)

        assert result.tier == SemanticTier.FULL

    def test_dominance_requires_full(self):
        """DOMINANCE query → FULL tier."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.DOMINANCE)

        assert result.tier == SemanticTier.FULL

    def test_flow_query_requires_extended(self):
        """FLOW query → EXTENDED tier (DFG needed)."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.FLOW)

        assert result.tier == SemanticTier.EXTENDED
        assert "DFG" in result.reason
        assert result.options.get("dfg_threshold") == 500

    def test_dependencies_requires_extended(self):
        """DEPENDENCIES query → EXTENDED tier."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.DEPENDENCIES)

        assert result.tier == SemanticTier.EXTENDED

    def test_side_effects_requires_extended(self):
        """SIDE_EFFECTS query → EXTENDED tier."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.SIDE_EFFECTS)

        assert result.tier == SemanticTier.EXTENDED

    def test_value_origin_requires_extended(self):
        """VALUE_ORIGIN query → EXTENDED tier."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.VALUE_ORIGIN)

        assert result.tier == SemanticTier.EXTENDED

    def test_callers_query_uses_base(self):
        """CALLERS query → BASE tier (Call Graph)."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.CALLERS)

        assert result.tier == SemanticTier.BASE
        assert "Call Graph" in result.reason

    def test_callees_query_uses_base(self):
        """CALLEES query → BASE tier."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.CALLEES)

        assert result.tier == SemanticTier.BASE

    def test_references_query_uses_base(self):
        """REFERENCES query → BASE tier."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.REFERENCES)

        assert result.tier == SemanticTier.BASE

    def test_definitions_query_uses_base(self):
        """DEFINITIONS query → BASE tier."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.DEFINITIONS)

        assert result.tier == SemanticTier.BASE

    def test_unknown_query_returns_none_from_query(self):
        """UNKNOWN query type → Falls back to intent."""
        planner = TierPlanner()
        result = planner.plan(
            query_type=QueryType.UNKNOWN,
            intent=AgentIntent.RENAME,
        )

        # Should use intent (RENAME → BASE)
        assert result.tier == SemanticTier.BASE


# ============================================================
# Test 2: Intent-Driven Tier Selection
# ============================================================


class TestIntentDrivenTierSelection:
    """Test tier selection based on agent intent."""

    def test_slice_intent_requires_full(self):
        """SLICE intent → FULL tier."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.SLICE)

        assert result.tier == SemanticTier.FULL

    def test_taint_intent_requires_full(self):
        """TAINT intent → FULL tier."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.TAINT)

        assert result.tier == SemanticTier.FULL

    def test_path_analysis_intent_requires_full(self):
        """PATH_ANALYSIS intent → FULL tier."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.PATH_ANALYSIS)

        assert result.tier == SemanticTier.FULL

    def test_null_check_intent_requires_full(self):
        """NULL_CHECK intent → FULL tier."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.NULL_CHECK)

        assert result.tier == SemanticTier.FULL

    def test_extract_method_requires_extended(self):
        """EXTRACT_METHOD intent → EXTENDED tier."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.EXTRACT_METHOD)

        assert result.tier == SemanticTier.EXTENDED
        assert result.options.get("dfg_threshold") == 500

    def test_inline_requires_extended(self):
        """INLINE intent → EXTENDED tier."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.INLINE)

        assert result.tier == SemanticTier.EXTENDED

    def test_add_parameter_requires_extended(self):
        """ADD_PARAMETER intent → EXTENDED tier."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.ADD_PARAMETER)

        assert result.tier == SemanticTier.EXTENDED

    def test_move_requires_extended(self):
        """MOVE intent → EXTENDED tier."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.MOVE)

        assert result.tier == SemanticTier.EXTENDED

    def test_understand_uses_base(self):
        """UNDERSTAND intent → BASE tier."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.UNDERSTAND)

        assert result.tier == SemanticTier.BASE

    def test_find_callers_uses_base(self):
        """FIND_CALLERS intent → BASE tier."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.FIND_CALLERS)

        assert result.tier == SemanticTier.BASE

    def test_find_references_uses_base(self):
        """FIND_REFERENCES intent → BASE tier."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.FIND_REFERENCES)

        assert result.tier == SemanticTier.BASE

    def test_rename_uses_base(self):
        """RENAME intent → BASE tier (simple rename)."""
        planner = TierPlanner()
        result = planner.plan(intent=AgentIntent.RENAME)

        assert result.tier == SemanticTier.BASE


# ============================================================
# Test 3: Priority Rules
# ============================================================


class TestPriorityRules:
    """Test priority rules (QueryType > Intent > Scope)."""

    def test_query_overrides_intent(self):
        """QueryType has higher priority than Intent."""
        planner = TierPlanner()

        # Intent says BASE, but Query says FULL
        result = planner.plan(
            intent=AgentIntent.RENAME,  # BASE
            query_type=QueryType.SLICE,  # FULL
        )

        # Query wins
        assert result.tier == SemanticTier.FULL

    def test_intent_overrides_scope(self):
        """Intent has higher priority than Scope."""
        planner = TierPlanner()

        # Scope says EXTENDED, but Intent says BASE
        result = planner.plan(
            intent=AgentIntent.UNDERSTAND,  # BASE
            scope=Scope.REPO,  # Would suggest EXTENDED
        )

        # Intent wins
        assert result.tier == SemanticTier.BASE

    def test_scope_used_when_no_intent_query(self):
        """Scope is used when no intent/query specified."""
        planner = TierPlanner()

        # Only scope provided
        result = planner.plan(scope=Scope.REPO)

        # Large scope → EXTENDED
        assert result.tier == SemanticTier.EXTENDED

    def test_query_and_intent_both_full(self):
        """Both query and intent require FULL → FULL."""
        planner = TierPlanner()

        result = planner.plan(
            intent=AgentIntent.SLICE,
            query_type=QueryType.SLICE,
        )

        assert result.tier == SemanticTier.FULL

    def test_conflicting_tiers_uses_higher(self):
        """Conflicting tiers → Use higher tier."""
        planner = TierPlanner()

        # Intent: EXTENDED, Query: FULL
        result = planner.plan(
            intent=AgentIntent.EXTRACT_METHOD,  # EXTENDED
            query_type=QueryType.SLICE,  # FULL
        )

        # Query wins (higher priority)
        assert result.tier == SemanticTier.FULL


# ============================================================
# Test 4: Edge Cases
# ============================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_no_inputs_defaults_to_base(self):
        """No inputs → BASE tier (default)."""
        planner = TierPlanner()
        result = planner.plan()

        assert result.tier == SemanticTier.BASE
        assert "default" in result.reason.lower()

    def test_all_unknown_defaults_to_base(self):
        """All UNKNOWN → BASE tier."""
        planner = TierPlanner()
        result = planner.plan(
            intent=AgentIntent.UNKNOWN,
            query_type=QueryType.UNKNOWN,
            scope=Scope.UNKNOWN,
        )

        assert result.tier == SemanticTier.BASE

    def test_small_scope_no_upgrade(self):
        """Small scope (FILE/FUNCTION) → No upgrade."""
        planner = TierPlanner()

        result_file = planner.plan(scope=Scope.FILE)
        result_func = planner.plan(scope=Scope.FUNCTION)

        # Should default to BASE (no upgrade)
        assert result_file.tier == SemanticTier.BASE
        assert result_func.tier == SemanticTier.BASE

    def test_large_scope_upgrades_to_extended(self):
        """Large scope (REPO/PACKAGE) → EXTENDED tier."""
        planner = TierPlanner()

        result_repo = planner.plan(scope=Scope.REPO)
        result_pkg = planner.plan(scope=Scope.PACKAGE)

        # Should upgrade to EXTENDED
        assert result_repo.tier == SemanticTier.EXTENDED
        assert result_pkg.tier == SemanticTier.EXTENDED

    def test_result_has_reason(self):
        """All results should have human-readable reason."""
        planner = TierPlanner()

        results = [
            planner.plan(query_type=QueryType.SLICE),
            planner.plan(intent=AgentIntent.EXTRACT_METHOD),
            planner.plan(scope=Scope.REPO),
            planner.plan(),
        ]

        for result in results:
            assert result.reason
            assert len(result.reason) > 0

    def test_options_contains_threshold_for_extended(self):
        """EXTENDED tier → options contain dfg_threshold."""
        planner = TierPlanner()

        result = planner.plan(query_type=QueryType.FLOW)

        assert result.tier == SemanticTier.EXTENDED
        assert "dfg_threshold" in result.options
        assert result.options["dfg_threshold"] == 500

    def test_options_empty_for_base(self):
        """BASE tier → options empty."""
        planner = TierPlanner()

        result = planner.plan(query_type=QueryType.CALLERS)

        assert result.tier == SemanticTier.BASE
        assert result.options == {}

    def test_options_empty_for_full(self):
        """FULL tier → options empty (no threshold)."""
        planner = TierPlanner()

        result = planner.plan(query_type=QueryType.SLICE)

        assert result.tier == SemanticTier.FULL
        assert result.options == {}


# ============================================================
# Test 5: Exhaustive Enum Coverage
# ============================================================


class TestExhaustiveEnumCoverage:
    """Test all enum values are handled."""

    def test_all_query_types_handled(self):
        """All QueryType enum values should be handled."""
        planner = TierPlanner()

        # Test all query types (except UNKNOWN)
        query_types = [qt for qt in QueryType if qt != QueryType.UNKNOWN]

        for query_type in query_types:
            result = planner.plan(query_type=query_type)

            # Should return valid tier
            assert result.tier in (SemanticTier.BASE, SemanticTier.EXTENDED, SemanticTier.FULL)
            assert result.reason

    def test_all_intents_handled(self):
        """All AgentIntent enum values should be handled."""
        planner = TierPlanner()

        # Test all intents (except UNKNOWN)
        intents = [intent for intent in AgentIntent if intent != AgentIntent.UNKNOWN]

        for intent in intents:
            result = planner.plan(intent=intent)

            # Should return valid tier
            assert result.tier in (SemanticTier.BASE, SemanticTier.EXTENDED, SemanticTier.FULL)
            assert result.reason

    def test_all_scopes_handled(self):
        """All Scope enum values should be handled."""
        planner = TierPlanner()

        # Test all scopes
        scopes = list(Scope)

        for scope in scopes:
            result = planner.plan(scope=scope)

            # Should return valid tier
            assert result.tier in (SemanticTier.BASE, SemanticTier.EXTENDED, SemanticTier.FULL)


# ============================================================
# Test 6: Real-World Scenarios
# ============================================================


class TestRealWorldScenarios:
    """Test real-world AI agent scenarios."""

    def test_scenario_simple_rename(self):
        """Scenario: "Rename this function"."""
        planner = TierPlanner()

        result = planner.plan(
            intent=AgentIntent.RENAME,
            query_type=QueryType.REFERENCES,
            scope=Scope.FILE,
        )

        # Simple rename only needs references (BASE)
        assert result.tier == SemanticTier.BASE

    def test_scenario_extract_method(self):
        """Scenario: "Extract this code into a method"."""
        planner = TierPlanner()

        result = planner.plan(
            intent=AgentIntent.EXTRACT_METHOD,
            query_type=QueryType.FLOW,
            scope=Scope.FUNCTION,
        )

        # Extract method needs DFG (EXTENDED)
        assert result.tier == SemanticTier.EXTENDED

    def test_scenario_understand_function(self):
        """Scenario: "Explain what this function does"."""
        planner = TierPlanner()

        result = planner.plan(
            intent=AgentIntent.UNDERSTAND,
            query_type=QueryType.CALLEES,
            scope=Scope.FUNCTION,
        )

        # Understanding only needs CFG (BASE)
        assert result.tier == SemanticTier.BASE

    def test_scenario_trace_value(self):
        """Scenario: "Where does this value come from?"."""
        planner = TierPlanner()

        result = planner.plan(
            intent=AgentIntent.UNKNOWN,
            query_type=QueryType.VALUE_ORIGIN,
            scope=Scope.FUNCTION,
        )

        # Value tracing needs DFG (EXTENDED)
        assert result.tier == SemanticTier.EXTENDED

    def test_scenario_program_slice(self):
        """Scenario: "Show me all code affecting this variable"."""
        planner = TierPlanner()

        result = planner.plan(
            intent=AgentIntent.SLICE,
            query_type=QueryType.SLICE,
            scope=Scope.FILE,
        )

        # Program slicing needs PDG (FULL)
        assert result.tier == SemanticTier.FULL

    def test_scenario_null_safety(self):
        """Scenario: "Can this variable be null here?"."""
        planner = TierPlanner()

        result = planner.plan(
            intent=AgentIntent.NULL_CHECK,
            query_type=QueryType.PATH_SENSITIVE,
            scope=Scope.FUNCTION,
        )

        # Null check needs path-sensitive analysis (FULL)
        assert result.tier == SemanticTier.FULL

    def test_scenario_find_usages(self):
        """Scenario: "Find all usages of this function"."""
        planner = TierPlanner()

        result = planner.plan(
            intent=AgentIntent.FIND_REFERENCES,
            query_type=QueryType.REFERENCES,
            scope=Scope.REPO,
        )

        # Find usages only needs references (BASE)
        # Even with REPO scope, query type wins
        assert result.tier == SemanticTier.BASE


# ============================================================
# Test 7: Tier Minimization
# ============================================================


class TestTierMinimization:
    """Test that planner selects minimum required tier."""

    def test_rename_doesnt_need_dfg(self):
        """RENAME should not require DFG."""
        planner = TierPlanner()

        result = planner.plan(intent=AgentIntent.RENAME)

        # Should use BASE (not EXTENDED)
        assert result.tier == SemanticTier.BASE

    def test_understand_doesnt_need_ssa(self):
        """UNDERSTAND should not require SSA."""
        planner = TierPlanner()

        result = planner.plan(intent=AgentIntent.UNDERSTAND)

        # Should use BASE (not FULL)
        assert result.tier == SemanticTier.BASE

    def test_extract_doesnt_need_ssa(self):
        """EXTRACT_METHOD should not require SSA."""
        planner = TierPlanner()

        result = planner.plan(intent=AgentIntent.EXTRACT_METHOD)

        # Should use EXTENDED (not FULL)
        assert result.tier == SemanticTier.EXTENDED


# ============================================================
# Test 8: Observability
# ============================================================


class TestObservability:
    """Test observability and metrics."""

    def test_result_has_tier(self):
        """All results should have tier."""
        planner = TierPlanner()

        result = planner.plan(query_type=QueryType.CALLERS)

        assert isinstance(result.tier, SemanticTier)

    def test_result_has_options(self):
        """All results should have options dict."""
        planner = TierPlanner()

        result = planner.plan(query_type=QueryType.CALLERS)

        assert isinstance(result.options, dict)

    def test_result_has_reason(self):
        """All results should have reason."""
        planner = TierPlanner()

        result = planner.plan(query_type=QueryType.CALLERS)

        assert isinstance(result.reason, str)
        assert len(result.reason) > 0

    def test_threshold_matches_buildconfig_default(self):
        """TierPlanner threshold should match BuildConfig default."""
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
        from codegraph_engine.code_foundation.infrastructure.tier_planning.planner import DEFAULT_DFG_THRESHOLD

        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.FLOW)

        # Should use same threshold as BuildConfig default
        config = BuildConfig(semantic_tier=SemanticTier.EXTENDED)

        assert result.options["dfg_threshold"] == DEFAULT_DFG_THRESHOLD
        assert result.options["dfg_threshold"] == config.dfg_function_loc_threshold


# ============================================================
# Test 9: Extreme Edge Cases (L11 SOTA)
# ============================================================


class TestExtremeEdgeCases:
    """Test extreme edge cases."""

    def test_none_none_none(self):
        """All None inputs → BASE tier."""
        planner = TierPlanner()

        result = planner.plan(intent=None, query_type=None, scope=None)

        assert result.tier == SemanticTier.BASE
        assert "default" in result.reason.lower()

    def test_unhandled_query_type_raises_error(self):
        """Unhandled QueryType enum should raise ValueError (fail-fast)."""
        from unittest.mock import Mock

        planner = TierPlanner()

        # Create a mock enum value that's not handled
        fake_query = Mock(spec=QueryType)
        fake_query.value = "fake_query_type"
        fake_query.__eq__ = lambda self, other: False  # Not equal to any known value

        # Should raise ValueError (not return None silently)
        with pytest.raises(ValueError, match="Unhandled QueryType enum value"):
            planner._tier_from_query_type(fake_query)

    def test_unhandled_intent_raises_error(self):
        """Unhandled AgentIntent enum should raise ValueError (fail-fast)."""
        from unittest.mock import Mock

        planner = TierPlanner()

        # Create a mock enum value that's not handled
        fake_intent = Mock(spec=AgentIntent)
        fake_intent.value = "fake_intent"
        fake_intent.__eq__ = lambda self, other: False

        # Should raise ValueError (not return None silently)
        with pytest.raises(ValueError, match="Unhandled AgentIntent enum value"):
            planner._tier_from_intent(fake_intent)

    def test_only_intent_unknown(self):
        """Only UNKNOWN intent → BASE tier."""
        planner = TierPlanner()

        result = planner.plan(intent=AgentIntent.UNKNOWN)

        assert result.tier == SemanticTier.BASE

    def test_only_query_unknown(self):
        """Only UNKNOWN query → BASE tier."""
        planner = TierPlanner()

        result = planner.plan(query_type=QueryType.UNKNOWN)

        assert result.tier == SemanticTier.BASE

    def test_only_scope_unknown(self):
        """Only UNKNOWN scope → BASE tier."""
        planner = TierPlanner()

        result = planner.plan(scope=Scope.UNKNOWN)

        assert result.tier == SemanticTier.BASE

    def test_multiple_calls_consistent(self):
        """Multiple calls with same input → same result."""
        planner = TierPlanner()

        result1 = planner.plan(query_type=QueryType.FLOW)
        result2 = planner.plan(query_type=QueryType.FLOW)

        assert result1.tier == result2.tier
        assert result1.options == result2.options

    def test_planner_is_stateless(self):
        """Planner should be stateless (no side effects)."""
        planner = TierPlanner()

        # Call with different inputs
        planner.plan(query_type=QueryType.SLICE)
        planner.plan(query_type=QueryType.CALLERS)

        # Should not affect subsequent calls
        result = planner.plan(query_type=QueryType.FLOW)
        assert result.tier == SemanticTier.EXTENDED

    def test_concurrent_access_safe(self):
        """Planner should be safe for concurrent access."""
        import concurrent.futures

        planner = TierPlanner()

        # Define test cases
        test_cases = [
            (QueryType.SLICE, SemanticTier.FULL),
            (QueryType.FLOW, SemanticTier.EXTENDED),
            (QueryType.CALLERS, SemanticTier.BASE),
        ] * 10  # Repeat for concurrency

        def plan_wrapper(query_type):
            return planner.plan(query_type=query_type)

        # Execute concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(plan_wrapper, query_type) for query_type, _ in test_cases]
            results = [f.result() for f in futures]

        # Verify all results are correct
        for i, (query_type, expected_tier) in enumerate(test_cases):
            assert results[i].tier == expected_tier

    def test_result_immutability(self):
        """TierPlanResult should be immutable (frozen dataclass)."""
        planner = TierPlanner()
        result = planner.plan(query_type=QueryType.FLOW)

        # Options dict should be a new dict (not shared reference)
        result.options["custom"] = "value"

        # Next call should not see the modification
        result2 = planner.plan(query_type=QueryType.FLOW)
        assert "custom" not in result2.options
