use crate::dependency_graph::{compute_affected_files, ReverseDependencyIndex};
use crate::error::Result;
use crate::job::StageId;
use crate::pipeline::{StageContext, StageHandler, StageInput, StageMetrics, StageOutput};
use async_trait::async_trait;
use crate::shared::models::EdgeKind;
use codegraph_ir::pipeline::processor::{process_python_file, ProcessResult};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Instant;
use tracing::{info, warn};

/// Serializable import information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImportInfo {
    pub source_file: String,
    pub target_file: String,
    pub import_type: String, // "wildcard", "specific", "module"
}

/// Serializable IR result from codegraph-ir ProcessResult
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IRResult {
    pub file_path: String,
    pub node_count: usize,
    pub edge_count: usize,
    pub occurrence_count: usize,
    pub bfg_count: usize,
    pub cfg_edges: usize,
    pub type_entities: usize,
    pub dfg_count: usize,
    pub ssa_count: usize,
    pub errors: Vec<String>,
    // NEW: Store import edges for incremental dependency tracking
    pub imports: Vec<ImportInfo>,
}

/// IR Generation Stage (L1) - Real codegraph-ir integration
///
/// Uses codegraph-ir::process_python_file (pure Rust, no PyO3)
/// Achieves 3-7x speedup vs Python implementation
pub struct IRStage {
    repo_id: String,
}

impl IRStage {
    pub fn new(repo_id: String) -> Self {
        Self { repo_id }
    }
}

impl Default for IRStage {
    fn default() -> Self {
        Self::new("default".to_string())
    }
}

#[async_trait]
impl StageHandler for IRStage {
    fn stage_id(&self) -> StageId {
        StageId::L1_IR
    }

    async fn execute(&self, input: StageInput, ctx: &mut StageContext) -> Result<StageOutput> {
        let start = Instant::now();

        // Incremental mode detection
        let (files_to_process, previous_results, reverse_deps_arc): (
            Vec<PathBuf>,
            Option<Vec<IRResult>>,
            Arc<ReverseDependencyIndex>,
        ) = if input.incremental {
            info!(
                "IRStage: INCREMENTAL mode - {} changed files, {} total files",
                input.changed_files.as_ref().map(|c| c.len()).unwrap_or(0),
                input.files.len()
            );

            // 1. Build reverse dependency index from previous IR results
            info!("IRStage: Building reverse dependency index");
            let reverse_deps = Arc::new(ReverseDependencyIndex::new());

            // 2. Load previous IR results
            let prev_ir_results = if let Some(prev_snapshot_id) = &ctx.previous_snapshot_id {
                let prev_cache_key = format!("ir:{}:{}", ctx.repo_id, prev_snapshot_id);
                match ctx.checkpoint_mgr.load_checkpoint(&prev_cache_key).await {
                    Ok(Some(data)) => {
                        match bincode::deserialize::<Vec<IRResult>>(&data) {
                            Ok(results) => {
                                info!("IRStage: Loaded {} previous IR results", results.len());

                                // Extract imports from previous IR results to build reverse dependency index
                                let import_extract_start = Instant::now();
                                let mut import_count = 0;

                                for ir_result in &results {
                                    let source_file = PathBuf::from(&ir_result.file_path);

                                    // Extract imports from stored import info
                                    for import in &ir_result.imports {
                                        let target_path = PathBuf::from(&import.target_file);
                                        reverse_deps
                                            .add_wildcard_import(source_file.clone(), target_path);
                                        import_count += 1;
                                    }
                                }

                                let import_duration = import_extract_start.elapsed();
                                info!(
                                    "IRStage: Extracted {} imports from {} previous IR files in {:?}",
                                    import_count, results.len(), import_duration
                                );

                                Some(results)
                            }
                            Err(e) => {
                                warn!("IRStage: Failed to deserialize previous IR: {}", e);
                                None
                            }
                        }
                    }
                    _ => {
                        warn!("IRStage: No previous IR found, falling back to full rebuild");
                        None
                    }
                }
            } else {
                None
            };

            // 3. Compute affected files using BFS
            let changed_files = input.changed_files.as_ref().unwrap();
            let affected = compute_affected_files(changed_files, &reverse_deps);

            info!(
                "IRStage: Changed {} files → affects {} files ({}x amplification)",
                changed_files.len(),
                affected.len(),
                if changed_files.is_empty() {
                    0
                } else {
                    affected.len() / changed_files.len()
                }
            );

            // 4. Filter files to process (only affected)
            let affected_files: Vec<PathBuf> = input
                .files
                .iter()
                .filter(|f| affected.contains(*f))
                .cloned()
                .collect();

            info!(
                "IRStage: Will process {} affected files (skipping {} unchanged)",
                affected_files.len(),
                input.files.len() - affected_files.len()
            );

            (affected_files, prev_ir_results, reverse_deps)
        } else {
            info!(
                "IRStage: FULL mode - processing {} files with {} workers (real codegraph-ir)",
                input.files.len(),
                input.config.parallel_workers
            );
            (
                input.files.clone(),
                None,
                Arc::new(ReverseDependencyIndex::new()),
            )
        };

        // Process files in parallel using Rayon + codegraph-ir
        let new_results: Vec<IRResult> = files_to_process
            .par_iter()
            .map(|file_path| {
                // Read file content
                let content = match std::fs::read_to_string(file_path) {
                    Ok(c) => c,
                    Err(e) => {
                        warn!("Failed to read {}: {}", file_path.display(), e);
                        return IRResult {
                            file_path: file_path.to_string_lossy().to_string(),
                            node_count: 0,
                            edge_count: 0,
                            occurrence_count: 0,
                            bfg_count: 0,
                            cfg_edges: 0,
                            type_entities: 0,
                            dfg_count: 0,
                            ssa_count: 0,
                            errors: vec![format!("Failed to read file: {}", e)],
                            imports: Vec::new(), // Empty imports on error
                        };
                    }
                };

                // Derive module path from file path (simplified)
                let module_path = file_path
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("unknown")
                    .to_string();

                // Process with real codegraph-ir
                let proc_result = process_python_file(
                    &content,
                    &self.repo_id,
                    &file_path.to_string_lossy(),
                    &module_path,
                );

                // Extract import edges for dependency tracking
                let mut imports = Vec::new();
                for edge in &proc_result.edges {
                    if edge.kind == EdgeKind::Imports {
                        // Extract target file from edge.target_id
                        // target_id format: typically "module:path" or similar
                        let target = edge.target_id.clone();

                        imports.push(ImportInfo {
                            source_file: file_path.to_string_lossy().to_string(),
                            target_file: target,
                            import_type: "wildcard".to_string(), // Simplified for now
                        });
                    }
                }

                // In parallel processing, populate reverse_deps for incremental mode
                if input.incremental {
                    for import in &imports {
                        // Convert target to PathBuf (might need normalization)
                        let target_path = PathBuf::from(&import.target_file);
                        reverse_deps_arc.add_wildcard_import(file_path.clone(), target_path);
                    }
                }

                IRResult {
                    file_path: file_path.to_string_lossy().to_string(),
                    node_count: proc_result.nodes.len(),
                    edge_count: proc_result.edges.len(),
                    occurrence_count: proc_result.occurrences.len(),
                    bfg_count: proc_result.bfg_graphs.len(),
                    cfg_edges: proc_result.cfg_edges.len(),
                    type_entities: proc_result.type_entities.len(),
                    dfg_count: proc_result.dfg_graphs.len(),
                    ssa_count: proc_result.ssa_graphs.len(),
                    errors: proc_result.errors,
                    imports, // NEW: Store imports
                }
            })
            .collect();

        // 5. Merge with previous results (if incremental)
        let final_results: Vec<IRResult> = if input.incremental && previous_results.is_some() {
            let prev_results = previous_results.unwrap();
            let affected_paths: HashSet<String> = files_to_process
                .iter()
                .map(|p| p.to_string_lossy().to_string())
                .collect();

            info!(
                "IRStage: Merging {} new results with {} previous results",
                new_results.len(),
                prev_results.len()
            );

            // Keep previous results for unchanged files, use new results for affected files
            let mut merged = Vec::new();
            for prev in prev_results {
                if !affected_paths.contains(&prev.file_path) {
                    merged.push(prev);
                }
            }
            merged.extend(new_results);

            info!("IRStage: Final merged results: {} files", merged.len());
            merged
        } else {
            new_results
        };

        // Collect results and count metrics
        let mut all_errors = Vec::new();
        let mut files_processed = 0;
        let mut nodes_created = 0;
        let mut chunks_created = 0;

        for result in &final_results {
            if result.errors.is_empty() {
                files_processed += 1;
            } else {
                all_errors.extend(result.errors.clone());
            }
            nodes_created += result.node_count;
            chunks_created += result.occurrence_count;
        }

        let duration_ms = start.elapsed().as_millis() as u64;

        if input.incremental {
            info!(
                "IRStage: INCREMENTAL - Processed {} affected files, merged {} total files, {} nodes in {}ms ({} errors)",
                files_to_process.len(),
                final_results.len(),
                nodes_created,
                duration_ms,
                all_errors.len()
            );
        } else {
            info!(
                "IRStage: FULL - Completed {} files, {} nodes, {} occurrences in {}ms ({} errors)",
                files_processed,
                nodes_created,
                chunks_created,
                duration_ms,
                all_errors.len()
            );
        }

        // Serialize IR results
        let cache_data = bincode::serialize(&final_results)?;

        Ok(StageOutput {
            cache_data,
            metrics: StageMetrics {
                files_processed,
                nodes_created,
                chunks_created,
                duration_ms,
                errors: all_errors,
            },
        })
    }

    fn output_cache_key(&self, ctx: &StageContext) -> String {
        ctx.cache_keys.ir_key()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::checkpoint::CheckpointManager;
    use crate::dag::CacheKeyManager;
    use crate::pipeline::StageConfig;
    use uuid::Uuid;

    #[tokio::test]
    async fn test_ir_stage_creation() {
        let stage = IRStage::new("test-repo".to_string());
        assert_eq!(stage.stage_id(), StageId::L1_IR);
    }

    #[tokio::test]
    async fn test_ir_stage_empty_input() {
        let stage = IRStage::new("test".to_string());
        let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
        let mut ctx = StageContext {
            job_id: Uuid::new_v4(),
            repo_id: "test".to_string(),
            snapshot_id: "snap1".to_string(),
            cache_keys: CacheKeyManager::new("test".to_string(), "snap1".to_string()),
            checkpoint_mgr,
            changed_files: None,
            previous_snapshot_id: None,
        };

        let input = StageInput {
            files: vec![],
            cache: std::collections::HashMap::new(),
            config: StageConfig::default(),
            incremental: false,
            changed_files: None,
        };

        let result = stage.execute(input, &mut ctx).await;
        assert!(result.is_ok());

        let output = result.unwrap();
        assert_eq!(output.metrics.files_processed, 0);
    }

    #[tokio::test]
    async fn test_ir_stage_output_cache_key() {
        let stage = IRStage::new("repo1".to_string());
        let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
        let ctx = StageContext {
            job_id: Uuid::new_v4(),
            repo_id: "repo1".to_string(),
            snapshot_id: "snap1".to_string(),
            cache_keys: CacheKeyManager::new("repo1".to_string(), "snap1".to_string()),
            checkpoint_mgr,
            changed_files: None,
            previous_snapshot_id: None,
        };

        let key = stage.output_cache_key(&ctx);
        assert_eq!(key, "ir:repo1:snap1");
    }

    #[tokio::test]
    async fn test_ir_stage_real_python_file() {
        // Create a real Python test file
        let test_dir = std::env::temp_dir().join("ir_stage_test");
        std::fs::create_dir_all(&test_dir).unwrap();
        let test_file = test_dir.join("test_calculator.py");

        let python_code = r#"
"""Test Python file for IR processing"""

def hello_world():
    """Simple function"""
    print("Hello, World!")
    return 42

class Calculator:
    """Simple calculator class"""

    def add(self, a, b):
        """Add two numbers"""
        return a + b

    def multiply(self, a, b):
        """Multiply two numbers"""
        result = a * b
        return result
"#;
        std::fs::write(&test_file, python_code).unwrap();

        // Setup stage and context
        let stage = IRStage::new("test-repo".to_string());
        let checkpoint_mgr = Arc::new(CheckpointManager::new_in_memory());
        let mut ctx = StageContext {
            job_id: Uuid::new_v4(),
            repo_id: "test-repo".to_string(),
            snapshot_id: "snap1".to_string(),
            cache_keys: CacheKeyManager::new("test-repo".to_string(), "snap1".to_string()),
            checkpoint_mgr,
            changed_files: None,
            previous_snapshot_id: None,
        };

        let input = StageInput {
            files: vec![test_file.clone()],
            cache: std::collections::HashMap::new(),
            config: StageConfig::default(),
            incremental: false,
            changed_files: None,
        };

        // Execute stage with real codegraph-ir
        let result = stage.execute(input, &mut ctx).await;
        assert!(
            result.is_ok(),
            "IRStage execution failed: {:?}",
            result.err()
        );

        let output = result.unwrap();

        // Debug: print actual metrics
        eprintln!(
            "DEBUG Metrics: files={}, nodes={}, chunks={}, duration={}ms",
            output.metrics.files_processed,
            output.metrics.nodes_created,
            output.metrics.chunks_created,
            output.metrics.duration_ms
        );

        assert!(output.metrics.files_processed > 0, "No files processed");
        assert!(output.metrics.nodes_created > 0, "No nodes created");
        // Note: chunks_created might be 0 if we're only counting occurrences

        // Cleanup
        std::fs::remove_dir_all(&test_dir).ok();

        println!("✓ Real IR processing successful:");
        println!("  - Files processed: {}", output.metrics.files_processed);
        println!("  - Nodes created: {}", output.metrics.nodes_created);
        println!("  - Chunks: {}", output.metrics.chunks_created);
        println!("  - Duration: {}ms", output.metrics.duration_ms);
    }
}
