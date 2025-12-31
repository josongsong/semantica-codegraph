//! Multi-language SSA tests
//!
//! Tests language-specific control flow constructs to ensure φ-node generation
//! works across all supported languages (Python, TypeScript, Java, Kotlin, Rust, Go)

use codegraph_ir::pipeline::processor::{
    process_file, process_python_file,
};

// ========================================
// TypeScript Tests
// ========================================

#[test]
fn test_typescript_if_expression() {
    let source = r#"
function conditional(x: number): number {
    let y: number;
    if (x > 10) {
        y = x + 5;
    } else {
        y = x - 5;
    }
    return y;
}
"#;

    let result = process_file(source, "test-repo", "test.ts", "test");

    // TypeScript uses if_statement (same as Python)
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph for TypeScript");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🔷 TypeScript if: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    assert!(y_vars.len() >= 2, "Should have 2+ y versions for TypeScript if/else");
    assert!(ssa.phi_nodes.len() > 0, "Should have φ-nodes for TypeScript");
}

#[test]
fn test_typescript_switch_statement() {
    let source = r#"
function switchCase(x: number): number {
    let y: number;
    switch (x) {
        case 1:
            y = 10;
            break;
        case 2:
            y = 20;
            break;
        default:
            y = 0;
    }
    return y;
}
"#;

    let result = process_file(source, "test-repo", "test.ts", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🔷 TypeScript switch: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // Switch creates multiple branches
    assert!(y_vars.len() >= 3, "Should have 3+ y versions for switch (3 cases)");
}

#[test]
fn test_typescript_ternary_operator() {
    let source = r#"
function ternary(x: number): number {
    const y = x > 10 ? x + 5 : x - 5;
    return y;
}
"#;

    let result = process_file(source, "test-repo", "test.ts", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🔷 TypeScript ternary: {} y versions", y_vars.len());

    // Ternary is single assignment (not control flow statement)
    assert!(y_vars.len() >= 1, "Should have y version");
}

#[test]
fn test_typescript_nested_if() {
    let source = r#"
function nested(x: number, y: number): number {
    let result: number = 0;
    if (x > 0) {
        if (y > 0) {
            result = x + y;
        } else {
            result = x - y;
        }
    } else {
        result = 0;
    }
    return result;
}
"#;

    let result = process_file(source, "test-repo", "test.ts", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🔷 TypeScript nested if: {} result versions", result_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    assert!(result_vars.len() >= 3, "Should have 3+ result versions for nested if");
    assert!(ssa.phi_nodes.len() >= 1, "Should have φ-nodes");
}

#[test]
fn test_typescript_for_loop() {
    let source = r#"
function loopTest(items: number[]): number {
    let total: number = 0;
    for (let item of items) {
        total = total + item;
    }
    return total;
}
"#;

    let result = process_file(source, "test-repo", "test.ts", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let total_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "total").collect();

    println!("🔷 TypeScript for loop: {} total versions", total_vars.len());

    assert!(total_vars.len() >= 2, "Should have 2+ total versions in loop");
}

// ========================================
// Java Tests
// ========================================

#[test]
fn test_java_if_statement() {
    let source = r#"
public class Test {
    public int conditional(int x) {
        int y;
        if (x > 10) {
            y = x + 5;
        } else {
            y = x - 5;
        }
        return y;
    }
}
"#;

    let result = process_file(source, "test-repo", "test.java", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph for Java");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("☕ Java if: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    assert!(y_vars.len() >= 2, "Should have 2+ y versions for Java if/else");
    assert!(ssa.phi_nodes.len() > 0, "Should have φ-nodes for Java");
}

#[test]
fn test_java_switch_expression_jdk14() {
    let source = r#"
public class Test {
    public int switchExpr(int x) {
        int y = switch (x) {
            case 1 -> 10;
            case 2 -> 20;
            default -> 0;
        };
        return y;
    }
}
"#;

    let result = process_file(source, "test-repo", "test.java", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("☕ Java switch expr: {} y versions", y_vars.len());

    // Switch expression is single assignment
    assert!(y_vars.len() >= 1, "Should have y version");
}

#[test]
fn test_java_while_loop() {
    let source = r#"
public class Test {
    public int whileTest(int n) {
        int sum = 0;
        int i = 0;
        while (i < n) {
            sum = sum + i;
            i = i + 1;
        }
        return sum;
    }
}
"#;

    let result = process_file(source, "test-repo", "test.java", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let sum_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "sum").collect();
    let i_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "i").collect();

    println!("☕ Java while: {} sum versions, {} i versions", sum_vars.len(), i_vars.len());

    assert!(sum_vars.len() >= 2, "Should have 2+ sum versions in while loop");
    assert!(i_vars.len() >= 2, "Should have 2+ i versions in while loop");
}

// ========================================
// Kotlin Tests (Expression-based)
// ========================================

#[test]
fn test_kotlin_if_expression() {
    let source = r#"
fun conditional(x: Int): Int {
    val y = if (x > 10) {
        x + 5
    } else {
        x - 5
    }
    return y
}
"#;

    let result = process_file(source, "test-repo", "test.kt", "test");

    // Kotlin uses if_expression (not if_statement)
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph for Kotlin");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🟣 Kotlin if expr: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // In Kotlin, if is an expression that returns a value
    // Should still create versions if we track intermediate values
    assert!(y_vars.len() >= 1, "Should have y version");
}

#[test]
fn test_kotlin_when_expression() {
    let source = r#"
fun whenExpr(x: Int): Int {
    val y = when (x) {
        1 -> 10
        2 -> 20
        else -> 0
    }
    return y
}
"#;

    let result = process_file(source, "test-repo", "test.kt", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🟣 Kotlin when expr: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // When expression returns value
    assert!(y_vars.len() >= 1, "Should have y version");
}

#[test]
fn test_kotlin_when_statement() {
    let source = r#"
fun whenStmt(x: Int): Int {
    var y: Int
    when (x) {
        1 -> y = 10
        2 -> y = 20
        else -> y = 0
    }
    return y
}
"#;

    let result = process_file(source, "test-repo", "test.kt", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🟣 Kotlin when stmt: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // When as statement creates multiple assignments
    assert!(y_vars.len() >= 3, "Should have 3 y versions for when statement");
}

#[test]
fn test_kotlin_nested_when() {
    let source = r#"
fun nestedWhen(x: Int, y: Int): Int {
    val result = when (x) {
        1 -> when (y) {
            1 -> 11
            2 -> 12
            else -> 10
        }
        2 -> 20
        else -> 0
    }
    return result
}
"#;

    let result = process_file(source, "test-repo", "test.kt", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🟣 Kotlin nested when: {} result versions", result_vars.len());

    assert!(result_vars.len() >= 1, "Should have result version for nested when");
}

#[test]
fn test_kotlin_for_loop() {
    let source = r#"
fun loopTest(items: List<Int>): Int {
    var total: Int = 0
    for (item in items) {
        total = total + item
    }
    return total
}
"#;

    let result = process_file(source, "test-repo", "test.kt", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let total_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "total").collect();

    println!("🟣 Kotlin for loop: {} total versions", total_vars.len());

    assert!(total_vars.len() >= 2, "Should have 2+ total versions in for loop");
}

// ========================================
// Rust Tests (Expression-based)
// ========================================

#[test]
fn test_rust_if_expression() {
    let source = r#"
fn conditional(x: i32) -> i32 {
    let y = if x > 10 {
        x + 5
    } else {
        x - 5
    };
    y
}
"#;

    let result = process_file(source, "test-repo", "test.rs", "test");

    // Rust uses if_expression
    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph for Rust");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🦀 Rust if expr: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // Rust if is expression-based
    assert!(y_vars.len() >= 1, "Should have y version");
}

#[test]
fn test_rust_match_expression() {
    let source = r#"
fn match_expr(x: i32) -> i32 {
    let y = match x {
        1 => 10,
        2 => 20,
        _ => 0,
    };
    y
}
"#;

    let result = process_file(source, "test-repo", "test.rs", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🦀 Rust match expr: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // Match expression returns value
    assert!(y_vars.len() >= 1, "Should have y version");
}

#[test]
fn test_rust_match_with_mutations() {
    let source = r#"
fn match_mut(x: i32) -> i32 {
    let mut y = 0;
    match x {
        1 => y = 10,
        2 => y = 20,
        _ => y = 0,
    };
    y
}
"#;

    let result = process_file(source, "test-repo", "test.rs", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🦀 Rust match mut: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // Match with mutations creates multiple versions
    assert!(y_vars.len() >= 4, "Should have 4 y versions (init + 3 arms)");
}

#[test]
fn test_rust_loop_with_mutation() {
    let source = r#"
fn loop_test(n: i32) -> i32 {
    let mut sum = 0;
    let mut i = 0;
    loop {
        if i >= n {
            break;
        }
        sum = sum + i;
        i = i + 1;
    }
    sum
}
"#;

    let result = process_file(source, "test-repo", "test.rs", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let sum_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "sum").collect();
    let i_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "i").collect();

    println!("🦀 Rust loop: {} sum versions, {} i versions", sum_vars.len(), i_vars.len());

    assert!(sum_vars.len() >= 2, "Should have 2+ sum versions in loop");
    assert!(i_vars.len() >= 2, "Should have 2+ i versions in loop");
}

#[test]
fn test_rust_nested_match() {
    let source = r#"
fn nested_match(x: i32, y: i32) -> i32 {
    let mut result = 0;
    match x {
        1 => match y {
            1 => result = 11,
            2 => result = 12,
            _ => result = 10,
        },
        2 => result = 20,
        _ => result = 0,
    };
    result
}
"#;

    let result = process_file(source, "test-repo", "test.rs", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🦀 Rust nested match: {} result versions", result_vars.len());

    assert!(result_vars.len() >= 3, "Should have 3+ result versions for nested match");
}

// ========================================
// Go Tests
// ========================================

#[test]
fn test_go_if_statement() {
    let source = r#"
func conditional(x int) int {
    var y int
    if x > 10 {
        y = x + 5
    } else {
        y = x - 5
    }
    return y
}
"#;

    let result = process_file(source, "test-repo", "test.go", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph for Go");

    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🐹 Go if: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    assert!(y_vars.len() >= 2, "Should have 2+ y versions for Go if/else");
    assert!(ssa.phi_nodes.len() > 0, "Should have φ-nodes for Go");
}

#[test]
fn test_go_switch_statement() {
    let source = r#"
func switchCase(x int) int {
    var y int
    switch x {
    case 1:
        y = 10
    case 2:
        y = 20
    default:
        y = 0
    }
    return y
}
"#;

    let result = process_file(source, "test-repo", "test.go", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🐹 Go switch: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    assert!(y_vars.len() >= 3, "Should have 3+ y versions for Go switch");
}

#[test]
fn test_go_select_statement() {
    let source = r#"
func selectCase(ch1 chan int, ch2 chan int) int {
    var y int
    select {
    case val := <-ch1:
        y = val
    case val := <-ch2:
        y = val * 2
    default:
        y = 0
    }
    return y
}
"#;

    let result = process_file(source, "test-repo", "test.go", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🐹 Go select: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // Select is unique to Go (concurrent channel selection)
    assert!(y_vars.len() >= 3, "Should have 3+ y versions for Go select");
}

#[test]
fn test_go_for_loop() {
    let source = r#"
func loopTest(n int) int {
    sum := 0
    for i := 0; i < n; i++ {
        sum = sum + i
    }
    return sum
}
"#;

    let result = process_file(source, "test-repo", "test.go", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let sum_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "sum").collect();
    let i_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "i").collect();

    println!("🐹 Go for loop: {} sum versions, {} i versions", sum_vars.len(), i_vars.len());

    assert!(sum_vars.len() >= 2, "Should have 2+ sum versions in for loop");
}

#[test]
fn test_go_nested_switch() {
    let source = r#"
func nestedSwitch(x int, y int) int {
    var result int
    switch x {
    case 1:
        switch y {
        case 1:
            result = 11
        case 2:
            result = 12
        default:
            result = 10
        }
    case 2:
        result = 20
    default:
        result = 0
    }
    return result
}
"#;

    let result = process_file(source, "test-repo", "test.go", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🐹 Go nested switch: {} result versions", result_vars.len());

    assert!(result_vars.len() >= 3, "Should have 3+ result versions for nested switch");
}

// ========================================
// Python Advanced Tests
// ========================================

#[test]
fn test_python_match_statement() {
    // Python 3.10+ pattern matching
    let source = r#"
def match_stmt(x):
    match x:
        case 1:
            y = 10
        case 2:
            y = 20
        case _:
            y = 0
    return y
"#;

    let result = process_file(source, "test-repo", "test.py", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🐍 Python match: {} y versions", y_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    // Pattern matching creates multiple branches
    assert!(y_vars.len() >= 3, "Should have 3 y versions for Python match");
}

#[test]
fn test_python_walrus_operator() {
    let source = r#"
def walrus(items):
    if (n := len(items)) > 10:
        y = n + 5
    else:
        y = 0
    return y
"#;

    let result = process_file(source, "test-repo", "test.py", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();
    let n_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "n").collect();

    println!("🐍 Python walrus: {} y versions, {} n versions", y_vars.len(), n_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    assert!(y_vars.len() >= 2, "Should have 2 y versions");
    assert!(n_vars.len() >= 1, "Should have n version from walrus operator");
}

#[test]
fn test_python_nested_if() {
    let source = r#"
def nested(x, y):
    result = 0
    if x > 0:
        if y > 0:
            result = x + y
        else:
            result = x - y
    else:
        result = 0
    return result
"#;

    let result = process_file(source, "test-repo", "test.py", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🐍 Python nested if: {} result versions", result_vars.len());
    println!("   φ-nodes: {}", ssa.phi_nodes.len());

    assert!(result_vars.len() >= 3, "Should have 3+ result versions for nested if");
    assert!(ssa.phi_nodes.len() >= 1, "Should have φ-nodes for nested if");
}

#[test]
fn test_python_for_loop() {
    let source = r#"
def loop_test(items):
    total = 0
    for item in items:
        total = total + item
    return total
"#;

    let result = process_file(source, "test-repo", "test.py", "test");

    assert!(result.ssa_graphs.len() >= 1, "Should have SSA graph");
    let ssa = &result.ssa_graphs[0];
    let total_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "total").collect();

    println!("🐍 Python for loop: {} total versions", total_vars.len());

    assert!(total_vars.len() >= 2, "Should have 2+ total versions in loop");
}

// ========================================
// Cross-Language Comparison Tests
// ========================================

#[test]
fn test_cross_language_if_else_consistency() {
    // Same semantic code in different languages should produce similar SSA structure

    let langs = vec![
        ("Python", "test.py", r#"
def test(x):
    if x > 10:
        y = 1
    else:
        y = 2
    return y
"#),
        ("TypeScript", "test.ts", r#"
function test(x: number): number {
    let y: number;
    if (x > 10) {
        y = 1;
    } else {
        y = 2;
    }
    return y;
}
"#),
        ("Java", "test.java", r#"
public class Test {
    public int test(int x) {
        int y;
        if (x > 10) {
            y = 1;
        } else {
            y = 2;
        }
        return y;
    }
}
"#),
        ("Go", "test.go", r#"
func test(x int) int {
    var y int
    if x > 10 {
        y = 1
    } else {
        y = 2
    }
    return y
}
"#),
    ];

    println!("\n=== Cross-Language If/Else Consistency ===");

    for (lang, filename, code) in langs {
        let result = if lang == "Python" {
            process_python_file(code, "test-repo", filename, "test")
        } else {
            process_file(code, "test-repo", filename, "test")
        };

        if result.ssa_graphs.len() > 0 {
            let ssa = &result.ssa_graphs[0];
            let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

            println!("{:12} y versions: {}, φ-nodes: {}",
                     lang, y_vars.len(), ssa.phi_nodes.len());

            // All should have 2 versions and at least 1 φ-node
            assert!(y_vars.len() >= 2, "{} should have 2+ y versions", lang);
        } else {
            println!("{:12} No SSA graphs generated", lang);
        }
    }
}

// ========================================
// Edge Case Tests
// ========================================

#[test]
fn test_python_complex_nested() {
    let source = r#"
def complex_nested(x, y, z):
    result = 0
    if x > 0:
        if y > 0:
            if z > 0:
                result = x + y + z
            else:
                result = x + y
        else:
            result = x
    else:
        result = 0
    return result
"#;

    let result = process_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🐍 Python 3-level nested if: {} result versions", result_vars.len());
    assert!(result_vars.len() >= 4, "Should have 4+ result versions for 3-level nesting");
}

#[test]
fn test_typescript_multiple_variables() {
    let source = r#"
function multiVar(x: number): void {
    let a: number, b: number, c: number;
    if (x > 10) {
        a = 1;
        b = 2;
        c = 3;
    } else {
        a = 4;
        b = 5;
        c = 6;
    }
    console.log(a, b, c);
}
"#;

    let result = process_file(source, "test-repo", "test.ts", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let a_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "a").collect();
    let b_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "b").collect();
    let c_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "c").collect();

    println!("🔷 TypeScript multi-var: {} a, {} b, {} c versions",
             a_vars.len(), b_vars.len(), c_vars.len());
    assert!(a_vars.len() >= 2, "Should have 2+ a versions");
    assert!(b_vars.len() >= 2, "Should have 2+ b versions");
    assert!(c_vars.len() >= 2, "Should have 2+ c versions");
}

#[test]
fn test_java_try_catch() {
    let source = r#"
public class Test {
    public int tryCatch(int x) {
        int result = 0;
        try {
            result = x / 10;
        } catch (Exception e) {
            result = -1;
        }
        return result;
    }
}
"#;

    let result = process_file(source, "test-repo", "test.java", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("☕ Java try/catch: {} result versions", result_vars.len());
    assert!(result_vars.len() >= 2, "Should have 2+ result versions in try/catch");
}

#[test]
fn test_kotlin_elvis_operator() {
    let source = r#"
fun elvis(x: Int?): Int {
    val y = x ?: 0
    return y
}
"#;

    let result = process_file(source, "test-repo", "test.kt", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let y_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "y").collect();

    println!("🟣 Kotlin elvis operator: {} y versions", y_vars.len());
    assert!(y_vars.len() >= 1, "Should have y version");
}

#[test]
fn test_rust_if_let() {
    let source = r#"
fn if_let(opt: Option<i32>) -> i32 {
    let mut result = 0;
    if let Some(x) = opt {
        result = x;
    } else {
        result = -1;
    }
    result
}
"#;

    let result = process_file(source, "test-repo", "test.rs", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🦀 Rust if let: {} result versions", result_vars.len());
    assert!(result_vars.len() >= 2, "Should have 2+ result versions in if let");
}

#[test]
fn test_go_defer_statement() {
    let source = r#"
func deferTest() int {
    var result int = 0
    defer func() {
        result = result + 1
    }()
    result = 10
    return result
}
"#;

    let result = process_file(source, "test-repo", "test.go", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🐹 Go defer: {} result versions", result_vars.len());
    assert!(result_vars.len() >= 2, "Should have 2+ result versions with defer");
}

#[test]
fn test_python_list_comprehension() {
    let source = r#"
def list_comp(items):
    result = [x * 2 for x in items if x > 0]
    return result
"#;

    let result = process_file(source, "test-repo", "test.py", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🐍 Python list comprehension: {} result versions", result_vars.len());
    assert!(result_vars.len() >= 1, "Should have result version");
}

#[test]
fn test_typescript_async_await() {
    let source = r#"
async function asyncTest(x: number): Promise<number> {
    let result: number = 0;
    if (x > 0) {
        result = await Promise.resolve(x);
    } else {
        result = -1;
    }
    return result;
}
"#;

    let result = process_file(source, "test-repo", "test.ts", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🔷 TypeScript async/await: {} result versions", result_vars.len());
    assert!(result_vars.len() >= 2, "Should have 2+ result versions in async");
}

#[test]
fn test_java_enhanced_for() {
    let source = r#"
public class Test {
    public int enhancedFor(int[] items) {
        int sum = 0;
        for (int item : items) {
            sum = sum + item;
        }
        return sum;
    }
}
"#;

    let result = process_file(source, "test-repo", "test.java", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let sum_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "sum").collect();

    println!("☕ Java enhanced for: {} sum versions", sum_vars.len());
    assert!(sum_vars.len() >= 2, "Should have 2+ sum versions in enhanced for");
}

#[test]
fn test_kotlin_safe_call_chain() {
    let source = r#"
fun safeCall(obj: MyObj?): Int {
    val result = obj?.field?.value ?: 0
    return result
}
"#;

    let result = process_file(source, "test-repo", "test.kt", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🟣 Kotlin safe call chain: {} result versions", result_vars.len());
    assert!(result_vars.len() >= 1, "Should have result version");
}

#[test]
fn test_rust_pattern_matching_enum() {
    let source = r#"
fn match_enum(val: Result<i32, String>) -> i32 {
    let mut result = 0;
    match val {
        Ok(x) => result = x,
        Err(_) => result = -1,
    }
    result
}
"#;

    let result = process_file(source, "test-repo", "test.rs", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🦀 Rust pattern matching enum: {} result versions", result_vars.len());
    assert!(result_vars.len() >= 2, "Should have 2+ result versions in enum match");
}

#[test]
fn test_go_type_switch() {
    let source = r#"
func typeSwitch(val interface{}) int {
    var result int
    switch v := val.(type) {
    case int:
        result = v
    case string:
        result = len(v)
    default:
        result = 0
    }
    return result
}
"#;

    let result = process_file(source, "test-repo", "test.go", "test");
    assert!(result.ssa_graphs.len() >= 1);
    let ssa = &result.ssa_graphs[0];
    let result_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "result").collect();

    println!("🐹 Go type switch: {} result versions", result_vars.len());
    assert!(result_vars.len() >= 3, "Should have 3+ result versions in type switch");
}

#[test]
fn test_cross_language_loop_consistency() {
    // Same semantic loop in different languages should produce similar SSA structure

    let langs = vec![
        ("Python", "test.py", r#"
def test(items):
    total = 0
    for item in items:
        total = total + item
    return total
"#),
        ("TypeScript", "test.ts", r#"
function test(items: number[]): number {
    let total: number = 0;
    for (let item of items) {
        total = total + item;
    }
    return total;
}
"#),
        ("Java", "test.java", r#"
public class Test {
    public int test(int[] items) {
        int total = 0;
        for (int item : items) {
            total = total + item;
        }
        return total;
    }
}
"#),
        ("Kotlin", "test.kt", r#"
fun test(items: List<Int>): Int {
    var total: Int = 0
    for (item in items) {
        total = total + item
    }
    return total
}
"#),
        ("Rust", "test.rs", r#"
fn test(items: Vec<i32>) -> i32 {
    let mut total = 0;
    for item in items {
        total = total + item;
    }
    total
}
"#),
        ("Go", "test.go", r#"
func test(items []int) int {
    total := 0
    for _, item := range items {
        total = total + item
    }
    return total
}
"#),
    ];

    println!("\n=== Cross-Language Loop Consistency ===");

    for (lang, filename, code) in langs {
        let result = process_file(code, "test-repo", filename, "test");

        if result.ssa_graphs.len() > 0 {
            let ssa = &result.ssa_graphs[0];
            let total_vars: Vec<_> = ssa.variables.iter().filter(|v| v.base_name == "total").collect();

            println!("{:12} total versions: {}, φ-nodes: {}",
                     lang, total_vars.len(), ssa.phi_nodes.len());

            // All should have 2+ versions (init + loop update)
            assert!(total_vars.len() >= 2, "{} should have 2+ total versions", lang);
        } else {
            println!("{:12} No SSA graphs generated", lang);
        }
    }
}
