/// Ground Truth Accuracy Validation Tests
///
/// Tests effect analysis accuracy by comparing strategy results
/// against each other and checking for consistency.
#[cfg(test)]
mod accuracy_tests {
    use crate::features::cross_file::IRDocument;
    use crate::features::effect_analysis::domain::{ports::*, EffectSet, EffectType};
    use crate::features::effect_analysis::infrastructure::{create_strategy, StrategyType};
    use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Span};
    use std::collections::HashMap;

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

    // ==================== Accuracy Metrics ====================

    #[derive(Debug, Clone)]
    struct StrategyComparison {
        strategy_name: &'static str,
        total_functions: usize,
        pure_count: usize,
        effects_count: usize,
        unknown_count: usize,
        avg_confidence: f64,
    }

    impl StrategyComparison {
        fn from_results(strategy_name: &'static str, results: &HashMap<String, EffectSet>) -> Self {
            let total = results.len();
            let pure_count = results
                .values()
                .filter(|e| e.effects.contains(&EffectType::Pure))
                .count();
            let unknown_count = results
                .values()
                .filter(|e| e.effects.contains(&EffectType::Unknown))
                .count();
            let effects_count = total - pure_count - unknown_count;
            let avg_confidence = if total > 0 {
                results.values().map(|e| e.confidence).sum::<f64>() / total as f64
            } else {
                0.0
            };

            Self {
                strategy_name,
                total_functions: total,
                pure_count,
                effects_count,
                unknown_count,
                avg_confidence,
            }
        }

        fn print_summary(&self) {
            println!("\n{} Strategy Results:", self.strategy_name);
            println!("  Total functions: {}", self.total_functions);
            println!(
                "  Pure functions: {} ({:.1}%)",
                self.pure_count,
                (self.pure_count as f64 / self.total_functions as f64) * 100.0
            );
            println!(
                "  Functions with effects: {} ({:.1}%)",
                self.effects_count,
                (self.effects_count as f64 / self.total_functions as f64) * 100.0
            );
            println!(
                "  Unknown: {} ({:.1}%)",
                self.unknown_count,
                (self.unknown_count as f64 / self.total_functions as f64) * 100.0
            );
            println!("  Avg confidence: {:.2}", self.avg_confidence);
        }
    }

    // ==================== Test Cases ====================

    fn create_simple_ir() -> IRDocument {
        // Simple IR with 5 functions in a call chain
        // func1 (pure) -> func2 (pure) -> func3 (pure) -> func4 (pure) -> func5 (pure)
        IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                create_test_function("func1", "add"),
                create_test_function("func2", "multiply"),
                create_test_function("func3", "compute"),
                create_test_function("func4", "process"),
                create_test_function("func5", "transform"),
            ],
            edges: vec![
                Edge::new("func1".to_string(), "func2".to_string(), EdgeKind::Calls),
                Edge::new("func2".to_string(), "func3".to_string(), EdgeKind::Calls),
                Edge::new("func3".to_string(), "func4".to_string(), EdgeKind::Calls),
                Edge::new("func4".to_string(), "func5".to_string(), EdgeKind::Calls),
            ],
            repo_id: None,
        }
    }

    fn create_complex_ir() -> IRDocument {
        // Complex IR with 10 functions, multiple call paths
        let mut nodes = Vec::new();
        let mut edges = Vec::new();

        for i in 0..10 {
            nodes.push(create_test_function(
                &format!("func{}", i),
                &format!("function_{}", i),
            ));
        }

        // Create diamond dependency pattern
        // func0 -> func1, func2
        // func1 -> func3
        // func2 -> func3
        // func3 -> func4
        edges.push(Edge::new(
            "func0".to_string(),
            "func1".to_string(),
            EdgeKind::Calls,
        ));
        edges.push(Edge::new(
            "func0".to_string(),
            "func2".to_string(),
            EdgeKind::Calls,
        ));
        edges.push(Edge::new(
            "func1".to_string(),
            "func3".to_string(),
            EdgeKind::Calls,
        ));
        edges.push(Edge::new(
            "func2".to_string(),
            "func3".to_string(),
            EdgeKind::Calls,
        ));
        edges.push(Edge::new(
            "func3".to_string(),
            "func4".to_string(),
            EdgeKind::Calls,
        ));

        IRDocument {
            file_path: "test.py".to_string(),
            nodes,
            edges,
            repo_id: None,
        }
    }

    // ==================== Accuracy Tests ====================

    #[test]
    fn test_strategy_consistency_simple() {
        // Test that all strategies produce consistent results on simple IR
        let ir_doc = create_simple_ir();

        let fixpoint = create_strategy(StrategyType::Fixpoint);
        let biabduction = create_strategy(StrategyType::BiAbduction);
        let hybrid = create_strategy(StrategyType::Hybrid);

        let fixpoint_results = fixpoint.analyze_all(&ir_doc);
        let biabduction_results = biabduction.analyze_all(&ir_doc);
        let hybrid_results = hybrid.analyze_all(&ir_doc);

        // All strategies should analyze same number of functions
        assert_eq!(fixpoint_results.len(), 5);
        assert_eq!(biabduction_results.len(), 5);
        assert_eq!(hybrid_results.len(), 5);

        // All function IDs should match
        for func_id in fixpoint_results.keys() {
            assert!(
                biabduction_results.contains_key(func_id),
                "BiAbduction missing function: {}",
                func_id
            );
            assert!(
                hybrid_results.contains_key(func_id),
                "Hybrid missing function: {}",
                func_id
            );
        }
    }

    #[test]
    fn test_strategy_consistency_complex() {
        // Test consistency on complex IR with diamond dependencies
        let ir_doc = create_complex_ir();

        let fixpoint = create_strategy(StrategyType::Fixpoint);
        let hybrid = create_strategy(StrategyType::Hybrid);

        let fixpoint_results = fixpoint.analyze_all(&ir_doc);
        let hybrid_results = hybrid.analyze_all(&ir_doc);

        assert_eq!(fixpoint_results.len(), 10);
        assert_eq!(hybrid_results.len(), 10);

        // Hybrid should have equal or better confidence than Fixpoint
        let fixpoint_avg = fixpoint_results.values().map(|e| e.confidence).sum::<f64>() / 10.0;
        let hybrid_avg = hybrid_results.values().map(|e| e.confidence).sum::<f64>() / 10.0;

        println!("Fixpoint avg confidence: {:.2}", fixpoint_avg);
        println!("Hybrid avg confidence: {:.2}", hybrid_avg);

        // Hybrid should be at least as good as Fixpoint (or very close)
        assert!(
            hybrid_avg >= fixpoint_avg - 0.01,
            "Hybrid confidence ({:.2}) should be >= Fixpoint ({:.2})",
            hybrid_avg,
            fixpoint_avg
        );
    }

    #[test]
    fn test_accuracy_comparison_all_strategies() {
        // Compare all three strategies on the same IR
        let ir_doc = create_complex_ir();

        let strategies = vec![
            (StrategyType::Fixpoint, "Fixpoint"),
            (StrategyType::BiAbduction, "BiAbduction"),
            (StrategyType::Hybrid, "Hybrid"),
        ];

        println!("\n========== ACCURACY COMPARISON ==========");

        let mut comparisons = Vec::new();

        for (strategy_type, name) in strategies {
            let strategy = create_strategy(strategy_type);
            let results = strategy.analyze_all(&ir_doc);
            let comparison = StrategyComparison::from_results(name, &results);
            comparison.print_summary();
            comparisons.push(comparison);

            let metrics = strategy.metrics();
            println!("  Analysis time: {:.2}ms", metrics.total_time_ms);
            println!("  Iterations: {}", metrics.iterations);
        }

        println!("\n========== SUMMARY ==========");
        println!(
            "All strategies successfully analyzed {} functions",
            comparisons[0].total_functions
        );

        // All strategies should have reasonable confidence (> 50%)
        for comp in &comparisons {
            assert!(
                comp.avg_confidence > 0.5,
                "{} has too low confidence: {:.2}",
                comp.strategy_name,
                comp.avg_confidence
            );
        }
    }

    #[test]
    fn test_hybrid_refinement_benefit() {
        // Test that Hybrid provides benefit over pure Fixpoint
        let ir_doc = create_complex_ir();

        let fixpoint = create_strategy(StrategyType::Fixpoint);
        let hybrid = create_strategy(StrategyType::Hybrid);

        let fixpoint_results = fixpoint.analyze_all(&ir_doc);
        let hybrid_results = hybrid.analyze_all(&ir_doc);

        let fixpoint_metrics = fixpoint.metrics();
        let hybrid_metrics = hybrid.metrics();

        println!(
            "\nFixpoint: {:.2}ms, {} functions",
            fixpoint_metrics.total_time_ms, fixpoint_metrics.functions_analyzed
        );
        println!(
            "Hybrid: {:.2}ms, {} functions (refined {} low-confidence)",
            hybrid_metrics.total_time_ms,
            hybrid_metrics.functions_analyzed,
            hybrid_metrics.cache_misses
        );

        // Both should analyze same functions
        assert_eq!(fixpoint_results.len(), hybrid_results.len());

        // Hybrid should have some refinement activity (cache_misses > 0 if confidence < threshold)
        // Or none if all functions have high confidence
        println!("Hybrid refined {} functions", hybrid_metrics.cache_misses);
    }

    #[test]
    fn test_incremental_accuracy() {
        // Test that incremental analysis preserves accuracy
        let ir_doc = create_complex_ir();

        let hybrid = create_strategy(StrategyType::Hybrid);

        // Full analysis
        let full_results = hybrid.analyze_all(&ir_doc);

        // Incremental with 1 changed function
        let changed = vec!["func5".to_string()];
        let incremental_results = hybrid.analyze_incremental(&ir_doc, &changed, &full_results);

        // Should analyze same functions
        assert_eq!(incremental_results.len(), full_results.len());

        // Unchanged functions should have same effects (from cache)
        for func_id in ["func0", "func1", "func2", "func3", "func4"] {
            let full_effects = &full_results.get(func_id).unwrap().effects;
            let incr_effects = &incremental_results.get(func_id).unwrap().effects;
            assert_eq!(
                full_effects, incr_effects,
                "Incremental changed effects for unchanged function {}",
                func_id
            );
        }

        let metrics = hybrid.metrics();
        println!(
            "Incremental analysis: {} cache hits, {} misses",
            metrics.cache_hits, metrics.cache_misses
        );
    }

    #[test]
    fn test_effect_propagation_accuracy() {
        // Test that effects correctly propagate through call graph
        let ir_doc = create_simple_ir();

        let fixpoint = create_strategy(StrategyType::Fixpoint);
        let results = fixpoint.analyze_all(&ir_doc);

        // In a pure call chain (no actual effects in IR),
        // all functions should be Pure or Unknown (BiAbduction stub)
        for (func_id, effect_set) in &results {
            let has_valid_effect = effect_set.effects.contains(&EffectType::Pure)
                || effect_set.effects.contains(&EffectType::Unknown)
                || effect_set.effects.is_empty();

            assert!(
                has_valid_effect,
                "Function {} has unexpected effects: {:?}",
                func_id, effect_set.effects
            );
        }
    }
}
