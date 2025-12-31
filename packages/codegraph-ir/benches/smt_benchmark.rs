//! SMT Engine Performance Benchmarks
//!
//! Criterion-based benchmarks to measure actual performance

use codegraph_ir::features::smt::domain::{ComparisonOp, ConstValue, PathCondition};
use codegraph_ir::features::smt::infrastructure::{
    ArrayBoundsChecker, ConstraintPropagator, EnhancedConstraintChecker, IntervalTracker,
    LatticeValue, LightweightConstraintChecker, StringConstraintSolver,
};
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// IntervalTracker Benchmarks
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

fn bench_interval_tracker(c: &mut Criterion) {
    let mut group = c.benchmark_group("interval_tracker");

    for num_conditions in [5, 10, 20, 50].iter() {
        group.bench_with_input(
            BenchmarkId::from_parameter(num_conditions),
            num_conditions,
            |b, &num| {
                b.iter(|| {
                    let mut tracker = IntervalTracker::new();

                    for i in 0..num {
                        tracker.add_constraint(&PathCondition::gt(
                            format!("x{}", i),
                            ConstValue::Int(black_box(i as i64)),
                        ));
                        tracker.add_constraint(&PathCondition::lt(
                            format!("x{}", i),
                            ConstValue::Int(black_box((i + 100) as i64)),
                        ));
                    }

                    black_box(tracker.is_feasible())
                });
            },
        );
    }

    group.finish();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ConstraintPropagator Benchmarks
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

fn bench_constraint_propagator(c: &mut Criterion) {
    let mut group = c.benchmark_group("constraint_propagator");

    // Transitive chain: x0 < x1 < x2 < ... < xN
    for chain_length in [5, 10, 20].iter() {
        group.bench_with_input(
            BenchmarkId::new("transitive_chain", chain_length),
            chain_length,
            |b, &len| {
                b.iter(|| {
                    let mut prop = ConstraintPropagator::new();

                    // Build chain
                    for i in 0..len {
                        prop.add_relation(
                            format!("x{}", i),
                            ComparisonOp::Lt,
                            format!("x{}", i + 1),
                        );
                    }

                    // Query longest inference
                    black_box(prop.can_infer_lt(&format!("x{}", 0), &format!("x{}", len)))
                });
            },
        );
    }

    group.finish();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// StringConstraintSolver Benchmarks
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

fn bench_string_solver(c: &mut Criterion) {
    let mut group = c.benchmark_group("string_solver");

    for num_vars in [10, 20, 50].iter() {
        group.bench_with_input(
            BenchmarkId::from_parameter(num_vars),
            num_vars,
            |b, &num| {
                b.iter(|| {
                    let mut solver = StringConstraintSolver::new();

                    for i in 0..num {
                        solver.add_length_constraint(
                            format!("s{}", i),
                            ComparisonOp::Ge,
                            black_box(i),
                        );
                        solver.add_length_constraint(
                            format!("s{}", i),
                            ComparisonOp::Le,
                            black_box(i + 100),
                        );
                    }

                    black_box(solver.is_feasible())
                });
            },
        );
    }

    group.finish();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ArrayBoundsChecker Benchmarks
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

fn bench_array_bounds_checker(c: &mut Criterion) {
    let mut group = c.benchmark_group("array_bounds_checker");

    group.bench_function("constant_access_100_arrays", |b| {
        b.iter(|| {
            let mut checker = ArrayBoundsChecker::new();

            // Create 100 arrays
            for i in 0..100 {
                checker.set_array_size(format!("arr{}", i), black_box(1000));
            }

            // Check 100 accesses
            for i in 0..100 {
                black_box(checker.is_access_safe(&format!("arr{}", i), black_box(i)));
            }
        });
    });

    group.bench_function("symbolic_access_50_indices", |b| {
        b.iter(|| {
            let mut checker = ArrayBoundsChecker::new();

            // Create 50 arrays with symbolic indices
            for i in 0..50 {
                checker.set_array_size(format!("arr{}", i), 100);

                checker.add_index_constraint(
                    format!("i{}", i),
                    &PathCondition::new(
                        format!("i{}", i),
                        ComparisonOp::Ge,
                        Some(ConstValue::Int(0)),
                    ),
                );

                checker.add_index_constraint(
                    format!("i{}", i),
                    &PathCondition::lt(format!("i{}", i), ConstValue::Int(100)),
                );

                black_box(
                    checker.is_symbolic_access_safe(&format!("arr{}", i), &format!("i{}", i)),
                );
            }
        });
    });

    group.finish();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// EnhancedConstraintChecker (v2) Benchmarks
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

fn bench_enhanced_checker_v2(c: &mut Criterion) {
    let mut group = c.benchmark_group("enhanced_checker_v2");

    for num_conditions in [10, 20, 50].iter() {
        group.bench_with_input(
            BenchmarkId::from_parameter(num_conditions),
            num_conditions,
            |b, &num| {
                b.iter(|| {
                    let mut checker = EnhancedConstraintChecker::new();

                    // Add SCCP values
                    for i in 0..num {
                        checker.add_sccp_value(
                            format!("x{}", i),
                            LatticeValue::Constant(ConstValue::Int(black_box(i as i64))),
                        );
                    }

                    // Add interval conditions
                    for i in 0..num {
                        checker.add_condition(&PathCondition::gt(
                            format!("x{}", i),
                            ConstValue::Int(black_box((i as i64) - 10)),
                        ));
                        checker.add_condition(&PathCondition::lt(
                            format!("x{}", i),
                            ConstValue::Int(black_box((i as i64) + 10)),
                        ));
                    }

                    black_box(checker.is_path_feasible())
                });
            },
        );
    }

    group.finish();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// v1 vs v2 Comparison Benchmarks
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

fn bench_v1_vs_v2_comparison(c: &mut Criterion) {
    let mut group = c.benchmark_group("v1_vs_v2");

    // v1 (LightweightConstraintChecker)
    group.bench_function("v1_10_conditions", |b| {
        b.iter(|| {
            let mut checker = LightweightConstraintChecker::new();

            for i in 0..10 {
                checker.add_sccp_value(
                    format!("x{}", i),
                    LatticeValue::Constant(ConstValue::Int(black_box(i as i64))),
                );
            }

            let conditions: Vec<PathCondition> = (0..10)
                .map(|i| PathCondition::lt(format!("x{}", i), ConstValue::Int(100)))
                .collect();

            black_box(checker.is_path_feasible(&conditions))
        });
    });

    // v2 (EnhancedConstraintChecker) - Same 10 conditions
    group.bench_function("v2_10_conditions", |b| {
        b.iter(|| {
            let mut checker = EnhancedConstraintChecker::new();

            for i in 0..10 {
                checker.add_sccp_value(
                    format!("x{}", i),
                    LatticeValue::Constant(ConstValue::Int(black_box(i as i64))),
                );
                checker.add_condition(&PathCondition::lt(format!("x{}", i), ConstValue::Int(100)));
            }

            black_box(checker.is_path_feasible())
        });
    });

    // v2 with 50 conditions (beyond v1's capacity)
    group.bench_function("v2_50_conditions", |b| {
        b.iter(|| {
            let mut checker = EnhancedConstraintChecker::new();

            for i in 0..50 {
                checker.add_sccp_value(
                    format!("x{}", i),
                    LatticeValue::Constant(ConstValue::Int(black_box(i as i64))),
                );
                checker.add_condition(&PathCondition::lt(format!("x{}", i), ConstValue::Int(100)));
            }

            black_box(checker.is_path_feasible())
        });
    });

    group.finish();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Real-World Scenario Benchmarks
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

fn bench_real_world_scenarios(c: &mut Criterion) {
    let mut group = c.benchmark_group("real_world");

    // Taint analysis path checking
    group.bench_function("taint_path_check", |b| {
        b.iter(|| {
            let mut checker = EnhancedConstraintChecker::new();

            // User input range
            checker.add_condition(&PathCondition::new(
                "input".to_string(),
                ComparisonOp::Ge,
                Some(ConstValue::Int(black_box(-100))),
            ));
            checker.add_condition(&PathCondition::new(
                "input".to_string(),
                ComparisonOp::Le,
                Some(ConstValue::Int(black_box(100))),
            ));

            // Sanitizer checks
            checker.add_condition(&PathCondition::new(
                "input".to_string(),
                ComparisonOp::Ge,
                Some(ConstValue::Int(0)),
            ));

            black_box(checker.is_path_feasible())
        });
    });

    // Buffer overflow check
    group.bench_function("buffer_overflow_check", |b| {
        b.iter(|| {
            let mut checker = EnhancedConstraintChecker::new();

            checker
                .array_checker_mut()
                .set_array_size("buffer".to_string(), 1000);

            checker.array_checker_mut().add_index_constraint(
                "i".to_string(),
                &PathCondition::new("i".to_string(), ComparisonOp::Ge, Some(ConstValue::Int(0))),
            );

            checker.array_checker_mut().add_index_constraint(
                "i".to_string(),
                &PathCondition::lt("i".to_string(), ConstValue::Int(1000)),
            );

            black_box(
                checker
                    .array_checker()
                    .is_symbolic_access_safe(&"buffer".to_string(), &"i".to_string()),
            )
        });
    });

    // XSS prevention check
    group.bench_function("xss_prevention_check", |b| {
        b.iter(|| {
            let mut checker = EnhancedConstraintChecker::new();

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

            black_box(checker.string_solver().is_feasible())
        });
    });

    group.finish();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Criterion Configuration
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

criterion_group!(
    benches,
    bench_interval_tracker,
    bench_constraint_propagator,
    bench_string_solver,
    bench_array_bounds_checker,
    bench_enhanced_checker_v2,
    bench_v1_vs_v2_comparison,
    bench_real_world_scenarios,
);

criterion_main!(benches);
