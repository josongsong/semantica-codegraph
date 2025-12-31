/// JavaScript-specific Pattern Tests
///
/// Comprehensive tests for JavaScript-specific patterns including:
/// - Console I/O (console.log, alert, etc.)
/// - Exception handling (throw, reject)
/// - Async/Promise patterns
/// - DOM manipulation
/// - Storage APIs (localStorage, cookies)
/// - Network APIs (fetch, XHR, WebSocket)

use codegraph_ir::features::cross_file::IRDocument;
use codegraph_ir::features::effect_analysis::domain::EffectType;
use codegraph_ir::features::effect_analysis::infrastructure::biabduction::AbductiveEngine;
use codegraph_ir::shared::models::{Node, NodeKind, Edge, EdgeKind, Span};

fn create_test_node(id: &str, kind: NodeKind, name: &str) -> Node {
    Node {
        id: id.to_string(),
        kind,
        fqn: name.to_string(),
        file_path: "test.js".to_string(),
        span: Span::new(1, 0, 10, 0),
        language: "javascript".to_string(),
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
// I/O PATTERNS
// ============================================================================

#[test]
fn test_js_console_log() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "console.log");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Io), "console.log should be Io");
    assert!(result.confidence > 0.9, "High confidence expected");
}

#[test]
fn test_js_console_error() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "console.error");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Io), "console.error should be Io");
}

#[test]
fn test_js_alert() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "alert");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Io), "alert should be Io");
}

#[test]
fn test_js_prompt() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "prompt");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Io), "prompt should be Io");
}

// ============================================================================
// EXCEPTION PATTERNS
// ============================================================================

#[test]
fn test_js_throw() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "throw");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Throws), "throw should be Throws");
    assert!(result.confidence > 0.9);
}

#[test]
fn test_js_promise_reject() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "reject");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Throws), "reject should be Throws");
}

// ============================================================================
// ASYNC/PROMISE PATTERNS
// ============================================================================

#[test]
fn test_js_promise() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "Promise");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::ExternalCall), "Promise should be ExternalCall");
}

#[test]
fn test_js_async() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "async");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::ExternalCall), "async should be ExternalCall");
}

#[test]
fn test_js_settimeout() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "setTimeout");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::ExternalCall), "setTimeout should be ExternalCall");
}

// ============================================================================
// DOM MANIPULATION PATTERNS
// ============================================================================

#[test]
fn test_js_innerhtml() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "innerHTML");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "innerHTML should be GlobalMutation");
}

#[test]
fn test_js_appendchild() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "appendChild");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "appendChild should be GlobalMutation");
}

#[test]
fn test_js_queryselector() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "querySelector");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::ReadState), "querySelector should be ReadState");
}

// ============================================================================
// STORAGE PATTERNS
// ============================================================================

#[test]
fn test_js_localstorage() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "localStorage");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "localStorage should be GlobalMutation");
}

#[test]
fn test_js_sessionstorage() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "sessionStorage");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "sessionStorage should be GlobalMutation");
}

#[test]
fn test_js_cookie() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "document.cookie");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "document.cookie should be GlobalMutation");
}

// ============================================================================
// NETWORK PATTERNS
// ============================================================================

#[test]
fn test_js_fetch() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "fetch");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Network), "fetch should be Network");
    assert!(result.confidence > 0.9);
}

#[test]
fn test_js_xmlhttprequest() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "XMLHttpRequest");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Network), "XMLHttpRequest should be Network");
}

#[test]
fn test_js_websocket() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "WebSocket");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Network), "WebSocket should be Network");
}

// ============================================================================
// GLOBAL PATTERNS
// ============================================================================

#[test]
fn test_js_window_global() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "window.location");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "window.* should be GlobalMutation");
}

#[test]
fn test_js_globalthis() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "globalThis.myVar");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::GlobalMutation), "globalThis.* should be GlobalMutation");
}

// ============================================================================
// EDGE CASES
// ============================================================================

#[test]
fn test_js_multiple_effects() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let console = create_test_node("v1", NodeKind::Variable, "console.log");
    let fetch_var = create_test_node("v2", NodeKind::Variable, "fetch");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), console, fetch_var],
        edges: vec![
            Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains),
            Edge::new("f1".to_string(), "v2".to_string(), EdgeKind::Contains),
        ],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Io), "Should have Io from console.log");
    assert!(result.effects.contains(&EffectType::Network), "Should have Network from fetch");
}

#[test]
fn test_js_no_false_positives() {
    let mut engine = AbductiveEngine::new();
    let func = create_test_node("f1", NodeKind::Function, "test");
    let var = create_test_node("v1", NodeKind::Variable, "unknownJsVariable");

    let ir_doc = IRDocument {
        file_path: "test.js".to_string(),
        nodes: vec![func.clone(), var],
        edges: vec![Edge::new("f1".to_string(), "v1".to_string(), EdgeKind::Contains)],
        repo_id: None,
    };

    let result = engine.bi_abduce(&ir_doc, &func);
    assert!(result.effects.contains(&EffectType::Pure), "Unknown variable should be Pure");
}
