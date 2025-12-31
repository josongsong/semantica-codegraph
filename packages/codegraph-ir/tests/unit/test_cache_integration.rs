//! Integration test for SOTA Rust cache system
//!
//! Tests the full L0→L1→L2 tiered cache with IRDocument

#[cfg(feature = "cache")]
mod cache_integration_tests {
    use codegraph_ir::features::cache::{
        TieredCache, CacheKey, FileId, Language, Fingerprint, FileMetadata,
        TieredCacheConfig, SessionCacheConfig, AdaptiveCacheConfig, DiskCacheConfig,
    };
    use codegraph_ir::features::ir_generation::domain::ir_document::IRDocument;
    use codegraph_ir::shared::models::{Node, NodeKind, Span};
    use prometheus::Registry;
    use std::sync::Arc;
    use std::time::Duration;
    use tempfile::TempDir;

    fn create_test_config() -> (TieredCacheConfig, TempDir) {
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
        (config, temp_dir)
    }

    fn create_test_ir_document() -> IRDocument {
        let mut doc = IRDocument::new("test.py".to_string());

        // Add some nodes
        for i in 0..10 {
            doc.add_node(Node::new(
                format!("func_{}", i),
                NodeKind::Function,
                format!("test.func_{}", i),
                "test.py".to_string(),
                Span::new(i, 0, i + 1, 0),
            ));
        }

        doc
    }

    #[tokio::test]
    async fn test_cache_roundtrip() {
        let (config, _temp) = create_test_config();
        let registry = Registry::new();
        let cache: TieredCache<IRDocument> = TieredCache::new(config, &registry).unwrap();

        let key = CacheKey::from_file_id(FileId::from_path_str("test.py", Language::Python));
        let metadata = FileMetadata {
            mtime_ns: 1234567890,
            size_bytes: 1024,
            fingerprint: Fingerprint::compute(b"test content"),
        };

        let doc = Arc::new(create_test_ir_document());

        // Set
        cache.set(&key, doc.clone(), &metadata).await.unwrap();

        // Get (should hit L0)
        let retrieved = cache.get(&key, &metadata).await.unwrap().unwrap();
        assert_eq!(retrieved.file_path, doc.file_path);
        assert_eq!(retrieved.nodes.len(), doc.nodes.len());
    }

    #[tokio::test]
    async fn test_cache_promotion() {
        let (config, _temp) = create_test_config();
        let registry = Registry::new();
        let cache: TieredCache<IRDocument> = TieredCache::new(config, &registry).unwrap();

        let key = CacheKey::from_file_id(FileId::from_path_str("test.py", Language::Python));
        let metadata = FileMetadata {
            mtime_ns: 9876543210,
            size_bytes: 2048,
            fingerprint: Fingerprint::compute(b"promotion test"),
        };

        let doc = Arc::new(create_test_ir_document());

        // Write directly to L2 (bypass L0/L1)
        cache.l2.set(&key, &*doc).unwrap();

        // Get (should hit L2 and promote to L1/L0)
        let retrieved = cache.get(&key, &metadata).await.unwrap().unwrap();
        assert_eq!(retrieved.nodes.len(), 10);

        // Second get should hit L0 (promoted)
        let retrieved2 = cache.get(&key, &metadata).await.unwrap().unwrap();
        assert_eq!(retrieved2.nodes.len(), 10);
    }

    #[tokio::test]
    async fn test_cache_hit_rate() {
        let (config, _temp) = create_test_config();
        let registry = Registry::new();
        let cache: TieredCache<IRDocument> = TieredCache::new(config, &registry).unwrap();

        let key = CacheKey::from_file_id(FileId::from_path_str("test.py", Language::Python));
        let metadata = FileMetadata {
            mtime_ns: 111111,
            size_bytes: 512,
            fingerprint: Fingerprint::compute(b"hit rate test"),
        };

        let doc = Arc::new(create_test_ir_document());

        // Set
        cache.set(&key, doc.clone(), &metadata).await.unwrap();

        // 2 hits
        cache.get(&key, &metadata).await.unwrap();
        cache.get(&key, &metadata).await.unwrap();

        // 1 miss (different key)
        let key2 = CacheKey::from_file_id(FileId::from_path_str("other.py", Language::Python));
        cache.get(&key2, &metadata).await.unwrap();

        // Hit rate: 2/3 = 0.666...
        let hit_rate = cache.hit_rate();
        assert!((hit_rate - 0.666).abs() < 0.01);
    }

    #[tokio::test]
    async fn test_cache_invalidation() {
        let (config, _temp) = create_test_config();
        let registry = Registry::new();
        let cache: TieredCache<IRDocument> = TieredCache::new(config, &registry).unwrap();

        let key = CacheKey::from_file_id(FileId::from_path_str("test.py", Language::Python));
        let metadata = FileMetadata {
            mtime_ns: 222222,
            size_bytes: 768,
            fingerprint: Fingerprint::compute(b"invalidation test"),
        };

        let doc = Arc::new(create_test_ir_document());

        // Set
        cache.set(&key, doc.clone(), &metadata).await.unwrap();
        assert!(cache.get(&key, &metadata).await.unwrap().is_some());

        // Invalidate
        cache.invalidate(&key).await.unwrap();

        // Should miss all tiers
        assert!(cache.get(&key, &metadata).await.unwrap().is_none());
    }

    #[tokio::test]
    async fn test_large_ir_document() {
        let (config, _temp) = create_test_config();
        let registry = Registry::new();
        let cache: TieredCache<IRDocument> = TieredCache::new(config, &registry).unwrap();

        // Create large IR document (1000 nodes)
        let mut doc = IRDocument::new("large.py".to_string());
        for i in 0..1000 {
            doc.add_node(Node::new(
                format!("node_{}", i),
                NodeKind::Function,
                format!("test.func_{}", i),
                "large.py".to_string(),
                Span::new(i, 0, i + 1, 0),
            ));
        }

        let key = CacheKey::from_file_id(FileId::from_path_str("large.py", Language::Python));
        let metadata = FileMetadata {
            mtime_ns: 333333,
            size_bytes: 100000,
            fingerprint: Fingerprint::compute(b"large doc"),
        };

        let doc_arc = Arc::new(doc);

        // Set and retrieve
        cache.set(&key, doc_arc.clone(), &metadata).await.unwrap();
        let retrieved = cache.get(&key, &metadata).await.unwrap().unwrap();

        assert_eq!(retrieved.nodes.len(), 1000);
        assert_eq!(retrieved.file_path, "large.py");
    }
}
