//! Integration test for orchestrator cache integration (RFC-RUST-CACHE-003 Phase 3)

#[cfg(feature = "cache")]
mod orchestrator_cache_tests {
    use codegraph_ir::pipeline::{IRIndexingOrchestrator, E2EPipelineConfig};
    use codegraph_ir::features::cache::{
        TieredCache, TieredCacheConfig, SessionCacheConfig, AdaptiveCacheConfig, DiskCacheConfig,
    };
    use prometheus::Registry;
    use std::sync::Arc;
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
                max_bytes: 10 * 1024 * 1024, // 10MB
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
    fn test_orchestrator_with_cache_creation() {
        let (cache, _temp) = create_test_cache();

        // Use default config
        let config = E2EPipelineConfig::default();

        // Create orchestrator with cache
        let _orchestrator = IRIndexingOrchestrator::new(config)
            .with_cache(cache.clone())
            .unwrap();

        // Verify cache is set (implicit - no panic means success)
        assert!(true, "Orchestrator created with cache successfully");
    }

    #[test]
    fn test_execute_incremental_without_cache_fails() {
        // Use default config
        let config = E2EPipelineConfig::default();

        // Create orchestrator WITHOUT cache
        let orchestrator = IRIndexingOrchestrator::new(config);

        // execute_incremental should fail
        let result = orchestrator.execute_incremental(vec!["src/foo.py".to_string()]);

        assert!(result.is_err(), "execute_incremental should fail without cache");
        let err = result.unwrap_err();
        assert!(
            err.to_string().contains("Cache not enabled"),
            "Error should mention cache not enabled"
        );
    }

    #[test]
    fn test_execute_incremental_with_cache_succeeds() {
        let (cache, _temp) = create_test_cache();

        // Use default config with empty file list (no files to process)
        let mut config = E2EPipelineConfig::default();
        config.repo_info.file_paths = Some(vec![]);

        // Create orchestrator WITH cache
        let orchestrator = IRIndexingOrchestrator::new(config)
            .with_cache(cache.clone())
            .unwrap();

        // execute_incremental should succeed (even with no files)
        let result = orchestrator.execute_incremental(vec!["src/foo.py".to_string()]);

        assert!(result.is_ok(), "execute_incremental should succeed with cache: {:?}", result.err());
    }
}
