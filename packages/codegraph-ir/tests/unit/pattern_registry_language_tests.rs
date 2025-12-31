/// Language-specific Pattern Registry Tests
///
/// Comprehensive test suite validating pattern detection across different programming languages.
/// Tests Python-specific patterns, generic cross-language patterns, and edge cases.

use codegraph_ir::features::cross_file::IRDocument;
use codegraph_ir::features::effect_analysis::domain::EffectType;
use codegraph_ir::features::effect_analysis::infrastructure::biabduction::AbductiveEngine;
use codegraph_ir::shared::models::{Node, NodeKind, Edge, EdgeKind, Span};

fn create_test_node(id: &str, kind: NodeKind, name: &str, language: &str) -> Node {
    Node {
        id: id.to_string(),
        kind,
        fqn: name.to_string(),
        file_path: format!("test.{}", if language == "python" { "py" } else if language == "javascript" { "js" } else if language == "go" { "go" } else { "java" }),
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

// ============================================================================
// PYTHON-SPECIFIC TESTS
// ============================================================================

#[test]
fn test_python_io_print() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "print", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Io), "print should be Io");
}

#[test]
fn test_python_io_input() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "input", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Io), "input should be Io");
}

#[test]
fn test_python_io_open() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "open", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Io), "open should be Io");
}

#[test]
fn test_python_exception_raise() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "raise", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Throws), "raise should be Throws");
}

#[test]
fn test_python_private_global_underscore() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "_global_state", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "_var should be GlobalMutation");
}

#[test]
fn test_python_private_global_connection() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "_db_connection", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "_db_connection should be GlobalMutation");
}

// ============================================================================
// DATABASE PATTERNS (Language-agnostic)
// ============================================================================

#[test]
fn test_db_select_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "select", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::DbRead), "select should be DbRead");
}

#[test]
fn test_db_query_javascript() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "javascript");
    let var = create_test_node("v1", NodeKind::Variable, "db_query", "javascript");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::DbRead), "db_query should be DbRead");
}

#[test]
fn test_db_insert_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "insert", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::DbWrite), "insert should be DbWrite");
}

#[test]
fn test_db_update_go() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "go");
    let var = create_test_node("v1", NodeKind::Variable, "update", "go");

    let ir_doc = IRDocument {
        file_path: "test.go".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::DbWrite), "update should be DbWrite");
}

#[test]
fn test_db_delete_java() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "java");
    let var = create_test_node("v1", NodeKind::Variable, "delete", "java");

    let ir_doc = IRDocument {
        file_path: "test.java".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::DbWrite), "delete should be DbWrite");
}

#[test]
fn test_db_create_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "create_table", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::DbWrite), "create_table should be DbWrite");
}

#[test]
fn test_db_commit_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "commit", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::DbWrite), "commit should be DbWrite");
}

#[test]
fn test_db_rollback_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "rollback", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::DbWrite), "rollback should be DbWrite");
}

// ============================================================================
// NETWORK PATTERNS (Language-agnostic)
// ============================================================================

#[test]
fn test_network_http_get_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "http_get", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Network), "http_get should be Network");
}

#[test]
fn test_network_http_post_javascript() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "javascript");
    let var = create_test_node("v1", NodeKind::Variable, "http_post", "javascript");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Network), "http_post should be Network");
}

#[test]
fn test_network_fetch_javascript() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "javascript");
    let var = create_test_node("v1", NodeKind::Variable, "fetch", "javascript");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Network), "fetch should be Network");
}

#[test]
fn test_network_request_go() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "go");
    let var = create_test_node("v1", NodeKind::Variable, "http_request", "go");

    let ir_doc = IRDocument {
        file_path: "test.go".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Network), "http_request should be Network");
}

#[test]
fn test_network_api_call_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "api_call", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Network), "api_call should be Network");
}

#[test]
fn test_network_socket_java() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "java");
    let var = create_test_node("v1", NodeKind::Variable, "socket_connect", "java");

    let ir_doc = IRDocument {
        file_path: "test.java".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Network), "socket_connect should be Network");
}

// ============================================================================
// LOGGING PATTERNS (Language-agnostic)
// ============================================================================

#[test]
fn test_logging_logger_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "logger", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Log), "logger should be Log");
}

#[test]
fn test_logging_debug_javascript() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "javascript");
    let var = create_test_node("v1", NodeKind::Variable, "debug", "javascript");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Log), "debug should be Log");
}

#[test]
fn test_logging_info_go() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "go");
    let var = create_test_node("v1", NodeKind::Variable, "log_info", "go");

    let ir_doc = IRDocument {
        file_path: "test.go".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Log), "log_info should be Log");
}

#[test]
fn test_logging_warn_java() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "java");
    let var = create_test_node("v1", NodeKind::Variable, "warn", "java");

    let ir_doc = IRDocument {
        file_path: "test.java".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Log), "warn should be Log");
}

#[test]
fn test_logging_error_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "log_error", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Log), "log_error should be Log");
}

// ============================================================================
// STATE/CACHE PATTERNS (Language-agnostic)
// ============================================================================

#[test]
fn test_state_cache_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "cache", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "cache should have GlobalMutation");
    assert!(result.effects.contains(&EffectType::ReadState), "cache should have ReadState");
}

#[test]
fn test_state_singleton_javascript() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "javascript");
    let var = create_test_node("v1", NodeKind::Variable, "singleton", "javascript");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "singleton should have GlobalMutation");
}

#[test]
fn test_state_config_go() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "go");
    let var = create_test_node("v1", NodeKind::Variable, "config", "go");

    let ir_doc = IRDocument {
        file_path: "test.go".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "config should have GlobalMutation");
}

#[test]
fn test_state_counter_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "counter", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "counter should have GlobalMutation");
}

#[test]
fn test_state_memoize_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "memoize", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "memoize should have GlobalMutation");
}

// ============================================================================
// CALLBACK/HANDLER PATTERNS (Language-agnostic)
// ============================================================================

#[test]
fn test_callback_python() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "python");
    let var = create_test_node("v1", NodeKind::Variable, "callback", "python");

    let ir_doc = IRDocument {
        file_path: "test.py".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::ExternalCall), "callback should be ExternalCall");
}

#[test]
fn test_handler_javascript() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "javascript");
    let var = create_test_node("v1", NodeKind::Variable, "handler", "javascript");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::ExternalCall), "handler should be ExternalCall");
}

#[test]
fn test_listener_java() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "java");
    let var = create_test_node("v1", NodeKind::Variable, "listener", "java");

    let ir_doc = IRDocument {
        file_path: "test.java".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::ExternalCall), "listener should be ExternalCall");
}

#[test]
fn test_observer_go() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test", "go");
    let var = create_test_node("v1", NodeKind::Variable, "observer", "go");

    let ir_doc = IRDocument {
        file_path: "test.go".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::ExternalCall), "observer should be ExternalCall");
}

// ============================================================================
// EDGE CASES & MULTI-LANGUAGE VALIDATION
// ============================================================================

#[test]
fn test_empty_function_all_languages() {
    let mut engine = AbductiveEngine::new();
    let languages = vec!["python", "javascript", "go", "java"];

    for lang in languages {
        let func = create_test_node("f1", NodeKind::Function, "empty", lang);
        let ir_doc = IRDocument {
            file_path: format!("test.{}", lang),
            nodes: vec![func.clone()],
            edges: vec![],
            repo_id: None,
        };

        let result = engine.bi_abduce(&ir_doc, &func);
        assert!(
            result.effects.contains(&EffectType::Pure),
            "Empty function in {} should be Pure",
            lang
        );
        assert_eq!(result.confidence, 1.0, "Empty function should have confidence 1.0");
    }
}

#[test]
fn test_generic_pattern_works_across_languages() {
    let mut engine = AbductiveEngine::new();
    let languages = vec!["python", "javascript", "go", "java"];

    for lang in languages {
        let func = create_test_node("f1", NodeKind::Function, "test", lang);
        let var = create_test_node("v1", NodeKind::Variable, "http_request", lang);

        let ir_doc = IRDocument {
            file_path: format!("test.{}", lang),
            nodes: vec![func.clone(), var],
            edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
            repo_id: None,
        };

        let result = engine.bi_abduce(&ir_doc, &func);
        assert!(
            result.effects.contains(&EffectType::Network),
            "http_request should be Network in {}",
            lang
        );
    }
}

#[test]
fn test_no_false_positive_across_languages() {
    let mut engine = AbductiveEngine::new();
    let languages = vec!["python", "javascript", "go", "java"];

    for lang in languages {
        let func = create_test_node("f1", NodeKind::Function, "test", lang);
        let var = create_test_node("v1", NodeKind::Variable, "unknown_variable", lang);

        let ir_doc = IRDocument {
            file_path: format!("test.{}", lang),
            nodes: vec![func.clone(), var],
            edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
            repo_id: None,
        };

        let result = engine.bi_abduce(&ir_doc, &func);
        assert!(
            result.effects.contains(&EffectType::Pure),
            "Unknown variable in {} should result in Pure",
            lang
        );
    }
}
