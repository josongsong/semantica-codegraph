//! L1: IR Build Executor
//!
//! Builds intermediate representation (IR) from source files using parallel processing.

use super::base::{StageExecutor, StageResult};
use super::context::PipelineContext;
use crate::pipeline::dag::StageId;
use crate::pipeline::unified_processor::process_any_file;
use crate::shared::models::{CodegraphError, Node, Edge, Occurrence};
use std::time::Instant;
use std::path::PathBuf;
use rayon::prelude::*;
use walkdir::WalkDir;

/// L1: IR Build Executor
///
/// Discovers and processes all source files in parallel to build the IR.
pub struct IRBuildExecutor {
    /// Number of parallel workers (None = use Rayon default)
    parallel_workers: Option<usize>,
}

impl IRBuildExecutor {
    pub fn new(parallel_workers: Option<usize>) -> Self {
        Self { parallel_workers }
    }

    /// Discover all source files in repository
    fn discover_files(&self, repo_root: &PathBuf) -> Result<Vec<PathBuf>, CodegraphError> {
        let mut files = Vec::new();

        for entry in WalkDir::new(repo_root)
            .follow_links(false)
            .into_iter()
            .filter_entry(|e| {
                // Skip hidden directories and common ignore patterns
                let name = e.file_name().to_string_lossy();
                !name.starts_with('.') &&
                name != "node_modules" &&
                name != "__pycache__" &&
                name != "target" &&
                name != "venv"
            })
        {
            let entry = entry.map_err(|e| CodegraphError::internal(format!("Walk error: {}", e)))?;

            if entry.file_type().is_file() {
                let path = entry.path();
                if let Some(ext) = path.extension() {
                    let ext_str = ext.to_string_lossy();
                    if matches!(ext_str.as_ref(), "py" | "java" | "kt" | "ts" | "tsx" | "js" | "jsx" | "rs" | "go") {
                        files.push(path.to_path_buf());
                    }
                }
            }
        }

        Ok(files)
    }

    /// Process a single file
    fn process_file(
        &self,
        file_path: &PathBuf,
        repo_root: &PathBuf,
        repo_name: &str,
    ) -> Option<(Vec<Node>, Vec<Edge>, Vec<Occurrence>)> {
        // Read file content
        let content = match std::fs::read_to_string(file_path) {
            Ok(c) => c,
            Err(e) => {
                eprintln!("[L1] Failed to read {:?}: {}", file_path, e);
                return None;
            }
        };

        // Determine language
        let language = match file_path.extension()?.to_str()? {
            "py" => "python",
            "java" => "java",
            "kt" => "kotlin",
            "ts" | "tsx" => "typescript",
            "js" | "jsx" => "javascript",
            "rs" => "rust",
            "go" => "go",
            _ => return None,
        };

        // Get relative path for module calculation
        let rel_path = file_path.strip_prefix(repo_root).ok()?;
        let rel_path_str = rel_path.to_string_lossy().to_string();

        // Process file using unified_processor
        match process_any_file(
            &rel_path_str,
            &content,
            repo_name,
        ) {
            Ok(result) => {
                Some((result.nodes, result.edges, result.occurrences))
            }
            Err(e) => {
                eprintln!("[L1] Failed to process {:?}: {}", file_path, e);
                None
            }
        }
    }
}

impl StageExecutor for IRBuildExecutor {
    fn stage_id(&self) -> StageId {
        StageId::L1IrBuild
    }

    fn execute(&self, context: &mut PipelineContext) -> Result<StageResult, CodegraphError> {
        let start = Instant::now();

        eprintln!("[L1] Starting IR Build");

        // Configure Rayon thread pool if specified
        if let Some(workers) = self.parallel_workers {
            rayon::ThreadPoolBuilder::new()
                .num_threads(workers)
                .build_global()
                .ok(); // Ignore if already initialized
        }

        // Discover files
        let files = self.discover_files(&context.repo_root)?;
        eprintln!("[L1] Discovered {} files", files.len());

        // Process files in parallel with Rayon
        let results: Vec<_> = files
            .par_iter()
            .filter_map(|file_path| {
                self.process_file(file_path, &context.repo_root, &context.repo_name)
            })
            .collect();

        // Aggregate results
        let mut all_nodes = Vec::new();
        let mut all_edges = Vec::new();
        let mut all_occurrences = Vec::new();

        for (nodes, edges, occurrences) in results {
            all_nodes.extend(nodes);
            all_edges.extend(edges);
            all_occurrences.extend(occurrences);
        }

        eprintln!(
            "[L1] Built IR: {} nodes, {} edges, {} occurrences",
            all_nodes.len(),
            all_edges.len(),
            all_occurrences.len()
        );

        // Store in context (Arc-wrapped automatically)
        context.set_nodes(all_nodes.clone());
        context.set_edges(all_edges.clone());
        context.set_occurrences(all_occurrences);

        let duration = start.elapsed();

        Ok(StageResult::success(
            StageId::L1IrBuild,
            duration,
            all_nodes.len(),
        ))
    }

    fn dependencies(&self) -> Vec<StageId> {
        vec![] // L1 has no dependencies
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_l1_executor_creation() {
        let executor = IRBuildExecutor::new(Some(4));
        assert_eq!(executor.stage_id(), StageId::L1IrBuild);
        assert_eq!(executor.dependencies().len(), 0);
    }
}
