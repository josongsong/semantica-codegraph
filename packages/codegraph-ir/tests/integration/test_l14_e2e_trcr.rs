//! Test L14 E2E Orchestrator with TRCR Integration
//!
//! This test validates the full pipeline:
//! 1. E2E Orchestrator reads test file
//! 2. Builds IR (L1-L6)
//! 3. Runs L14 taint analysis with TRCR enabled
//! 4. Detects SQL injection vulnerability

#[cfg(all(test, feature = "python"))]
mod tests {
    use codegraph_ir::pipeline::{E2EPipelineConfig, IRIndexingOrchestrator, RepoInfo, StageControl, ParallelConfig, CacheConfig, IndexingMode};
    use std::path::PathBuf;

    #[test]
    fn test_l14_trcr_sql_injection() {
        // Test: E2E orchestrator with TRCR detects SQL injection
        println!("=== L14 E2E TRCR Test: SQL Injection Detection ===");

        // Configuration: Enable taint analysis with TRCR
        let config = E2EPipelineConfig {
            repo_info: RepoInfo {
                repo_name: "test-trcr".to_string(),
                repo_root: PathBuf::from("/tmp"),
                file_paths: Some(vec![PathBuf::from("/tmp/test_sql_injection.py")]),
                language_filter: Some("python".to_string()),
            },
            stages: StageControl {
                // L1: IR Build (required)
                enable_ir_build: true,

                // L2-L6: Basic analysis
                enable_chunking: false,
                enable_lexical: false,
                enable_cross_file: true,  // Needed for call graph
                enable_clone_detection: false,
                enable_flow_graph: true,   // Needed for L14
                enable_types: false,
                enable_data_flow: true,    // Needed for L14
                enable_ssa: false,
                enable_symbols: false,
                enable_occurrences: false,
                enable_points_to: false,
                enable_pdg: false,
                enable_heap_analysis: false,
                enable_slicing: false,

                // L14: Taint Analysis with TRCR
                enable_taint: true,
                use_trcr: true,  // 🔥 ENABLE TRCR

                // Other stages
                enable_cost_analysis: false,
                enable_repomap: false,
                enable_concurrency_analysis: false,
                enable_effect_analysis: false,
                enable_smt_verification: false,
                enable_git_history: false,
                enable_query_engine: false,
            },
            parallel_config: ParallelConfig {
                num_workers: Some(1),
                batch_size: 100,
                parallel_cross_file: false,
            },
            cache_config: CacheConfig {
                enable_cache: false,
                redis_url: String::new(),
                cache_ttl_seconds: 0,
                pool_size: 0,
                connection_timeout_ms: 0,
            },
            mode: IndexingMode::Full,
            mmap_threshold_bytes: 1024 * 1024,
            pagerank_settings: Default::default(),
        };

        // Execute pipeline
        let orchestrator = IRIndexingOrchestrator::new(config);
        let result = orchestrator.execute();

        // Assertions
        assert!(result.is_ok(), "Pipeline execution failed: {:?}", result.err());

        let pipeline_result = result.unwrap();

        // Check taint results
        println!("\n📊 Taint Analysis Results:");
        println!("  - Total taint summaries: {}", pipeline_result.taint_results.len());

        for (i, summary) in pipeline_result.taint_results.iter().enumerate() {
            println!("\n  [{}/{}] Function: {}", i + 1, pipeline_result.taint_results.len(), summary.function_id);
            println!("      Sources: {}", summary.sources_found);
            println!("      Sinks: {}", summary.sinks_found);
            println!("      Flows: {}", summary.taint_flows);
        }

        // Validate results
        assert!(!pipeline_result.taint_results.is_empty(),
            "Expected taint flows but found none");

        // Should detect at least one taint flow (input() → execute())
        let total_flows: usize = pipeline_result.taint_results.iter()
            .map(|s| s.taint_flows as usize)
            .sum();

        assert!(total_flows > 0,
            "Expected at least one taint flow (input→execute) but found {}", total_flows);

        println!("\n✅ SUCCESS: TRCR detected {} taint flow(s)", total_flows);
        println!("   Expected: SQL injection (input() → cursor.execute())");
    }
}
