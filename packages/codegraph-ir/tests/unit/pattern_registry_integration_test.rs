/// Integration tests for Pattern Registry with BiAbduction
///
/// This test suite validates that the pattern registry system is properly
/// integrated into the BiAbduction effect analysis and produces correct results.

use codegraph_ir::features::cross_file::IRDocument;
use codegraph_ir::features::effect_analysis::domain::EffectType;
use codegraph_ir::features::effect_analysis::infrastructure::biabduction::AbductiveEngine;
use codegraph_ir::shared::models::{Node, NodeKind, Edge, EdgeKind, Span};

fn create_test_node(id: &str, kind: NodeKind, name: &str, language: &str) -> Node {
    Node {
        id: id.to_string(),
        kind,
        fqn: name.to_string(),
        file_path: "test.py".to_string(),
        span: Span::new(1, 0, 10, 0),
        language: language.to_string(),
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
    }
}

#[test]
fn test_python_io_pattern_print() {
    let mut engine = AbductiveEngine::new();

    let func = create_test_node("func1", NodeKind::Function, "do_print", "python");
    let print_var = create_test_node("var1", NodeKind::Variable, "print", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), print_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    assert!(
        result.effects.contains(&EffectType::Io),
        "Expected Io effect for 'print', got {:?}",
        result.effects
    );
    assert!(result.confidence > 0.8);
}

#[test]
fn test_python_database_pattern_query() {
    let mut engine = AbductiveEngine::new();

    let func = create_test_node("func1", NodeKind::Function, "fetch_data", "python");
    let db_var = create_test_node("var1", NodeKind::Variable, "db_query", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), db_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    assert!(
        result.effects.contains(&EffectType::DbRead),
        "Expected DbRead effect for 'db_query', got {:?}",
        result.effects
    );
}

#[test]
fn test_python_database_pattern_insert() {
    let mut engine = AbductiveEngine::new();

    let func = create_test_node("func1", NodeKind::Function, "save_data", "python");
    let db_var = create_test_node("var1", NodeKind::Variable, "db_insert", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), db_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    assert!(
        result.effects.contains(&EffectType::DbWrite),
        "Expected DbWrite effect for 'db_insert', got {:?}",
        result.effects
    );
}

#[test]
fn test_python_exception_pattern() {
    let mut engine = AbductiveEngine::new();

    let func = create_test_node("func1", NodeKind::Function, "error_handler", "python");
    let raise_var = create_test_node("var1", NodeKind::Variable, "raise", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), raise_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    assert!(
        result.effects.contains(&EffectType::Throws),
        "Expected Throws effect for 'raise', got {:?}",
        result.effects
    );
}

#[test]
fn test_generic_network_pattern_http() {
    let mut engine = AbductiveEngine::new();

    let func = create_test_node("func1", NodeKind::Function, "fetch_api", "python");
    let http_var = create_test_node("var1", NodeKind::Variable, "http_get", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), http_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    assert!(
        result.effects.contains(&EffectType::Network),
        "Expected Network effect for 'http_get', got {:?}",
        result.effects
    );
}

#[test]
fn test_generic_network_pattern_javascript() {
    let mut engine = AbductiveEngine::new();

    // Test that generic patterns work for JavaScript too
    let func = create_test_node("func1", NodeKind::Function, "fetchData", "javascript");
    let http_var = create_test_node("var1", NodeKind::Variable, "http_request", "javascript");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), http_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    assert!(
        result.effects.contains(&EffectType::Network),
        "Expected Network effect for 'http_request' (JavaScript), got {:?}",
        result.effects
    );
}

#[test]
fn test_generic_logging_pattern() {
    let mut engine = AbductiveEngine::new();

    let func = create_test_node("func1", NodeKind::Function, "debug_info", "python");
    let log_var = create_test_node("var1", NodeKind::Variable, "logger", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), log_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    assert!(
        result.effects.contains(&EffectType::Log),
        "Expected Log effect for 'logger', got {:?}",
        result.effects
    );
}

#[test]
fn test_generic_cache_pattern() {
    let mut engine = AbductiveEngine::new();

    let func = create_test_node("func1", NodeKind::Function, "get_cached", "python");
    let cache_var = create_test_node("var1", NodeKind::Variable, "cache_store", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), cache_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    assert!(
        result.effects.contains(&EffectType::GlobalMutation),
        "Expected GlobalMutation effect for 'cache_store', got {:?}",
        result.effects
    );
    assert!(
        result.effects.contains(&EffectType::ReadState),
        "Expected ReadState effect for 'cache_store', got {:?}",
        result.effects
    );
}

#[test]
fn test_empty_function_pure() {
    let mut engine = AbductiveEngine::new();

    let func = create_test_node("func1", NodeKind::Function, "empty", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone()],
        edges: vec![],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    assert!(
        result.effects.contains(&EffectType::Pure),
        "Expected Pure effect for empty function, got {:?}",
        result.effects
    );
    assert_eq!(result.confidence, 1.0);
}

#[test]
fn test_multiple_effects_combination() {
    let mut engine = AbductiveEngine::new();

    let func = create_test_node("func1", NodeKind::Function, "complex_func", "python");
    let print_var = create_test_node("var1", NodeKind::Variable, "print", "python");
    let db_var = create_test_node("var2", NodeKind::Variable, "db_query", "python");
    let log_var = create_test_node("var3", NodeKind::Variable, "logger", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), print_var, db_var, log_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
            Edge::new("func1".to_string(), "var2".to_string(), EdgeKind::Contains),
            Edge::new("func1".to_string(), "var3".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    // Should have all three effects
    assert!(
        result.effects.contains(&EffectType::Io),
        "Expected Io effect, got {:?}",
        result.effects
    );
    assert!(
        result.effects.contains(&EffectType::DbRead),
        "Expected DbRead effect, got {:?}",
        result.effects
    );
    assert!(
        result.effects.contains(&EffectType::Log),
        "Expected Log effect, got {:?}",
        result.effects
    );

    // Should NOT have Pure effect
    assert!(
        !result.effects.contains(&EffectType::Pure),
        "Should not have Pure effect with other effects present"
    );
}

#[test]
fn test_language_specific_python_private_global() {
    let mut engine = AbductiveEngine::new();

    let func = create_test_node("func1", NodeKind::Function, "use_global", "python");
    // Python convention: _var = private global
    let global_var = create_test_node("var1", NodeKind::Variable, "_connection", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), global_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    assert!(
        result.effects.contains(&EffectType::GlobalMutation),
        "Expected GlobalMutation effect for '_connection', got {:?}",
        result.effects
    );
}

#[test]
fn test_callback_pattern() {
    let mut engine = AbductiveEngine::new();

    let func = create_test_node("func1", NodeKind::Function, "process_callback", "python");
    let callback_var = create_test_node("var1", NodeKind::Variable, "callback", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), callback_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    assert!(
        result.effects.contains(&EffectType::ExternalCall),
        "Expected ExternalCall effect for 'callback', got {:?}",
        result.effects
    );
}

#[test]
fn test_compositional_analysis() {
    // NOTE: This test validates that the callee can detect effects from patterns.
    // Call graph propagation (caller inheriting effects) is handled by BiAbductionStrategy,
    // not AbductiveEngine directly.
    let mut engine = AbductiveEngine::new();

    // Create callee function with print
    let callee = create_test_node("callee", NodeKind::Function, "callee_func", "python");
    let print_var = create_test_node("var1", NodeKind::Variable, "print", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![callee.clone(), print_var],
        edges: vec![
            Edge::new("callee".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    // Analyze callee
    let callee_result = engine.bi_abduce(&ir_doc, &callee);

    // Callee should have Io effect from pattern registry
    assert!(
        callee_result.effects.contains(&EffectType::Io),
        "Expected Io effect in callee detected via pattern registry, got {:?}",
        callee_result.effects
    );

    // Verify pattern registry is working
    assert!(callee_result.confidence > 0.8, "Expected high confidence from pattern match");
}

#[test]
fn test_pattern_confidence_levels() {
    let mut engine = AbductiveEngine::new();

    // High confidence: exact match
    let func1 = create_test_node("func1", NodeKind::Function, "test1", "python");
    let print_var = create_test_node("var1", NodeKind::Variable, "print", "python");

    let ir_doc1 = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func1.clone(), print_var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result1 = engine.bi_abduce(&ir_doc1, &func1);
    assert!(result1.confidence >= 0.9, "Expected high confidence for 'print'");

    // Empty function should have confidence 1.0
    let func2 = create_test_node("func2", NodeKind::Function, "empty", "python");
    let ir_doc2 = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func2.clone()],
        edges: vec![],
        repo_id: None,
    };

    let result2 = engine.bi_abduce(&ir_doc2, &func2);
    assert_eq!(result2.confidence, 1.0, "Expected confidence 1.0 for empty function");
}

#[test]
fn test_no_false_positives() {
    let mut engine = AbductiveEngine::new();

    // A function with a variable that doesn't match any pattern
    let func = create_test_node("func1", NodeKind::Function, "compute", "python");
    let var = create_test_node("var1", NodeKind::Variable, "result", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![
            Edge::new("func1".to_string(), "var1".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);

    // Should be Pure (no effects detected)
    assert!(
        result.effects.contains(&EffectType::Pure),
        "Expected Pure effect for non-matching pattern, got {:?}",
        result.effects
    );
}
