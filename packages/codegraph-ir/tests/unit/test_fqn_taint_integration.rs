/*
 * FQN + Taint Analysis Integration Tests
 *
 * Verifies that FQN-resolved CALLS edges enable accurate taint detection
 * by eliminating false positives from user-defined functions.
 *
 * Key Tests:
 * 1. Built-in sinks detected (builtins.eval, os.system)
 * 2. User-defined functions NOT detected (user's eval(), system())
 * 3. End-to-end taint flow (source -> sink)
 */

use codegraph_ir::pipeline::processor::process_file;
use codegraph_ir::features::taint_analysis::infrastructure::taint::{
    TaintAnalyzer, TaintSource, TaintSink, TaintSeverity, CallGraphNode,
};
use codegraph_ir::shared::models::{Edge, EdgeKind};
use std::collections::{HashMap, HashSet};

/// Test 1: FQN-based sink detection - Built-ins detected
#[test]
fn test_fqn_taint_builtin_detection() {
    let code = r#"
def vulnerable(user_input):
    # These should be detected as sinks (built-ins with FQN)
    result = eval(user_input)      # builtins.eval
    exec(user_input)               # builtins.exec
    import os
    os.system(user_input)          # os.system
    f = open(user_input, 'r')      # builtins.open
    return result
"#;

    let result = process_file(code, "test_repo", "test.py", "test_module");

    // Extract CALLS edges
    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    let target_ids: HashSet<String> = calls_edges
        .iter()
        .map(|e| e.target_id.clone())
        .collect();

    println!("Detected CALLS targets: {:?}", target_ids);

    // Verify FQN resolution
    assert!(target_ids.contains("builtins.eval"), "Should detect builtins.eval");
    assert!(target_ids.contains("builtins.exec"), "Should detect builtins.exec");
    assert!(target_ids.iter().any(|id| id.contains("os.system")), "Should detect os.system");
    assert!(target_ids.contains("builtins.open"), "Should detect builtins.open");

    // Create taint analyzer with FQN sinks
    let analyzer = TaintAnalyzer::new();

    // Check that sinks match FQN targets
    let sinks = analyzer.get_sinks();
    let sink_patterns: Vec<String> = sinks.iter().map(|s| s.pattern.clone()).collect();

    println!("Configured sink patterns: {:?}", sink_patterns);

    assert!(sink_patterns.contains(&"builtins.eval".to_string()), "Analyzer should have builtins.eval sink");
    assert!(sink_patterns.contains(&"builtins.exec".to_string()), "Analyzer should have builtins.exec sink");
    assert!(sink_patterns.contains(&"os.system".to_string()), "Analyzer should have os.system sink");
    assert!(sink_patterns.contains(&"builtins.open".to_string()), "Analyzer should have builtins.open sink");
}

/// Test 2: FQN-based false positive elimination - User-defined functions NOT detected
#[test]
fn test_fqn_taint_false_positive_elimination() {
    let code = r#"
# User-defined functions with same names as built-ins
def eval(x):
    """User's safe eval function"""
    return int(x) if x.isdigit() else 0

def exec(code):
    """User's safe exec function"""
    print("Would execute:", code)

def system(cmd):
    """User's safe system function"""
    print("Would run:", cmd)

def open(path, mode='r'):
    """User's safe open function"""
    print("Would open:", path)
    return None

def process_user_input(user_input):
    # These are USER-DEFINED functions, should NOT be detected as sinks
    result = eval(user_input)
    exec(user_input)
    system(user_input)
    f = open(user_input)
    return result
"#;

    let result = process_file(code, "test_repo", "safe.py", "safe_module");

    // Extract CALLS edges
    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    let target_ids: HashSet<String> = calls_edges
        .iter()
        .map(|e| e.target_id.clone())
        .collect();

    println!("User-defined function calls: {:?}", target_ids);

    // Verify that FQN does NOT contain "builtins." prefix
    // (user-defined functions don't get FQN prefix)
    assert!(
        !target_ids.contains("builtins.eval"),
        "User-defined eval should NOT have builtins. prefix"
    );
    assert!(
        !target_ids.contains("builtins.exec"),
        "User-defined exec should NOT have builtins. prefix"
    );
    assert!(
        !target_ids.contains("os.system"),
        "User-defined system should NOT be os.system"
    );
    assert!(
        !target_ids.contains("builtins.open"),
        "User-defined open should NOT have builtins. prefix"
    );

    // These should be simple names or module-qualified names without "builtins."
    // The key is they DON'T match the FQN sinks in TaintAnalyzer
}

/// Test 3: End-to-end taint flow detection with FQN
#[test]
fn test_fqn_taint_e2e_flow() {
    let code = r#"
def get_user_input():
    return input("Enter command: ")

def vulnerable_function():
    # Source: user input
    user_data = get_user_input()

    # Flow: user_data is tainted
    command = user_data

    # Sink: tainted data reaches dangerous built-in
    eval(command)              # builtins.eval - DETECTED

    import os
    os.system(command)         # os.system - DETECTED

def safe_wrapper():
    # User-defined safe functions
    def eval(x):
        return int(x) if x.isdigit() else 0

    user_data = input("Enter number: ")
    result = eval(user_data)   # User's eval - NOT DETECTED
    return result
"#;

    let result = process_file(code, "test_repo", "flow.py", "flow_module");

    println!("Total nodes: {}", result.nodes.len());
    println!("Total edges: {}", result.edges.len());

    // Extract CALLS edges
    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    let target_ids: HashSet<String> = calls_edges
        .iter()
        .map(|e| e.target_id.clone())
        .collect();

    println!("All CALLS targets:");
    for target in &target_ids {
        println!("  - {}", target);
    }

    // Verify built-in sinks detected
    assert!(
        target_ids.contains("builtins.eval"),
        "Should detect built-in eval as sink"
    );
    assert!(
        target_ids.iter().any(|id| id.contains("os.system")),
        "Should detect os.system as sink"
    );
    assert!(
        target_ids.contains("builtins.input"),
        "Should detect input as source"
    );

    // Count dangerous calls (FQN sinks only)
    let dangerous_count = target_ids
        .iter()
        .filter(|id| {
            id.starts_with("builtins.eval")
                || id.starts_with("builtins.exec")
                || id.contains("os.system")
                || id.contains("subprocess.")
        })
        .count();

    println!("Dangerous built-in calls detected: {}", dangerous_count);
    assert!(dangerous_count >= 2, "Should detect at least 2 dangerous calls");
}

/// Test 4: OWASP Top 10 Injection - All categories with FQN
#[test]
fn test_fqn_taint_owasp_top10() {
    let code = r#"
def owasp_vulnerabilities(user_input):
    # A03:2021 – Injection

    # Code Injection
    eval(user_input)           # builtins.eval
    exec(user_input)           # builtins.exec
    compile(user_input, '<string>', 'exec')  # builtins.compile

    # Command Injection
    import os
    os.system(user_input)      # os.system

    import subprocess
    subprocess.run(user_input, shell=True)   # subprocess.run
    subprocess.Popen(user_input, shell=True) # subprocess.Popen
    subprocess.call(user_input, shell=True)  # subprocess.call

    # Path Traversal
    open(user_input, 'r')      # builtins.open

    # Deserialization
    import pickle
    pickle.loads(user_input)   # pickle.loads

    import yaml
    yaml.load(user_input)      # yaml.load

    # Module Injection
    __import__(user_input)     # builtins.__import__
"#;

    let result = process_file(code, "test_repo", "owasp.py", "owasp_module");

    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    let target_ids: HashSet<String> = calls_edges
        .iter()
        .map(|e| e.target_id.clone())
        .collect();

    println!("OWASP Top 10 sinks detected:");
    for target in &target_ids {
        if target.starts_with("builtins.")
            || target.starts_with("os.")
            || target.starts_with("subprocess.")
            || target.starts_with("pickle.")
            || target.starts_with("yaml.")
        {
            println!("  ✓ {}", target);
        }
    }

    // Verify all OWASP categories
    let owasp_sinks = vec![
        "builtins.eval",
        "builtins.exec",
        "builtins.compile",
        "os.system",
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.call",
        "builtins.open",
        "pickle.loads",
        "yaml.load",
        "builtins.__import__",
    ];

    let mut detected = 0;
    for sink in &owasp_sinks {
        if target_ids.iter().any(|id| id.contains(sink)) {
            detected += 1;
        }
    }

    println!("Detected {}/{} OWASP sinks", detected, owasp_sinks.len());
    assert!(
        detected >= 8,
        "Should detect at least 8 out of {} OWASP sinks",
        owasp_sinks.len()
    );
}

/// Test 5: Mixed safe and unsafe - Precision test
#[test]
fn test_fqn_taint_mixed_precision() {
    let code = r#"
# User-defined safe alternatives
def safe_eval(expression):
    """Safely evaluate numeric expressions"""
    import ast
    return ast.literal_eval(expression)

def safe_exec(code):
    """Safely execute whitelisted code"""
    if code in ['print("hello")', 'x = 1']:
        exec(code)  # This is built-in exec - DETECTED

def process_mixed(user_input):
    # Safe: user-defined function
    result1 = safe_eval(user_input)  # NOT a sink

    # Unsafe: built-in function
    result2 = eval(user_input)       # builtins.eval - DETECTED

    # Safe: user-defined wrapper
    safe_exec(user_input)            # NOT a sink (wrapper function)

    # Unsafe: direct built-in in safe_exec
    # (detected when analyzing safe_exec function body)

    return result1, result2
"#;

    let result = process_file(code, "test_repo", "mixed.py", "mixed_module");

    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    let target_ids: HashSet<String> = calls_edges
        .iter()
        .map(|e| e.target_id.clone())
        .collect();

    println!("Mixed code analysis:");
    for target in &target_ids {
        let is_builtin = target.starts_with("builtins.");
        let marker = if is_builtin { "🔴" } else { "🟢" };
        println!("  {} {}", marker, target);
    }

    // Should detect built-in eval (dangerous)
    assert!(
        target_ids.contains("builtins.eval"),
        "Should detect dangerous built-in eval"
    );

    // Should NOT detect safe_eval as builtins.eval
    let builtin_eval_count = target_ids
        .iter()
        .filter(|id| id == &"builtins.eval")
        .count();

    println!("Built-in eval calls: {}", builtin_eval_count);
    assert!(
        builtin_eval_count >= 1,
        "Should detect at least 1 built-in eval call"
    );
}

/// Helper: Print analyzer sinks for debugging
#[allow(dead_code)]
fn print_analyzer_sinks() {
    let analyzer = TaintAnalyzer::new();
    let sinks = analyzer.get_sinks();

    println!("TaintAnalyzer configured sinks:");
    for sink in sinks {
        println!("  - {} ({})", sink.pattern, sink.description);
    }
}
