//! SMT Engine Edge Cases and Extreme Condition Tests
//!
//! Tests covering:
//! - Edge cases (boundary conditions)
//! - Extreme cases (stress testing)
//! - Corner cases (unusual combinations)

use codegraph_ir::features::smt::domain::{ComparisonOp, ConstValue, PathCondition};
use codegraph_ir::features::smt::infrastructure::{
    ArrayBoundsChecker, ConstraintPropagator, EnhancedConstraintChecker, IntervalTracker,
    LatticeValue, PathFeasibility, StringConstraintSolver, StringPattern,
};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// IntervalTracker Edge Cases
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn edge_interval_zero_width() {
    // [5, 5] - exact single value interval
    let mut tracker = IntervalTracker::new();

    tracker.add_constraint(&PathCondition::new(
        "x".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(5)),
    ));
    tracker.add_constraint(&PathCondition::new(
        "x".to_string(),
        ComparisonOp::Le,
        Some(ConstValue::Int(5)),
    ));

    assert!(tracker.is_feasible());
    let interval = tracker.get_interval(&"x".to_string()).unwrap();
    assert!(interval.contains(5));
    assert!(!interval.contains(4));
    assert!(!interval.contains(6));
}

#[test]
fn edge_interval_adjacent_boundaries() {
    // x < 10 && x >= 10 - should be infeasible
    let mut tracker = IntervalTracker::new();

    tracker.add_constraint(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));
    let result = tracker.add_constraint(&PathCondition::new(
        "x".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(10)),
    ));

    assert!(!result); // Contradiction detected
}

#[test]
fn edge_interval_negative_numbers() {
    // -100 < x < -50
    let mut tracker = IntervalTracker::new();

    tracker.add_constraint(&PathCondition::gt("x".to_string(), ConstValue::Int(-100)));
    tracker.add_constraint(&PathCondition::lt("x".to_string(), ConstValue::Int(-50)));

    assert!(tracker.is_feasible());
    let interval = tracker.get_interval(&"x".to_string()).unwrap();
    assert!(interval.contains(-75));
    assert!(!interval.contains(-100));
    assert!(!interval.contains(-50));
}

#[test]
fn edge_interval_i64_max() {
    // Test with maximum i64 value
    let mut tracker = IntervalTracker::new();

    tracker.add_constraint(&PathCondition::lt(
        "x".to_string(),
        ConstValue::Int(i64::MAX),
    ));
    tracker.add_constraint(&PathCondition::gt(
        "x".to_string(),
        ConstValue::Int(i64::MAX - 100),
    ));

    assert!(tracker.is_feasible());
}

#[test]
fn edge_interval_i64_min() {
    // Test with minimum i64 value
    let mut tracker = IntervalTracker::new();

    tracker.add_constraint(&PathCondition::gt(
        "x".to_string(),
        ConstValue::Int(i64::MIN),
    ));
    tracker.add_constraint(&PathCondition::lt(
        "x".to_string(),
        ConstValue::Int(i64::MIN + 100),
    ));

    assert!(tracker.is_feasible());
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ConstraintPropagator Edge Cases
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn edge_propagator_self_loop() {
    // x == x should always be valid
    let mut prop = ConstraintPropagator::new();

    prop.add_relation("x".to_string(), ComparisonOp::Eq, "x".to_string());

    assert!(!prop.has_contradiction());
    assert!(prop.can_infer_eq("x", "x"));
}

#[test]
fn edge_propagator_long_equality_chain() {
    // a == b == c == d == e == f == g == h == i == j
    let mut prop = ConstraintPropagator::new();

    let vars = vec!["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"];
    for i in 0..vars.len() - 1 {
        prop.add_relation(
            vars[i].to_string(),
            ComparisonOp::Eq,
            vars[i + 1].to_string(),
        );
    }

    assert!(prop.can_infer_eq("a", "j"));
    assert!(prop.can_infer_eq("c", "h"));
}

#[test]
fn edge_propagator_transitive_ordering() {
    // a < b < c < d < e - verify all pairs
    let mut prop = ConstraintPropagator::new();

    prop.add_relation("a".to_string(), ComparisonOp::Lt, "b".to_string());
    prop.add_relation("b".to_string(), ComparisonOp::Lt, "c".to_string());
    prop.add_relation("c".to_string(), ComparisonOp::Lt, "d".to_string());
    prop.add_relation("d".to_string(), ComparisonOp::Lt, "e".to_string());

    assert!(prop.can_infer_lt("a", "e"));
    assert!(prop.can_infer_lt("b", "d"));
    assert!(prop.can_infer_lt("a", "c"));
}

#[test]
fn edge_propagator_mixed_relations() {
    // x == y, y < z, should infer x < z
    let mut prop = ConstraintPropagator::new();

    prop.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
    prop.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());

    assert!(prop.can_infer_lt("x", "z"));
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// StringConstraintSolver Edge Cases
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn edge_string_zero_length() {
    // len(s) == 0 (empty string)
    let mut solver = StringConstraintSolver::new();

    solver.add_length_constraint("s".to_string(), ComparisonOp::Eq, 0);

    assert!(solver.is_feasible());
    assert!(solver.can_be_empty(&"s".to_string()));
}

#[test]
fn edge_string_impossible_length() {
    // len(s) >= 10 && len(s) <= 5 - contradiction
    let mut solver = StringConstraintSolver::new();

    solver.add_length_constraint("s".to_string(), ComparisonOp::Ge, 10);
    let result = solver.add_length_constraint("s".to_string(), ComparisonOp::Le, 5);

    assert!(!result); // Should detect contradiction
}

#[test]
fn edge_string_very_long() {
    // len(s) >= 1_000_000 (very long string)
    let mut solver = StringConstraintSolver::new();

    solver.add_length_constraint("s".to_string(), ComparisonOp::Ge, 1_000_000);

    assert!(solver.is_feasible());
    assert!(!solver.can_be_empty(&"s".to_string()));
}

#[test]
fn edge_string_multiple_patterns() {
    // Must contain "https://" AND "api" AND ".json"
    let mut solver = StringConstraintSolver::new();

    solver.add_required_pattern(
        "url".to_string(),
        StringPattern::StartsWith("https://".to_string()),
    );
    solver.add_required_pattern(
        "url".to_string(),
        StringPattern::Contains("api".to_string()),
    );
    solver.add_required_pattern(
        "url".to_string(),
        StringPattern::EndsWith(".json".to_string()),
    );

    assert!(solver.is_feasible());
}

#[test]
fn edge_string_contradictory_patterns() {
    // Must start with "http://" AND "https://" - impossible
    let mut solver = StringConstraintSolver::new();

    solver.add_required_pattern(
        "url".to_string(),
        StringPattern::StartsWith("http://".to_string()),
    );
    solver.add_required_pattern(
        "url".to_string(),
        StringPattern::StartsWith("https://".to_string()),
    );

    // Should still be feasible (we don't detect all pattern contradictions)
    // This is a known limitation
    assert!(solver.is_feasible());
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ArrayBoundsChecker Edge Cases
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn edge_array_size_zero() {
    // Empty array
    let mut checker = ArrayBoundsChecker::new();

    checker.set_array_size("arr".to_string(), 0);

    // Any access is out of bounds
    assert!(!checker.is_access_safe(&"arr".to_string(), 0));
}

#[test]
fn edge_array_size_one() {
    // Single element array
    let mut checker = ArrayBoundsChecker::new();

    checker.set_array_size("arr".to_string(), 1);

    assert!(checker.is_access_safe(&"arr".to_string(), 0));
    assert!(!checker.is_access_safe(&"arr".to_string(), 1));
}

#[test]
fn edge_array_negative_index() {
    // Negative index should be unsafe
    let mut checker = ArrayBoundsChecker::new();

    checker.set_array_size("arr".to_string(), 100);

    assert!(!checker.is_access_safe(&"arr".to_string(), -1));
    assert!(!checker.is_access_safe(&"arr".to_string(), -100));
}

#[test]
fn edge_array_exact_boundary() {
    // arr[size-1] should be safe, arr[size] should not
    let mut checker = ArrayBoundsChecker::new();

    checker.set_array_size("arr".to_string(), 10);

    assert!(checker.is_access_safe(&"arr".to_string(), 9)); // Last valid
    assert!(!checker.is_access_safe(&"arr".to_string(), 10)); // First invalid
}

#[test]
fn edge_array_very_large() {
    // Test with very large array
    let mut checker = ArrayBoundsChecker::new();

    checker.set_array_size("arr".to_string(), i64::MAX as usize);

    assert!(checker.is_access_safe(&"arr".to_string(), 1_000_000));
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// EnhancedConstraintChecker Extreme Cases
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn extreme_max_conditions() {
    // Test with 50 conditions (max capacity)
    let mut checker = EnhancedConstraintChecker::new();

    for i in 0..50 {
        checker.add_condition(&PathCondition::gt(
            format!("x{}", i),
            ConstValue::Int(i as i64),
        ));
    }

    assert_eq!(checker.condition_count(), 50);
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn extreme_single_variable_many_constraints() {
    // Many constraints on single variable
    let mut checker = EnhancedConstraintChecker::new();

    // x > 0, x > 1, x > 2, ... x > 9
    for i in 0..10 {
        checker.add_condition(&PathCondition::gt(
            "x".to_string(),
            ConstValue::Int(i as i64),
        ));
    }

    // All should narrow to x > 9
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn extreme_sccp_overrides_interval() {
    // SCCP says x=5, intervals say x>10 - SCCP should win
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_sccp_value("x".to_string(), LatticeValue::Constant(ConstValue::Int(5)));
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(10)));

    // Should be infeasible (5 > 10 is false)
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Infeasible);
}

#[test]
fn extreme_all_modules_active() {
    // Test with all modules processing simultaneously
    let mut checker = EnhancedConstraintChecker::new();

    // SCCP
    checker.add_sccp_value("i".to_string(), LatticeValue::Constant(ConstValue::Int(5)));

    // Intervals
    checker.add_condition(&PathCondition::new(
        "i".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(0)),
    ));
    checker.add_condition(&PathCondition::lt("i".to_string(), ConstValue::Int(10)));

    // String (different variable)
    checker.add_condition(&PathCondition::new(
        "len_password".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(8)),
    ));

    // Array (manual)
    checker.array_checker_mut().set_array_size("buffer".to_string(), 100);
    checker.array_checker_mut().add_index_constraint(
        "j".to_string(),
        &PathCondition::new(
            "j".to_string(),
            ComparisonOp::Ge,
            Some(ConstValue::Int(0)),
        ),
    );

    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn extreme_reset_and_reuse() {
    // Test reset functionality
    let mut checker = EnhancedConstraintChecker::new();

    // First use
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(20)));
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Infeasible);

    // Reset
    checker.reset();
    assert_eq!(checker.condition_count(), 0);

    // Second use - should be clean
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Corner Cases - Unusual Combinations
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn corner_empty_checker() {
    // No conditions added
    let checker = EnhancedConstraintChecker::new();

    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn corner_only_sccp() {
    // Only SCCP, no conditions
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_sccp_value("x".to_string(), LatticeValue::Constant(ConstValue::Int(42)));

    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn corner_sccp_top_value() {
    // SCCP Top value (non-constant)
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_sccp_value("x".to_string(), LatticeValue::Top);
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));

    // Should be feasible (Top means unknown, so we can't contradict)
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn corner_sccp_bottom_value() {
    // SCCP Bottom value (unreachable)
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_sccp_value("x".to_string(), LatticeValue::Bottom);
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));

    // Bottom means unreachable, so path might be infeasible
    // But our current implementation treats it as unknown
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn corner_duplicate_conditions() {
    // Same condition added multiple times
    let mut checker = EnhancedConstraintChecker::new();

    for _ in 0..10 {
        checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));
    }

    assert_eq!(checker.condition_count(), 10);
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn corner_eq_with_intervals() {
    // x == 7 combined with interval constraints
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::eq("x".to_string(), ConstValue::Int(7)));
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));

    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn corner_eq_contradiction() {
    // x == 7 && x == 10 - contradiction
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::eq("x".to_string(), ConstValue::Int(7)));
    checker.add_condition(&PathCondition::eq("x".to_string(), ConstValue::Int(10)));

    assert_eq!(checker.is_path_feasible(), PathFeasibility::Infeasible);
}

#[test]
fn corner_neq_with_eq() {
    // x == 5 && x != 5 - contradiction
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::eq("x".to_string(), ConstValue::Int(5)));
    checker.add_condition(&PathCondition::neq("x".to_string(), ConstValue::Int(5)));

    assert_eq!(checker.is_path_feasible(), PathFeasibility::Infeasible);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Regression Tests - Known Bug Scenarios
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn regression_gt_lt_ordering() {
    // Bug 4: x > 5 && x < 10 was incorrectly flagged as contradiction
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));

    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn regression_le_ge_boundary() {
    // x <= 10 && x >= 10 should be feasible (x == 10)
    let mut checker = EnhancedConstraintChecker::new();

    checker.add_condition(&PathCondition::new(
        "x".to_string(),
        ComparisonOp::Le,
        Some(ConstValue::Int(10)),
    ));
    checker.add_condition(&PathCondition::new(
        "x".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(10)),
    ));

    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn regression_string_solver_integer_vars() {
    // Bug 2: Integer variables shouldn't trigger string solver
    let mut checker = EnhancedConstraintChecker::new();

    // Variable "i" shouldn't go to string solver
    checker.add_condition(&PathCondition::new(
        "i".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(0)),
    ));

    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn regression_equality_bidirectional() {
    // Bug 1: Equality should work in both directions
    let mut prop = ConstraintPropagator::new();

    prop.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());

    assert!(prop.can_infer_eq("x", "y"));
    assert!(prop.can_infer_eq("y", "x")); // Both directions!
}
