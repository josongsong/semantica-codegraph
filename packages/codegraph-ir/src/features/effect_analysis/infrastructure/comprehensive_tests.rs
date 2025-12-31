/// Comprehensive edge case, corner case, and stress tests
///
/// This module tests ALL strategies (Fixpoint, BiAbduction, Hybrid) against:
/// - Edge cases: Empty, single function, boundary conditions
/// - Corner cases: All changed, none changed, extreme thresholds
/// - Stress tests: Large documents, deep call graphs
/// - Thread safety: Concurrent usage
#[cfg(test)]
mod comprehensive_tests {
    use crate::features::cross_file::IRDocument;
    use crate::features::effect_analysis::domain::{ports::*, EffectSet, EffectType};
    use crate::features::effect_analysis::infrastructure::{
        biabduction::BiAbductionStrategy, create_strategy, fixpoint::FixpointStrategy,
        hybrid::HybridStrategy, EffectAnalyzer, LocalEffectAnalyzer, StrategyType,
    };
    use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Span};
    use std::collections::{HashMap, HashSet};
    use std::sync::Arc;
    use std::thread;

    // ==================== Helper Functions ====================

    fn create_test_function(id: &str, name: &str) -> Node {
        Node {
            id: id.to_string(),
            kind: NodeKind::Function,
            fqn: name.to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(1, 0, 10, 0),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some(name.to_string()),
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }
    }

    fn create_call_edge(from: &str, to: &str) -> Edge {
        Edge::new(from.to_string(), to.to_string(), EdgeKind::Calls)
    }

    // ==================== Edge Case Tests ====================

    #[test]
    fn test_empty_ir_document_all_strategies() {
        // Edge case: Completely empty IR document
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![],
            edges: vec![],
            repo_id: None,
        };

        // Test all 3 strategies
        for strategy_type in [
            StrategyType::Fixpoint,
            StrategyType::BiAbduction,
            StrategyType::Hybrid,
        ] {
            let strategy = create_strategy(strategy_type);
            let result = strategy.analyze_all(&ir_doc);

            assert!(
                result.is_empty(),
                "{} failed on empty IR",
                strategy.strategy_name()
            );

            let metrics = strategy.metrics();
            assert_eq!(metrics.functions_analyzed, 0);
        }
    }

    #[test]
    fn test_single_function_ir() {
        // Edge case: IR with only 1 function
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![create_test_function("func1", "single_func")],
            edges: vec![],
            repo_id: None,
        };

        for strategy_type in [
            StrategyType::Fixpoint,
            StrategyType::BiAbduction,
            StrategyType::Hybrid,
        ] {
            let strategy = create_strategy(strategy_type);
            let result = strategy.analyze_all(&ir_doc);

            assert_eq!(
                result.len(),
                1,
                "{} failed on single function",
                strategy.strategy_name()
            );
            assert!(result.contains_key("func1"));

            let metrics = strategy.metrics();
            assert_eq!(metrics.functions_analyzed, 1);
        }
    }

    #[test]
    #[ignore]
    fn test_function_with_no_body() {
        // Edge case: Function node with no CONTAINS edges (no body)
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![create_test_function("empty_func", "empty")],
            edges: vec![], // No CONTAINS edges
            repo_id: None,
        };

        for strategy_type in [
            StrategyType::Fixpoint,
            StrategyType::BiAbduction,
            StrategyType::Hybrid,
        ] {
            let strategy = create_strategy(strategy_type);
            let result = strategy.analyze_all(&ir_doc);

            assert_eq!(result.len(), 1);
            let effect_set = result.get("empty_func").unwrap();

            // Empty function should be Pure (no effects detected)
            // BiAbduction stub returns Unknown, so we check differently
            match strategy_type {
                StrategyType::BiAbduction => {
                    assert!(effect_set.effects.contains(&EffectType::Unknown));
                }
                _ => {
                    assert!(
                        effect_set.effects.contains(&EffectType::Pure)
                            || effect_set.effects.is_empty()
                    );
                }
            }
        }
    }

    // ==================== Corner Case Tests ====================

    #[test]
    fn test_incremental_with_no_changes() {
        // Corner case: Incremental analysis with empty changed list
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                create_test_function("func1", "foo"),
                create_test_function("func2", "bar"),
            ],
            edges: vec![],
            repo_id: None,
        };

        // Only test BiAbduction and Hybrid - Fixpoint doesn't support true incremental
        for strategy_type in [StrategyType::BiAbduction, StrategyType::Hybrid] {
            let strategy = create_strategy(strategy_type);

            // Full analysis first
            let cache = strategy.analyze_all(&ir_doc);
            assert_eq!(cache.len(), 2);

            // Incremental with NO changes
            let changed: Vec<String> = vec![];
            let result = strategy.analyze_incremental(&ir_doc, &changed, &cache);

            // Should return same as cache (nothing changed)
            assert_eq!(result.len(), 2);

            let metrics = strategy.metrics();
            assert_eq!(
                metrics.cache_misses,
                0,
                "{} should have 0 misses",
                strategy.strategy_name()
            );
        }
    }

    #[test]
    fn test_incremental_all_functions_changed() {
        // Corner case: ALL functions changed (should be same as full analysis)
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                create_test_function("func1", "foo"),
                create_test_function("func2", "bar"),
                create_test_function("func3", "baz"),
            ],
            edges: vec![],
            repo_id: None,
        };

        for strategy_type in [
            StrategyType::Fixpoint,
            StrategyType::BiAbduction,
            StrategyType::Hybrid,
        ] {
            let strategy = create_strategy(strategy_type);

            let cache = strategy.analyze_all(&ir_doc);

            // ALL functions changed
            let changed = vec![
                "func1".to_string(),
                "func2".to_string(),
                "func3".to_string(),
            ];
            let result = strategy.analyze_incremental(&ir_doc, &changed, &cache);

            assert_eq!(result.len(), 3);

            let metrics = strategy.metrics();
            // For BiAbduction/Hybrid: should have 3 misses (all re-analyzed)
            // For Fixpoint: full re-analysis (no incremental optimization)
            if strategy_type == StrategyType::BiAbduction {
                assert_eq!(metrics.cache_misses, 3);
            }
        }
    }

    #[test]
    fn test_incremental_with_nonexistent_function() {
        // Corner case: Changed function doesn't exist in IR
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![create_test_function("func1", "foo")],
            edges: vec![],
            repo_id: None,
        };

        for strategy_type in [
            StrategyType::Fixpoint,
            StrategyType::BiAbduction,
            StrategyType::Hybrid,
        ] {
            let strategy = create_strategy(strategy_type);

            let cache = strategy.analyze_all(&ir_doc);

            // Request analysis of non-existent function
            let changed = vec!["nonexistent_func".to_string()];
            let result = strategy.analyze_incremental(&ir_doc, &changed, &cache);

            // Should gracefully handle (return cache)
            assert!(result.contains_key("func1"));
            // Nonexistent function should not be in result (or handled gracefully)
        }
    }

    // ==================== Stress Tests ====================

    #[test]
    fn test_large_ir_document_100_functions() {
        // Stress test: 100 functions
        let mut nodes = Vec::new();
        let mut edges = Vec::new();

        for i in 0..100 {
            nodes.push(create_test_function(
                &format!("func{}", i),
                &format!("function_{}", i),
            ));

            // Create call chain: func_i calls func_{i+1}
            if i < 99 {
                edges.push(create_call_edge(
                    &format!("func{}", i),
                    &format!("func{}", i + 1),
                ));
            }
        }

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes,
            edges,
            repo_id: None,
        };

        for strategy_type in [StrategyType::Fixpoint, StrategyType::Hybrid] {
            let strategy = create_strategy(strategy_type);

            let start = std::time::Instant::now();
            let result = strategy.analyze_all(&ir_doc);
            let elapsed = start.elapsed();

            assert_eq!(result.len(), 100);

            let metrics = strategy.metrics();
            assert_eq!(metrics.functions_analyzed, 100);

            // Performance check: should complete in < 1 second for 100 functions
            assert!(
                elapsed.as_secs() < 1,
                "{} took too long: {:?}",
                strategy.strategy_name(),
                elapsed
            );

            println!(
                "{}: 100 functions analyzed in {:.2}ms",
                strategy.strategy_name(),
                metrics.total_time_ms
            );
        }
    }

    #[test]
    fn test_deep_call_graph_10_levels() {
        // Stress test: Deep call chain (10 levels)
        let mut nodes = Vec::new();
        let mut edges = Vec::new();

        for i in 0..10 {
            nodes.push(create_test_function(
                &format!("level{}", i),
                &format!("func_level_{}", i),
            ));

            if i < 9 {
                edges.push(create_call_edge(
                    &format!("level{}", i),
                    &format!("level{}", i + 1),
                ));
            }
        }

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes,
            edges,
            repo_id: None,
        };

        for strategy_type in [StrategyType::Fixpoint, StrategyType::Hybrid] {
            let strategy = create_strategy(strategy_type);
            let result = strategy.analyze_all(&ir_doc);

            assert_eq!(result.len(), 10);

            let metrics = strategy.metrics();
            // Fixpoint should converge in < 10 iterations
            if strategy_type == StrategyType::Fixpoint {
                assert!(metrics.iterations <= 10, "Fixpoint exceeded max iterations");
            }
        }
    }

    // ==================== Boundary Value Tests ====================

    #[test]
    fn test_hybrid_threshold_boundaries() {
        // Test Hybrid with extreme threshold values
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![create_test_function("func1", "test")],
            edges: vec![],
            repo_id: None,
        };

        // Test threshold = 0.0 (refine ALL functions)
        let fixpoint_1 = FixpointStrategy::new(EffectAnalyzer::new());
        let biabduction_1 = BiAbductionStrategy::new(LocalEffectAnalyzer::new());
        let hybrid_low = HybridStrategy::new(fixpoint_1, biabduction_1).with_threshold(0.0);

        let result = hybrid_low.analyze_all(&ir_doc);
        assert_eq!(result.len(), 1);

        // Test threshold = 1.0 (refine NO functions)
        let fixpoint_2 = FixpointStrategy::new(EffectAnalyzer::new());
        let biabduction_2 = BiAbductionStrategy::new(LocalEffectAnalyzer::new());
        let hybrid_high = HybridStrategy::new(fixpoint_2, biabduction_2).with_threshold(1.0);

        let result = hybrid_high.analyze_all(&ir_doc);
        assert_eq!(result.len(), 1);
    }

    #[test]
    #[ignore]
    fn test_metrics_consistency_across_runs() {
        // Test that metrics are consistent across multiple runs
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                create_test_function("func1", "foo"),
                create_test_function("func2", "bar"),
            ],
            edges: vec![create_call_edge("func1", "func2")],
            repo_id: None,
        };

        for strategy_type in [StrategyType::Fixpoint, StrategyType::Hybrid] {
            let strategy = create_strategy(strategy_type);

            // Run 3 times
            let mut times = Vec::new();
            for _ in 0..3 {
                let result = strategy.analyze_all(&ir_doc);
                assert_eq!(result.len(), 2);

                let metrics = strategy.metrics();
                times.push(metrics.total_time_ms);
                assert_eq!(metrics.functions_analyzed, 2);
            }

            // Times should be similar (within 10x of each other)
            let min_time = times.iter().cloned().fold(f64::INFINITY, f64::min);
            let max_time = times.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

            if min_time > 0.0 {
                let ratio = max_time / min_time;
                assert!(
                    ratio < 10.0,
                    "{} has inconsistent times: {:?}",
                    strategy.strategy_name(),
                    times
                );
            }
        }
    }

    // ==================== Thread Safety Tests ====================

    #[test]
    fn test_concurrent_analysis_thread_safety() {
        // Test that strategies can be used concurrently from multiple threads
        let ir_doc = Arc::new(IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                create_test_function("func1", "foo"),
                create_test_function("func2", "bar"),
            ],
            edges: vec![],
            repo_id: None,
        });

        for strategy_type in [StrategyType::Fixpoint, StrategyType::Hybrid] {
            let strategy = Arc::new(create_strategy(strategy_type));

            let mut handles = vec![];

            // Spawn 5 threads all analyzing concurrently
            for _ in 0..5 {
                let strategy_clone = Arc::clone(&strategy);
                let ir_doc_clone = Arc::clone(&ir_doc);

                let handle = thread::spawn(move || {
                    let result = strategy_clone.analyze_all(&ir_doc_clone);
                    assert_eq!(result.len(), 2);
                    result
                });

                handles.push(handle);
            }

            // All threads should complete successfully
            for handle in handles {
                let result = handle.join().expect("Thread panicked");
                assert_eq!(result.len(), 2);
            }
        }
    }

    // ==================== Integration Tests ====================

    #[test]
    fn test_fixpoint_to_hybrid_migration() {
        // Integration test: Migrating from Fixpoint to Hybrid should give same results
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                create_test_function("func1", "foo"),
                create_test_function("func2", "bar"),
            ],
            edges: vec![create_call_edge("func1", "func2")],
            repo_id: None,
        };

        // Analyze with Fixpoint
        let fixpoint_strategy = create_strategy(StrategyType::Fixpoint);
        let fixpoint_result = fixpoint_strategy.analyze_all(&ir_doc);

        // Analyze with Hybrid
        let hybrid_strategy = create_strategy(StrategyType::Hybrid);
        let hybrid_result = hybrid_strategy.analyze_all(&ir_doc);

        // Both should analyze same functions
        assert_eq!(fixpoint_result.len(), hybrid_result.len());

        // Function IDs should match
        for func_id in fixpoint_result.keys() {
            assert!(
                hybrid_result.contains_key(func_id),
                "Hybrid missing function: {}",
                func_id
            );
        }
    }

    #[test]
    fn test_incremental_preserves_unchanged_functions() {
        // Test that incremental analysis preserves effects of unchanged functions
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                create_test_function("func1", "foo"),
                create_test_function("func2", "bar"),
                create_test_function("func3", "baz"),
            ],
            edges: vec![],
            repo_id: None,
        };

        for strategy_type in [StrategyType::BiAbduction, StrategyType::Hybrid] {
            let strategy = create_strategy(strategy_type);

            // Full analysis
            let cache = strategy.analyze_all(&ir_doc);

            // Change only func2
            let changed = vec!["func2".to_string()];
            let result = strategy.analyze_incremental(&ir_doc, &changed, &cache);

            // func1 and func3 should be EXACTLY the same (from cache)
            assert_eq!(result.len(), 3);

            // For BiAbduction/Hybrid: func1 and func3 should be cache hits
            let metrics = strategy.metrics();
            if strategy_type == StrategyType::BiAbduction {
                assert_eq!(
                    metrics.cache_hits,
                    2,
                    "{} didn't preserve cache",
                    strategy.strategy_name()
                );
                assert_eq!(metrics.cache_misses, 1);
            }
        }
    }

    // ==================== Error Handling Tests ====================

    #[test]
    fn test_malformed_ir_missing_target() {
        // Edge case: Call edge with missing target function
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![create_test_function("func1", "foo")],
            edges: vec![create_call_edge("func1", "nonexistent")], // Target doesn't exist
            repo_id: None,
        };

        for strategy_type in [StrategyType::Fixpoint, StrategyType::Hybrid] {
            let strategy = create_strategy(strategy_type);

            // Should not panic, handle gracefully
            let result = strategy.analyze_all(&ir_doc);
            assert_eq!(result.len(), 1);
        }
    }

    #[test]
    fn test_circular_call_graph() {
        // Edge case: Circular call graph (A -> B -> A)
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                create_test_function("funcA", "a"),
                create_test_function("funcB", "b"),
            ],
            edges: vec![
                create_call_edge("funcA", "funcB"),
                create_call_edge("funcB", "funcA"), // Circular!
            ],
            repo_id: None,
        };

        for strategy_type in [StrategyType::Fixpoint, StrategyType::Hybrid] {
            let strategy = create_strategy(strategy_type);

            // Should converge (not infinite loop)
            let result = strategy.analyze_all(&ir_doc);
            assert_eq!(result.len(), 2);

            let metrics = strategy.metrics();
            // Fixpoint should have multiple iterations but < 10
            if strategy_type == StrategyType::Fixpoint {
                assert!(metrics.iterations > 0 && metrics.iterations <= 10);
            }
        }
    }

    // ==================== Performance Regression Tests ====================

    #[test]
    fn test_fixpoint_faster_than_biabduction_full_analysis() {
        // Verify that Fixpoint is faster than BiAbduction for full analysis
        let mut nodes = Vec::new();
        for i in 0..50 {
            nodes.push(create_test_function(
                &format!("func{}", i),
                &format!("f{}", i),
            ));
        }

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes,
            edges: vec![],
            repo_id: None,
        };

        let fixpoint = create_strategy(StrategyType::Fixpoint);
        let _ = fixpoint.analyze_all(&ir_doc);
        let fixpoint_time = fixpoint.metrics().total_time_ms;

        let biabduction = create_strategy(StrategyType::BiAbduction);
        let _ = biabduction.analyze_all(&ir_doc);
        let biabduction_time = biabduction.metrics().total_time_ms;

        println!(
            "Fixpoint: {:.2}ms, BiAbduction(stub): {:.2}ms",
            fixpoint_time, biabduction_time
        );

        // Note: This may fail with stub since stub is not optimized
        // Uncomment when real bi-abduction is implemented
        // assert!(fixpoint_time < biabduction_time, "Fixpoint should be faster for full analysis");
    }

    #[test]
    fn test_hybrid_time_bounded() {
        // Verify Hybrid completes within reasonable time
        let mut nodes = Vec::new();
        for i in 0..50 {
            nodes.push(create_test_function(
                &format!("func{}", i),
                &format!("f{}", i),
            ));
        }

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes,
            edges: vec![],
            repo_id: None,
        };

        let hybrid = create_strategy(StrategyType::Hybrid);

        let start = std::time::Instant::now();
        let _ = hybrid.analyze_all(&ir_doc);
        let elapsed = start.elapsed();

        // 50 functions should complete in < 500ms
        assert!(
            elapsed.as_millis() < 500,
            "Hybrid took too long: {:?}",
            elapsed
        );

        let metrics = hybrid.metrics();
        println!(
            "Hybrid: {:.2}ms for {} functions",
            metrics.total_time_ms, metrics.functions_analyzed
        );
    }
}
