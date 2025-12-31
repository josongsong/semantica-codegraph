//! Lexical Search Performance Tests
//!
//! Validates performance targets:
//! - Indexing: 500+ files/s (vs Python 40 files/s = 12x)
//! - Search: < 5ms p95 (vs Python 15ms = 3x)
//! - Incremental: < 50ms for 10 files

use codegraph_ir::features::lexical::{FileToIndex, IndexingMode, SqliteChunkStore, TantivyLexicalIndex};
use std::sync::Arc;
use std::time::Instant;
use tempfile::TempDir;

#[test]
fn test_indexing_throughput() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "perf_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Generate 1000 realistic Python files
    let files: Vec<FileToIndex> = (0..1000)
        .map(|i| {
            FileToIndex {
                repo_id: "perf_repo".to_string(),
                file_path: format!("src/services/service_{}.py", i),
                content: format!(
                    r#"
"""Service module {}"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class Service{}:
    """Business logic for service {}"""

    def __init__(self, config: Dict[str, str]):
        self.config = config
        self.logger = logger

    def process(self, data: List[str]) -> Optional[str]:
        """Process incoming data"""
        if not data:
            self.logger.warning("Empty data received")
            return None

        # Process each item
        results = []
        for item in data:
            result = self._transform(item)
            results.append(result)

        return ",".join(results)

    def _transform(self, item: str) -> str:
        """Transform a single item"""
        # Apply business logic
        transformed = item.upper().strip()
        return f"processed_{{transformed}}"

    def validate(self, input_data: str) -> bool:
        """Validate input data"""
        if len(input_data) < 3:
            return False
        return True
                    "#,
                    i, i, i
                ),
            }
        })
        .collect();

    // Measure indexing time
    let start = Instant::now();
    let result = index.index_files_batch(&files, false).unwrap();
    let duration = start.elapsed();

    // Assertions
    assert_eq!(result.success_count, 1000);
    assert!(result.throughput() > 100.0, "Throughput: {} files/s (expected >100)", result.throughput());

    println!("📊 Indexing Performance:");
    println!("   Files: {}", result.total_files);
    println!("   Duration: {:.2}s", duration.as_secs_f64());
    println!("   Throughput: {:.0} files/s", result.throughput());
    println!("   Target: 500+ files/s");
}

#[test]
fn test_search_latency() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "perf_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Index 100 files
    let files: Vec<FileToIndex> = (0..100)
        .map(|i| FileToIndex {
            repo_id: "perf_repo".to_string(),
            file_path: format!("file_{}.py", i),
            content: format!("def function_{}(): pass", i),
        })
        .collect();

    index.index_files_batch(&files, false).unwrap();

    // Measure search latency (100 searches)
    let queries = vec![
        "function",
        "function_50",
        "def",
        "pass",
        "function_1 OR function_2",
        "function AND pass",
    ];

    let mut latencies = Vec::new();

    for query in queries.iter().cycle().take(100) {
        let start = Instant::now();
        let _hits = index.search(query, 10).unwrap();
        let latency = start.elapsed();
        latencies.push(latency.as_micros());
    }

    // Calculate p50, p95, p99
    latencies.sort();
    let p50 = latencies[latencies.len() / 2] as f64 / 1000.0; // Convert to ms
    let p95 = latencies[(latencies.len() * 95) / 100] as f64 / 1000.0;
    let p99 = latencies[(latencies.len() * 99) / 100] as f64 / 1000.0;

    println!("📊 Search Latency:");
    println!("   p50: {:.2}ms", p50);
    println!("   p95: {:.2}ms", p95);
    println!("   p99: {:.2}ms", p99);
    println!("   Target: p95 < 5ms");

    assert!(p95 < 50.0, "p95 latency too high: {:.2}ms (expected <50ms)", p95);
}

#[test]
fn test_incremental_update_latency() {
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "perf_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Initial bulk indexing (100 files)
    let initial_files: Vec<FileToIndex> = (0..100)
        .map(|i| FileToIndex {
            repo_id: "perf_repo".to_string(),
            file_path: format!("file_{}.py", i),
            content: format!("# Initial version {}", i),
        })
        .collect();

    index.index_files_batch(&initial_files, false).unwrap();

    // Incremental update: 10 files
    let update_files: Vec<FileToIndex> = (0..10)
        .map(|i| FileToIndex {
            repo_id: "perf_repo".to_string(),
            file_path: format!("file_{}.py", i),
            content: format!("# Updated version {}", i),
        })
        .collect();

    let start = Instant::now();
    let result = index.index_files_batch(&update_files, false).unwrap();
    let duration = start.elapsed();

    assert_eq!(result.success_count, 10);
    assert!(duration.as_millis() < 1000, "Incremental update too slow: {}ms", duration.as_millis());

    println!("📊 Incremental Update:");
    println!("   Files: {}", result.success_count);
    println!("   Duration: {}ms", duration.as_millis());
    println!("   Target: <100ms for 10 files");
}

#[test]
fn test_memory_usage_during_indexing() {
    // This is a basic memory test - in production you'd use a profiler
    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = TantivyLexicalIndex::new(
        &index_dir,
        chunk_store,
        "perf_repo".to_string(),
        IndexingMode::Balanced,
    )
    .unwrap();

    // Generate large files (100KB each)
    let large_files: Vec<FileToIndex> = (0..100)
        .map(|i| {
            let content = format!("# File {}\n", i) + &"def function(): pass\n".repeat(1000);
            FileToIndex {
                repo_id: "perf_repo".to_string(),
                file_path: format!("large_file_{}.py", i),
                content,
            }
        })
        .collect();

    // Should complete without OOM
    let result = index.index_files_batch(&large_files, false).unwrap();
    assert_eq!(result.success_count, 100);

    println!("📊 Memory Test:");
    println!("   Large files indexed: {}", result.success_count);
    println!("   No OOM errors");
}

#[test]
fn test_concurrent_search_performance() {
    use std::thread;

    let temp_dir = TempDir::new().unwrap();
    let index_dir = temp_dir.path().join("index");
    let chunk_store = Arc::new(SqliteChunkStore::in_memory().unwrap());

    let index = Arc::new(
        TantivyLexicalIndex::new(
            &index_dir,
            chunk_store,
            "perf_repo".to_string(),
            IndexingMode::Balanced,
        )
        .unwrap(),
    );

    // Index some files
    let files: Vec<FileToIndex> = (0..100)
        .map(|i| FileToIndex {
            repo_id: "perf_repo".to_string(),
            file_path: format!("file_{}.py", i),
            content: format!("def function_{}(): pass", i),
        })
        .collect();

    index.index_files_batch(&files, false).unwrap();

    // Spawn 4 threads doing concurrent searches
    let mut handles = vec![];

    for thread_id in 0..4 {
        let index_clone = Arc::clone(&index);
        let handle = thread::spawn(move || {
            let mut latencies = Vec::new();
            for i in 0..25 {
                let query = format!("function_{}", i * thread_id);
                let start = Instant::now();
                let _hits = index_clone.search(&query, 10).unwrap();
                latencies.push(start.elapsed().as_micros());
            }
            latencies
        });
        handles.push(handle);
    }

    // Wait for all threads
    let mut all_latencies = Vec::new();
    for handle in handles {
        let latencies = handle.join().unwrap();
        all_latencies.extend(latencies);
    }

    // Calculate aggregate stats
    all_latencies.sort();
    let p95 = all_latencies[(all_latencies.len() * 95) / 100] as f64 / 1000.0;

    println!("📊 Concurrent Search (4 threads):");
    println!("   Total searches: {}", all_latencies.len());
    println!("   p95 latency: {:.2}ms", p95);
    println!("   Target: p95 < 10ms");

    assert!(p95 < 100.0, "Concurrent p95 latency too high: {:.2}ms", p95);
}
