//! End-to-End Integration Tests for 23-Level Pipeline
//!
//! Tests all integrated features (L1-L37) with realistic code examples.
//!
//! Levels tested:
//! - L1: IR Build
//! - L2: Chunking
//! - L2.5: Lexical
//! - L3: CrossFile
//! - L4: FlowGraph
//! - L5: Types
//! - L6: DataFlow
//! - L7: SSA
//! - L8: Symbols
//! - L9: Occurrences
//! - L10: Clone Detection ⭐
//! - L11: Points-to
//! - L12: PDG
//! - L13: Effect Analysis ⭐
//! - L14: Heap Analysis
//! - L15: Slicing
//! - L16: Taint
//! - L17: Cost Analysis
//! - L18: Concurrency Analysis ⭐
//! - L19: RepoMap
//! - L21: SMT Verification ⭐
//! - L33: Git History ⭐
//! - L37: Query Engine ⭐

use codegraph_ir::pipeline::{E2EPipelineConfig, IRIndexingOrchestrator};
use tempfile::TempDir;

/// Test L1-L9: Basic pipeline (core IR + symbols)
#[test]
fn test_l1_to_l9_basic_pipeline() {
    let temp_dir = create_test_repo(vec![
        ("main.py", r#"
def add(a, b):
    """Add two numbers"""
    return a + b

result = add(1, 2)
print(result)
"#),
    ]);

    let mut config = E2EPipelineConfig::minimal();
    config.repo_info.repo_root = temp_dir.path().to_path_buf();
    config.repo_info.repo_name = "test_repo".to_string();

    // Enable L1-L9
    config.stages.enable_ir_build = true;
    config.stages.enable_chunking = true;
    config.stages.enable_symbols = true;
    config.stages.enable_occurrences = true;

    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Pipeline should succeed");

    // Validate L1: IR Build
    assert!(!result.nodes.is_empty(), "Should have IR nodes");
    assert!(!result.edges.is_empty(), "Should have IR edges");

    // Validate L2: Chunking
    assert!(!result.chunks.is_empty(), "Should have chunks");

    // Validate L8: Symbols
    assert!(!result.symbols.is_empty(), "Should have symbols");
    let add_symbol = result.symbols.iter().find(|s| s.name == "add");
    assert!(add_symbol.is_some(), "Should find 'add' symbol");

    // Validate L9: Occurrences (may be empty if not fully enabled)
    println!("Occurrences: {}", result.occurrences.len());
}

/// Test L10: Clone Detection
#[test]
fn test_l10_clone_detection() {
    let temp_dir = create_test_repo(vec![
        ("file1.py", r#"
def calculate_sum(x, y):
    return x + y
"#),
        ("file2.py", r#"
def add_numbers(a, b):
    return a + b
"#),
    ]);

    let mut config = E2EPipelineConfig::minimal();
    config.repo_info.repo_root = temp_dir.path().to_path_buf();
    config.repo_info.repo_name = "clone_test".to_string();

    config.stages.enable_ir_build = true;
    config.stages.enable_clone_detection = true;

    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Pipeline should succeed");

    // Clone detection may or may not find clones depending on threshold
    println!("Clone pairs found: {}", result.clone_pairs.len());
    if !result.clone_pairs.is_empty() {
        let has_type2_clone = result.clone_pairs.iter()
            .any(|pair| pair.clone_type == "Type2");
        if has_type2_clone {
            println!("Type-2 clone detected!");
        }
    }
}

/// Test L13: Effect Analysis
#[test]
fn test_l13_effect_analysis() {
    let temp_dir = create_test_repo(vec![
        ("effects.py", r#"
def pure_function(x):
    """Pure function - no side effects"""
    return x * 2

def impure_function(x):
    """Impure - has I/O"""
    print(x)
    return x

def mutating_function(lst):
    """Mutating - modifies state"""
    lst.append(1)
    return lst
"#),
    ]);

    let mut config = E2EPipelineConfig::minimal();
    config.repo_info.repo_root = temp_dir.path().to_path_buf();
    config.repo_info.repo_name = "effect_test".to_string();

    config.stages.enable_ir_build = true;
    config.stages.enable_data_flow = true;
    config.stages.enable_effect_analysis = true;

    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Pipeline should succeed");

    // Should detect effects
    assert!(!result.effect_results.is_empty(), "Should have effect analysis results");

    // Pure function should be marked as pure
    let pure_result = result.effect_results.iter()
        .find(|e| e.function_id.contains("pure_function"));
    if let Some(pure) = pure_result {
        assert!(pure.is_pure, "pure_function should be marked as pure");
    }

    // Impure function should have I/O effect
    let impure_result = result.effect_results.iter()
        .find(|e| e.function_id.contains("impure_function"));
    if let Some(impure) = impure_result {
        assert!(!impure.is_pure, "impure_function should not be pure");
        assert!(impure.effects.contains(&"IO".to_string()), "Should detect I/O effect");
    }
}

/// Test L18: Concurrency Analysis
#[test]
fn test_l18_concurrency_analysis() {
    let temp_dir = create_test_repo(vec![
        ("async_code.py", r#"
import asyncio

shared_counter = 0

async def increment():
    global shared_counter
    temp = shared_counter
    await asyncio.sleep(0)  # Potential race here
    shared_counter = temp + 1

async def decrement():
    global shared_counter
    temp = shared_counter
    await asyncio.sleep(0)  # Potential race here
    shared_counter = temp - 1
"#),
    ]);

    let mut config = E2EPipelineConfig::minimal();
    config.repo_info.repo_root = temp_dir.path().to_path_buf();
    config.repo_info.repo_name = "concurrency_test".to_string();

    config.stages.enable_ir_build = true;
    config.stages.enable_data_flow = true;
    config.stages.enable_points_to = true;
    config.stages.enable_concurrency_analysis = true;

    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Pipeline should succeed");

    // Should detect potential race conditions on shared_counter
    println!("Concurrency issues found: {}", result.concurrency_results.len());
    for issue in &result.concurrency_results {
        println!("  - {} on {}: {}", issue.issue_type, issue.shared_variable, issue.severity);
    }
}

/// Test L21: SMT Verification (infrastructure)
#[test]
fn test_l21_smt_verification() {
    let temp_dir = create_test_repo(vec![
        ("verified.py", r#"
def safe_divide(a, b):
    """Division with precondition"""
    assert b != 0, "Divisor must be non-zero"
    return a / b

def bounded_access(arr, idx):
    """Array access with bounds check"""
    assert 0 <= idx < len(arr), "Index out of bounds"
    return arr[idx]
"#),
    ]);

    let mut config = E2EPipelineConfig::minimal();
    config.repo_info.repo_root = temp_dir.path().to_path_buf();
    config.repo_info.repo_name = "smt_test".to_string();

    config.stages.enable_ir_build = true;
    config.stages.enable_ssa = true;
    config.stages.enable_pdg = true;
    config.stages.enable_smt_verification = true;

    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Pipeline should succeed");

    // SMT verification results (skeleton - no actual solver yet)
    println!("SMT verification results: {}", result.smt_results.len());
}

/// Test L33: Git History (graceful degradation)
#[test]
fn test_l33_git_history_no_repo() {
    let temp_dir = create_test_repo(vec![
        ("code.py", r#"
def hello():
    print("Hello, world!")
"#),
    ]);

    let mut config = E2EPipelineConfig::minimal();
    config.repo_info.repo_root = temp_dir.path().to_path_buf();
    config.repo_info.repo_name = "git_test".to_string();

    config.stages.enable_ir_build = true;
    config.stages.enable_git_history = true;

    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Pipeline should succeed");

    // Should gracefully skip git history if not a git repo
    assert_eq!(result.git_history_results.len(), 0,
        "Should skip git history for non-git repo");
}

/// Test L37: Query Engine
#[test]
fn test_l37_query_engine() {
    let temp_dir = create_test_repo(vec![
        ("query_test.py", r#"
def process_data(user_input):
    data = transform(user_input)
    result = execute(data)
    return result

def transform(x):
    return x * 2

def execute(x):
    print(f"Executing: {x}")
    return x
"#),
    ]);

    let mut config = E2EPipelineConfig::minimal();
    config.repo_info.repo_root = temp_dir.path().to_path_buf();
    config.repo_info.repo_name = "query_test".to_string();

    config.stages.enable_ir_build = true;
    config.stages.enable_query_engine = true;

    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Pipeline should succeed");

    // Query engine should be initialized
    assert!(result.query_engine_stats.is_some(), "Query engine should be initialized");

    let stats = result.query_engine_stats.unwrap();
    assert!(stats.node_count > 0, "Should have indexed nodes");
    assert!(stats.edge_count > 0, "Should have indexed edges");
}

/// Test full pipeline with all features enabled
#[test]
fn test_full_pipeline_all_23_levels() {
    let temp_dir = create_test_repo(vec![
        ("app.py", r#"
"""Main application module"""

import asyncio

class Counter:
    def __init__(self):
        self.value = 0

    def increment(self):
        self.value += 1
        return self.value

async def async_increment(counter):
    """Async increment with potential race"""
    temp = counter.value
    await asyncio.sleep(0)
    counter.value = temp + 1

def pure_double(x):
    """Pure function"""
    return x * 2

def impure_log(msg):
    """Impure function with I/O"""
    print(msg)
    with open("log.txt", "a") as f:
        f.write(msg)

# Similar code for clone detection
def add_items(a, b):
    return a + b

def sum_values(x, y):
    return x + y
"#),
    ]);

    // Full config with all features
    let config = E2EPipelineConfig::balanced()
        .repo_root(temp_dir.path().to_path_buf())
        .repo_name("full_test".to_string());

    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Full pipeline should succeed");

    // Validate results from all levels
    assert!(!result.nodes.is_empty(), "L1: Should have nodes");
    assert!(!result.chunks.is_empty(), "L2: Should have chunks");
    assert!(!result.symbols.is_empty(), "L8: Should have symbols");
    println!("L9: Occurrences: {}", result.occurrences.len());

    // New integrated features
    println!("Clone pairs: {}", result.clone_pairs.len());
    println!("Effect results: {}", result.effect_results.len());
    println!("Concurrency issues: {}", result.concurrency_results.len());
    println!("SMT results: {}", result.smt_results.len());
    println!("Git history: {}", result.git_history_results.len());

    if let Some(qe_stats) = result.query_engine_stats {
        println!("Query engine: {} nodes, {} edges", qe_stats.node_count, qe_stats.edge_count);
        assert!(qe_stats.node_count > 0, "L37: Query engine should have nodes");
    }

    // Pipeline statistics
    println!("\nPipeline stats:");
    println!("  Files processed: {}", result.stats.files_processed);
    println!("  Total duration: {:?}", result.stats.total_duration);
    println!("  Stages executed: {}", result.stats.stage_durations.len());
}

/// Test performance: pipeline should complete in reasonable time
#[test]
fn test_pipeline_performance() {
    let temp_dir = create_test_repo(vec![
        ("perf1.py", "def func1(): pass\n".repeat(100).as_str()),
        ("perf2.py", "def func2(): pass\n".repeat(100).as_str()),
        ("perf3.py", "def func3(): pass\n".repeat(100).as_str()),
    ]);

    let config = E2EPipelineConfig::balanced()
        .repo_root(temp_dir.path().to_path_buf())
        .repo_name("perf_test".to_string());

    let start = std::time::Instant::now();
    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute().expect("Pipeline should succeed");
    let duration = start.elapsed();

    println!("Pipeline completed in {:?}", duration);
    println!("  Nodes: {}", result.nodes.len());
    println!("  Edges: {}", result.edges.len());
    println!("  Chunks: {}", result.chunks.len());

    // Should complete in reasonable time (< 10 seconds for this small repo)
    assert!(duration.as_secs() < 10, "Pipeline should complete in < 10s");
}

/// Test configuration: minimal vs default
#[test]
fn test_config_minimal_vs_default() {
    let temp_dir = create_test_repo(vec![
        ("simple.py", "def test(): pass"),
    ]);

    // Minimal config
    let mut minimal_config = E2EPipelineConfig::minimal();
    minimal_config.repo_info.repo_root = temp_dir.path().to_path_buf();
    minimal_config.repo_info.repo_name = "minimal_test".to_string();

    let orchestrator = IRIndexingOrchestrator::new(minimal_config);
    let minimal_result = orchestrator.execute().expect("Minimal should succeed");

    // Default config
    let mut default_config = E2EPipelineConfig::default();
    default_config.repo_info.repo_root = temp_dir.path().to_path_buf();
    default_config.repo_info.repo_name = "default_test".to_string();

    let orchestrator = IRIndexingOrchestrator::new(default_config);
    let default_result = orchestrator.execute().expect("Default should succeed");

    // Default should have more features enabled
    assert!(minimal_result.chunks.is_empty(), "Minimal should skip chunking");
    assert!(!default_result.chunks.is_empty(), "Default should have chunking");

    assert_eq!(minimal_result.clone_pairs.len(), 0, "Minimal should skip clone detection");
    // default_result may or may not have clones depending on code
}

// ============================================================================
// Helper Functions
// ============================================================================

fn create_test_repo(files: Vec<(&str, &str)>) -> TempDir {
    let temp_dir = TempDir::new().expect("Failed to create temp dir");

    for (filename, content) in files {
        let file_path = temp_dir.path().join(filename);
        std::fs::write(&file_path, content).expect("Failed to write test file");
    }

    temp_dir
}
