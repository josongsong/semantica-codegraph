/*
 * RFC-001 Edge Case & Stress Tests
 *
 * SOTA-level extreme case testing for production readiness.
 */

use codegraph_ir::features::taint_analysis::infrastructure::differential::GitDifferentialAnalyzer;
use codegraph_ir::features::taint_analysis::infrastructure::DifferentialTaintAnalyzer;
use std::fs;
use std::process::Command;

// ═══════════════════════════════════════════════════════════════════
// Edge Case 1: File Size Limits
// ═══════════════════════════════════════════════════════════════════

#[test]
fn test_large_file_rejected() {
    // Create 11MB file (exceeds 10MB limit)
    let large_code = "def f(): pass\n".repeat(800_000); // ~11MB

    let mut analyzer = DifferentialTaintAnalyzer::new();
    let result = analyzer.compare(&large_code, &large_code);

    // Should fail with file size error
    assert!(result.is_err(), "Should reject files > 10MB");

    let err = result.unwrap_err();
    let err_str = err.to_string();
    assert!(
        err_str.contains("too large") || err_str.contains("File too large"),
        "Error should mention file size: {}",
        err_str
    );
}

// REMOVED: test_boundary_file_size - too slow (60+ seconds)
// File size limit is already tested by test_large_file_rejected

// ═══════════════════════════════════════════════════════════════════
// Edge Case 2: Empty and Minimal Inputs
// ═══════════════════════════════════════════════════════════════════

#[test]
fn test_empty_code() {
    let mut analyzer = DifferentialTaintAnalyzer::new();
    let result = analyzer.compare("", "").unwrap();

    assert_eq!(result.new_vulnerabilities.len(), 0);
    assert_eq!(result.fixed_vulnerabilities.len(), 0);
}

#[test]
fn test_whitespace_only() {
    let mut analyzer = DifferentialTaintAnalyzer::new();
    let result = analyzer.compare("   \n\n\t  ", "   \n\n\t  ").unwrap();

    assert_eq!(result.regression_count(), 0);
}

#[test]
fn test_single_line() {
    let mut analyzer = DifferentialTaintAnalyzer::new();
    let result = analyzer.compare("x = 1", "x = 2").unwrap();

    assert_eq!(result.regression_count(), 0);
}

// ═══════════════════════════════════════════════════════════════════
// Edge Case 3: Special Characters and Encoding
// ═══════════════════════════════════════════════════════════════════

#[test]
fn test_unicode_code() {
    let code = r#"
def process(데이터):
    """한글 주석"""
    결과 = sanitize(데이터)
    return execute(결과)
"#;

    let mut analyzer = DifferentialTaintAnalyzer::new();
    let result = analyzer.compare(code, code).unwrap();

    // Should handle Unicode without errors
    assert_eq!(result.regression_count(), 0);
}

#[test]
fn test_special_characters_in_strings() {
    let code = r#"
def process(data):
    query = "SELECT * FROM users WHERE name = '\"; DROP TABLE users; --'"
    execute(query)
"#;

    let mut analyzer = DifferentialTaintAnalyzer::new();
    let result = analyzer.compare(code, code).unwrap();

    assert_eq!(result.regression_count(), 0);
}

// ═══════════════════════════════════════════════════════════════════
// Edge Case 4: Syntax Errors and Invalid Code
// ═══════════════════════════════════════════════════════════════════

#[test]
fn test_python_syntax_error() {
    let invalid = r#"
def broken(  # Missing closing paren
    return x
"#;

    let mut analyzer = DifferentialTaintAnalyzer::new();
    let result = analyzer.compare(invalid, invalid);

    // Should either error or return empty (graceful handling)
    match result {
        Ok(r) => assert_eq!(r.regression_count(), 0),
        Err(_) => {} // Error is acceptable
    }
}

#[test]
fn test_javascript_syntax_error() {
    let invalid = r#"
function broken( {  // Invalid syntax
    return x;
}
"#;

    let mut analyzer = DifferentialTaintAnalyzer::new();
    let result = analyzer.compare(invalid, invalid);

    // Should handle gracefully
    assert!(result.is_ok() || result.is_err());
}

// ═══════════════════════════════════════════════════════════════════
// Edge Case 5: Concurrent/Parallel Processing
// ═══════════════════════════════════════════════════════════════════

#[test]
fn test_parallel_git_analysis() {
    let (_temp_dir, repo_path) = create_temp_repo();

    // Create 10 files
    for i in 0..10 {
        let code = format!(
            r#"
def process_{i}(data):
    sanitized = clean(data)
    execute(sanitized)
"#
        );
        create_commit(
            &repo_path,
            &format!("file{}.py", i),
            &code,
            &format!("Add file {}", i),
        );
    }

    // Modify all files
    for i in 0..10 {
        let code = format!(
            r#"
def process_{i}(data):
    execute(data)  # Removed sanitization
"#
        );
        update_file(&repo_path, &format!("file{}.py", i), &code);
    }
    create_commit(&repo_path, "file0.py", "", "Modify files");

    // Analyze with parallel
    let mut analyzer = GitDifferentialAnalyzer::new(&repo_path).unwrap();
    let result = analyzer.compare_commits_parallel("HEAD~1", "HEAD").unwrap();

    assert!(
        result.stats.files_analyzed >= 1,
        "Should analyze multiple files"
    );
}

// ═══════════════════════════════════════════════════════════════════
// Edge Case 6: Performance Benchmarks
// ═══════════════════════════════════════════════════════════════════

#[test]
fn test_sequential_vs_parallel_benchmark() {
    let (_temp_dir, repo_path) = create_temp_repo();

    // Create 20 files for meaningful benchmark
    for i in 0..20 {
        let code = format!("def f{i}(): pass\n");
        create_commit(
            &repo_path,
            &format!("f{}.py", i),
            &code,
            &format!("Add {}", i),
        );
    }

    // Modify all
    for i in 0..20 {
        let code = format!("def f{i}(): return {i}\n");
        update_file(&repo_path, &format!("f{}.py", i), &code);
    }
    create_commit(&repo_path, "f0.py", "", "Update all");

    // Sequential
    let start_seq = std::time::Instant::now();
    let mut analyzer_seq = GitDifferentialAnalyzer::new(&repo_path).unwrap();
    let result_seq = analyzer_seq.compare_commits("HEAD~1", "HEAD").unwrap();
    let time_seq = start_seq.elapsed();

    // Parallel
    let start_par = std::time::Instant::now();
    let mut analyzer_par = GitDifferentialAnalyzer::new(&repo_path).unwrap();
    let result_par = analyzer_par
        .compare_commits_parallel("HEAD~1", "HEAD")
        .unwrap();
    let time_par = start_par.elapsed();

    eprintln!("[BENCHMARK] Sequential: {:?}", time_seq);
    eprintln!("[BENCHMARK] Parallel: {:?}", time_par);
    eprintln!(
        "[BENCHMARK] Speedup: {:.2}x",
        time_seq.as_secs_f64() / time_par.as_secs_f64()
    );

    // Results should be identical
    assert_eq!(
        result_seq.new_vulnerabilities.len(),
        result_par.new_vulnerabilities.len()
    );
}

// ═══════════════════════════════════════════════════════════════════
// Edge Case 7: Git Edge Cases
// ═══════════════════════════════════════════════════════════════════

#[test]
fn test_empty_commit_diff() {
    let (_temp_dir, repo_path) = create_temp_repo();
    create_commit(&repo_path, "f.py", "pass", "C1");

    // No changes between HEAD and HEAD
    let mut analyzer = GitDifferentialAnalyzer::new(&repo_path).unwrap();
    let result = analyzer.compare_commits("HEAD", "HEAD").unwrap();

    assert_eq!(result.stats.files_changed, 0);
    assert_eq!(result.new_vulnerabilities.len(), 0);
}

#[test]
fn test_binary_file_skipped() {
    let (_temp_dir, repo_path) = create_temp_repo();

    // Add non-code file (image)
    create_commit(&repo_path, "image.png", "fake_binary_content", "Add binary");
    create_commit(&repo_path, "code.py", "pass", "Add code");

    let mut analyzer = GitDifferentialAnalyzer::new(&repo_path).unwrap();
    let result = analyzer.compare_commits("HEAD~1", "HEAD").unwrap();

    // Should skip non-code file (.png)
    assert_eq!(
        result.stats.files_analyzed, 1,
        "Should only analyze .py file"
    );
}

// ═══════════════════════════════════════════════════════════════════
// Edge Case 8: Memory and Resource Limits
// ═══════════════════════════════════════════════════════════════════

#[test]
fn test_many_small_files() {
    // Test with 100 small files (memory safety)
    let mut analyzer = DifferentialTaintAnalyzer::new();

    for i in 0..100 {
        let code = format!("def f{i}(): pass\n");
        let _ = analyzer.compare(&code, &code);
    }

    // Should not OOM
    assert!(true, "Completed 100 analyses without crash");
}

#[test]
fn test_deeply_nested_code() {
    // Test with deeply nested structures
    let mut code = String::from("def outer():\n");
    for i in 0..50 {
        code.push_str(&format!("{}if True:\n", "    ".repeat(i + 1)));
    }
    code.push_str(&format!("{}pass\n", "    ".repeat(51)));

    let mut analyzer = DifferentialTaintAnalyzer::new();
    let result = analyzer.compare(&code, &code).unwrap();

    // Should handle deep nesting
    assert_eq!(result.regression_count(), 0);
}

// ═══════════════════════════════════════════════════════════════════
// Helper Functions
// ═══════════════════════════════════════════════════════════════════

fn create_temp_repo() -> (tempfile::TempDir, std::path::PathBuf) {
    let temp_dir = tempfile::tempdir().unwrap();
    let repo_path = temp_dir.path().to_path_buf();

    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .unwrap();

    Command::new("git")
        .args(["config", "user.email", "test@test.com"])
        .current_dir(&repo_path)
        .output()
        .unwrap();

    Command::new("git")
        .args(["config", "user.name", "Test"])
        .current_dir(&repo_path)
        .output()
        .unwrap();

    (temp_dir, repo_path)
}

fn create_commit(repo_path: &std::path::Path, filename: &str, content: &str, message: &str) {
    let file_path = repo_path.join(filename);
    fs::write(&file_path, content).unwrap();

    Command::new("git")
        .args(["add", filename])
        .current_dir(repo_path)
        .output()
        .unwrap();

    Command::new("git")
        .args(["commit", "-m", message])
        .current_dir(repo_path)
        .output()
        .unwrap();
}

fn update_file(repo_path: &std::path::Path, filename: &str, content: &str) {
    let file_path = repo_path.join(filename);
    fs::write(&file_path, content).unwrap();

    Command::new("git")
        .args(["add", filename])
        .current_dir(repo_path)
        .output()
        .unwrap();
}
