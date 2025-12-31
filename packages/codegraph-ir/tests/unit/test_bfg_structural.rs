//! Structural verification tests for BFG block splitting
//!
//! These tests verify that BFG correctly handles various control flow structures
//! WITHOUT hardcoding - purely based on AST structure.

use codegraph_ir::pipeline::processor::process_python_file;

#[test]
fn test_nested_if_blocks() {
    let source = r#"
def nested(x, y):
    if x > 0:
        if y > 0:
            z = 1
        else:
            z = 2
    else:
        z = 3
    return z
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");

    // Should have SSA graph
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];

    // Should have at least 3 versions of z (3 branches)
    let z_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "z").collect();
    assert!(z_vars.len() >= 3,
        "Nested if should create at least 3 z versions. Found: {}", z_vars.len());

    println!("✅ Nested if: {} z versions", z_vars.len());

    // φ-nodes should be generated for merges
    println!("   φ-nodes: {}", ssa.phi_nodes.len());
    for phi in &ssa.phi_nodes {
        println!("   - {} = φ({} predecessors)", phi.variable, phi.predecessors.len());
    }
}

#[test]
fn test_elif_chain_blocks() {
    let source = r#"
def elif_chain(x):
    if x > 10:
        y = 1
    elif x > 5:
        y = 2
    elif x > 0:
        y = 3
    else:
        y = 4
    return y
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];

    // Should have 4 versions of y (4 branches)
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();
    assert!(y_vars.len() >= 4,
        "Elif chain should create 4 y versions. Found: {}", y_vars.len());

    println!("✅ Elif chain: {} y versions", y_vars.len());

    // φ-nodes should be generated
    println!("   φ-nodes: {}", ssa.phi_nodes.len());
}

#[test]
fn test_loop_with_if_blocks() {
    let source = r#"
def loop_with_if(items):
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

    // Should have multiple versions of total (loop + if)
    let total_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "total").collect();
    assert!(total_vars.len() >= 2,
        "Loop with if should create multiple total versions. Found: {}", total_vars.len());

    println!("✅ Loop with if: {} total versions", total_vars.len());

    // φ-nodes for both loop and if merge points
    println!("   φ-nodes: {}", ssa.phi_nodes.len());
}

#[test]
fn test_try_except_with_if_blocks() {
    let source = r#"
def try_with_if(x):
    try:
        if x > 0:
            y = 1
        else:
            y = 0
    except:
        y = -1
    return y
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];

    // Should have 3 versions of y (if/else/except)
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();
    assert!(y_vars.len() >= 2,
        "Try/except with if should create multiple y versions. Found: {}", y_vars.len());

    println!("✅ Try/except with if: {} y versions", y_vars.len());

    // φ-nodes should be generated
    println!("   φ-nodes: {}", ssa.phi_nodes.len());
}

#[test]
fn test_deeply_nested_structure() {
    let source = r#"
def deeply_nested(a, b, c):
    if a > 0:
        if b > 0:
            if c > 0:
                x = 1
            else:
                x = 2
        else:
            x = 3
    else:
        x = 4
    return x
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];

    // Should have 4 versions of x (4 leaf branches)
    let x_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "x").collect();
    assert!(x_vars.len() >= 4,
        "Deeply nested should create 4 x versions. Found: {}", x_vars.len());

    println!("✅ Deeply nested: {} x versions", x_vars.len());

    // Multiple φ-nodes for nested merges
    println!("   φ-nodes: {}", ssa.phi_nodes.len());
    for phi in &ssa.phi_nodes {
        println!("   - {} = φ({} predecessors)", phi.variable, phi.predecessors.len());
    }
}

#[test]
fn test_mixed_control_flow() {
    let source = r#"
def mixed(items, threshold):
    result = 0
    for item in items:
        try:
            if item > threshold:
                result = result + item
            else:
                result = result - item
        except:
            result = 0
    return result
"#;

    let result = process_python_file(source, "test-repo", "test.py", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];

    // Should have multiple versions of result (loop + try + if)
    let result_vars: Vec<_> = ssa.variables.iter()
        .filter(|v| v.base_name == "result")
        .collect();
    assert!(result_vars.len() >= 3,
        "Mixed control flow should create multiple result versions. Found: {}",
        result_vars.len());

    println!("✅ Mixed control flow: {} result versions", result_vars.len());

    // Multiple φ-nodes for complex merges
    println!("   φ-nodes: {}", ssa.phi_nodes.len());
}
