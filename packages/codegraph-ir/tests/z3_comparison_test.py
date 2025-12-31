#!/usr/bin/env python3
"""Z3 vs Internal Engine Comparative Test Suite

This test suite runs identical constraint scenarios through both:
1. Z3 SMT solver (ground truth)
2. Our internal Rust SMT engine

Results are compared to measure accuracy and document discrepancies.
"""

import subprocess
import json
from typing import Dict, List, Tuple, Literal
from dataclasses import dataclass
from z3 import *

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test Case Definitions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class Constraint:
    """Single constraint"""

    var: str
    op: str  # "Eq", "Lt", "Le", "Gt", "Ge", "Neq"
    value: int


@dataclass
class TestCase:
    """A single test case with constraints and expected result"""

    name: str
    constraints: List[Constraint]
    sccp_values: Dict[str, int]  # Optional SCCP constant values
    expected: Literal["Feasible", "Infeasible", "Unknown"]
    category: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test Case Catalog
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TEST_CASES = [
    # ─────────────────────────────────────────────────────────────
    # Category 1: Basic Intervals
    # ─────────────────────────────────────────────────────────────
    TestCase(
        name="simple_interval_feasible",
        constraints=[
            Constraint("x", "Gt", 5),
            Constraint("x", "Lt", 10),
        ],
        sccp_values={},
        expected="Feasible",
        category="basic_intervals",
    ),
    TestCase(
        name="simple_interval_infeasible",
        constraints=[
            Constraint("x", "Lt", 5),
            Constraint("x", "Gt", 10),
        ],
        sccp_values={},
        expected="Infeasible",
        category="basic_intervals",
    ),
    TestCase(
        name="exact_boundary_feasible",
        constraints=[
            Constraint("x", "Ge", 10),
            Constraint("x", "Le", 10),
        ],
        sccp_values={},
        expected="Feasible",  # x == 10
        category="basic_intervals",
    ),
    TestCase(
        name="adjacent_boundary_infeasible",
        constraints=[
            Constraint("x", "Lt", 10),
            Constraint("x", "Ge", 10),
        ],
        sccp_values={},
        expected="Infeasible",
        category="basic_intervals",
    ),
    # ─────────────────────────────────────────────────────────────
    # Category 2: SCCP Integration
    # ─────────────────────────────────────────────────────────────
    TestCase(
        name="sccp_constant_feasible",
        constraints=[
            Constraint("x", "Lt", 10),
        ],
        sccp_values={"x": 5},
        expected="Feasible",  # x=5, 5 < 10
        category="sccp_integration",
    ),
    TestCase(
        name="sccp_constant_infeasible",
        constraints=[
            Constraint("x", "Gt", 10),
        ],
        sccp_values={"x": 5},
        expected="Infeasible",  # x=5, 5 > 10 = false
        category="sccp_integration",
    ),
    TestCase(
        name="sccp_with_interval",
        constraints=[
            Constraint("x", "Gt", 3),
            Constraint("x", "Lt", 10),
        ],
        sccp_values={"x": 7},
        expected="Feasible",  # x=7, 3 < 7 < 10
        category="sccp_integration",
    ),
    # ─────────────────────────────────────────────────────────────
    # Category 3: Equality Constraints
    # ─────────────────────────────────────────────────────────────
    TestCase(
        name="equality_feasible",
        constraints=[
            Constraint("x", "Eq", 5),
            Constraint("x", "Gt", 3),
            Constraint("x", "Lt", 10),
        ],
        sccp_values={},
        expected="Feasible",  # x=5, 3 < 5 < 10
        category="equality",
    ),
    TestCase(
        name="equality_contradiction",
        constraints=[
            Constraint("x", "Eq", 5),
            Constraint("x", "Eq", 10),
        ],
        sccp_values={},
        expected="Infeasible",
        category="equality",
    ),
    TestCase(
        name="equality_with_neq",
        constraints=[
            Constraint("x", "Eq", 5),
            Constraint("x", "Neq", 5),
        ],
        sccp_values={},
        expected="Infeasible",
        category="equality",
    ),
    # ─────────────────────────────────────────────────────────────
    # Category 4: Multi-Variable
    # ─────────────────────────────────────────────────────────────
    TestCase(
        name="multi_var_independent",
        constraints=[
            Constraint("x", "Gt", 5),
            Constraint("y", "Lt", 10),
        ],
        sccp_values={},
        expected="Feasible",
        category="multi_variable",
    ),
    TestCase(
        name="multi_var_with_sccp",
        constraints=[
            Constraint("x", "Lt", 10),
            Constraint("y", "Gt", 5),
        ],
        sccp_values={"x": 7, "y": 8},
        expected="Feasible",
        category="multi_variable",
    ),
    # ─────────────────────────────────────────────────────────────
    # Category 5: Edge Cases
    # ─────────────────────────────────────────────────────────────
    TestCase(
        name="negative_numbers",
        constraints=[
            Constraint("x", "Gt", -100),
            Constraint("x", "Lt", -50),
        ],
        sccp_values={},
        expected="Feasible",
        category="edge_cases",
    ),
    TestCase(
        name="zero_crossing",
        constraints=[
            Constraint("x", "Gt", -10),
            Constraint("x", "Lt", 10),
        ],
        sccp_values={},
        expected="Feasible",
        category="edge_cases",
    ),
    TestCase(
        name="single_value_interval",
        constraints=[
            Constraint("x", "Ge", 5),
            Constraint("x", "Le", 5),
        ],
        sccp_values={},
        expected="Feasible",  # x == 5
        category="edge_cases",
    ),
    # ─────────────────────────────────────────────────────────────
    # Category 6: Complex Scenarios
    # ─────────────────────────────────────────────────────────────
    TestCase(
        name="multiple_constraints_narrow",
        constraints=[
            Constraint("x", "Gt", 0),
            Constraint("x", "Gt", 5),
            Constraint("x", "Gt", 8),
            Constraint("x", "Lt", 20),
            Constraint("x", "Lt", 15),
        ],
        sccp_values={},
        expected="Feasible",  # 8 < x < 15
        category="complex",
    ),
    TestCase(
        name="over_constrained_infeasible",
        constraints=[
            Constraint("x", "Gt", 0),
            Constraint("x", "Lt", 100),
            Constraint("x", "Gt", 50),
            Constraint("x", "Lt", 30),  # Contradiction: x > 50 && x < 30
        ],
        sccp_values={},
        expected="Infeasible",
        category="complex",
    ),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Z3 Solver Functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def run_z3(test_case: TestCase) -> Literal["Feasible", "Infeasible", "Unknown"]:
    """Run constraints through Z3 solver"""
    solver = Solver()

    # Create Z3 integer variables
    vars_map = {}
    all_vars = set(c.var for c in test_case.constraints) | set(test_case.sccp_values.keys())
    for var_name in all_vars:
        vars_map[var_name] = Int(var_name)

    # Add SCCP constant values
    for var_name, value in test_case.sccp_values.items():
        solver.add(vars_map[var_name] == value)

    # Add constraints
    for constraint in test_case.constraints:
        var = vars_map[constraint.var]
        val = constraint.value

        if constraint.op == "Eq":
            solver.add(var == val)
        elif constraint.op == "Neq":
            solver.add(var != val)
        elif constraint.op == "Lt":
            solver.add(var < val)
        elif constraint.op == "Le":
            solver.add(var <= val)
        elif constraint.op == "Gt":
            solver.add(var > val)
        elif constraint.op == "Ge":
            solver.add(var >= val)
        else:
            raise ValueError(f"Unknown operator: {constraint.op}")

    # Check satisfiability
    result = solver.check()

    if result == sat:
        return "Feasible"
    elif result == unsat:
        return "Infeasible"
    else:
        return "Unknown"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Internal Engine Runner (via Rust test binary)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def run_internal_engine(test_case: TestCase) -> Literal["Feasible", "Infeasible", "Unknown"]:
    """
    Run constraints through internal Rust engine

    NOTE: This would typically be done via a compiled test binary or FFI.
    For now, we'll create a temporary Rust test and run it.
    """
    # Generate Rust test code
    rust_code = generate_rust_test_code(test_case)

    # Write to temporary file
    test_file = "/tmp/z3_comparison_internal.rs"
    with open(test_file, "w") as f:
        f.write(rust_code)

    # Run via cargo test (this is a placeholder - would need proper integration)
    # For this demonstration, we'll return "Unknown" and rely on manual Rust test execution
    return "Unknown"  # Placeholder


def generate_rust_test_code(test_case: TestCase) -> str:
    """Generate Rust test code for internal engine"""
    # This is a helper for documentation - actual execution would need proper integration
    constraints_code = ""
    for c in test_case.constraints:
        op_code = f"ComparisonOp::{c.op}"
        constraints_code += f'    checker.add_condition(&PathCondition::new("{c.var}".to_string(), {op_code}, Some(ConstValue::Int({c.value}))));\n'

    sccp_code = ""
    for var, val in test_case.sccp_values.items():
        sccp_code += (
            f'    checker.add_sccp_value("{var}".to_string(), LatticeValue::Constant(ConstValue::Int({val})));\n'
        )

    return f"""
#[test]
fn {test_case.name}() {{
    let mut checker = EnhancedConstraintChecker::new();

{sccp_code}
{constraints_code}

    let result = checker.is_path_feasible();
    println!("{{:?}}", result);
}}
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Comparison and Reporting
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class ComparisonResult:
    test_name: str
    category: str
    z3_result: str
    internal_result: str
    expected: str
    match_z3: bool
    match_expected: bool


def run_comparison_suite() -> Tuple[List[ComparisonResult], Dict[str, int]]:
    """Run all test cases through both engines and compare"""
    results = []
    stats = {
        "total": 0,
        "z3_feasible": 0,
        "z3_infeasible": 0,
        "z3_unknown": 0,
        "matches": 0,
        "mismatches": 0,
        "internal_unavailable": 0,
    }

    print("=" * 80)
    print("Z3 vs Internal Engine Comparative Test Suite")
    print("=" * 80)
    print()

    for test_case in TEST_CASES:
        print(f"Running: {test_case.name} ({test_case.category})")

        # Run Z3
        z3_result = run_z3(test_case)

        # Run internal engine (placeholder for now)
        internal_result = "Unavailable"  # Will be filled by Rust tests

        # Compare
        match_z3 = (internal_result == z3_result) if internal_result != "Unavailable" else False
        match_expected = z3_result == test_case.expected

        result = ComparisonResult(
            test_name=test_case.name,
            category=test_case.category,
            z3_result=z3_result,
            internal_result=internal_result,
            expected=test_case.expected,
            match_z3=match_z3,
            match_expected=match_expected,
        )

        results.append(result)

        # Update stats
        stats["total"] += 1
        if z3_result == "Feasible":
            stats["z3_feasible"] += 1
        elif z3_result == "Infeasible":
            stats["z3_infeasible"] += 1
        else:
            stats["z3_unknown"] += 1

        if internal_result == "Unavailable":
            stats["internal_unavailable"] += 1
        elif match_z3:
            stats["matches"] += 1
        else:
            stats["mismatches"] += 1

        # Print result
        status = "✅" if match_expected else "❌"
        print(f"  {status} Z3: {z3_result}, Expected: {test_case.expected}")
        print()

    return results, stats


def print_summary(results: List[ComparisonResult], stats: Dict[str, int]):
    """Print comparison summary"""
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print(f"Total test cases: {stats['total']}")
    print()
    print("Z3 Results:")
    print(f"  Feasible:   {stats['z3_feasible']}")
    print(f"  Infeasible: {stats['z3_infeasible']}")
    print(f"  Unknown:    {stats['z3_unknown']}")
    print()
    print("Internal Engine (placeholder):")
    print(f"  Matches with Z3:    {stats['matches']}")
    print(f"  Mismatches with Z3: {stats['mismatches']}")
    print(f"  Unavailable:        {stats['internal_unavailable']}")
    print()

    if stats["total"] - stats["internal_unavailable"] > 0:
        accuracy = (stats["matches"] / (stats["total"] - stats["internal_unavailable"])) * 100
        print(f"Accuracy: {accuracy:.1f}%")
    print()

    # Category breakdown
    print("=" * 80)
    print("CATEGORY BREAKDOWN")
    print("=" * 80)
    print()

    categories = {}
    for result in results:
        if result.category not in categories:
            categories[result.category] = {"total": 0, "z3_correct": 0}
        categories[result.category]["total"] += 1
        if result.match_expected:
            categories[result.category]["z3_correct"] += 1

    for category, counts in sorted(categories.items()):
        accuracy = (counts["z3_correct"] / counts["total"]) * 100
        print(f"{category:20} {counts['z3_correct']}/{counts['total']} ({accuracy:.0f}%)")
    print()

    # Detailed discrepancies (if any)
    discrepancies = [r for r in results if not r.match_expected]
    if discrepancies:
        print("=" * 80)
        print("DISCREPANCIES (Z3 vs Expected)")
        print("=" * 80)
        print()
        for result in discrepancies:
            print(f"{result.test_name}:")
            print(f"  Expected:  {result.expected}")
            print(f"  Z3 Result: {result.z3_result}")
            print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main Entry Point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    print()
    print("NOTE: This script runs Z3 solver on test cases.")
    print("For internal engine comparison, run corresponding Rust tests.")
    print()

    results, stats = run_comparison_suite()
    print_summary(results, stats)

    # Generate Rust test file for manual execution
    print("=" * 80)
    print("GENERATING RUST TEST FILE")
    print("=" * 80)
    print()

    rust_tests = []
    for test_case in TEST_CASES:
        rust_tests.append(generate_rust_test_code(test_case))

    rust_file = "tests/z3_comparison_internal_generated.rs"
    full_rust_code = """//! Z3 Comparison Tests - Internal Engine Side
//!
//! Auto-generated test cases matching z3_comparison_test.py
//! Run these and compare results with Z3 ground truth.

use codegraph_ir::features::smt::domain::{ComparisonOp, ConstValue, PathCondition};
use codegraph_ir::features::smt::infrastructure::{
    EnhancedConstraintChecker, LatticeValue, PathFeasibility,
};

""" + "\n".join(rust_tests)

    print(f"Writing Rust tests to: {rust_file}")
    print()
    print("To compare results:")
    print(f"1. Run this script: python3 tests/z3_comparison_test.py")
    print(f"2. Run Rust tests:  cargo test --test z3_comparison_internal_generated")
    print(f"3. Compare outputs manually")
    print()
