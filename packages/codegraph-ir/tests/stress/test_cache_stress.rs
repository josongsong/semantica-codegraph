//! Stress tests for cache system - large files, concurrent access, edge cases

#[cfg(feature = "cache")]
mod cache_stress_tests {
    use codegraph_ir::features::cache::{
        TieredCache, CacheKey, Language, Fingerprint, FileMetadata,
        TieredCacheConfig, SessionCacheConfig, AdaptiveCacheConfig, DiskCacheConfig,
    };
    use codegraph_ir::features::ir_generation::domain::ir_document::IRDocument;
    use codegraph_ir::shared::models::{Node, NodeKind, Span};
    use prometheus::Registry;
    use std::sync::Arc;
    use std::time::Duration;
    use tempfile::TempDir;

    fn create_test_cache() -> (Arc<TieredCache<IRDocument>>, TempDir) {
        let temp_dir = TempDir::new().unwrap();
        let config = TieredCacheConfig {
            l0: SessionCacheConfig {
                max_entries: 1000,
                enable_bloom_filter: true,
                bloom_capacity: 10000,
                bloom_fp_rate: 0.01,
            },
            l1: AdaptiveCacheConfig {
                max_entries: 500,
                max_bytes: 100 * 1024 * 1024, // 100MB
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
    async fn test_cache_1000_files() {
        let (cache, _temp) = create_test_cache();

        // Cache 1000 files
        for i in 0..1000 {
            let file_path = format!("file_{}.py", i);
            let content = format!("def func_{}():\n    pass\n", i);

            let key = CacheKey::from_content(&file_path, Language::Python, content.as_bytes());
            let metadata = FileMetadata {
                mtime_ns: i as u64,
                size_bytes: content.len() as u64,
                fingerprint: Fingerprint::compute(content.as_bytes()),
            };

            let mut ir_doc = IRDocument::new(file_path.clone());
            ir_doc.add_node(Node::new(
                format!("func_{}", i),
                NodeKind::Function,
                format!("module.func_{}", i),
                file_path,
                Span::new(1, 0, 2, 0),
            ));

            cache.set(&key, Arc::new(ir_doc), &metadata).await.unwrap();
        }

        // Verify all 1000 files are cached
        for i in 0..1000 {
            let file_path = format!("file_{}.py", i);
            let content = format!("def func_{}():\n    pass\n", i);

            let key = CacheKey::from_content(&file_path, Language::Python, content.as_bytes());
            let metadata = FileMetadata {
                mtime_ns: i as u64,
                size_bytes: content.len() as u64,
                fingerprint: Fingerprint::compute(content.as_bytes()),
            };

            let result = cache.get(&key, &metadata).await.unwrap();
            assert!(result.is_some(), "File {} not found in cache", i);
            assert_eq!(result.unwrap().nodes.len(), 1);
        }
    }

    #[tokio::test]
    async fn test_cache_very_large_ir_document() {
        let (cache, _temp) = create_test_cache();

        // Create IR document with 10,000 nodes
        let mut ir_doc = IRDocument::new("huge_file.py".to_string());
        for i in 0..10000 {
            ir_doc.add_node(Node::new(
                format!("node_{}", i),
                NodeKind::Function,
                format!("module.func_{}", i),
                "huge_file.py".to_string(),
                Span::new(i * 3, 0, i * 3 + 3, 0),
            ));
        }

        let content = "# Very large file\n".repeat(10000);
        let key = CacheKey::from_content("huge_file.py", Language::Python, content.as_bytes());
        let metadata = FileMetadata {
            mtime_ns: 123456789,
            size_bytes: content.len() as u64,
            fingerprint: Fingerprint::compute(content.as_bytes()),
        };

        // Store
        cache.set(&key, Arc::new(ir_doc.clone()), &metadata).await.unwrap();

        // Retrieve
        let retrieved = cache.get(&key, &metadata).await.unwrap().unwrap();
        assert_eq!(retrieved.nodes.len(), 10000);
        assert_eq!(retrieved.file_path, "huge_file.py");
    }

    #[tokio::test]
    async fn test_cache_concurrent_access() {
        let (cache, _temp) = create_test_cache();

        // Prepare data
        let file_path = "concurrent.py";
        let content = b"def foo():\n    pass\n";
        let key = CacheKey::from_content(file_path, Language::Python, content);
        let metadata = FileMetadata {
            mtime_ns: 111111,
            size_bytes: content.len() as u64,
            fingerprint: Fingerprint::compute(content),
        };

        let mut ir_doc = IRDocument::new(file_path.to_string());
        ir_doc.add_node(Node::new(
            "foo".to_string(),
            NodeKind::Function,
            "module.foo".to_string(),
            file_path.to_string(),
            Span::new(1, 0, 2, 0),
        ));

        cache.set(&key, Arc::new(ir_doc), &metadata).await.unwrap();

        // Concurrent reads (100 tasks)
        let mut handles = vec![];
        for _ in 0..100 {
            let cache_clone = cache.clone();
            let key_clone = key.clone();
            let metadata_clone = metadata.clone();

            let handle = tokio::spawn(async move {
                let result = cache_clone.get(&key_clone, &metadata_clone).await.unwrap();
                assert!(result.is_some());
                assert_eq!(result.unwrap().nodes.len(), 1);
            });

            handles.push(handle);
        }

        // Wait for all tasks
        for handle in handles {
            handle.await.unwrap();
        }
    }

    #[tokio::test]
    async fn test_cache_eviction_l0_overflow() {
        let temp_dir = TempDir::new().unwrap();
        let config = TieredCacheConfig {
            l0: SessionCacheConfig {
                max_entries: 10, // Small L0 for eviction test
                enable_bloom_filter: true,
                bloom_capacity: 100,
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
        let cache: TieredCache<IRDocument> = TieredCache::new(config, &registry).unwrap();

        // Add 20 files (exceeds L0 capacity of 10)
        for i in 0..20 {
            let file_path = format!("file_{}.py", i);
            let content = format!("def func_{}():\n    pass\n", i);

            let key = CacheKey::from_content(&file_path, Language::Python, content.as_bytes());
            let metadata = FileMetadata {
                mtime_ns: i as u64,
                size_bytes: content.len() as u64,
                fingerprint: Fingerprint::compute(content.as_bytes()),
            };

            let mut ir_doc = IRDocument::new(file_path.clone());
            ir_doc.add_node(Node::new(
                format!("func_{}", i),
                NodeKind::Function,
                format!("module.func_{}", i),
                file_path,
                Span::new(1, 0, 2, 0),
            ));

            cache.set(&key, Arc::new(ir_doc), &metadata).await.unwrap();
        }

        // All should still be accessible (L1 or L2 promotion)
        for i in 0..20 {
            let file_path = format!("file_{}.py", i);
            let content = format!("def func_{}():\n    pass\n", i);

            let key = CacheKey::from_content(&file_path, Language::Python, content.as_bytes());
            let metadata = FileMetadata {
                mtime_ns: i as u64,
                size_bytes: content.len() as u64,
                fingerprint: Fingerprint::compute(content.as_bytes()),
            };

            let result = cache.get(&key, &metadata).await.unwrap();
            assert!(result.is_some(), "File {} should still be cached", i);
        }
    }

    #[tokio::test]
    async fn test_cache_empty_file() {
        let (cache, _temp) = create_test_cache();

        let key = CacheKey::from_content("empty.py", Language::Python, b"");
        let metadata = FileMetadata {
            mtime_ns: 0,
            size_bytes: 0,
            fingerprint: Fingerprint::compute(b""),
        };

        let ir_doc = IRDocument::new("empty.py".to_string());
        cache.set(&key, Arc::new(ir_doc.clone()), &metadata).await.unwrap();

        let retrieved = cache.get(&key, &metadata).await.unwrap().unwrap();
        assert_eq!(retrieved.nodes.len(), 0);
        assert_eq!(retrieved.edges.len(), 0);
    }

    #[tokio::test]
    async fn test_cache_same_path_different_content() {
        let (cache, _temp) = create_test_cache();

        let file_path = "test.py";

        // Version 1
        let content_v1 = b"def foo(): pass";
        let key_v1 = CacheKey::from_content(file_path, Language::Python, content_v1);
        let metadata_v1 = FileMetadata {
            mtime_ns: 100,
            size_bytes: content_v1.len() as u64,
            fingerprint: Fingerprint::compute(content_v1),
        };

        let mut ir_v1 = IRDocument::new(file_path.to_string());
        ir_v1.add_node(
            Node::new("foo".to_string(), NodeKind::Function, "module.foo".to_string(), file_path.to_string(), Span::new(1, 0, 1, 15))
                .with_name("foo")
        );

        cache.set(&key_v1, Arc::new(ir_v1.clone()), &metadata_v1).await.unwrap();

        // Version 2 (different content)
        let content_v2 = b"def bar(): pass";
        let key_v2 = CacheKey::from_content(file_path, Language::Python, content_v2);
        let metadata_v2 = FileMetadata {
            mtime_ns: 200,
            size_bytes: content_v2.len() as u64,
            fingerprint: Fingerprint::compute(content_v2),
        };

        let mut ir_v2 = IRDocument::new(file_path.to_string());
        ir_v2.add_node(
            Node::new("bar".to_string(), NodeKind::Function, "module.bar".to_string(), file_path.to_string(), Span::new(1, 0, 1, 15))
                .with_name("bar")
        );

        cache.set(&key_v2, Arc::new(ir_v2.clone()), &metadata_v2).await.unwrap();

        // Both versions should be cached independently
        let retrieved_v1 = cache.get(&key_v1, &metadata_v1).await.unwrap().unwrap();
        let retrieved_v2 = cache.get(&key_v2, &metadata_v2).await.unwrap().unwrap();

        assert_eq!(retrieved_v1.nodes[0].name, Some("foo".to_string()));
        assert_eq!(retrieved_v2.nodes[0].name, Some("bar".to_string()));
    }
}
