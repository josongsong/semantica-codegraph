//! SMT Engine Integration Tests
//!
//! 독립 테스트 파일 - 다른 모듈 의존성 없이 SMT 엔진만 테스트

use codegraph_ir::features::smt::domain::{ComparisonOp, ConstValue, PathCondition};
use codegraph_ir::features::smt::infrastructure::{
    ArrayBoundsChecker, ConstraintPropagator, EnhancedConstraintChecker, IntInterval,
    IntervalTracker, LatticeValue, PathFeasibility, StringConstraintSolver, StringPattern,
};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// IntervalTracker Tests
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn integration_interval_tracker_basic() {
    let mut tracker = IntervalTracker::new();

    // x > 5
    assert!(tracker.add_constraint(&PathCondition::gt(
        "x".to_string(),
        ConstValue::Int(5)
    )));

    // x < 10
    assert!(tracker.add_constraint(&PathCondition::lt(
        "x".to_string(),
        ConstValue::Int(10)
    )));

    assert!(tracker.is_feasible());

    let interval = tracker.get_interval(&"x".to_string()).unwrap();
    assert!(interval.contains(7)); // 5 < 7 < 10
    assert!(!interval.contains(5)); // 5 not in (5, 10)
    assert!(!interval.contains(10)); // 10 not in (5, 10)
}

#[test]
fn integration_interval_tracker_contradiction() {
    let mut tracker = IntervalTracker::new();

    // x < 5
    tracker.add_constraint(&PathCondition::lt("x".to_string(), ConstValue::Int(5)));

    // x > 10 (contradiction)
    let result = tracker.add_constraint(&PathCondition::gt("x".to_string(), ConstValue::Int(10)));

    assert!(!result); // Should detect contradiction
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ConstraintPropagator Tests
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn integration_constraint_propagator_transitive() {
    let mut prop = ConstraintPropagator::new();

    // x < y
    prop.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
    // y < z
    prop.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());

    // Should infer: x < z
    assert!(prop.can_infer_lt("x", "z"));
}

#[test]
fn integration_constraint_propagator_equality() {
    let mut prop = ConstraintPropagator::new();

    // x == y
    prop.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
    // y == z
    prop.add_relation("y".to_string(), ComparisonOp::Eq, "z".to_string());

    // x == y == z
    assert!(prop.can_infer_eq("x", "z"));
}

#[test]
fn integration_constraint_propagator_cycle_detection() {
    let mut prop = ConstraintPropagator::new();

    // x < y < z
    prop.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
    prop.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());

    // z < x (creates cycle!)
    let result = prop.add_relation("z".to_string(), ComparisonOp::Lt, "x".to_string());

    assert!(!result); // Should detect cycle
    assert!(prop.has_contradiction());
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// StringConstraintSolver Tests
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn integration_string_solver_password_length() {
    let mut solver = StringConstraintSolver::new();

    // len(password) >= 8
    solver.add_length_constraint("password".to_string(), ComparisonOp::Ge, 8);

    // len(password) <= 20
    solver.add_length_constraint("password".to_string(), ComparisonOp::Le, 20);

    assert_eq!(solver.min_length(&"password".to_string()), Some(8));
    assert_eq!(solver.max_length(&"password".to_string()), Some(20));
    assert!(!solver.can_be_empty(&"password".to_string()));
}

#[test]
fn integration_string_solver_contradiction() {
    let mut solver = StringConstraintSolver::new();

    // len(s) < 5
    solver.add_length_constraint("s".to_string(), ComparisonOp::Lt, 5);

    // len(s) > 10 (contradiction)
    let result = solver.add_length_constraint("s".to_string(), ComparisonOp::Gt, 10);

    assert!(!result);
    assert!(!solver.is_feasible());
}

#[test]
fn integration_string_solver_pattern_contradiction() {
    let mut solver = StringConstraintSolver::new();

    let pattern = StringPattern::Contains("test".to_string());

    // Must contain "test"
    solver.add_required_pattern("s".to_string(), pattern.clone());

    // Must NOT contain "test" (contradiction)
    solver.add_forbidden_pattern("s".to_string(), pattern);

    assert!(!solver.is_feasible());
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ArrayBoundsChecker Tests
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn integration_array_bounds_safe_access() {
    let mut checker = ArrayBoundsChecker::new();

    // arr has size 10
    checker.set_array_size("arr".to_string(), 10);

    // arr[0..9] is safe
    assert!(checker.is_access_safe(&"arr".to_string(), 0));
    assert!(checker.is_access_safe(&"arr".to_string(), 9));

    // arr[-1] and arr[10] are unsafe
    assert!(!checker.is_access_safe(&"arr".to_string(), -1));
    assert!(!checker.is_access_safe(&"arr".to_string(), 10));
}

#[test]
fn integration_array_bounds_symbolic_access() {
    let mut checker = ArrayBoundsChecker::new();

    checker.set_array_size("arr".to_string(), 10);

    // i >= 0
    checker.add_index_constraint(
        "i".to_string(),
        &PathCondition::new(
            "i".to_string(),
            ComparisonOp::Ge,
            Some(ConstValue::Int(0)),
        ),
    );

    // i < 10
    checker.add_index_constraint(
        "i".to_string(),
        &PathCondition::lt("i".to_string(), ConstValue::Int(10)),
    );

    // arr[i] is safe
    assert!(checker.is_symbolic_access_safe(&"arr".to_string(), &"i".to_string()));
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// EnhancedConstraintChecker Integration Tests
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn integration_enhanced_checker_sccp_and_intervals() {
    let mut checker = EnhancedConstraintChecker::new();

    // SCCP: x = 7
    checker.add_sccp_value("x".to_string(), LatticeValue::Constant(ConstValue::Int(7)));

    // Interval: x > 5
    checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));

    // Interval: x < 10
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));

    // All consistent: x = 7, 5 < x < 10
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn integration_enhanced_checker_contradiction() {
    let mut checker = EnhancedConstraintChecker::new();

    // x < 10
    checker.add_condition(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));

    // x > 20 (contradiction)
    let result = checker.add_condition(&PathCondition::gt("x".to_string(), ConstValue::Int(20)));

    assert!(!result);
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Infeasible);
}

#[test]
fn integration_enhanced_checker_capacity() {
    let mut checker = EnhancedConstraintChecker::new();

    // Add 50 conditions (v1 max was 10)
    for i in 0..50 {
        let var = format!("x{}", i);
        checker.add_condition(&PathCondition::lt(var, ConstValue::Int(100)));
    }

    assert_eq!(checker.condition_count(), 50);
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);
}

#[test]
fn integration_enhanced_checker_multi_module() {
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

    // String
    checker.add_condition(&PathCondition::new(
        "len_s".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(1)),
    ));

    // All modules working together
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);

    // Verify elapsed time < 1ms
    let elapsed = checker.elapsed_us();
    println!("Elapsed time: {} μs", elapsed);
    assert!(elapsed < 1000); // < 1ms = 1000μs
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Real-World Scenario Tests
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[test]
fn scenario_taint_analysis_false_positive_reduction() {
    let mut checker = EnhancedConstraintChecker::new();

    // User input: -10 <= input <= 10
    checker.add_condition(&PathCondition::new(
        "input".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(-10)),
    ));
    checker.add_condition(&PathCondition::new(
        "input".to_string(),
        ComparisonOp::Le,
        Some(ConstValue::Int(10)),
    ));

    // Sanitizer check: input >= 0
    checker.add_condition(&PathCondition::new(
        "input".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(0)),
    ));

    // Path should be feasible: 0 <= input <= 10
    assert_eq!(checker.is_path_feasible(), PathFeasibility::Feasible);

    // Now add impossible path: input < 0
    let mut checker2 = EnhancedConstraintChecker::new();
    checker2.add_condition(&PathCondition::new(
        "input".to_string(),
        ComparisonOp::Ge,
        Some(ConstValue::Int(0)),
    ));
    checker2.add_condition(&PathCondition::lt("input".to_string(), ConstValue::Int(0)));

    // Should detect contradiction
    assert_eq!(
        checker2.is_path_feasible(),
        PathFeasibility::Infeasible
    );
}

#[test]
fn scenario_buffer_overflow_prevention() {
    let mut checker = EnhancedConstraintChecker::new();

    // Array size: 100
    checker.array_checker_mut().set_array_size("buffer".to_string(), 100);

    // Index: 0 <= i < 100
    checker.array_checker_mut().add_index_constraint(
        "i".to_string(),
        &PathCondition::new(
            "i".to_string(),
            ComparisonOp::Ge,
            Some(ConstValue::Int(0)),
        ),
    );
    checker.array_checker_mut().add_index_constraint(
        "i".to_string(),
        &PathCondition::lt("i".to_string(), ConstValue::Int(100)),
    );

    // buffer[i] is safe
    assert!(
        checker
            .array_checker()
            .is_symbolic_access_safe(&"buffer".to_string(), &"i".to_string())
    );

    // buffer[150] is unsafe
    assert!(!checker.array_checker().is_access_safe(&"buffer".to_string(), 150));
}

#[test]
fn scenario_xss_prevention() {
    let mut checker = EnhancedConstraintChecker::new();

    // Input length: 1 <= len(input) <= 1000
    checker.string_solver_mut().add_length_constraint(
        "input".to_string(),
        ComparisonOp::Ge,
        1,
    );
    checker.string_solver_mut().add_length_constraint(
        "input".to_string(),
        ComparisonOp::Le,
        1000,
    );

    // Input must not contain "<script>"
    checker.string_solver_mut().add_forbidden_pattern(
        "input".to_string(),
        StringPattern::Contains("<script>".to_string()),
    );

    // Verify constraints
    assert!(!checker.string_solver().can_be_empty(&"input".to_string()));
    assert!(checker
        .string_solver()
        .cannot_contain(&"input".to_string(), "<script>"));
}
