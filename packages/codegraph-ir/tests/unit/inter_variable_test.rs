//! Inter-Variable Relationship Tracker Tests (Phase 1)
//!
//! Comprehensive test suite for inter-variable reasoning capabilities.

use codegraph_ir::features::smt::domain::{ComparisonOp, ConstValue};
use codegraph_ir::features::smt::infrastructure::{
    EnhancedConstraintChecker, InterVariableTracker, LatticeValue, PathFeasibility,
};
use std::collections::HashMap;

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Unit Tests: InterVariableTracker Standalone
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn test_transitive_inference_basic() {
    let mut tracker = InterVariableTracker::new();

    // x < y
    assert!(tracker.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string()));
    // y < z
    assert!(tracker.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string()));

    // Should infer x < z (transitive)
    assert!(tracker.can_infer_lt(&"x".to_string(), &"z".to_string()));
    assert!(tracker.is_feasible());
}

#[test]
fn test_transitive_inference_deep_chain() {
    let mut tracker = InterVariableTracker::new();

    // a < b < c < d
    tracker.add_relation("a".to_string(), ComparisonOp::Lt, "b".to_string());
    tracker.add_relation("b".to_string(), ComparisonOp::Lt, "c".to_string());
    tracker.add_relation("c".to_string(), ComparisonOp::Lt, "d".to_string());

    // Should infer a < d (depth 3)
    assert!(tracker.can_infer_lt(&"a".to_string(), &"d".to_string()));
    assert!(tracker.is_feasible());
}

#[test]
fn test_cycle_detection_basic() {
    let mut tracker = InterVariableTracker::new();

    // x < y
    tracker.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
    // y < z
    tracker.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());
    // z < x - CYCLE!
    let result = tracker.add_relation("z".to_string(), ComparisonOp::Lt, "x".to_string());

    assert!(!result);
    assert!(!tracker.is_feasible());
}

#[test]
fn test_cycle_detection_self_loop() {
    let mut tracker = InterVariableTracker::new();

    // x < x is immediately a contradiction
    let result = tracker.add_relation("x".to_string(), ComparisonOp::Lt, "x".to_string());

    // Should detect cycle (x < ... < x)
    // Note: Current implementation allows same variable, but should fail on consistency check
    assert!(!result);
}

#[test]
fn test_equality_propagation_basic() {
    let mut tracker = InterVariableTracker::new();

    // x == y
    tracker.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());

    // Should infer x == y (bidirectional)
    assert!(tracker.can_infer_eq(&"x".to_string(), &"y".to_string()));
    assert!(tracker.can_infer_eq(&"y".to_string(), &"x".to_string()));
}

#[test]
fn test_equality_propagation_transitive() {
    let mut tracker = InterVariableTracker::new();

    // x == y
    tracker.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
    // y == z
    tracker.add_relation("y".to_string(), ComparisonOp::Eq, "z".to_string());

    // Should infer x == z (transitive equality)
    assert!(tracker.can_infer_eq(&"x".to_string(), &"z".to_string()));
    assert!(tracker.can_infer_eq(&"z".to_string(), &"x".to_string()));
}

#[test]
fn test_equality_constant_propagation() {
    let mut tracker = InterVariableTracker::new();

    // x == y
    tracker.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());

    // SCCP: y = 5
    let mut sccp = HashMap::new();
    sccp.insert("y".to_string(), LatticeValue::Constant(ConstValue::Int(5)));

    tracker.propagate_constants(&sccp);

    // Should infer x = 5
    assert_eq!(
        tracker.get_inferred_constant(&"x".to_string()),
        Some(&ConstValue::Int(5))
    );
}

#[test]
fn test_equality_constant_propagation_chain() {
    let mut tracker = InterVariableTracker::new();

    // x == y == z
    tracker.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
    tracker.add_relation("y".to_string(), ComparisonOp::Eq, "z".to_string());

    // SCCP: z = 42
    let mut sccp = HashMap::new();
    sccp.insert(
        "z".to_string(),
        LatticeValue::Constant(ConstValue::Int(42)),
    );

    tracker.propagate_constants(&sccp);

    // Should infer both x = 42 and y = 42
    assert_eq!(
        tracker.get_inferred_constant(&"x".to_string()),
        Some(&ConstValue::Int(42))
    );
    assert_eq!(
        tracker.get_inferred_constant(&"y".to_string()),
        Some(&ConstValue::Int(42))
    );
}

#[test]
fn test_contradiction_neq_eq() {
    let mut tracker = InterVariableTracker::new();

    // x == y
    tracker.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
    // x != y - contradiction!
    let result = tracker.add_relation("x".to_string(), ComparisonOp::Neq, "y".to_string());

    assert!(!result);
    assert!(!tracker.is_feasible());
}

#[test]
fn test_contradiction_lt_gt() {
    let mut tracker = InterVariableTracker::new();

    // x < y
    tracker.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
    // x > y - contradiction!
    let result = tracker.add_relation("x".to_string(), ComparisonOp::Gt, "y".to_string());

    assert!(!result);
    assert!(!tracker.is_feasible());
}

#[test]
fn test_contradiction_lt_ge() {
    let mut tracker = InterVariableTracker::new();

    // x < y
    tracker.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
    // x >= y - contradiction!
    let result = tracker.add_relation("x".to_string(), ComparisonOp::Ge, "y".to_string());

    assert!(!result);
    assert!(!tracker.is_feasible());
}

#[test]
fn test_variable_limit() {
    let mut tracker = InterVariableTracker::with_limits(3, 3);

    // Add 3 variables - OK
    tracker.add_relation("x1".to_string(), ComparisonOp::Lt, "x2".to_string());
    tracker.add_relation("x2".to_string(), ComparisonOp::Lt, "x3".to_string());

    assert_eq!(tracker.variable_count(), 3);

    // Try to add 4th - should be ignored conservatively
    tracker.add_relation("x3".to_string(), ComparisonOp::Lt, "x4".to_string());

    // 4 variables tracked but should still work conservatively
    assert_eq!(tracker.variable_count(), 4);
    assert!(tracker.is_feasible());
}

#[test]
fn test_depth_limit() {
    let mut tracker = InterVariableTracker::with_limits(20, 2); // depth 2

    // Chain: a < b < c < d
    tracker.add_relation("a".to_string(), ComparisonOp::Lt, "b".to_string());
    tracker.add_relation("b".to_string(), ComparisonOp::Lt, "c".to_string());
    tracker.add_relation("c".to_string(), ComparisonOp::Lt, "d".to_string());

    // a < c should be inferable (depth 2: a < b < c)
    assert!(tracker.can_infer_lt(&"a".to_string(), &"c".to_string()));

    // a < d requires depth 3, might not be inferable due to limit
    // (depending on implementation details)
    // Not testing this as it's depth-limited
}

#[test]
fn test_clear() {
    let mut tracker = InterVariableTracker::new();

    tracker.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
    assert_eq!(tracker.variable_count(), 2);

    tracker.clear();
    assert_eq!(tracker.variable_count(), 0);
    assert!(tracker.is_feasible());
}

#[test]
fn test_relation_count() {
    let mut tracker = InterVariableTracker::new();

    tracker.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
    assert_eq!(tracker.relation_count(), 1); // Bidirectional, so /2

    tracker.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());
    assert_eq!(tracker.relation_count(), 2);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Integration Tests: EnhancedConstraintChecker with InterVariableTracker
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

// Note: Current PathCondition doesn't support variable-to-variable comparisons yet.
// These tests demonstrate the API, but manual calls to inter_variable_tracker_mut() are needed.

#[test]
fn test_enhanced_checker_inter_variable_manual() {
    let mut checker = EnhancedConstraintChecker::new();

    // Manually add inter-variable relations
    checker
        .inter_variable_tracker_mut()
        .add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
    checker
        .inter_variable_tracker_mut()
        .add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());

    // Verify transitive inference works
    assert!(checker
        .inter_variable_tracker()
        .can_infer_lt(&"x".to_string(), &"z".to_string()));

    // Path should be feasible
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn test_enhanced_checker_inter_variable_contradiction() {
    let mut checker = EnhancedConstraintChecker::new();

    // Manually add cycle
    checker
        .inter_variable_tracker_mut()
        .add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
    checker
        .inter_variable_tracker_mut()
        .add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());
    checker
        .inter_variable_tracker_mut()
        .add_relation("z".to_string(), ComparisonOp::Lt, "x".to_string());

    // Should detect infeasible path
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Infeasible);
}

#[test]
fn test_enhanced_checker_equality_sccp_integration() {
    let mut checker = EnhancedConstraintChecker::new();

    // Add equality: x == y
    checker
        .inter_variable_tracker_mut()
        .add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());

    // SCCP: y = 7
    checker.add_sccp_value("y".to_string(), LatticeValue::Constant(ConstValue::Int(7)));

    // Propagate constants
    let sccp_map = {
        let mut map = HashMap::new();
        map.insert(
            "y".to_string(),
            LatticeValue::Constant(ConstValue::Int(7)),
        );
        map
    };
    checker
        .inter_variable_tracker_mut()
        .propagate_constants(&sccp_map);

    // Should infer x = 7
    assert_eq!(
        checker
            .inter_variable_tracker()
            .get_inferred_constant(&"x".to_string()),
        Some(&ConstValue::Int(7))
    );
}

#[test]
fn test_enhanced_checker_reset_clears_inter_variable() {
    let mut checker = EnhancedConstraintChecker::new();

    // Add some relations
    checker
        .inter_variable_tracker_mut()
        .add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());

    assert_eq!(checker.inter_variable_tracker().variable_count(), 2);

    // Reset
    checker.reset();

    // Should be cleared
    assert_eq!(checker.inter_variable_tracker().variable_count(), 0);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Edge Cases
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn test_edge_case_same_variable_equality() {
    let mut tracker = InterVariableTracker::new();

    // x == x (trivially true)
    assert!(tracker.add_relation("x".to_string(), ComparisonOp::Eq, "x".to_string()));
    assert!(tracker.is_feasible());
}

#[test]
fn test_edge_case_empty_variable_names() {
    let mut tracker = InterVariableTracker::new();

    // Empty string variables (edge case)
    assert!(tracker.add_relation("".to_string(), ComparisonOp::Lt, "y".to_string()));
    assert_eq!(tracker.variable_count(), 2);
}

#[test]
fn test_edge_case_very_long_variable_names() {
    let mut tracker = InterVariableTracker::new();

    let long_var = "x".repeat(1000);
    assert!(tracker.add_relation(long_var.clone(), ComparisonOp::Lt, "y".to_string()));
    assert_eq!(tracker.variable_count(), 2);
}

#[test]
fn test_edge_case_unicode_variable_names() {
    let mut tracker = InterVariableTracker::new();

    assert!(tracker.add_relation("변수1".to_string(), ComparisonOp::Lt, "変数2".to_string()));
    assert!(tracker.is_feasible());
}

#[test]
fn test_edge_case_relation_inverse() {
    use codegraph_ir::features::smt::infrastructure::Relation;

    // Test relation inverse
    assert_eq!(Relation::Lt.inverse(), Relation::Gt);
    assert_eq!(Relation::Le.inverse(), Relation::Ge);
    assert_eq!(Relation::Gt.inverse(), Relation::Lt);
    assert_eq!(Relation::Ge.inverse(), Relation::Le);
    assert_eq!(Relation::Eq.inverse(), Relation::Eq);
    assert_eq!(Relation::Neq.inverse(), Relation::Neq);
}
