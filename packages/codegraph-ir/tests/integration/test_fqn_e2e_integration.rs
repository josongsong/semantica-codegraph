//! End-to-End Integration Test for FQN Resolver + Taint Analysis
//!
//! This test verifies that:
//! 1. FQN resolver correctly resolves built-in function calls
//! 2. CALLS edges have properly resolved target FQNs
//! 3. Taint sinks use FQN patterns for precise matching
//! 4. False positives eliminated (user-defined functions ignored)

use codegraph_ir::pipeline::processor::process_file;
use codegraph_ir::shared::{Edge, EdgeKind};
use codegraph_ir::features::taint_analysis::infrastructure::taint::TaintAnalyzer;
use std::collections::HashSet;

/// Test basic FQN resolution for built-in functions
#[test]
fn test_fqn_builtin_resolution() {
    let code = r#"
def vulnerable_function(user_input):
    # Code injection vulnerability
    result = eval(user_input)

    # Command injection
    import os
    os.system(user_input)

    # Path traversal
    f = open(user_input, 'r')

    return result
"#;

    let result = process_file(code, "test_repo", "test.py", "test_module");

    println!("Total nodes: {}", result.nodes.len());
    println!("Total edges: {}", result.edges.len());
    for edge in &result.edges {
        println!("  Edge: {} {:?} -> {}", edge.source_id, edge.kind, edge.target_id);
    }

    // Find CALLS edges
    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    assert!(!calls_edges.is_empty(), "Should have CALLS edges. Total edges: {}", result.edges.len());

    // Verify FQN resolution
    let target_ids: Vec<String> = calls_edges.iter().map(|e| e.target_id.clone()).collect();

    println!("Target IDs: {:?}", target_ids);

    // Check for resolved built-in FQNs
    let has_builtin_eval = target_ids.iter().any(|id| id == "builtins.eval");
    let has_os_system = target_ids
        .iter()
        .any(|id| id == "os.system" || id.contains("system"));
    let has_builtin_open = target_ids.iter().any(|id| id == "builtins.open");

    assert!(
        has_builtin_eval,
        "eval() should be resolved to builtins.eval. Found: {:?}",
        target_ids
    );
    assert!(
        has_os_system,
        "os.system() should be resolved with FQN. Found: {:?}",
        target_ids
    );
    assert!(
        has_builtin_open,
        "open() should be resolved to builtins.open. Found: {:?}",
        target_ids
    );

    // === TAINT ANALYSIS INTEGRATION ===
    // Verify that TaintAnalyzer sinks use FQN patterns
    let taint_analyzer = TaintAnalyzer::new();
    let sinks = taint_analyzer.get_sinks();
    let sink_patterns: Vec<String> = sinks.iter().map(|s| s.pattern.clone()).collect();

    println!("\n🔐 Taint Analyzer Sinks (FQN-based):");
    for pattern in &sink_patterns {
        if pattern.starts_with("builtins.") || pattern.starts_with("os.") || pattern.starts_with("subprocess.") {
            println!("  ✓ {}", pattern);
        }
    }

    // Verify FQN sinks are configured
    assert!(
        sink_patterns.contains(&"builtins.eval".to_string()),
        "TaintAnalyzer should have FQN sink: builtins.eval"
    );
    assert!(
        sink_patterns.contains(&"builtins.exec".to_string()),
        "TaintAnalyzer should have FQN sink: builtins.exec"
    );
    assert!(
        sink_patterns.contains(&"os.system".to_string()),
        "TaintAnalyzer should have FQN sink: os.system"
    );
    assert!(
        sink_patterns.contains(&"builtins.open".to_string()),
        "TaintAnalyzer should have FQN sink: builtins.open"
    );

    // Check which targets match taint sinks
    let mut detected_sinks = Vec::new();
    for target in &target_ids {
        for sink in sinks {
            if sink.matches(target) {
                detected_sinks.push((target.clone(), sink.pattern.clone(), sink.description.clone()));
            }
        }
    }

    println!("\n🎯 Detected Taint Sinks in Code:");
    for (target, pattern, desc) in &detected_sinks {
        println!("  🔥 {} → {} ({})", target, pattern, desc);
    }

    // Should detect dangerous calls
    assert!(
        detected_sinks.len() >= 2,
        "Should detect at least 2 dangerous sinks, found: {}",
        detected_sinks.len()
    );

    // Verify specific sinks detected
    let has_eval_sink = detected_sinks.iter().any(|(t, _, _)| t.contains("eval"));
    let has_system_sink = detected_sinks.iter().any(|(t, _, _)| t.contains("system"));

    assert!(has_eval_sink, "Should detect eval as taint sink");
    assert!(has_system_sink, "Should detect system as taint sink");

    println!("\n✅ FQN + Taint Integration: PASSED");
}

/// Test FQN resolution with imports
#[test]
fn test_fqn_with_imports() {
    let code = r#"
import os
import subprocess
from pathlib import Path

def vulnerable_operations(user_input):
    # Different import styles
    os.system(user_input)  # Direct import
    subprocess.run(user_input, shell=True)  # Module import
    Path(user_input).read_text()  # From import
"#;

    let result = process_file(code, "test_repo", "test.py", "test_module");

    // Find all CALLS edges
    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    let target_ids: HashSet<String> = calls_edges.iter().map(|e| e.target_id.clone()).collect();

    println!("Resolved targets: {:?}", target_ids);

    // Verify module-qualified names
    assert!(
        target_ids.iter().any(|id| id.contains("os.system")),
        "Should have os.system: {:?}",
        target_ids
    );
    assert!(
        target_ids.iter().any(|id| id.contains("subprocess")),
        "Should have subprocess calls: {:?}",
        target_ids
    );
}

/// Test FQN resolution for all common dangerous functions
#[test]
fn test_fqn_dangerous_functions_comprehensive() {
    let code = r#"
import os
import subprocess
import pickle
import yaml

def all_vulnerabilities(user_input):
    # Code execution
    eval(user_input)
    exec(user_input)
    compile(user_input, '<string>', 'exec')

    # Command injection
    os.system(user_input)
    os.popen(user_input)
    subprocess.run(user_input, shell=True)
    subprocess.Popen(user_input, shell=True)

    # Deserialization
    pickle.loads(user_input)
    yaml.load(user_input)

    # File operations
    open(user_input, 'r')
    __import__(user_input)
"#;

    let result = process_file(code, "test_repo", "test.py", "test_module");

    

    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    let target_ids: HashSet<String> = calls_edges.iter().map(|e| e.target_id.clone()).collect();

    println!("All resolved dangerous functions:");
    for target in &target_ids {
        println!("  - {}", target);
    }

    // Expected dangerous functions with FQNs
    let expected_builtins = vec!["eval", "exec", "compile", "open", "__import__"];

    for builtin in expected_builtins {
        let fqn = format!("builtins.{}", builtin);
        assert!(
            target_ids.contains(&fqn),
            "Should have resolved {}: {:?}",
            fqn,
            target_ids
        );
    }

    // Module functions
    let expected_modules = vec![
        ("os", vec!["system", "popen"]),
        ("subprocess", vec!["run", "Popen"]),
        ("pickle", vec!["loads"]),
        ("yaml", vec!["load"]),
    ];

    for (module, funcs) in expected_modules {
        for func in funcs {
            let has_func = target_ids
                .iter()
                .any(|id| id.contains(module) && id.contains(func));
            assert!(
                has_func,
                "Should have {}.{}: {:?}",
                module, func, target_ids
            );
        }
    }
}

/// Test FQN resolver with nested function calls
#[test]
fn test_fqn_nested_calls() {
    let code = r#"
def process_data(data):
    # Nested calls
    result = eval(compile(data, '<string>', 'exec'))

    import os
    os.system(open('/tmp/cmd').read())

    return result
"#;

    let result = process_file(code, "test_repo", "test.py", "test_module");

    

    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    assert!(calls_edges.len() >= 4, "Should have at least 4 CALLS edges");

    let target_ids: Vec<String> = calls_edges.iter().map(|e| e.target_id.clone()).collect();

    println!("Nested call targets: {:?}", target_ids);

    // All should be resolved
    assert!(target_ids.iter().any(|id| id == "builtins.eval"));
    assert!(target_ids.iter().any(|id| id == "builtins.compile"));
    assert!(target_ids.iter().any(|id| id == "builtins.open"));
    assert!(target_ids.iter().any(|id| id.contains("os.system")));
}

/// Test FQN resolver edge cases
#[test]
fn test_fqn_edge_cases() {
    let code = r#"
def edge_cases():
    # Aliased imports
    from os import system as cmd
    cmd("ls")

    # Dynamic attribute access
    import subprocess
    func = getattr(subprocess, 'run')
    func(['ls'])

    # Lambda with built-in
    f = lambda x: eval(x)
    f("1+1")
"#;

    let result = process_file(code, "test_repo", "test.py", "test_module");

    

    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    let target_ids: HashSet<String> = calls_edges.iter().map(|e| e.target_id.clone()).collect();

    println!("Edge case targets: {:?}", target_ids);

    // Should still resolve built-ins and module functions
    assert!(
        target_ids.iter().any(|id| id == "builtins.eval"),
        "Should resolve eval in lambda: {:?}",
        target_ids
    );
    assert!(
        target_ids.iter().any(|id| id.contains("getattr")),
        "Should have getattr call: {:?}",
        target_ids
    );
}

/// Test that FQNs appear in all expected edge types
#[test]
fn test_fqn_in_various_contexts() {
    let code = r#"
import os

# Direct call
os.system("ls")

# Assignment
cmd = os.system
result = cmd("ls")

# Passed as argument
def run_command(fn):
    fn("ls")

run_command(os.system)

# Conditional
if True:
    eval("1+1")
else:
    exec("pass")
"#;

    let result = process_file(code, "test_repo", "test.py", "test_module");

    

    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    let target_ids: HashSet<String> = calls_edges.iter().map(|e| e.target_id.clone()).collect();

    println!("Context targets: {:?}", target_ids);

    // Check all contexts have FQNs
    assert!(
        target_ids.iter().any(|id| id.contains("os.system")),
        "Direct call should have FQN: {:?}",
        target_ids
    );
    assert!(
        target_ids.iter().any(|id| id == "builtins.eval"),
        "Conditional call should have FQN: {:?}",
        target_ids
    );
}

/// Benchmark FQN resolution performance
#[test]
#[ignore] // Run with --ignored for performance testing
fn bench_fqn_resolution_performance() {
    use std::time::Instant;

    // Large test file with many calls
    let mut code = String::from("import os\nimport subprocess\n\n");
    for i in 0..100 {
        code.push_str(&format!(
            r#"
def func_{}(x):
    eval(x)
    os.system(x)
    subprocess.run(x)
    open(x)
"#,
            i
        ));
    }

    let start = Instant::now();
    let result = process_file(&code, "test_repo", "large.py", "large");
    let duration = start.elapsed();

    

    println!("FQN resolution for 100 functions took: {:?}", duration);
    println!("Total nodes: {}", result.nodes.len());
    println!("Total edges: {}", result.edges.len());

    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    println!("CALLS edges: {}", calls_edges.len());

    // Should complete in reasonable time
    assert!(
        duration.as_secs() < 5,
        "FQN resolution should complete in <5s, took {:?}",
        duration
    );
}

/// Verify FQN resolver handles common security sinks
#[test]
fn test_fqn_security_sinks() {
    let code = r#"
def security_test(user_input):
    # All common security sinks should be resolved with FQNs
    eval(user_input)        # Code injection
    exec(user_input)        # Code injection
    __import__(user_input)  # Module injection

    import os
    os.system(user_input)   # Command injection
    os.popen(user_input)    # Command injection

    import subprocess
    subprocess.run(user_input, shell=True)     # Command injection
    subprocess.Popen(user_input, shell=True)   # Command injection
    subprocess.call(user_input, shell=True)    # Command injection

    open(user_input)        # Path traversal
"#;

    let result = process_file(code, "test_repo", "test.py", "test_module");

    

    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    let target_ids: HashSet<String> = calls_edges.iter().map(|e| e.target_id.clone()).collect();

    println!("Security sink FQNs:");
    for target in &target_ids {
        println!("  - {}", target);
    }

    // Verify all critical security sinks have FQNs
    let security_sinks = vec![
        "builtins.eval",
        "builtins.exec",
        "builtins.__import__",
        "builtins.open",
    ];

    for sink in security_sinks {
        assert!(
            target_ids.contains(sink),
            "Security sink {} should be resolved: {:?}",
            sink,
            target_ids
        );
    }

    // Verify module security sinks
    assert!(
        target_ids.iter().any(|id| id.contains("os.system")),
        "os.system should be resolved: {:?}",
        target_ids
    );
    assert!(
        target_ids
            .iter()
            .any(|id| id.contains("subprocess") && id.contains("run")),
        "subprocess.run should be resolved: {:?}",
        target_ids
    );
}

/// Test FQN + Taint: False Positive Elimination
///
/// This is the KEY test proving FQN integration eliminates false positives.
/// User-defined functions with same names as built-ins should NOT be detected as sinks.
#[test]
fn test_fqn_taint_false_positive_elimination() {
    let code = r#"
# User-defined SAFE functions with same names as dangerous built-ins
def eval(expression):
    """Safely evaluate numeric expressions only"""
    import ast
    try:
        return ast.literal_eval(expression)  # Safe: only literals
    except:
        return 0

def exec(code_str):
    """Safely execute whitelisted code"""
    allowed = ['print("hello")', 'x = 1']
    if code_str in allowed:
        # This uses built-in exec, but wrapper is safe
        __builtins__['exec'](code_str)
    else:
        print("Rejected:", code_str)

def system(command):
    """Safely log system commands"""
    print("Would run:", command)
    return 0

def open(path, mode='r'):
    """Safely open files with validation"""
    import os
    if '..' in path or path.startswith('/'):
        raise ValueError("Path traversal detected")
    # Would use real open with validation
    print("Would open:", path)
    return None

def process_user_input(user_data):
    # All these call USER-DEFINED functions, NOT built-ins
    result1 = eval(user_data)       # User's eval - SAFE
    exec(user_data)                 # User's exec - SAFE
    system(user_data)               # User's system - SAFE
    f = open(user_data)             # User's open - SAFE

    return result1
"#;

    let result = process_file(code, "test_repo", "safe.py", "safe_module");

    println!("\n=== FALSE POSITIVE ELIMINATION TEST ===");
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

    println!("\nUser-defined function calls:");
    for target in &target_ids {
        println!("  - {}", target);
    }

    // KEY ASSERTIONS: User-defined functions should NOT have "builtins." prefix
    assert!(
        !target_ids.contains("builtins.eval"),
        "User-defined eval should NOT be resolved as builtins.eval"
    );
    assert!(
        !target_ids.contains("builtins.exec"),
        "User-defined exec should NOT be resolved as builtins.exec"
    );
    assert!(
        !target_ids.contains("os.system"),
        "User-defined system should NOT be resolved as os.system"
    );
    assert!(
        !target_ids.contains("builtins.open"),
        "User-defined open should NOT be resolved as builtins.open"
    );

    // Verify with TaintAnalyzer that user-defined functions don't match sinks
    let taint_analyzer = TaintAnalyzer::new();
    let sinks = taint_analyzer.get_sinks();

    let mut false_positives = Vec::new();
    for target in &target_ids {
        for sink in sinks {
            if sink.matches(target) {
                // Check if this is a user-defined function matching a sink pattern
                if !target.starts_with("builtins.")
                    && !target.starts_with("os.")
                    && !target.starts_with("subprocess.")
                    && !target.starts_with("pickle.")
                    && !target.starts_with("yaml.")
                {
                    false_positives.push((target.clone(), sink.pattern.clone()));
                }
            }
        }
    }

    println!("\n🔍 Checking for false positives...");
    if false_positives.is_empty() {
        println!("  ✅ NO FALSE POSITIVES - User-defined functions correctly ignored!");
    } else {
        println!("  ❌ FALSE POSITIVES DETECTED:");
        for (target, pattern) in &false_positives {
            println!("    - {} matched sink pattern: {}", target, pattern);
        }
    }

    // Should have ZERO false positives
    assert_eq!(
        false_positives.len(),
        0,
        "Should have zero false positives, but found: {:?}",
        false_positives
    );

    println!("\n✅ FALSE POSITIVE ELIMINATION: PASSED");
    println!("   User-defined safe wrappers are correctly ignored by taint analysis");
}

/// Test FQN + Taint: Mixed Safe and Dangerous Code
///
/// Verifies precision when mixing user-defined safe functions and actual dangerous built-ins.
#[test]
fn test_fqn_taint_mixed_code_precision() {
    let code = r#"
# User-defined safe wrapper
def safe_eval(expression):
    import ast
    return ast.literal_eval(expression)

def mixed_function(user_input):
    # Safe: user-defined function
    safe_result = safe_eval(user_input)

    # DANGEROUS: actual built-in eval
    dangerous_result = eval(user_input)

    # Safe: user-defined wrapper called
    safe_result2 = safe_eval(user_input)

    import os
    # DANGEROUS: actual os.system
    os.system(user_input)

    return safe_result, dangerous_result
"#;

    let result = process_file(code, "test_repo", "mixed.py", "mixed_module");

    println!("\n=== MIXED CODE PRECISION TEST ===");

    let calls_edges: Vec<&Edge> = result
        .edges
        .iter()
        .filter(|e| e.kind == EdgeKind::Calls)
        .collect();

    let target_ids: HashSet<String> = calls_edges
        .iter()
        .map(|e| e.target_id.clone())
        .collect();

    println!("\nAll function calls:");
    for target in &target_ids {
        println!("  - {}", target);
    }

    // Verify with TaintAnalyzer
    let taint_analyzer = TaintAnalyzer::new();
    let sinks = taint_analyzer.get_sinks();

    let mut safe_calls = Vec::new();
    let mut dangerous_calls = Vec::new();

    for target in &target_ids {
        let mut is_dangerous = false;
        for sink in sinks {
            if sink.matches(target) {
                dangerous_calls.push(target.clone());
                is_dangerous = true;
                break;
            }
        }
        if !is_dangerous {
            safe_calls.push(target.clone());
        }
    }

    println!("\n🟢 Safe calls (user-defined or safe built-ins):");
    for call in &safe_calls {
        println!("  ✓ {}", call);
    }

    println!("\n🔴 Dangerous calls (detected sinks):");
    for call in &dangerous_calls {
        println!("  🔥 {}", call);
    }

    // Should detect ONLY built-in eval and os.system as dangerous
    assert!(
        dangerous_calls.iter().any(|c| c.contains("builtins.eval")),
        "Should detect built-in eval as dangerous"
    );
    assert!(
        dangerous_calls.iter().any(|c| c.contains("os.system")),
        "Should detect os.system as dangerous"
    );

    // safe_eval should NOT be in dangerous calls
    let has_safe_eval_in_dangerous = dangerous_calls.iter().any(|c| c.contains("safe_eval"));
    assert!(
        !has_safe_eval_in_dangerous,
        "safe_eval should NOT be detected as dangerous"
    );

    // Count: should have exactly 2 dangerous calls (eval + os.system)
    // May have more if there are other calls, but at least 2
    assert!(
        dangerous_calls.len() >= 2,
        "Should detect at least 2 dangerous calls (eval, os.system), found: {}",
        dangerous_calls.len()
    );

    println!("\n✅ MIXED CODE PRECISION: PASSED");
    println!("   Correctly distinguished {} safe calls from {} dangerous calls",
             safe_calls.len(), dangerous_calls.len());
}
