//! Edge case and stress tests for SSA φ-node generation
//!
//! Tests extreme cases to ensure robustness:
//! - Deep nesting (10+ levels)
//! - Many branches (100+ elif)
//! - Empty blocks
//! - Single statement blocks
//! - No else clause
//! - Only else, no if
//! - Chained assignments
//! - Multiple variables in same block

use codegraph_ir::pipeline::processor::process_python_file;

// ========================================
// Edge Case 1: Very Deep Nesting (10 levels)
// ========================================

#[test]
fn test_extreme_nesting_10_levels() {
    let source = r#"
def deep_nest(a, b, c, d, e, f, g, h, i, j):
    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:
                    if e > 0:
                        if f > 0:
                            if g > 0:
                                if h > 0:
                                    if i > 0:
                                        if j > 0:
                                            x = 1
                                        else:
                                            x = 2
                                    else:
                                        x = 3
                                else:
                                    x = 4
                            else:
                                x = 5
                        else:
                            x = 6
                    else:
                        x = 7
                else:
                    x = 8
            else:
                x = 9
        else:
            x = 10
    else:
        x = 11
    return x
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];
    let x_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "x").collect();

    println!("🔥 Extreme nesting (10 levels): {} x versions", x_vars.len());

    // Should have 11 versions (11 leaf branches)
    assert!(x_vars.len() >= 11,
        "Deep nesting should create 11 x versions. Found: {}", x_vars.len());

    // Should have φ-nodes for merges
    println!("   φ-nodes: {}", ssa.phi_nodes.len());
    assert!(ssa.phi_nodes.len() > 0, "Should have φ-nodes for deep nesting");
}

// ========================================
// Edge Case 2: Many Branches (50 elif)
// ========================================

#[test]
fn test_many_elif_branches() {
    let mut source = String::from("def many_branches(x):\n");

    // Generate 50 elif branches
    for i in 0..50 {
        if i == 0 {
            source.push_str(&format!("    if x == {}:\n", i));
        } else {
            source.push_str(&format!("    elif x == {}:\n", i));
        }
        source.push_str(&format!("        y = {}\n", i));
    }
    source.push_str("    else:\n");
    source.push_str("        y = 999\n");
    source.push_str("    return y\n");

    let result = process_python_file(&source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🔥 Many branches (50 elif): {} y versions", y_vars.len());

    // Should have 51 versions (50 elif + else)
    assert!(y_vars.len() >= 51,
        "50 elif + else should create 51 y versions. Found: {}", y_vars.len());

    println!("   φ-nodes: {}", ssa.phi_nodes.len());
    assert!(ssa.phi_nodes.len() > 0, "Should have φ-nodes");
}

// ========================================
// Edge Case 3: Empty If Block
// ========================================

#[test]
fn test_empty_if_block() {
    let source = r#"
def empty_if(x):
    y = 0
    if x > 10:
        pass
    else:
        y = 1
    return y
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🔥 Empty if block: {} y versions", y_vars.len());

    // Should have 2 versions (initial + else)
    assert!(y_vars.len() >= 2,
        "Empty if should still create versions. Found: {}", y_vars.len());
}

// ========================================
// Edge Case 4: No Else Clause
// ========================================

#[test]
fn test_no_else_clause() {
    let source = r#"
def no_else(x):
    y = 0
    if x > 10:
        y = 1
    return y
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🔥 No else clause: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // Should have 2 versions (initial + if)
    assert!(y_vars.len() >= 2,
        "No else should create 2 versions. Found: {}", y_vars.len());
}

// ========================================
// Edge Case 5: Chained Assignments
// ========================================

#[test]
fn test_chained_assignments() {
    let source = r#"
def chained(x):
    if x > 10:
        y = 1
        y = y + 1
        y = y + 1
        y = y + 1
    else:
        y = 2
        y = y - 1
    return y
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🔥 Chained assignments: {} y versions", y_vars.len());

    // Should have many versions (1 + 3 in then, 1 + 1 in else = 6)
    assert!(y_vars.len() >= 6,
        "Chained assignments should create many versions. Found: {}", y_vars.len());

    println!("   φ-nodes: {}", ssa.phi_nodes.len());
    assert!(ssa.phi_nodes.len() > 0, "Should have φ-nodes");
}

// ========================================
// Edge Case 6: Multiple Variables Same Block
// ========================================

#[test]
fn test_multiple_variables_same_block() {
    let source = r#"
def multi_vars(x):
    if x > 10:
        a = 1
        b = 2
        c = 3
    else:
        a = 4
        b = 5
        c = 6
    return a + b + c
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];

    let a_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "a").collect();
    let b_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "b").collect();
    let c_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "c").collect();

    println!("🔥 Multiple variables: a={}, b={}, c={} versions",
             a_vars.len(), b_vars.len(), c_vars.len());

    // Each should have 2 versions (then + else)
    assert!(a_vars.len() >= 2, "a should have 2 versions");
    assert!(b_vars.len() >= 2, "b should have 2 versions");
    assert!(c_vars.len() >= 2, "c should have 2 versions");

    // Should have φ-nodes for all variables
    println!("   φ-nodes: {}", ssa.phi_nodes.len());
    assert!(ssa.phi_nodes.len() >= 3, "Should have φ-nodes for a, b, c");
}

// ========================================
// Edge Case 7: If in Loop (Nested Control Flow)
// ========================================

#[test]
fn test_if_in_loop() {
    let source = r#"
def if_in_loop(items):
    total = 0
    for item in items:
        if item > 0:
            total = total + item
        else:
            total = total - item
    return total
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];
    let total_vars: Vec<_> = ssa.variables.iter()
        .filter(|v| v.base_name == "total")
        .collect();

    println!("🔥 If in loop: {} total versions", total_vars.len());

    // Should have multiple versions (init + loop iterations)
    assert!(total_vars.len() >= 3,
        "If in loop should create multiple versions. Found: {}", total_vars.len());

    println!("   φ-nodes: {}", ssa.phi_nodes.len());
}

// ========================================
// Edge Case 8: Loop in If (Reverse Nesting)
// ========================================

#[test]
fn test_loop_in_if() {
    let source = r#"
def loop_in_if(x, items):
    total = 0
    if x > 0:
        for item in items:
            total = total + item
    else:
        for item in items:
            total = total - item
    return total
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];
    let total_vars: Vec<_> = ssa.variables.iter()
        .filter(|v| v.base_name == "total")
        .collect();

    println!("🔥 Loop in if: {} total versions", total_vars.len());

    // Should have versions from both branches
    assert!(total_vars.len() >= 3,
        "Loop in if should create versions. Found: {}", total_vars.len());

    println!("   φ-nodes: {}", ssa.phi_nodes.len());
}

// ========================================
// Edge Case 9: Same Variable Different Types (Python)
// ========================================

#[test]
fn test_same_variable_different_types() {
    let source = r#"
def type_change(x):
    if x > 0:
        y = 42
    else:
        y = "hello"
    return y
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🔥 Type change: {} y versions", y_vars.len());

    // Should have 2 versions (different types)
    assert!(y_vars.len() >= 2,
        "Type change should create versions. Found: {}", y_vars.len());

    println!("   φ-nodes: {}", ssa.phi_nodes.len());
    assert!(ssa.phi_nodes.len() > 0, "Should have φ-nodes despite type change");
}

// ========================================
// Edge Case 10: Ternary-like (Inline If)
// ========================================

#[test]
fn test_inline_if_expression() {
    let source = r#"
def inline_if(x, a, b):
    y = a if x > 0 else b
    return y
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🔥 Inline if: {} y versions", y_vars.len());

    // Inline if is single assignment (not control flow)
    assert!(y_vars.len() >= 1,
        "Inline if should create version. Found: {}", y_vars.len());
}

// ========================================
// Edge Case 11: Early Return (Divergent Paths)
// ========================================

#[test]
fn test_early_return() {
    let source = r#"
def early_return(x):
    y = 0
    if x > 10:
        y = 1
        return y
    else:
        y = 2
    return y
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🔥 Early return: {} y versions", y_vars.len());

    // Should have 3 versions (init + then + else)
    assert!(y_vars.len() >= 3,
        "Early return should create versions. Found: {}", y_vars.len());
}

// ========================================
// Edge Case 12: No Variable Assignment (Control Flow Only)
// ========================================

#[test]
fn test_control_flow_no_assignment() {
    let source = r#"
def no_assignment(x):
    if x > 10:
        pass
    else:
        pass
    return 0
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];

    println!("🔥 No assignment: {} variables total", ssa.variables.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // Should handle gracefully even with no variables
    // (no crash is success)
}

// ========================================
// Edge Case 13: All Branches Assign Different Variables
// ========================================

#[test]
fn test_different_variables_per_branch() {
    let source = r#"
def different_vars(x):
    if x > 10:
        a = 1
    elif x > 5:
        b = 2
    else:
        c = 3
    return x
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];

    let a_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "a").collect();
    let b_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "b").collect();
    let c_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "c").collect();

    println!("🔥 Different vars per branch: a={}, b={}, c={} versions",
             a_vars.len(), b_vars.len(), c_vars.len());

    // Each should have 1 version (only defined in one branch)
    assert_eq!(a_vars.len(), 1, "a should have 1 version");
    assert_eq!(b_vars.len(), 1, "b should have 1 version");
    assert_eq!(c_vars.len(), 1, "c should have 1 version");

    // No φ-nodes (different variables)
    println!("   φ-nodes: {} (should be 0)", ssa.phi_nodes.len());
}

// ========================================
// Stress Test: Combination of All Edge Cases
// ========================================

#[test]
fn test_extreme_combination() {
    let source = r#"
def extreme_combo(x, y, items):
    a = 0
    b = 0
    if x > 10:
        if y > 5:
            for item in items:
                if item > 0:
                    a = a + 1
                    b = b + item
                else:
                    a = a - 1
        else:
            a = 100
    elif x > 5:
        for item in items:
            b = b + item
    else:
        pass
    return a + b
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");

    let ssa = &result.ssa_graphs[0];

    let a_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "a").collect();
    let b_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "b").collect();

    println!("🔥 EXTREME COMBO:");
    println!("   a versions: {}", a_vars.len());
    println!("   b versions: {}", b_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // Should handle complex nesting without crashing
    assert!(a_vars.len() >= 2, "Should create multiple a versions");
    assert!(b_vars.len() >= 2, "Should create multiple b versions");
}
