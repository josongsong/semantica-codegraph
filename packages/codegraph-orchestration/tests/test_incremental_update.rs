/// Integration tests for incremental update functionality
///
/// Tests the complete incremental update flow with BFS affected files detection
use codegraph_orchestration::{
    compute_affected_files, CacheKeyManager, CheckpointManager, ReverseDependencyIndex,
    StageConfig, StageContext, StageInput,
};
use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::Arc;
use uuid::Uuid;

#[test]
fn test_incremental_mode_detection() {
    // Test that StageInput correctly detects incremental mode
    let changed_files = HashSet::from([PathBuf::from("a.py")]);

    let input_incremental = StageInput {
        files: vec![PathBuf::from("a.py"), PathBuf::from("b.py")],
        cache: std::collections::HashMap::new(),
        config: StageConfig::default(),
        incremental: true,
        changed_files: Some(changed_files.clone()),
    };

    assert!(input_incremental.incremental);
    assert_eq!(input_incremental.changed_files.as_ref().unwrap().len(), 1);

    let input_full = StageInput {
        files: vec![PathBuf::from("a.py"), PathBuf::from("b.py")],
        cache: std::collections::HashMap::new(),
        config: StageConfig::default(),
        incremental: false,
        changed_files: None,
    };

    assert!(!input_full.incremental);
    assert!(input_full.changed_files.is_none());
}

#[test]
fn test_bfs_single_level_dependency() {
    let index = ReverseDependencyIndex::new();

    // Setup: main.py imports utils.py
    index.add_wildcard_import(PathBuf::from("main.py"), PathBuf::from("utils.py"));

    // Change utils.py
    let changed = HashSet::from([PathBuf::from("utils.py")]);
    let affected = compute_affected_files(&changed, &index);

    // Should affect: utils.py (changed) + main.py (importer)
    assert_eq!(affected.len(), 2);
    assert!(affected.contains(&PathBuf::from("utils.py")));
    assert!(affected.contains(&PathBuf::from("main.py")));
}

#[test]
fn test_bfs_multi_level_dependency() {
    let index = ReverseDependencyIndex::new();

    // Setup: app.py → services.py → models.py (3-level chain)
    index.add_wildcard_import(PathBuf::from("services.py"), PathBuf::from("models.py"));
    index.add_wildcard_import(PathBuf::from("app.py"), PathBuf::from("services.py"));

    // Change models.py (leaf)
    let changed = HashSet::from([PathBuf::from("models.py")]);
    let affected = compute_affected_files(&changed, &index);

    // Should transitively affect all 3 files
    assert_eq!(affected.len(), 3);
    assert!(affected.contains(&PathBuf::from("models.py")));
    assert!(affected.contains(&PathBuf::from("services.py")));
    assert!(affected.contains(&PathBuf::from("app.py")));
}

#[test]
fn test_bfs_diamond_dependency() {
    let index = ReverseDependencyIndex::new();

    // Setup:
    //     main.py
    //     /     \
    //  utils.py  helpers.py
    //     \     /
    //     base.py
    index.add_wildcard_import(PathBuf::from("utils.py"), PathBuf::from("base.py"));
    index.add_wildcard_import(PathBuf::from("helpers.py"), PathBuf::from("base.py"));
    index.add_wildcard_import(PathBuf::from("main.py"), PathBuf::from("utils.py"));
    index.add_wildcard_import(PathBuf::from("main.py"), PathBuf::from("helpers.py"));

    // Change base.py
    let changed = HashSet::from([PathBuf::from("base.py")]);
    let affected = compute_affected_files(&changed, &index);

    // Should affect all 4 files
    assert_eq!(affected.len(), 4);
    assert!(affected.contains(&PathBuf::from("base.py")));
    assert!(affected.contains(&PathBuf::from("utils.py")));
    assert!(affected.contains(&PathBuf::from("helpers.py")));
    assert!(affected.contains(&PathBuf::from("main.py")));
}

#[test]
fn test_bfs_multiple_changed_files() {
    let index = ReverseDependencyIndex::new();

    // Setup: independent imports
    index.add_wildcard_import(PathBuf::from("app1.py"), PathBuf::from("utils1.py"));
    index.add_wildcard_import(PathBuf::from("app2.py"), PathBuf::from("utils2.py"));

    // Change both utils files
    let changed = HashSet::from([PathBuf::from("utils1.py"), PathBuf::from("utils2.py")]);
    let affected = compute_affected_files(&changed, &index);

    // Should affect: utils1.py + app1.py + utils2.py + app2.py
    assert_eq!(affected.len(), 4);
    assert!(affected.contains(&PathBuf::from("utils1.py")));
    assert!(affected.contains(&PathBuf::from("app1.py")));
    assert!(affected.contains(&PathBuf::from("utils2.py")));
    assert!(affected.contains(&PathBuf::from("app2.py")));
}

#[test]
fn test_bfs_no_importers() {
    let index = ReverseDependencyIndex::new();

    // Setup: isolated.py has no importers
    index.add_wildcard_import(PathBuf::from("isolated.py"), PathBuf::from("some_lib.py"));

    // Change isolated.py
    let changed = HashSet::from([PathBuf::from("isolated.py")]);
    let affected = compute_affected_files(&changed, &index);

    // Should only affect isolated.py itself
    assert_eq!(affected.len(), 1);
    assert!(affected.contains(&PathBuf::from("isolated.py")));
}

#[test]
fn test_bfs_circular_dependency() {
    let index = ReverseDependencyIndex::new();

    // Setup: circular dependency a.py ⇄ b.py
    index.add_wildcard_import(PathBuf::from("a.py"), PathBuf::from("b.py"));
    index.add_wildcard_import(PathBuf::from("b.py"), PathBuf::from("a.py"));

    // Change a.py
    let changed = HashSet::from([PathBuf::from("a.py")]);
    let affected = compute_affected_files(&changed, &index);

    // Should detect both files (BFS handles cycles correctly)
    assert_eq!(affected.len(), 2);
    assert!(affected.contains(&PathBuf::from("a.py")));
    assert!(affected.contains(&PathBuf::from("b.py")));
}

#[test]
fn test_stage_context_incremental_fields() {
    let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());

    // Test full mode context
    let ctx_full = StageContext {
        job_id: Uuid::new_v4(),
        repo_id: "test-repo".to_string(),
        snapshot_id: "snapshot-1".to_string(),
        cache_keys: CacheKeyManager::new("test-repo".to_string(), "snapshot-1".to_string()),
        checkpoint_mgr: checkpoint_mgr.clone(),
        changed_files: None,
        previous_snapshot_id: None,
    };

    assert!(ctx_full.changed_files.is_none());
    assert!(ctx_full.previous_snapshot_id.is_none());

    // Test incremental mode context
    let changed = HashSet::from([PathBuf::from("changed.py")]);
    let ctx_incremental = StageContext {
        job_id: Uuid::new_v4(),
        repo_id: "test-repo".to_string(),
        snapshot_id: "snapshot-2".to_string(),
        cache_keys: CacheKeyManager::new("test-repo".to_string(), "snapshot-2".to_string()),
        checkpoint_mgr,
        changed_files: Some(changed.clone()),
        previous_snapshot_id: Some("snapshot-1".to_string()),
    };

    assert!(ctx_incremental.changed_files.is_some());
    assert_eq!(ctx_incremental.changed_files.unwrap().len(), 1);
    assert_eq!(ctx_incremental.previous_snapshot_id.unwrap(), "snapshot-1");
}

#[test]
fn test_reverse_dependency_index_concurrent_access() {
    use std::thread;

    let index = Arc::new(ReverseDependencyIndex::new());
    let mut handles = vec![];

    // Spawn 10 threads concurrently adding imports
    for i in 0..10 {
        let index_clone = Arc::clone(&index);
        let handle = thread::spawn(move || {
            for j in 0..100 {
                let from = PathBuf::from(format!("file_{}.py", i));
                let to = PathBuf::from(format!("lib_{}.py", j % 10));
                index_clone.add_wildcard_import(from, to);
            }
        });
        handles.push(handle);
    }

    // Wait for all threads
    for handle in handles {
        handle.join().unwrap();
    }

    // Verify index is populated (lock-free DashMap should handle concurrency)
    assert!(index.len() > 0);

    // Verify we can read concurrently
    let importers = index.get_importers(&PathBuf::from("lib_0.py"));
    assert!(importers.len() > 0); // Multiple files import lib_0.py
}

#[test]
fn test_performance_large_dependency_graph() {
    use std::time::Instant;

    let index = ReverseDependencyIndex::new();

    // Build large dependency graph (1000 files)
    let start_build = Instant::now();
    for i in 0..1000 {
        let from = PathBuf::from(format!("app_{}.py", i));
        let to = PathBuf::from(format!("lib_{}.py", i % 100)); // 10 files per lib
        index.add_wildcard_import(from, to);
    }
    let build_duration = start_build.elapsed();

    println!("Built 1000-file dependency graph in {:?}", build_duration);
    assert!(build_duration.as_millis() < 100); // Should be < 100ms

    // Test BFS performance
    let changed = HashSet::from([PathBuf::from("lib_0.py")]);
    let start_bfs = Instant::now();
    let affected = compute_affected_files(&changed, &index);
    let bfs_duration = start_bfs.elapsed();

    println!(
        "BFS found {} affected files in {:?}",
        affected.len(),
        bfs_duration
    );
    assert!(bfs_duration.as_millis() < 50); // Should be < 50ms
    assert!(affected.len() >= 10); // At least 10 files import lib_0.py
}

#[test]
fn test_incremental_vs_full_mode_comparison() {
    // Simulate real-world scenario: 1% file change in 1000-file repo
    let index = ReverseDependencyIndex::new();

    // Build realistic dependency graph
    for i in 0..1000 {
        if i % 10 != 0 {
            // 90% of files import some common library
            let from = PathBuf::from(format!("app_{}.py", i));
            let to = PathBuf::from(format!("lib_{}.py", i % 10));
            index.add_wildcard_import(from, to);
        }
    }

    // Scenario: Change 1 library file (affects ~100 files)
    let changed = HashSet::from([PathBuf::from("lib_0.py")]);
    let affected = compute_affected_files(&changed, &index);

    let full_rebuild_cost = 1000; // Process all 1000 files
    let incremental_cost = affected.len(); // Process only affected files
    let speedup = full_rebuild_cost as f64 / incremental_cost as f64;

    println!("Changed: 1 file");
    println!("Affected: {} files", affected.len());
    println!("Full rebuild: {} files", full_rebuild_cost);
    println!("Speedup: {:.1}x", speedup);

    assert!(affected.len() < 200); // Should affect < 20% of files
    assert!(speedup > 5.0); // At least 5x speedup
}
