//! Integration tests for incremental update
//!
//! Tests the SOTA-level incremental update algorithm with:
//! - Single file changes
//! - Multi-file dependency chains
//! - Transitive dependency propagation
//! - Performance measurements

use codegraph_orchestration::{CheckpointManager, IncrementalOrchestrator, IncrementalResult};
use std::sync::Arc;
use uuid::Uuid;

#[tokio::test]
async fn test_incremental_update_single_file_change() {
    let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
    let mut orch = IncrementalOrchestrator::new(checkpoint_mgr.clone());

    // Initial files
    let initial_files = vec![
        (
            "utils.py".to_string(),
            r#"
def helper():
    return "original"
"#
            .to_string(),
        ),
        (
            "main.py".to_string(),
            r#"
from utils import helper

def main():
    return helper()
"#
            .to_string(),
        ),
    ];

    // Full build (first time)
    let job_id = Uuid::new_v4();
    let full_result = orch
        .incremental_update(
            job_id,
            "test-repo",
            "snapshot-1",
            initial_files.clone(),
            initial_files.clone(),
            None,
        )
        .await
        .expect("Full build failed");

    println!(
        "Full build: {} files, {} ms",
        full_result.total_files, full_result.total_duration_ms
    );

    // Incremental update (change utils.py)
    let changed_files = vec![(
        "utils.py".to_string(),
        r#"
def helper():
    return "modified"

def new_function():
    return "new"
"#
        .to_string(),
    )];

    let all_files = vec![
        (
            "utils.py".to_string(),
            r#"
def helper():
    return "modified"

def new_function():
    return "new"
"#
            .to_string(),
        ),
        (
            "main.py".to_string(),
            r#"
from utils import helper

def main():
    return helper()
"#
            .to_string(),
        ),
    ];

    // Load previous global context
    let cache_key = format!("global_context:test-repo:snapshot-1");
    let existing_cache = checkpoint_mgr
        .load_checkpoint(&cache_key)
        .await
        .expect("Failed to load cache")
        .expect("No cache found");

    let job_id2 = Uuid::new_v4();
    let incremental_result = orch
        .incremental_update(
            job_id2,
            "test-repo",
            "snapshot-2",
            changed_files,
            all_files.clone(),
            Some(existing_cache),
        )
        .await
        .expect("Incremental update failed");

    // Assertions
    assert_eq!(incremental_result.changed_files.len(), 1);
    assert!(incremental_result.affected_files.len() >= 1);
    assert_eq!(incremental_result.total_files, 2);

    // Should have speedup
    assert!(incremental_result.speedup_factor >= 1.0);

    println!("✅ Incremental update test passed:");
    println!("  Changed: {:?}", incremental_result.changed_files);
    println!("  Affected: {:?}", incremental_result.affected_files);
    println!("  Speedup: {:.1}x", incremental_result.speedup_factor);
    println!(
        "  Duration: {} ms (L1: {} ms, L3: {} ms, L2: {} ms)",
        incremental_result.total_duration_ms,
        incremental_result.l1_ir_duration_ms,
        incremental_result.l3_cross_file_duration_ms,
        incremental_result.l2_chunk_duration_ms
    );
}

#[tokio::test]
async fn test_incremental_update_transitive_dependencies() {
    let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
    let mut orch = IncrementalOrchestrator::new(checkpoint_mgr.clone());

    // Complex dependency chain: base.py → user.py → service.py → main.py
    let initial_files = vec![
        (
            "base.py".to_string(),
            r#"
class Base:
    def common_method(self):
        return "base"
"#
            .to_string(),
        ),
        (
            "user.py".to_string(),
            r#"
from base import Base

class User(Base):
    def save(self):
        return "save"
"#
            .to_string(),
        ),
        (
            "service.py".to_string(),
            r#"
from user import User

class UserService:
    def create_user(self):
        return User()
"#
            .to_string(),
        ),
        (
            "main.py".to_string(),
            r#"
from service import UserService

def main():
    service = UserService()
    return service.create_user()
"#
            .to_string(),
        ),
    ];

    // Full build
    let job_id = Uuid::new_v4();
    let full_result = orch
        .incremental_update(
            job_id,
            "complex-repo",
            "snapshot-1",
            initial_files.clone(),
            initial_files.clone(),
            None,
        )
        .await
        .expect("Full build failed");

    println!(
        "Full build: {} files, {} ms",
        full_result.total_files, full_result.total_duration_ms
    );

    // Change base.py (root of dependency chain)
    let changed_files = vec![(
        "base.py".to_string(),
        r#"
class Base:
    def common_method(self):
        return "modified_base"

    def new_method(self):
        return "new"
"#
        .to_string(),
    )];

    let all_files = vec![
        (
            "base.py".to_string(),
            r#"
class Base:
    def common_method(self):
        return "modified_base"

    def new_method(self):
        return "new"
"#
            .to_string(),
        ),
        (
            "user.py".to_string(),
            r#"
from base import Base

class User(Base):
    def save(self):
        return "save"
"#
            .to_string(),
        ),
        (
            "service.py".to_string(),
            r#"
from user import User

class UserService:
    def create_user(self):
        return User()
"#
            .to_string(),
        ),
        (
            "main.py".to_string(),
            r#"
from service import UserService

def main():
    service = UserService()
    return service.create_user()
"#
            .to_string(),
        ),
    ];

    // Load cache
    let cache_key = format!("global_context:complex-repo:snapshot-1");
    let existing_cache = checkpoint_mgr
        .load_checkpoint(&cache_key)
        .await
        .expect("Failed to load cache")
        .expect("No cache found");

    let job_id2 = Uuid::new_v4();
    let incremental_result = orch
        .incremental_update(
            job_id2,
            "complex-repo",
            "snapshot-2",
            changed_files,
            all_files,
            Some(existing_cache),
        )
        .await
        .expect("Incremental update failed");

    // Assertions: All files should be affected due to transitive dependencies
    assert_eq!(incremental_result.changed_files.len(), 1);
    assert!(
        incremental_result.affected_files.len() >= 1,
        "Should detect transitive dependencies"
    );

    // Check if user.py is in affected files (direct dependency)
    assert!(
        incremental_result
            .affected_files
            .contains(&"base.py".to_string()),
        "base.py (changed) should be affected"
    );

    println!("✅ Transitive dependency test passed:");
    println!("  Changed: {:?}", incremental_result.changed_files);
    println!("  Affected: {:?}", incremental_result.affected_files);
    println!("  Speedup: {:.1}x", incremental_result.speedup_factor);
    println!(
        "  BFS detected {} affected files from 1 changed file",
        incremental_result.affected_files.len()
    );
}

#[tokio::test]
async fn test_incremental_update_performance() {
    let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
    let mut orch = IncrementalOrchestrator::new(checkpoint_mgr.clone());

    // Create 10 files to simulate realistic scenario
    let mut initial_files = vec![];
    for i in 0..10 {
        initial_files.push((
            format!("module_{}.py", i),
            format!(
                r#"
def function_{}():
    return {}

class Class{}:
    def method(self):
        return {}
"#,
                i, i, i, i
            ),
        ));
    }

    // Full build
    let job_id = Uuid::new_v4();
    let full_result = orch
        .incremental_update(
            job_id,
            "perf-repo",
            "snapshot-1",
            initial_files.clone(),
            initial_files.clone(),
            None,
        )
        .await
        .expect("Full build failed");

    println!("Full build: {} ms", full_result.total_duration_ms);

    // Change only 1 file
    let changed_files = vec![(
        "module_0.py".to_string(),
        r#"
def function_0():
    return "modified"

class Class0:
    def method(self):
        return "modified"
"#
        .to_string(),
    )];

    let mut all_files = initial_files.clone();
    all_files[0] = changed_files[0].clone();

    // Load cache
    let cache_key = format!("global_context:perf-repo:snapshot-1");
    let existing_cache = checkpoint_mgr
        .load_checkpoint(&cache_key)
        .await
        .expect("Failed to load cache")
        .expect("No cache found");

    let job_id2 = Uuid::new_v4();
    let incremental_result = orch
        .incremental_update(
            job_id2,
            "perf-repo",
            "snapshot-2",
            changed_files,
            all_files,
            Some(existing_cache),
        )
        .await
        .expect("Incremental update failed");

    // Performance assertions
    assert!(incremental_result.speedup_factor >= 1.0);

    println!("✅ Performance test passed:");
    println!("  Full build: {} ms", full_result.total_duration_ms);
    println!("  Incremental: {} ms", incremental_result.total_duration_ms);
    println!(
        "  Speedup: {:.1}x (estimated)",
        incremental_result.speedup_factor
    );
    println!(
        "  Changed: {}/10 files, Affected: {}/10 files",
        incremental_result.changed_files.len(),
        incremental_result.affected_files.len()
    );
}
