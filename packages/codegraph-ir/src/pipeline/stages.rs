//! Pipeline Stages Implementations
//!
//! Defines the three specialized pipeline configurations:
//! 1. SingleFileStages - L1-L6 analysis (ProcessResult)
//! 2. RepositoryStages - L1-L5 indexing (E2EPipelineResult)
//! 3. IncrementalStages - L1-L3 incremental (LayeredResult)

use super::core::{PipelineStages, PipelineType};
use std::collections::HashMap as AHashMap;

// Type imports for single file pipeline
use crate::features::data_flow::domain::DataFlowGraph;
use crate::features::flow_graph::domain::{BasicFlowGraph, CFGEdge};
use crate::features::ssa::domain::SSAGraph;
use crate::features::type_resolution::domain::type_entity::TypeEntity;
use crate::shared::models::Occurrence;
use crate::shared::models::{Edge, Node};

// Type imports for repository pipeline
use crate::features::ir_generation::domain::IRDocument;
use crate::shared::models::{Edge as SharedEdge, Node as SharedNode};

// Type imports for incremental pipeline
use crate::features::chunking::domain::Chunk as DomainChunk;
use crate::features::chunking::infrastructure::ChunkStore;
use crate::features::cross_file::GlobalContextResult;
// Node/Edge aliases removed - using shared::models directly

// ═══════════════════════════════════════════════════════════════════════════
// 1. Single File Pipeline (L1-L6)
// ═══════════════════════════════════════════════════════════════════════════

/// PDG summary for Python serialization
#[derive(Debug, Clone)]
pub struct PDGSummary {
    pub function_id: String,
    pub node_count: usize,
    pub control_edges: usize,
    pub data_edges: usize,
}

/// Taint analysis summary
#[derive(Debug, Clone)]
pub struct TaintSummary {
    pub function_id: String,
    pub sources_found: usize,
    pub sinks_found: usize,
    pub taint_flows: usize,
}

/// Slice summary
#[derive(Debug, Clone)]
pub struct SliceSummary {
    pub function_id: String,
    pub criterion: String,
    pub slice_size: usize,
}

/// Single file pipeline stages (L1-L6 complete analysis)
///
/// Outputs:
/// - L1-L2: IR (nodes, edges, occurrences)
/// - L3: Flow + Types (BFG, CFG, TypeEntity)
/// - L4-L5: Data Flow + SSA (DFG, SSA)
/// - L6: Advanced Analysis (PDG, Taint, Slice)
pub struct SingleFileStages;

impl PipelineStages for SingleFileStages {
    type Outputs = SingleFileOutputs;

    fn empty() -> Self::Outputs {
        SingleFileOutputs {
            nodes: Vec::new(),
            edges: Vec::new(),
            occurrences: Vec::new(),
            bfg_graphs: Vec::new(),
            cfg_edges: Vec::new(),
            type_entities: Vec::new(),
            dfg_graphs: Vec::new(),
            ssa_graphs: Vec::new(),
            pdg_graphs: Vec::new(),
            taint_results: Vec::new(),
            slice_results: Vec::new(),
        }
    }

    fn stage_names() -> &'static [&'static str] {
        &[
            "L1_IR",
            "L1_Occurrences",
            "L3_Flow",
            "L3_Types",
            "L4_DFG",
            "L5_SSA",
            "L6_PDG",
            "L6_Taint",
            "L6_Slice",
        ]
    }

    fn pipeline_type() -> PipelineType {
        PipelineType::SingleFile
    }
}

/// Single file outputs (replaces ProcessResult fields)
#[derive(Debug, Clone)]
pub struct SingleFileOutputs {
    // L1-L2: IR
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub occurrences: Vec<Occurrence>,

    // L3: Flow + Types
    pub bfg_graphs: Vec<BasicFlowGraph>,
    pub cfg_edges: Vec<CFGEdge>,
    pub type_entities: Vec<TypeEntity>,

    // L4-L5: Data Flow + SSA
    pub dfg_graphs: Vec<DataFlowGraph>,
    pub ssa_graphs: Vec<SSAGraph>,

    // L6: Advanced Analysis
    pub pdg_graphs: Vec<PDGSummary>,
    pub taint_results: Vec<TaintSummary>,
    pub slice_results: Vec<SliceSummary>,
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. Repository Pipeline (L1-L5)
// ═══════════════════════════════════════════════════════════════════════════

/// Chunk for semantic search
#[derive(Debug, Clone)]
pub struct Chunk {
    pub id: String,
    pub file_path: String,
    pub content: String,
    pub start_line: usize,
    pub end_line: usize,
    pub chunk_type: String,
    pub symbol_id: Option<String>,
}

/// Symbol for code navigation
#[derive(Debug, Clone)]
pub struct Symbol {
    pub id: String,
    pub name: String,
    pub kind: String,
    pub file_path: String,
    pub definition: (usize, usize),
    pub documentation: Option<String>,
}

/// Repository pipeline stages (L1-L5 indexing)
///
/// Outputs:
/// - L1: IR (nodes, edges)
/// - L2: Chunks
/// - L3: Cross-file (GlobalContext)
/// - L4: Occurrences (SCIP)
/// - L5: Symbols
#[derive(Debug, Clone)]
pub struct RepositoryStages;

impl PipelineStages for RepositoryStages {
    type Outputs = RepositoryOutputs;

    fn empty() -> Self::Outputs {
        RepositoryOutputs {
            nodes: Vec::new(),
            edges: Vec::new(),
            chunks: Vec::new(),
            symbols: Vec::new(),
            occurrences: Vec::new(),
            ir_documents: AHashMap::new(),
            bfg_graphs: Vec::new(),
            cfg_edges: Vec::new(),
            type_entities: Vec::new(),
            dfg_graphs: Vec::new(),
            ssa_graphs: Vec::new(),
            pdg_graphs: Vec::new(),
            taint_results: Vec::new(),
            slice_results: Vec::new(),
        }
    }

    fn stage_names() -> &'static [&'static str] {
        &[
            "L1_IR",
            "L2_Chunk",
            "L3_CrossFile",
            "L4_Occurrences",
            "L5_Symbols",
        ]
    }

    fn pipeline_type() -> PipelineType {
        PipelineType::Repository
    }
}

/// Repository outputs (replaces E2EPipelineResult fields)
#[derive(Debug, Clone)]
pub struct RepositoryOutputs {
    // L1-L2: IR
    pub nodes: Vec<SharedNode>,
    pub edges: Vec<SharedEdge>,
    pub chunks: Vec<Chunk>,
    pub symbols: Vec<Symbol>,
    pub occurrences: Vec<Occurrence>,
    pub ir_documents: AHashMap<String, IRDocument>,

    // L3-L5: SemanticIR (from SingleFileOutputs aggregation)
    pub bfg_graphs: Vec<BasicFlowGraph>,
    pub cfg_edges: Vec<CFGEdge>,
    pub type_entities: Vec<TypeEntity>,
    pub dfg_graphs: Vec<DataFlowGraph>,
    pub ssa_graphs: Vec<SSAGraph>,

    // L6: Advanced Analysis
    pub pdg_graphs: Vec<PDGSummary>,
    pub taint_results: Vec<TaintSummary>,
    pub slice_results: Vec<SliceSummary>,
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. Incremental Pipeline (L1-L3)
// ═══════════════════════════════════════════════════════════════════════════

/// Incremental pipeline stages (L1-L3 with persistent storage)
///
/// Outputs:
/// - L1: IR (Node, Edge) - IR Builder output types
/// - L2: Chunks
/// - L3: GlobalContext (cross-file resolution)
/// - P0-2: ChunkStore (persistent chunk storage for incremental updates)
pub struct IncrementalStages;

impl PipelineStages for IncrementalStages {
    type Outputs = IncrementalOutputs;

    fn empty() -> Self::Outputs {
        IncrementalOutputs {
            nodes: Vec::new(),
            edges: Vec::new(),
            chunks: Vec::new(),
            global_context: GlobalContextResult::default(),
            bfg_graphs: Vec::new(),
            dfg_graphs: Vec::new(),
            ssa_graphs: Vec::new(),
            chunk_store: ChunkStore::new(),
            chunk_count_by_kind: AHashMap::new(),
        }
    }

    fn stage_names() -> &'static [&'static str] {
        &["L1_IR", "L2_Chunk", "L3_CrossFile"]
    }

    fn pipeline_type() -> PipelineType {
        PipelineType::Incremental
    }
}

/// Incremental outputs (replaces LayeredResult fields)
#[derive(Debug, Clone)]
pub struct IncrementalOutputs {
    // L1: IR (codegraph_core types from IR Builder)
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,

    // L2: Chunks
    pub chunks: Vec<DomainChunk>,
    pub chunk_count_by_kind: AHashMap<String, usize>,

    // L3: Cross-file resolution
    pub global_context: GlobalContextResult,

    // L4: Flow graphs (preserved for incremental updates)
    pub bfg_graphs: Vec<BasicFlowGraph>,
    pub dfg_graphs: Vec<DataFlowGraph>,
    pub ssa_graphs: Vec<SSAGraph>,

    // P0-2: Persistent chunk storage (for incremental updates)
    pub chunk_store: ChunkStore,
}

// ═══════════════════════════════════════════════════════════════════════════
// Helper Implementations
// ═══════════════════════════════════════════════════════════════════════════

impl SingleFileOutputs {
    /// Get total count of all graph structures
    pub fn total_graph_count(&self) -> usize {
        self.bfg_graphs.len()
            + self.cfg_edges.len()
            + self.dfg_graphs.len()
            + self.ssa_graphs.len()
            + self.pdg_graphs.len()
    }

    /// Get total count of all entities
    pub fn total_entity_count(&self) -> usize {
        self.nodes.len() + self.edges.len() + self.occurrences.len()
    }
}

impl RepositoryOutputs {
    /// Get total count of all entities
    pub fn total_entity_count(&self) -> usize {
        self.nodes.len()
            + self.edges.len()
            + self.chunks.len()
            + self.symbols.len()
            + self.occurrences.len()
    }

    /// Get summary string
    pub fn summary(&self) -> String {
        format!(
            "{} nodes, {} edges, {} chunks, {} symbols, {} occurrences",
            self.nodes.len(),
            self.edges.len(),
            self.chunks.len(),
            self.symbols.len(),
            self.occurrences.len()
        )
    }
}

impl IncrementalOutputs {
    /// Get total chunk count
    pub fn total_chunks(&self) -> usize {
        self.chunks.len()
    }

    /// Get summary by chunk kind
    pub fn chunk_summary(&self) -> String {
        let mut parts: Vec<String> = self
            .chunk_count_by_kind
            .iter()
            .map(|(kind, count)| format!("{}: {}", kind, count))
            .collect();
        parts.sort();
        parts.join(", ")
    }
}
