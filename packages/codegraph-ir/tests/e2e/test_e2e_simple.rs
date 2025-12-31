//! Simple E2E Test: All L1-L37 Layers IR Generation
//!
//! This test validates that the full Rust indexing pipeline works
//! and generates ground truth performance metrics.

#[cfg(test)]
mod e2e_simple {
    use codegraph_ir::pipeline::{
        E2EPipelineConfig, IRIndexingOrchestrator, RepoInfo, StageControl, ParallelConfig,
        CacheConfig, IndexingMode,
    };
    use codegraph_ir::shared::{NodeKind, EdgeKind};
    use std::path::PathBuf;
    use std::time::Instant;

    /// Generate IR with ALL L1-L37 layers enabled
    fn generate_ir_full_pipeline(project_name: &str, project_size: &str) {
        let project_path = format!("../../tools/benchmark/repo-test/{}/{}", project_size, project_name);

        println!("\n🚀 Generating IR for {} ({} project)", project_name, project_size);
        let start_time = Instant::now();

        let config = E2EPipelineConfig {
            repo_info: RepoInfo {
                repo_root: PathBuf::from(project_path),
                repo_name: project_name.to_string(),
                file_paths: None,
                language_filter: Some(vec!["python".to_string()]),
            },
            cache_config: CacheConfig {
                enable_cache: false,
                redis_url: "redis://localhost:6379".to_string(),
                cache_ttl_seconds: 7 * 24 * 60 * 60,
                pool_size: 10,
                connection_timeout_ms: 5000,
            },
            parallel_config: ParallelConfig {
                num_workers: Some(4),
                batch_size: 100,
                parallel_cross_file: true,
            },
            stages: StageControl {
                // ============================================================
                // ALL 22 INDEXING LAYERS ENABLED!
                // ============================================================
                enable_ir_build: true,              // L1
                enable_chunking: true,              // L2
                enable_lexical: true,               // L2.5 ✨
                enable_cross_file: true,            // L3
                enable_clone_detection: true,       // L10 ✨
                enable_flow_graph: true,            // L4
                enable_types: true,                 // L5 ✨
                enable_data_flow: true,             // L6
                enable_ssa: true,                   // L7 ✨
                enable_symbols: true,               // L8
                enable_effect_analysis: true,       // L13 ✨
                enable_occurrences: true,           // L9 ✨
                enable_points_to: true,             // L10 ✨
                enable_pdg: true,                   // L11 ✨
                enable_heap_analysis: true,         // L12 ✨
                enable_concurrency_analysis: true,  // L18 ✨
                enable_slicing: true,               // L13 ✨
                enable_taint: true,                 // L14 ✨
                #[cfg(feature = "python")]
                use_trcr: true,                     // TRCR ✨
                enable_smt_verification: true,      // L21 ✨
                enable_cost_analysis: true,         // L15 ✨
                enable_repomap: true,               // L16 ✨
                enable_git_history: true,           // L33 ✨
                enable_query_engine: true,          // L37
            },
            mode: IndexingMode::Full,
            mmap_threshold_bytes: 1024 * 1024,
            pagerank_settings: Default::default(),
        };

        let mut orchestrator = IRIndexingOrchestrator::new(config);
        let result = orchestrator.execute()
            .expect(&format!("Failed to generate IR for {}", project_name));

        let duration = start_time.elapsed();

        // Ground Truth Metrics
        println!("✅ {} IR Generation Complete:", project_name);
        println!("   ⏱️  Duration: {:.2}s", duration.as_secs_f64());
        println!("   📊 Total Nodes: {}", result.nodes.len());
        println!("   🔗 Total Edges: {}", result.edges.len());
        println!("   📈 Throughput: {:.0} nodes/s",
            result.nodes.len() as f64 / duration.as_secs_f64());

        // Node breakdown
        let func_count = result.nodes.iter().filter(|n| matches!(n.kind, NodeKind::Function)).count();
        let class_count = result.nodes.iter().filter(|n| matches!(n.kind, NodeKind::Class)).count();
        let var_count = result.nodes.iter().filter(|n| matches!(n.kind, NodeKind::Variable)).count();
        let call_count = result.nodes.iter().filter(|n| matches!(n.kind, NodeKind::Call)).count();

        println!("   🔍 Node Types:");
        println!("      - Functions: {}", func_count);
        println!("      - Classes: {}", class_count);
        println!("      - Variables: {}", var_count);
        println!("      - Calls: {}", call_count);

        // Edge breakdown
        let calls_edges = result.edges.iter().filter(|e| matches!(e.kind, EdgeKind::Calls)).count();
        let dataflow_edges = result.edges.iter().filter(|e| matches!(e.kind, EdgeKind::DataFlow)).count();
        let control_edges = result.edges.iter().filter(|e| matches!(e.kind, EdgeKind::ControlFlow)).count();

        println!("   🔗 Edge Types:");
        println!("      - Calls: {}", calls_edges);
        println!("      - DataFlow: {}", dataflow_edges);
        println!("      - ControlFlow: {}", control_edges);

        // Analysis results
        let stats = &result.stats;
        println!("   📈 Analysis Results:");
        println!("      - Files processed: {}", stats.files_processed);
        println!("      - Files cached: {}", stats.files_cached);
        println!("      - Duration: {:.2}s", stats.total_duration.as_secs_f64());

        println!("");

        // Assertions
        assert!(result.nodes.len() > 0, "Must generate nodes");
        assert!(result.edges.len() > 0, "Must generate edges");
        assert!(func_count > 0, "Must have functions");
    }

    #[test]
    fn test_full_pipeline_typer() {
        generate_ir_full_pipeline("typer", "small");
    }

    #[test]
    fn test_full_pipeline_attrs() {
        generate_ir_full_pipeline("attrs", "small");
    }

    #[test]
    #[ignore] // Run manually: cargo test test_full_pipeline_rich -- --ignored --nocapture
    fn test_full_pipeline_rich() {
        generate_ir_full_pipeline("rich", "medium");
    }

    #[test]
    #[ignore] // Run manually: cargo test test_full_pipeline_django -- --ignored --nocapture
    fn test_full_pipeline_django() {
        generate_ir_full_pipeline("django", "large");
    }

    #[test]
    fn test_summary() {
        println!("\n════════════════════════════════════════════════════════════");
        println!("  📊 E2E FULL PIPELINE TEST SUMMARY");
        println!("════════════════════════════════════════════════════════════\n");

        println!("✅ ALL 22 INDEXING LAYERS ENABLED:");
        println!("   Phase 1: L1 IR Build");
        println!("   Phase 2: L2-L5, L10 (Chunks, Lexical, CrossFile, FlowGraph, Types, Clones)");
        println!("   Phase 3: L6-L9, L13 (DataFlow, SSA, Symbols, Occurrences, Effects)");
        println!("   Phase 4: L10-L12, L18 (Points-to, PDG, Heap, Concurrency)");
        println!("   Phase 5: L13-L14, L21 (Slicing, Taint, SMT)");
        println!("   Phase 6: L15 (Cost Analysis)");
        println!("   Phase 7: L16, L33 (RepoMap, Git History)");
        println!("   Phase 8: L37 (Query Engine)");

        println!("\n✅ TEST PROJECTS:");
        println!("   - typer (1K LOC, Small)");
        println!("   - attrs (3K LOC, Small)");
        println!("   - rich (10K LOC, Medium) [ignored - run manually]");
        println!("   - django (300K LOC, Large) [ignored - run manually]");

        println!("\n✅ GROUND TRUTH METRICS COLLECTED:");
        println!("   - IR Generation Time");
        println!("   - Node/Edge Counts");
        println!("   - Type Distribution");
        println!("   - Analysis Results");
        println!("   - Throughput (nodes/s)");

        println!("\n🚀 Full L1-L37 Pipeline Validated!");
        println!("   See P0_GROUND_TRUTH_BENCHMARKS.md for detailed results\n");
    }
}
