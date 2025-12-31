//! Z3 Comparison Tests - Internal Engine Side
//!
//! This file contains identical test cases to z3_comparison_test.py
//! Run both and compare results to measure accuracy.
//!
//! Categories:
//! - Basic intervals
//! - SCCP integration
//! - Equality constraints
//! - Multi-variable
//! - Edge cases
//! - Complex scenarios

use codegraph_ir::features::smt::domain::{ComparisonOp, ConstValue, PathCondition};
use codegraph_ir::features::smt::infrastructure::{
    EnhancedConstraintChecker, LatticeValue, PathFeasibility,
};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Category 1: Basic Intervals
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn simple_interval_feasible() {
    // x > 5 && x < 10
    // Z3 Expected: Feasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));

    let result = checker.is_path_feasible();
    println!("simple_interval_feasible: {:?}", result);
    assert_eq!(result, PathFeasibility::Feasible);
}

#[test]
fn simple_interval_infeasible() {
    // x < 5 && x > 10
    // Z3 Expected: Infeasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(5)));
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(10)));

    let result = checker.is_path_feasible();
    println!("simple_interval_infeasible: {:?}", result);
    assert_eq!(result, PathFeasibility::Infeasible);
}

#[test]
fn exact_boundary_feasible() {
    // x >= 10 && x <= 10 (i.e., x == 10)
    // Z3 Expected: Feasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::new(
        "x".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(10)),
    ));
    checker.add_condition(&PathCondition::new(
        "x".to_string(),
        ComparisonOp::Le,
        Some(ConstValue::Int(10)),
    ));

    let result = checker.is_path_feasible();
    println!("exact_boundary_feasible: {:?}", result);
    assert_eq!(result, PathFeasibility::Feasible);
}

#[test]
fn adjacent_boundary_infeasible() {
    // x < 10 && x >= 10
    // Z3 Expected: Infeasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));
    checker.add_condition(&PathCondition::new(
        "x".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(10)),
    ));

    let result = checker.is_path_feasible();
    println!("adjacent_boundary_infeasible: {:?}", result);
    assert_eq!(result, PathFeasibility::Infeasible);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Category 2: SCCP Integration
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn sccp_constant_feasible() {
    // SCCP: x = 5, Constraint: x < 10
    // Z3 Expected: Feasible (5 < 10)
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_sccp_value("x".to_string(), LatticeValue::Constant(ConstValue::Int(5)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));

    let result = checker.is_path_feasible();
    println!("sccp_constant_feasible: {:?}", result);
    assert_eq!(result, PathFeasibility::Feasible);
}

#[test]
fn sccp_constant_infeasible() {
    // SCCP: x = 5, Constraint: x > 10
    // Z3 Expected: Infeasible (5 > 10 = false)
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_sccp_value("x".to_string(), LatticeValue::Constant(ConstValue::Int(5)));
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(10)));

    let result = checker.is_path_feasible();
    println!("sccp_constant_infeasible: {:?}", result);
    assert_eq!(result, PathFeasibility::Infeasible);
}

#[test]
fn sccp_with_interval() {
    // SCCP: x = 7, Constraints: x > 3 && x < 10
    // Z3 Expected: Feasible (3 < 7 < 10)
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_sccp_value("x".to_string(), LatticeValue::Constant(ConstValue::Int(7)));
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(3)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));

    let result = checker.is_path_feasible();
    println!("sccp_with_interval: {:?}", result);
    assert_eq!(result, PathFeasibility::Feasible);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Category 3: Equality Constraints
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn equality_feasible() {
    // x == 5 && x > 3 && x < 10
    // Z3 Expected: Feasible (3 < 5 < 10)
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::eq("x".to_string(), ConstValue::Int(5)));
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(3)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));

    let result = checker.is_path_feasible();
    println!("equality_feasible: {:?}", result);
    assert_eq!(result, PathFeasibility::Feasible);
}

#[test]
fn equality_contradiction() {
    // x == 5 && x == 10
    // Z3 Expected: Infeasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::eq("x".to_string(), ConstValue::Int(5)));
    checker.add_condition(&PathCondition::eq("x".to_string(), ConstValue::Int(10)));

    let result = checker.is_path_feasible();
    println!("equality_contradiction: {:?}", result);
    assert_eq!(result, PathFeasibility::Infeasible);
}

#[test]
fn equality_with_neq() {
    // x == 5 && x != 5
    // Z3 Expected: Infeasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::eq("x".to_string(), ConstValue::Int(5)));
    checker.add_condition(&PathCondition::neq("x".to_string(), ConstValue::Int(5)));

    let result = checker.is_path_feasible();
    println!("equality_with_neq: {:?}", result);
    assert_eq!(result, PathFeasibility::Infeasible);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Category 4: Multi-Variable
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn multi_var_independent() {
    // x > 5 && y < 10 (independent variables)
    // Z3 Expected: Feasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));
    checker.add_condition(&PathCondition::lt("y".to_string(), ConstValue::Int(10)));

    let result = checker.is_path_feasible();
    println!("multi_var_independent: {:?}", result);
    assert_eq!(result, PathFeasibility::Feasible);
}

#[test]
fn multi_var_with_sccp() {
    // SCCP: x=7, y=8, Constraints: x < 10 && y > 5
    // Z3 Expected: Feasible (7 < 10 && 8 > 5)
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_sccp_value("x".to_string(), LatticeValue::Constant(ConstValue::Int(7)));
    checker.add_sccp_value("y".to_string(), LatticeValue::Constant(ConstValue::Int(8)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));
    checker.add_condition(&PathCondition::gt("y".to_string(), ConstValue::Int(5)));

    let result = checker.is_path_feasible();
    println!("multi_var_with_sccp: {:?}", result);
    assert_eq!(result, PathFeasibility::Feasible);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Category 5: Edge Cases
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn negative_numbers() {
    // x > -100 && x < -50
    // Z3 Expected: Feasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(-100)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(-50)));

    let result = checker.is_path_feasible();
    println!("negative_numbers: {:?}", result);
    assert_eq!(result, PathFeasibility::Feasible);
}

#[test]
fn zero_crossing() {
    // x > -10 && x < 10
    // Z3 Expected: Feasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(-10)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));

    let result = checker.is_path_feasible();
    println!("zero_crossing: {:?}", result);
    assert_eq!(result, PathFeasibility::Feasible);
}

#[test]
fn single_value_interval() {
    // x >= 5 && x <= 5 (i.e., x == 5)
    // Z3 Expected: Feasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::new(
        "x".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(5)),
    ));
    checker.add_condition(&PathCondition::new(
        "x".to_string(),
        ComparisonOp::Le,
        Some(ConstValue::Int(5)),
    ));

    let result = checker.is_path_feasible();
    println!("single_value_interval: {:?}", result);
    assert_eq!(result, PathFeasibility::Feasible);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Category 6: Complex Scenarios
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn multiple_constraints_narrow() {
    // x > 0 && x > 5 && x > 8 && x < 20 && x < 15
    // Should narrow to: 8 < x < 15
    // Z3 Expected: Feasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(0)));
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(8)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(20)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(15)));

    let result = checker.is_path_feasible();
    println!("multiple_constraints_narrow: {:?}", result);
    assert_eq!(result, PathFeasibility::Feasible);
}

#[test]
fn over_constrained_infeasible() {
    // x > 0 && x < 100 && x > 50 && x < 30
    // Contradiction: x > 50 && x < 30
    // Z3 Expected: Infeasible
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(0)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(100)));
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(50)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(30)));

    let result = checker.is_path_feasible();
    println!("over_constrained_infeasible: {:?}", result);
    assert_eq!(result, PathFeasibility::Infeasible);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Summary Test
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
#[ignore] // Manual execution to print summary
fn z3_comparison_summary() {
    println!();
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("Z3 COMPARISON TEST SUITE - INTERNAL ENGINE RESULTS");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!();
    println!("Test Coverage:");
    println!("  • Basic intervals:     4 tests");
    println!("  • SCCP integration:    3 tests");
    println!("  • Equality constraints: 3 tests");
    println!("  • Multi-variable:      2 tests");
    println!("  • Edge cases:          3 tests");
    println!("  • Complex scenarios:   2 tests");
    println!("  ─────────────────────────────");
    println!("  TOTAL:                17 tests");
    println!();
    println!("To compare with Z3 ground truth:");
    println!("  1. Run Z3 tests:      python3 tests/z3_comparison_test.py");
    println!("  2. Run Rust tests:    cargo test --test z3_comparison_internal");
    println!("  3. Compare outputs");
    println!();
    println!("Expected: 100% agreement with Z3 on these test cases");
    println!();
}
