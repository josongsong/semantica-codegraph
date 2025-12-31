"""
Query Engine Parity Tests - RFC-021 Phase 3.2

Ensures QueryEngine produces same results as legacy systems.

Golden Data Strategy:
1. Capture current production results (50 real-world cases)
2. Compare QueryEngine results with golden snapshots
3. Allow minor differences (path ordering, etc.) but verify equivalence

Test Coverage:
- TaintAnalysisService (휴리스틱) vs QueryEngine(mode="pr")
- FullTaintEngine (k-CFA) vs QueryEngine(mode="full")
- PathResult ordering stability
"""

import json
from pathlib import Path

import pytest


def load_golden_cases():
    """
    Load golden test cases

    TODO (Phase 3.2):
        Capture 50 real-world cases from:
        - Django samples
        - Flask samples
        - FastAPI samples
        - Internal test fixtures

    Format:
        {
            "case_id": "django_sqli_001",
            "ir_doc_path": "tests/fixtures/golden/django_sqli_001.json",
            "flow_expr": "(Q.Var('user_input') >> Q.Call('execute'))",
            "expected_paths": [...],
            "mode": "pr"
        }
    """
    golden_dir = Path("tests/fixtures/golden")
    if not golden_dir.exists():
        return []

    cases = []
    for case_file in golden_dir.glob("*.json"):
        with open(case_file) as f:
            cases.append(json.load(f))

    return cases


@pytest.mark.skipif(True, reason="Golden data not captured yet (RFC-021 Phase 3.2)")
@pytest.mark.parametrize("case", load_golden_cases())
def test_query_engine_vs_legacy(case):
    """
    Compare QueryEngine results with legacy system

    Args:
        case: Golden test case

    Checks:
        - Same number of paths found
        - Paths contain same nodes (order may differ)
        - uncertain flags consistent
        - severity consistent
    """
    # TODO: Implement after capturing golden data
    pass


@pytest.mark.skipif(True, reason="Golden data not captured yet (RFC-021 Phase 3.2)")
def test_pathset_ordering_stability():
    """
    Verify PathSet.paths are sorted stably

    RFC-021: Sorting order = severity → uncertain → length → node_id

    Critical for CI diff stability.
    """
    # TODO: Implement after capturing golden data
    pass


@pytest.mark.skipif(True, reason="Phase 2 k-CFA not implemented yet")
def test_full_mode_vs_full_taint_engine():
    """
    Compare QueryEngine(mode="full") vs FullTaintEngine

    Allowed differences:
    - Path ordering
    - Diagnostics format

    Must match:
    - Vulnerability count
    - Source-sink pairs
    - Severity levels
    """
    # TODO: Implement in Phase 2 after DeepAnalyzer k-CFA
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
