/// Comprehensive Bi-Abduction Tests
///
/// Tests ALL aspects of bi-abduction with separation logic:
/// - Core cases: Basic abduction, effect inference
/// - Edge cases: Empty functions, single statements, missing nodes
/// - Complex cases: Deep call chains, diamond dependencies, recursion
/// - Corner cases: Null handling, field aliasing, symbolic constraints
/// - Stress tests: Large IR, many existentials, complex heaps
#[cfg(test)]
mod biabduction_comprehensive_tests {
    use crate::features::cross_file::IRDocument;
    use crate::features::effect_analysis::domain::{ports::*, EffectType};
    use crate::features::effect_analysis::infrastructure::{
        biabduction::{BiAbductionStrategy, HeapPredicate, PureFormula, SymbolicHeap, SymbolicVar},
        create_strategy, LocalEffectAnalyzer, StrategyType,
    };
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

    fn create_variable(id: &str, name: &str) -> Node {
        let mut node = create_test_function(id, name);
        node.kind = NodeKind::Variable;
        node
    }

    fn create_field(id: &str, name: &str) -> Node {
        let mut node = create_test_function(id, name);
        node.kind = NodeKind::Field;
        node
    }

    // ==================== CORE CASES ====================

    #[test]
    fn test_core_empty_function_pure() {
        // Core: Empty function should be Pure with 1.0 confidence
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "empty");
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func],
            edges: vec![],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        assert_eq!(result.len(), 1);
        let effect_set = result.get("func1").unwrap();
        assert!(effect_set.effects.contains(&EffectType::Pure));
        assert_eq!(effect_set.confidence, 1.0);
        assert!(effect_set.idempotent);
    }

    #[test]
    fn test_core_io_print_detection() {
        // Core: Detect I/O from "print" variable
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "do_print");
        let print_var = create_variable("var1", "print");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func, print_var],
            edges: vec![Edge::new(
                "func1".to_string(),
                "var1".to_string(),
                EdgeKind::Contains,
            )],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        let effect_set = result.get("func1").unwrap();
        assert!(effect_set.effects.contains(&EffectType::Io));
        assert!(effect_set.confidence > 0.8);
    }

    #[test]
    fn test_core_database_read_detection() {
        // Core: Detect DB read from "db_query"
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "fetch_data");
        let query_var = create_variable("var1", "db_query");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func, query_var],
            edges: vec![Edge::new(
                "func1".to_string(),
                "var1".to_string(),
                EdgeKind::Contains,
            )],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        let effect_set = result.get("func1").unwrap();
        assert!(effect_set.effects.contains(&EffectType::DbRead));
        assert!(effect_set.confidence > 0.8);
    }

    #[test]
    fn test_core_network_http_detection() {
        // Core: Detect network from "http_request"
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "call_api");
        let http_var = create_variable("var1", "http_request");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func, http_var],
            edges: vec![Edge::new(
                "func1".to_string(),
                "var1".to_string(),
                EdgeKind::Contains,
            )],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        let effect_set = result.get("func1").unwrap();
        assert!(effect_set.effects.contains(&EffectType::Network));
        assert!(effect_set.confidence > 0.8);
    }

    #[test]
    fn test_core_field_access_readstate() {
        // Core: Field access should infer ReadState
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "get_field");
        let field = create_field("field1", "data");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func, field],
            edges: vec![Edge::new(
                "func1".to_string(),
                "field1".to_string(),
                EdgeKind::Contains,
            )],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        let effect_set = result.get("func1").unwrap();
        assert!(effect_set.effects.contains(&EffectType::ReadState));
        assert!(effect_set.confidence > 0.8);
    }

    // ==================== EDGE CASES ====================

    #[test]
    fn test_edge_single_statement_function() {
        // Edge: Function with exactly 1 statement
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "single");
        let var = create_variable("var1", "x");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func, var],
            edges: vec![Edge::new(
                "func1".to_string(),
                "var1".to_string(),
                EdgeKind::Contains,
            )],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        assert_eq!(result.len(), 1);
        // Single variable with no known effects -> could be Pure or low confidence
        let effect_set = result.get("func1").unwrap();
        assert!(effect_set.confidence >= 0.5);
    }

    #[test]
    fn test_edge_function_no_body_but_has_calls() {
        // Edge: Function with no CONTAINS edges but has CALLS edges
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func1 = create_test_function("func1", "caller");
        let func2 = create_test_function("func2", "callee");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func1, func2],
            edges: vec![Edge::new(
                "func1".to_string(),
                "func2".to_string(),
                EdgeKind::Calls,
            )],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        assert_eq!(result.len(), 2);
        // func1 calls func2 but has no body -> depends on func2's effects
        let func1_effects = result.get("func1").unwrap();
        // func2 is empty -> Pure
        let func2_effects = result.get("func2").unwrap();
        assert!(func2_effects.effects.contains(&EffectType::Pure));
    }

    #[test]
    fn test_edge_unknown_variable_name() {
        // Edge: Variable with unknown name (not in heuristics)
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "mystery");
        let unknown_var = create_variable("var1", "xyz_unknown_abc");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func, unknown_var],
            edges: vec![Edge::new(
                "func1".to_string(),
                "var1".to_string(),
                EdgeKind::Contains,
            )],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        let effect_set = result.get("func1").unwrap();
        // Unknown variable -> no specific effects detected, should be Pure or low confidence
        assert!(effect_set.confidence >= 0.5);
    }

    // ==================== COMPLEX CASES ====================

    #[test]
    fn test_complex_multiple_effects_combination() {
        // Complex: Function with multiple different effects
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "multi_effect");
        let print_var = create_variable("var1", "print");
        let db_var = create_variable("var2", "db_query");
        let http_var = create_variable("var3", "http_get");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func, print_var, db_var, http_var],
            edges: vec![
                Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
                Edge::new("func1".to_string(), "var2".to_string(), EdgeKind::Contains),
                Edge::new("func1".to_string(), "var3".to_string(), EdgeKind::Contains),
            ],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        let effect_set = result.get("func1").unwrap();
        // Should detect all three: Io, DbRead, Network
        assert!(effect_set.effects.contains(&EffectType::Io));
        assert!(effect_set.effects.contains(&EffectType::DbRead));
        assert!(effect_set.effects.contains(&EffectType::Network));
        assert!(!effect_set.idempotent); // Has side effects
    }

    #[test]
    fn test_complex_deep_call_chain_5_levels() {
        // Complex: Deep call chain (5 levels)
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func1 = create_test_function("func1", "level1");
        let func2 = create_test_function("func2", "level2");
        let func3 = create_test_function("func3", "level3");
        let func4 = create_test_function("func4", "level4");
        let func5 = create_test_function("func5", "level5");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func1, func2, func3, func4, func5],
            edges: vec![
                Edge::new("func1".to_string(), "func2".to_string(), EdgeKind::Calls),
                Edge::new("func2".to_string(), "func3".to_string(), EdgeKind::Calls),
                Edge::new("func3".to_string(), "func4".to_string(), EdgeKind::Calls),
                Edge::new("func4".to_string(), "func5".to_string(), EdgeKind::Calls),
            ],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        assert_eq!(result.len(), 5);
        // All should be analyzed (bi-abduction is compositional!)
        for i in 1..=5 {
            let func_id = format!("func{}", i);
            assert!(result.contains_key(&func_id));
        }
    }

    #[test]
    fn test_complex_diamond_dependency() {
        // Complex: Diamond pattern (A -> B, A -> C, B -> D, C -> D)
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func_a = create_test_function("funcA", "top");
        let func_b = create_test_function("funcB", "left");
        let func_c = create_test_function("funcC", "right");
        let func_d = create_test_function("funcD", "bottom");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func_a, func_b, func_c, func_d],
            edges: vec![
                Edge::new("funcA".to_string(), "funcB".to_string(), EdgeKind::Calls),
                Edge::new("funcA".to_string(), "funcC".to_string(), EdgeKind::Calls),
                Edge::new("funcB".to_string(), "funcD".to_string(), EdgeKind::Calls),
                Edge::new("funcC".to_string(), "funcD".to_string(), EdgeKind::Calls),
            ],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        assert_eq!(result.len(), 4);
        // All nodes should be analyzed
        for func_id in ["funcA", "funcB", "funcC", "funcD"] {
            assert!(result.contains_key(func_id));
        }
    }

    #[test]
    fn test_complex_circular_dependency() {
        // Complex: Circular call (A -> B -> A)
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func_a = create_test_function("funcA", "a");
        let func_b = create_test_function("funcB", "b");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func_a, func_b],
            edges: vec![
                Edge::new("funcA".to_string(), "funcB".to_string(), EdgeKind::Calls),
                Edge::new("funcB".to_string(), "funcA".to_string(), EdgeKind::Calls),
            ],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        assert_eq!(result.len(), 2);
        // Should handle circular dependencies without infinite loop
        assert!(result.contains_key("funcA"));
        assert!(result.contains_key("funcB"));
    }

    // ==================== CORNER CASES ====================

    #[test]
    fn test_corner_field_access_with_null_like_name() {
        // Corner: Field named "null" or "none"
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "check_null");
        let null_field = create_field("field1", "null");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func, null_field],
            edges: vec![Edge::new(
                "func1".to_string(),
                "field1".to_string(),
                EdgeKind::Contains,
            )],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        let effect_set = result.get("func1").unwrap();
        // Should still detect ReadState even with "null" name
        assert!(effect_set.effects.contains(&EffectType::ReadState));
    }

    #[test]
    fn test_corner_mixed_io_and_pure_operations() {
        // Corner: Mix of I/O and pure operations
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "mixed");
        let print_var = create_variable("var1", "print");
        let add_var = create_variable("var2", "add");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func, print_var, add_var],
            edges: vec![
                Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
                Edge::new("func1".to_string(), "var2".to_string(), EdgeKind::Contains),
            ],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        let effect_set = result.get("func1").unwrap();
        // Should detect Io (dominant over pure)
        assert!(effect_set.effects.contains(&EffectType::Io));
        // Should NOT be Pure (has I/O)
        assert!(!effect_set.effects.contains(&EffectType::Pure));
    }

    #[test]
    fn test_corner_exception_throw_detection() {
        // Corner: Exception throwing
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "error_handler");
        let throw_var = create_variable("var1", "raise_exception");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func, throw_var],
            edges: vec![Edge::new(
                "func1".to_string(),
                "var1".to_string(),
                EdgeKind::Contains,
            )],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        let effect_set = result.get("func1").unwrap();
        assert!(effect_set.effects.contains(&EffectType::Throws));
    }

    #[test]
    fn test_corner_logging_detection() {
        // Corner: Logging operations
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "do_log");
        let log_var = create_variable("var1", "logger");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func, log_var],
            edges: vec![Edge::new(
                "func1".to_string(),
                "var1".to_string(),
                EdgeKind::Contains,
            )],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        let effect_set = result.get("func1").unwrap();
        assert!(effect_set.effects.contains(&EffectType::Log));
    }

    // ==================== STRESS TESTS ====================

    #[test]
    fn test_stress_50_functions() {
        // Stress: 50 functions
        let strategy = create_strategy(StrategyType::BiAbduction);

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

        let start = std::time::Instant::now();
        let result = strategy.analyze_all(&ir_doc);
        let elapsed = start.elapsed();

        assert_eq!(result.len(), 50);
        // Should complete in reasonable time (< 1 second)
        assert!(elapsed.as_secs() < 1);

        let metrics = strategy.metrics();
        println!(
            "BiAbduction: 50 functions in {:.2}ms",
            metrics.total_time_ms
        );
    }

    #[test]
    fn test_stress_100_functions_call_chain() {
        // Stress: 100 functions in call chain
        let strategy = create_strategy(StrategyType::BiAbduction);

        let mut nodes = Vec::new();
        let mut edges = Vec::new();

        for i in 0..100 {
            nodes.push(create_test_function(
                &format!("func{}", i),
                &format!("f{}", i),
            ));
            if i < 99 {
                edges.push(Edge::new(
                    format!("func{}", i),
                    format!("func{}", i + 1),
                    EdgeKind::Calls,
                ));
            }
        }

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes,
            edges,
            repo_id: None,
        };

        let start = std::time::Instant::now();
        let result = strategy.analyze_all(&ir_doc);
        let elapsed = start.elapsed();

        assert_eq!(result.len(), 100);
        // Should complete in reasonable time
        assert!(elapsed.as_secs() < 2);

        let metrics = strategy.metrics();
        println!(
            "BiAbduction: 100 functions in {:.2}ms",
            metrics.total_time_ms
        );
    }

    #[test]
    fn test_stress_many_variables_per_function() {
        // Stress: Function with 20 variables
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func = create_test_function("func1", "many_vars");
        let mut nodes = vec![func];
        let mut edges = Vec::new();

        for i in 0..20 {
            let var = create_variable(&format!("var{}", i), &format!("v{}", i));
            nodes.push(var);
            edges.push(Edge::new(
                "func1".to_string(),
                format!("var{}", i),
                EdgeKind::Contains,
            ));
        }

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes,
            edges,
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        assert_eq!(result.len(), 1);
        let effect_set = result.get("func1").unwrap();
        // Should handle many variables without issue
        assert!(effect_set.confidence >= 0.5);
    }

    // ==================== INCREMENTAL ANALYSIS TESTS ====================

    #[test]
    fn test_incremental_single_function_change() {
        // Incremental: Only 1 function changed out of 10
        let strategy = create_strategy(StrategyType::BiAbduction);

        let mut nodes = Vec::new();
        for i in 0..10 {
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

        // Full analysis
        let cache = strategy.analyze_all(&ir_doc);
        assert_eq!(cache.len(), 10);

        // Incremental: only func5 changed
        let changed = vec!["func5".to_string()];
        let result = strategy.analyze_incremental(&ir_doc, &changed, &cache);

        assert_eq!(result.len(), 10);

        let metrics = strategy.metrics();
        // Should have 9 cache hits, 1 miss
        assert_eq!(metrics.cache_hits, 9);
        assert_eq!(metrics.cache_misses, 1);

        println!(
            "Incremental: {} cache hits, {} misses",
            metrics.cache_hits, metrics.cache_misses
        );
    }

    #[test]
    fn test_incremental_no_changes() {
        // Incremental: No changes (all from cache)
        let strategy = create_strategy(StrategyType::BiAbduction);

        let func1 = create_test_function("func1", "foo");
        let func2 = create_test_function("func2", "bar");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func1, func2],
            edges: vec![],
            repo_id: None,
        };

        let cache = strategy.analyze_all(&ir_doc);

        // Incremental with NO changes
        let changed: Vec<String> = vec![];
        let result = strategy.analyze_incremental(&ir_doc, &changed, &cache);

        assert_eq!(result.len(), 2);

        let metrics = strategy.metrics();
        // All from cache
        assert_eq!(metrics.cache_hits, 2);
        assert_eq!(metrics.cache_misses, 0);
    }

    // ==================== SEPARATION LOGIC SPECIFIC TESTS ====================

    #[test]
    fn test_separation_logic_symbolic_var() {
        // Test symbolic variable creation
        let var = SymbolicVar::ProgramVar("x".to_string());
        assert_eq!(var.to_string(), "x");

        let exist = SymbolicVar::Existential(42);
        assert_eq!(exist.to_string(), "?v42");

        let ret = SymbolicVar::ReturnValue;
        assert_eq!(ret.to_string(), "ret");
    }

    #[test]
    fn test_separation_logic_pure_formula_satisfiability() {
        // Test pure formula satisfiability
        let true_formula = PureFormula::True;
        assert!(true_formula.is_satisfiable());

        let false_formula = PureFormula::False;
        assert!(!false_formula.is_satisfiable());

        let x = SymbolicVar::ProgramVar("x".to_string());
        let y = SymbolicVar::ProgramVar("y".to_string());

        let eq = PureFormula::Equal(x.clone(), y.clone());
        assert!(eq.is_satisfiable());

        let and = PureFormula::True.and(eq);
        assert!(and.is_satisfiable());
    }

    #[test]
    fn test_separation_logic_heap_emp() {
        // Test empty heap
        let heap = SymbolicHeap::emp();
        assert!(heap.is_emp());
        assert!(heap.get_free_vars().is_empty());
    }

    #[test]
    fn test_separation_logic_sep_conj() {
        // Test separating conjunction
        let x = SymbolicVar::ProgramVar("x".to_string());
        let y = SymbolicVar::ProgramVar("y".to_string());

        let h1 = HeapPredicate::PointsTo {
            base: x,
            fields: HashMap::new(),
        };

        let h2 = HeapPredicate::PointsTo {
            base: y,
            fields: HashMap::new(),
        };

        let combined = h1.sep_conj(h2);

        // Should contain both heaps
        assert!(combined.to_string().contains("*"));
    }
}
