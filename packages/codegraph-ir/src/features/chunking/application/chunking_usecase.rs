//! Chunking UseCase Implementation
//!
//! Provides the application layer interface for chunking operations.
//! This is the ONLY entry point for external callers.
//!
//! # Architecture
//! ```text
//! Pipeline/Adapters
//!        ↓
//! ChunkingUseCase (this module)
//!        ↓
//! ChunkBuilder (infrastructure)
//!        ↓
//! Chunk (domain)
//! ```

use std::collections::HashMap;

use crate::features::chunking::domain::{
    Chunk, ChunkIdGenerator, ChunkKind, ChunkToGraph, ChunkToIR,
};
use crate::features::chunking::infrastructure::ChunkBuilder;
use crate::shared::models::Node;

/// Input for building chunks
#[derive(Debug, Clone)]
pub struct BuildChunksInput<'a> {
    /// Repository identifier
    pub repo_id: &'a str,
    /// File path relative to repo root
    pub file_path: &'a str,
    /// Programming language (e.g., "python", "rust")
    pub language: &'a str,
    /// IR nodes from IR builder
    pub ir_nodes: &'a [Node],
    /// Source code lines
    pub file_text: &'a [String],
    /// Git commit hash or timestamp (optional)
    pub snapshot_id: Option<&'a str>,
}

/// Output from building chunks
#[derive(Debug, Clone)]
pub struct BuildChunksOutput {
    /// Generated chunks (hierarchical)
    pub chunks: Vec<Chunk>,
    /// Mapping: ChunkId → IRNodeIds
    pub chunk_to_ir: ChunkToIR,
    /// Mapping: ChunkId → GraphNodeIds
    pub chunk_to_graph: ChunkToGraph,
    /// Statistics
    pub stats: ChunkingStats,
}

/// Chunking statistics
#[derive(Debug, Clone, Default)]
pub struct ChunkingStats {
    pub total_chunks: usize,
    pub repo_chunks: usize,
    pub project_chunks: usize,
    pub module_chunks: usize,
    pub file_chunks: usize,
    pub class_chunks: usize,
    pub function_chunks: usize,
    pub docstring_chunks: usize,
    pub skeleton_chunks: usize,
    pub constant_chunks: usize,
    pub variable_chunks: usize,
}

impl ChunkingStats {
    fn from_chunks(chunks: &[Chunk]) -> Self {
        let mut stats = Self::default();
        stats.total_chunks = chunks.len();

        for chunk in chunks {
            match chunk.kind {
                ChunkKind::Repo => stats.repo_chunks += 1,
                ChunkKind::Project => stats.project_chunks += 1,
                ChunkKind::Module => stats.module_chunks += 1,
                ChunkKind::File => stats.file_chunks += 1,
                ChunkKind::Class => stats.class_chunks += 1,
                ChunkKind::Function => stats.function_chunks += 1,
                ChunkKind::Docstring => stats.docstring_chunks += 1,
                ChunkKind::Skeleton => stats.skeleton_chunks += 1,
                ChunkKind::Constant => stats.constant_chunks += 1,
                ChunkKind::Variable => stats.variable_chunks += 1,
                _ => {}
            }
        }

        stats
    }
}

/// Chunking UseCase Trait (Port)
///
/// This trait defines the contract for chunking operations.
/// External callers should depend on this trait, not on concrete implementations.
pub trait ChunkingUseCase: Send + Sync {
    /// Build chunks from IR nodes
    ///
    /// This is the main entry point for chunking.
    /// It builds a hierarchical chunk structure from IR nodes.
    ///
    /// # Arguments
    /// * `input` - Build chunks input containing repo_id, file_path, ir_nodes, etc.
    ///
    /// # Returns
    /// * `BuildChunksOutput` - Generated chunks and mappings
    fn build_chunks(&self, input: BuildChunksInput) -> BuildChunksOutput;

    /// Build chunks for multiple files (batch)
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `files` - List of (file_path, language, ir_nodes, file_text)
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// * `BuildChunksOutput` - Aggregated chunks from all files
    fn build_chunks_batch(
        &self,
        repo_id: &str,
        files: Vec<(&str, &str, &[Node], &[String])>,
        snapshot_id: Option<&str>,
    ) -> BuildChunksOutput;
}

/// Chunking UseCase Implementation
///
/// Wraps `ChunkBuilder` and provides a clean interface for external callers.
///
/// **RFC-001 Config Integration**: Accepts ChunkingConfig for chunk size settings.
#[derive(Debug)]
pub struct ChunkingUseCaseImpl {
    id_gen: ChunkIdGenerator,
    config: crate::config::stage_configs::ChunkingConfig,
}

impl Default for ChunkingUseCaseImpl {
    fn default() -> Self {
        Self::new()
    }
}

impl ChunkingUseCaseImpl {
    /// Create a new ChunkingUseCase with default config
    pub fn new() -> Self {
        Self {
            id_gen: ChunkIdGenerator::new(),
            config: crate::config::stage_configs::ChunkingConfig::from_preset(
                crate::config::preset::Preset::Balanced
            ),
        }
    }

    /// Create with specific ChunkingConfig
    pub fn with_config(config: crate::config::stage_configs::ChunkingConfig) -> Self {
        Self {
            id_gen: ChunkIdGenerator::new(),
            config,
        }
    }

    /// Create from preset
    pub fn from_preset(preset: crate::config::preset::Preset) -> Self {
        Self::with_config(crate::config::stage_configs::ChunkingConfig::from_preset(preset))
    }

    /// Create with custom ID generator
    pub fn with_id_generator(id_gen: ChunkIdGenerator) -> Self {
        Self {
            id_gen,
            config: crate::config::stage_configs::ChunkingConfig::from_preset(
                crate::config::preset::Preset::Balanced
            ),
        }
    }

    /// Get current config
    pub fn config(&self) -> &crate::config::stage_configs::ChunkingConfig {
        &self.config
    }
}

impl ChunkingUseCase for ChunkingUseCaseImpl {
    fn build_chunks(&self, input: BuildChunksInput) -> BuildChunksOutput {
        eprintln!(
            "[ChunkingUseCase] Config: max_size={}, min_size={}, overlap={}, semantic={}",
            self.config.max_chunk_size,
            self.config.min_chunk_size,
            self.config.overlap_lines,
            self.config.enable_semantic
        );

        let mut builder = ChunkBuilder::new(self.id_gen.clone());

        let (chunks, chunk_to_ir, chunk_to_graph) = builder.build_with_ir(
            input.repo_id,
            input.file_path,
            input.language,
            input.ir_nodes,
            input.file_text,
            input.snapshot_id,
        );

        let stats = ChunkingStats::from_chunks(&chunks);

        BuildChunksOutput {
            chunks,
            chunk_to_ir,
            chunk_to_graph,
            stats,
        }
    }

    fn build_chunks_batch(
        &self,
        repo_id: &str,
        files: Vec<(&str, &str, &[Node], &[String])>,
        snapshot_id: Option<&str>,
    ) -> BuildChunksOutput {
        let mut all_chunks = Vec::new();
        let mut all_chunk_to_ir: ChunkToIR = HashMap::new();
        let mut all_chunk_to_graph: ChunkToGraph = HashMap::new();

        for (file_path, language, ir_nodes, file_text) in files {
            let input = BuildChunksInput {
                repo_id,
                file_path,
                language,
                ir_nodes,
                file_text,
                snapshot_id,
            };

            let output = self.build_chunks(input);

            // Skip repo/project chunks after first file to avoid duplicates
            let chunks_to_add: Vec<_> = if all_chunks.is_empty() {
                output.chunks
            } else {
                output
                    .chunks
                    .into_iter()
                    .filter(|c| !matches!(c.kind, ChunkKind::Repo | ChunkKind::Project))
                    .collect()
            };

            all_chunks.extend(chunks_to_add);
            all_chunk_to_ir.extend(output.chunk_to_ir);
            all_chunk_to_graph.extend(output.chunk_to_graph);
        }

        let stats = ChunkingStats::from_chunks(&all_chunks);

        BuildChunksOutput {
            chunks: all_chunks,
            chunk_to_ir: all_chunk_to_ir,
            chunk_to_graph: all_chunk_to_graph,
            stats,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{NodeKind, Span};

    fn create_test_node(
        id: &str,
        kind: NodeKind,
        fqn: &str,
        file_path: &str,
        span: Span,
        name: Option<&str>,
    ) -> Node {
        Node {
            id: id.to_string(),
            kind,
            fqn: fqn.to_string(),
            file_path: file_path.to_string(),
            span,
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: name.map(|s| s.to_string()),
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }
    }

    #[test]
    fn test_build_chunks_usecase() {
        let usecase = ChunkingUseCaseImpl::new();

        let ir_nodes = vec![
            create_test_node(
                "n1",
                NodeKind::Function,
                "mymodule.hello",
                "mymodule.py",
                Span::new(1, 0, 5, 0),
                Some("hello"),
            ),
            create_test_node(
                "n2",
                NodeKind::Variable,
                "mymodule.MAX_SIZE",
                "mymodule.py",
                Span::new(6, 0, 6, 20),
                Some("MAX_SIZE"),
            ),
        ];

        let file_text = vec![
            "def hello():".to_string(),
            "    print('hello')".to_string(),
            "".to_string(),
            "".to_string(),
            "".to_string(),
            "MAX_SIZE = 100".to_string(),
        ];

        let input = BuildChunksInput {
            repo_id: "test-repo",
            file_path: "mymodule.py",
            language: "python",
            ir_nodes: &ir_nodes,
            file_text: &file_text,
            snapshot_id: Some("abc123"),
        };

        let output = usecase.build_chunks(input);

        // Verify stats
        assert!(output.stats.total_chunks > 0);
        assert_eq!(output.stats.repo_chunks, 1);
        assert_eq!(output.stats.file_chunks, 1);
        assert_eq!(output.stats.function_chunks, 1);
        assert_eq!(output.stats.constant_chunks, 1);

        // Verify chunks exist
        assert!(!output.chunks.is_empty());

        // Verify mapping
        assert!(!output.chunk_to_ir.is_empty());
    }

    #[test]
    fn test_build_chunks_batch() {
        let usecase = ChunkingUseCaseImpl::new();

        let ir_nodes1 = vec![create_test_node(
            "n1",
            NodeKind::Function,
            "mod1.func1",
            "mod1.py",
            Span::new(1, 0, 3, 0),
            Some("func1"),
        )];

        let ir_nodes2 = vec![create_test_node(
            "n2",
            NodeKind::Function,
            "mod2.func2",
            "mod2.py",
            Span::new(1, 0, 3, 0),
            Some("func2"),
        )];

        let file_text1 = vec!["def func1(): pass".to_string()];
        let file_text2 = vec!["def func2(): pass".to_string()];

        let files = vec![
            ("mod1.py", "python", ir_nodes1.as_slice(), file_text1.as_slice()),
            ("mod2.py", "python", ir_nodes2.as_slice(), file_text2.as_slice()),
        ];

        let output = usecase.build_chunks_batch("test-repo", files, Some("abc123"));

        // Only 1 repo chunk (not duplicated)
        assert_eq!(output.stats.repo_chunks, 1);

        // 2 file chunks (one per file)
        assert_eq!(output.stats.file_chunks, 2);

        // 2 function chunks (one per file)
        assert_eq!(output.stats.function_chunks, 2);
    }

    #[test]
    fn test_empty_input() {
        let usecase = ChunkingUseCaseImpl::new();

        let ir_nodes: Vec<Node> = vec![];
        let file_text: Vec<String> = vec![];

        let input = BuildChunksInput {
            repo_id: "test-repo",
            file_path: "empty.py",
            language: "python",
            ir_nodes: &ir_nodes,
            file_text: &file_text,
            snapshot_id: None,
        };

        let output = usecase.build_chunks(input);

        // Should still have structural chunks (repo, project, module, file)
        assert!(output.stats.repo_chunks >= 1);
        assert!(output.stats.file_chunks >= 1);

        // No symbol chunks
        assert_eq!(output.stats.function_chunks, 0);
        assert_eq!(output.stats.class_chunks, 0);
    }
}
