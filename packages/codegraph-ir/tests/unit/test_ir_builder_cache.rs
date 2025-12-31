//! Integration test for IRBuilder cache integration (RFC-RUST-CACHE-002 Phase 2)

#[cfg(feature = "cache")]
mod ir_builder_cache_tests {
    use codegraph_ir::features::ir_generation::infrastructure::ir_builder::IRBuilder;
    use codegraph_ir::features::cache::{
        TieredCache, TieredCacheConfig, SessionCacheConfig, AdaptiveCacheConfig, DiskCacheConfig,
    };
    use codegraph_ir::shared::models::Span;
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

    #[tokio::test]
    async fn test_ir_builder_cache_miss_then_hit() {
        let (cache, _temp) = create_test_cache();

        let file_content = b"def foo():\n    pass\n";
        let file_path = "test.py".to_string();

        // First build - cache miss
        let mut builder1 = IRBuilder::new(
            "repo1".to_string(),
            file_path.clone(),
            "python".to_string(),
            "test_module".to_string(),
        )
        .with_cache(cache.clone(), file_content);

        // Add a test node
        let node_id = builder1.create_function_node(
            "foo".to_string(),
            Span::new(1, 0, 2, 0),
            None,  // body_span
            false, // is_method
            None,  // docstring
            "def foo():\n    pass",  // source_text
            None,  // return_type_annotation
        ).unwrap();

        let ir_doc1 = builder1.build_with_cache().await.unwrap();
        assert_eq!(ir_doc1.nodes.len(), 1);
        assert_eq!(ir_doc1.nodes[0].id, node_id);
        assert_eq!(ir_doc1.file_path, file_path);

        // Second build with SAME content - cache hit
        let builder2 = IRBuilder::new(
            "repo1".to_string(),
            file_path.clone(),
            "python".to_string(),
            "test_module".to_string(),
        )
        .with_cache(cache.clone(), file_content);

        // DON'T add any nodes - should still get cached IR
        let ir_doc2 = builder2.build_with_cache().await.unwrap();
        assert_eq!(ir_doc2.nodes.len(), 1); // From cache!
        assert_eq!(ir_doc2.nodes[0].id, ir_doc1.nodes[0].id);
    }

    #[tokio::test]
    async fn test_ir_builder_cache_invalidation_on_content_change() {
        let (cache, _temp) = create_test_cache();

        let file_path = "test.py".to_string();

        // Build with v1 content
        let content_v1 = b"def foo():\n    pass\n";
        let mut builder1 = IRBuilder::new(
            "repo1".to_string(),
            file_path.clone(),
            "python".to_string(),
            "test_module".to_string(),
        )
        .with_cache(cache.clone(), content_v1);

        builder1.create_function_node(
            "foo".to_string(),
            Span::new(1, 0, 2, 0),
            None, false, None, "def foo():\n    pass", None,
        ).unwrap();

        let ir_doc1 = builder1.build_with_cache().await.unwrap();
        assert_eq!(ir_doc1.nodes.len(), 1);

        // Build with v2 content (different fingerprint)
        let content_v2 = b"def bar():\n    pass\n";
        let mut builder2 = IRBuilder::new(
            "repo1".to_string(),
            file_path.clone(),
            "python".to_string(),
            "test_module".to_string(),
        )
        .with_cache(cache.clone(), content_v2);

        builder2.create_function_node(
            "bar".to_string(),
            Span::new(1, 0, 2, 0),
            None, false, None, "def bar():\n    pass", None,
        ).unwrap();

        let ir_doc2 = builder2.build_with_cache().await.unwrap();
        assert_eq!(ir_doc2.nodes.len(), 1);
        assert_ne!(ir_doc2.nodes[0].id, ir_doc1.nodes[0].id); // Different node!
    }

    #[tokio::test]
    async fn test_ir_builder_without_cache() {
        let file_path = "test.py".to_string();

        // Build without cache
        let mut builder = IRBuilder::new(
            "repo1".to_string(),
            file_path.clone(),
            "python".to_string(),
            "test_module".to_string(),
        );
        // No .with_cache() call

        builder.create_function_node(
            "foo".to_string(),
            Span::new(1, 0, 2, 0),
            None, false, None, "def foo():\n    pass", None,
        ).unwrap();

        let ir_doc = builder.build_with_cache().await.unwrap();
        assert_eq!(ir_doc.nodes.len(), 1);
        assert_eq!(ir_doc.file_path, file_path);
    }

    #[tokio::test]
    async fn test_ir_builder_cache_large_file() {
        let (cache, _temp) = create_test_cache();

        // Simulate large file with 100 functions
        let file_path = "large.py".to_string();
        let file_content = "def func():\n    pass\n".repeat(100);

        let mut builder = IRBuilder::new(
            "repo1".to_string(),
            file_path.clone(),
            "python".to_string(),
            "test_module".to_string(),
        )
        .with_cache(cache.clone(), file_content.as_bytes());

        // Add 100 function nodes
        for i in 0..100 {
            builder.create_function_node(
                format!("func_{}", i),
                Span::new(i * 2, 0, i * 2 + 2, 0),
                None, false, None, "def func():\n    pass", None,
            ).unwrap();
        }

        let ir_doc = builder.build_with_cache().await.unwrap();
        assert_eq!(ir_doc.nodes.len(), 100);

        // Second build - should hit cache
        let builder2 = IRBuilder::new(
            "repo1".to_string(),
            file_path,
            "python".to_string(),
            "test_module".to_string(),
        )
        .with_cache(cache, file_content.as_bytes());

        let ir_doc2 = builder2.build_with_cache().await.unwrap();
        assert_eq!(ir_doc2.nodes.len(), 100); // From cache!
    }

    #[tokio::test]
    async fn test_ir_builder_cache_multi_language() {
        let (cache, _temp) = create_test_cache();

        // Python file
        let python_content = b"def foo():\n    pass\n";
        let mut builder_py = IRBuilder::new(
            "repo1".to_string(),
            "test.py".to_string(),
            "python".to_string(),
            "test_module".to_string(),
        )
        .with_cache(cache.clone(), python_content);

        builder_py.create_function_node(
            "foo".to_string(),
            Span::new(1, 0, 2, 0),
            None, false, None, "def foo():\n    pass", None,
        ).unwrap();

        let ir_py = builder_py.build_with_cache().await.unwrap();
        assert_eq!(ir_py.nodes.len(), 1);

        // TypeScript file
        let ts_content = b"function bar() {}\n";
        let mut builder_ts = IRBuilder::new(
            "repo1".to_string(),
            "test.ts".to_string(),
            "typescript".to_string(),
            "test_module".to_string(),
        )
        .with_cache(cache.clone(), ts_content);

        builder_ts.create_function_node(
            "bar".to_string(),
            Span::new(1, 0, 1, 17),
            None, false, None, "function bar() {}", None,
        ).unwrap();

        let ir_ts = builder_ts.build_with_cache().await.unwrap();
        assert_eq!(ir_ts.nodes.len(), 1);

        // Both should be cached independently
        assert_ne!(ir_py.nodes[0].id, ir_ts.nodes[0].id);
    }
}
