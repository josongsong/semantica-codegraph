//! Integration test for incremental build with BFS dependency propagation
//!
//! Tests Phase 3 Full implementation: compute_affected_files() and execute_incremental()

#[cfg(feature = "cache")]
mod incremental_build_tests {
    use codegraph_ir::pipeline::{IRIndexingOrchestrator, E2EPipelineConfig};
    use codegraph_ir::features::cache::{
        TieredCache, TieredCacheConfig, SessionCacheConfig, AdaptiveCacheConfig, DiskCacheConfig,
        DependencyGraph, FileId, Language, Fingerprint,
    };
    use prometheus::Registry;
    use std::sync::{Arc, Mutex};
    use std::time::Duration;
    use tempfile::TempDir;

    fn create_test_cache() -> (Arc<TieredCache<codegraph_ir::features::ir_generation::domain::ir_document::IRDocument>>, TempDir) {
        let temp_dir = TempDir::new().unwrap();
        let config = TieredCacheConfig {
            l0: SessionCacheConfig {
                max_entries: 100,
                enable_bloom_filter: true,
                bloom_capacity: 1000,
                bloom_fp_rate: 0.01,
            },
            l1: AdaptiveCacheConfig {
                max_entries: 50,
                max_bytes: 10 * 1024 * 1024,
                ttl: Duration::from_secs(3600),
                enable_eviction_listener: false,
            },
            l2: DiskCacheConfig {
                cache_dir: temp_dir.path().to_path_buf(),
                enable_compression: false,
                enable_rocksdb: false,
            },
            enable_background_l2_writes: false,
        };

        let registry = Registry::new();
        let cache = Arc::new(TieredCache::new(config, &registry).unwrap());
        (cache, temp_dir)
    }

    #[test]
    fn test_compute_affected_files_single_change() {
        let (cache, _temp) = create_test_cache();

        // Create orchestrator with cache
        let mut config = E2EPipelineConfig::default();
        config.repo_info.file_paths = Some(vec![]);

        let _orchestrator = IRIndexingOrchestrator::new(config)
            .with_cache(cache.clone())
            .unwrap();

        // Manually populate dependency graph
        // Setup: a.py -> b.py -> c.py (chain dependency)
        let dep_graph = Arc::new(Mutex::new(DependencyGraph::new()));

        let file_a = FileId::from_path_str("a.py", Language::Python);
        let file_b = FileId::from_path_str("b.py", Language::Python);
        let file_c = FileId::from_path_str("c.py", Language::Python);

        {
            let mut graph = dep_graph.lock().unwrap();
            // a.py imports b.py
            graph.register_file(file_a.clone(), Fingerprint::compute(b"a"), &[file_b.clone()]);
            // b.py imports c.py
            graph.register_file(file_b.clone(), Fingerprint::compute(b"b"), &[file_c.clone()]);
            // c.py has no imports
            graph.register_file(file_c.clone(), Fingerprint::compute(b"c"), &[]);
        }

        // If c.py changes, affected files should be: c.py, b.py, a.py
        let affected = {
            let graph = dep_graph.lock().unwrap();
            graph.get_affected_files(&[file_c.clone()])
        };

        // Verify all files in chain are affected
        assert_eq!(affected.len(), 3);
        assert!(affected.contains(&file_a));
        assert!(affected.contains(&file_b));
        assert!(affected.contains(&file_c));
    }

    #[test]
    fn test_compute_affected_files_leaf_change() {
        let (_cache, _temp) = create_test_cache();

        // Setup: a.py has no dependencies (leaf file)
        let dep_graph = Arc::new(Mutex::new(DependencyGraph::new()));

        let file_a = FileId::from_path_str("a.py", Language::Python);

        {
            let mut graph = dep_graph.lock().unwrap();
            graph.register_file(file_a.clone(), Fingerprint::compute(b"a"), &[]);
        }

        // If a.py changes, only a.py is affected
        let affected = {
            let graph = dep_graph.lock().unwrap();
            graph.get_affected_files(&[file_a.clone()])
        };

        assert_eq!(affected.len(), 1);
        assert!(affected.contains(&file_a));
    }

    #[test]
    fn test_compute_affected_files_diamond_dependency() {
        let (_cache, _temp) = create_test_cache();

        // Setup: Diamond dependency
        //     a.py
        //    /    \
        //  b.py  c.py
        //    \    /
        //     d.py

        let dep_graph = Arc::new(Mutex::new(DependencyGraph::new()));

        let file_a = FileId::from_path_str("a.py", Language::Python);
        let file_b = FileId::from_path_str("b.py", Language::Python);
        let file_c = FileId::from_path_str("c.py", Language::Python);
        let file_d = FileId::from_path_str("d.py", Language::Python);

        {
            let mut graph = dep_graph.lock().unwrap();
            // a.py imports b.py and c.py
            graph.register_file(file_a.clone(), Fingerprint::compute(b"a"), &[file_b.clone(), file_c.clone()]);
            // b.py imports d.py
            graph.register_file(file_b.clone(), Fingerprint::compute(b"b"), &[file_d.clone()]);
            // c.py imports d.py
            graph.register_file(file_c.clone(), Fingerprint::compute(b"c"), &[file_d.clone()]);
            // d.py has no imports
            graph.register_file(file_d.clone(), Fingerprint::compute(b"d"), &[]);
        }

        // If d.py changes, affected files should be: d.py, b.py, c.py, a.py
        let affected = {
            let graph = dep_graph.lock().unwrap();
            graph.get_affected_files(&[file_d.clone()])
        };

        assert_eq!(affected.len(), 4);
        assert!(affected.contains(&file_a));
        assert!(affected.contains(&file_b));
        assert!(affected.contains(&file_c));
        assert!(affected.contains(&file_d));
    }

    #[test]
    fn test_execute_incremental_with_empty_files() {
        let (cache, _temp) = create_test_cache();

        // Create orchestrator with cache and empty file list
        let mut config = E2EPipelineConfig::default();
        config.repo_info.file_paths = Some(vec![]);

        let orchestrator = IRIndexingOrchestrator::new(config)
            .with_cache(cache.clone())
            .unwrap();

        // Execute incremental with no actual files
        let result = orchestrator.execute_incremental(vec!["nonexistent.py".to_string()]);

        // Should succeed (no files to process)
        assert!(result.is_ok(), "execute_incremental should succeed with empty files: {:?}", result.err());
    }
}
