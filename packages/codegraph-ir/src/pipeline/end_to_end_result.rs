//! End-to-End Pipeline Result Types
//!
//! Aggregated results from repository-wide SOTA pipeline execution (L1-L9)
//!
//! # Output Structure
//!
//! ```text
//! E2EPipelineResult
//! ├── Phase 1: Foundation
//! │   ├── nodes: Vec<Node>           (L1)
//! │   ├── edges: Vec<Edge>           (L1)
//! │   └── occurrences: Vec<Occurrence> (L1)
//! │
//! ├── Phase 2: Analysis
//! │   ├── chunks: Vec<Chunk>         (L2)
//! │   ├── cross_file: CrossFileContext (L3)
//! │   ├── cfg_edges: Vec<CFGEdge>    (L4)
//! │   ├── bfg_graphs: Vec<BFGSummary> (L4)
//! │   └── types: Vec<TypeSummary>    (L5)
//! │
//! ├── Phase 3: Advanced Analysis
//! │   ├── dfg_graphs: Vec<DFGSummary> (L6)
//! │   ├── ssa_graphs: Vec<SSASummary> (L7)
//! │   └── symbols: Vec<Symbol>       (L8)
//! │
//! └── Phase 4: Repository-Wide
//!     └── points_to_summary: PointsToSummary (L9)
//! ```

use crate::features::ir_generation::domain::IRDocument;
use crate::features::query_engine::QueryEngineStats;
use crate::pipeline::processor::PointsToSummary;
use crate::pipeline::stages::{PDGSummary, SliceSummary, TaintSummary};
use crate::shared::models::{Edge, Node, Occurrence};
use std::collections::HashMap;
use std::time::Duration;

/// Aggregated result from SOTA pipeline (L1-L9)
#[derive(Debug, Clone)]
pub struct E2EPipelineResult {
    // ═══════════════════════════════════════════════════════════════════
    // Phase 1: Foundation (L1)
    // ═══════════════════════════════════════════════════════════════════
    /// All IR nodes across repository
    pub nodes: Vec<Node>,

    /// All edges (calls, imports, etc.)
    pub edges: Vec<Edge>,

    /// All occurrences (SCIP-compatible)
    pub occurrences: Vec<Occurrence>,

    // ═══════════════════════════════════════════════════════════════════
    // Phase 2: Analysis (L2-L5)
    // ═══════════════════════════════════════════════════════════════════
    /// L2: All chunks for semantic search
    pub chunks: Vec<Chunk>,

    /// L3: Cross-file resolution context
    pub cross_file_context: Option<CrossFileContext>,

    /// L4: CFG edges per function
    pub cfg_edges: Vec<CFGEdgeSummary>,

    /// L4: Basic flow graphs per function
    pub bfg_graphs: Vec<BFGSummary>,

    /// L5: Type information per node
    pub types: Vec<TypeSummary>,

    // ═══════════════════════════════════════════════════════════════════
    // Phase 3: Advanced Analysis (L6-L8)
    // ═══════════════════════════════════════════════════════════════════
    /// L6: Data flow graphs per function
    pub dfg_graphs: Vec<DFGSummary>,

    /// L7: SSA graphs per function
    pub ssa_graphs: Vec<SSASummary>,

    /// L8: All symbols for navigation
    pub symbols: Vec<Symbol>,

    // ═══════════════════════════════════════════════════════════════════
    // Phase 4: Advanced Security & Analysis (L7-L9)
    // ═══════════════════════════════════════════════════════════════════
    /// L7: PDG (Program Dependence Graph) summaries per function
    pub pdg_graphs: Vec<PDGSummary>,

    /// L7: Taint analysis results per function
    pub taint_results: Vec<TaintSummary>,

    /// L7: Slicing results
    pub slice_results: Vec<SliceSummary>,

    /// L8: Memory safety issues (heap analysis)
    pub memory_safety_issues: Vec<MemorySafetyIssueSummary>,

    /// L8: Security vulnerabilities (deep security analysis)
    pub security_vulnerabilities: Vec<SecurityVulnerabilitySummary>,

    /// L8: Effect analysis results per function
    pub effect_results: Vec<EffectSummary>,

    /// L8: SMT verification results
    pub smt_results: Vec<SMTVerificationSummary>,

    /// L8: Clone detection results
    pub clone_pairs: Vec<ClonePairSummary>,

    /// L18: Concurrency analysis results (race conditions, deadlocks)
    pub concurrency_results: Vec<ConcurrencyIssueSummary>,

    /// L9: Points-to analysis summary (repository-wide)
    pub points_to_summary: Option<PointsToSummary>,

    // ═══════════════════════════════════════════════════════════════════
    // Phase 6: Performance & Quality Analysis
    // ═══════════════════════════════════════════════════════════════════
    /// L15: Cost analysis results per function (computational complexity)
    pub cost_analysis_results: Vec<CostAnalysisSummary>,

    // ═══════════════════════════════════════════════════════════════════
    // Phase 7: Repository Structure & Navigation
    // ═══════════════════════════════════════════════════════════════════
    /// L16: RepoMap snapshot (repository structure with importance scores)
    pub repomap_snapshot: Option<RepoMapSnapshotSummary>,

    /// L33: Git history analysis results (churn metrics, co-change patterns)
    pub git_history_results: Vec<GitHistorySummary>,

    // ═══════════════════════════════════════════════════════════════════
    // Phase 8: Unified Query Interface
    // ═══════════════════════════════════════════════════════════════════
    /// L37: Query engine statistics (unified query interface)
    pub query_engine_stats: Option<QueryEngineStats>,

    // ═══════════════════════════════════════════════════════════════════
    // Metadata
    // ═══════════════════════════════════════════════════════════════════
    /// Per-file IR documents (for debugging/inspection)
    pub ir_documents: HashMap<String, IRDocument>,

    /// Pipeline statistics
    pub stats: PipelineStats,
}

/// Chunk for semantic search
#[derive(Debug, Clone)]
pub struct Chunk {
    /// Chunk ID
    pub id: String,

    /// File path
    pub file_path: String,

    /// Chunk content
    pub content: String,

    /// Start line
    pub start_line: usize,

    /// End line
    pub end_line: usize,

    /// Chunk type (function, class, etc.)
    pub chunk_type: String,

    /// Associated symbol ID (if any)
    pub symbol_id: Option<String>,
}

/// Symbol for code navigation (L8)
#[derive(Debug, Clone)]
pub struct Symbol {
    /// Symbol ID (SCIP format)
    pub id: String,

    /// Symbol name
    pub name: String,

    /// Symbol kind (function, class, variable, etc.)
    pub kind: String,

    /// File path
    pub file_path: String,

    /// Definition location (line, column)
    pub definition: (usize, usize),

    /// Documentation string (if any)
    pub documentation: Option<String>,
}

// ═══════════════════════════════════════════════════════════════════════════
// Phase 2-3 Summary Types
// ═══════════════════════════════════════════════════════════════════════════

/// L3: Cross-file resolution context
#[derive(Debug, Clone, Default)]
pub struct CrossFileContext {
    /// File dependencies (file_path -> list of imported files)
    pub file_dependencies: HashMap<String, Vec<String>>,

    /// Symbol exports (file_path -> list of exported symbol IDs)
    pub symbol_exports: HashMap<String, Vec<String>>,

    /// Import resolutions (import_id -> resolved_symbol_id)
    pub import_resolutions: HashMap<String, String>,

    /// Number of unresolved imports
    pub unresolved_count: usize,
}

/// L4: CFG edge summary (lightweight for storage)
#[derive(Debug, Clone)]
pub struct CFGEdgeSummary {
    /// Function ID this edge belongs to
    pub function_id: String,

    /// Source block ID
    pub source_block: String,

    /// Target block ID
    pub target_block: String,

    /// Edge kind (e.g., "conditional", "unconditional", "true_branch", "false_branch")
    pub kind: String,
}

/// L4: Basic Flow Graph summary
#[derive(Debug, Clone)]
pub struct BFGSummary {
    /// Function ID
    pub function_id: String,

    /// File path
    pub file_path: String,

    /// Number of basic blocks
    pub block_count: usize,

    /// Number of edges
    pub edge_count: usize,

    /// Entry block ID
    pub entry_block: Option<String>,

    /// Exit block IDs
    pub exit_blocks: Vec<String>,

    /// Cyclomatic complexity
    pub cyclomatic_complexity: usize,
}

/// L5: Type summary for a node
#[derive(Debug, Clone)]
pub struct TypeSummary {
    /// Node ID this type belongs to
    pub node_id: String,

    /// Inferred type (e.g., "int", "str", "List[int]", "Optional[User]")
    pub inferred_type: String,

    /// Confidence score (0.0 - 1.0)
    pub confidence: f32,

    /// Type source (e.g., "annotation", "inference", "literal")
    pub source: String,
}

/// L6: Data Flow Graph summary
#[derive(Debug, Clone)]
pub struct DFGSummary {
    /// Function ID
    pub function_id: String,

    /// File path
    pub file_path: String,

    /// Number of def nodes
    pub def_count: usize,

    /// Number of use nodes
    pub use_count: usize,

    /// Number of def-use edges
    pub def_use_edges: usize,

    /// Variables tracked
    pub variables: Vec<String>,
}

/// L7: SSA Graph summary
#[derive(Debug, Clone)]
pub struct SSASummary {
    /// Function ID
    pub function_id: String,

    /// File path
    pub file_path: String,

    /// Number of SSA versions created
    pub version_count: usize,

    /// Number of phi nodes
    pub phi_node_count: usize,

    /// Variables with multiple definitions
    pub multi_def_variables: Vec<String>,
}

/// Pipeline execution statistics
#[derive(Debug, Clone, Default)]
pub struct PipelineStats {
    /// Total execution time
    pub total_duration: Duration,

    /// Per-stage durations
    pub stage_durations: HashMap<String, Duration>,

    /// Number of files processed
    pub files_processed: usize,

    /// Number of files cached
    pub files_cached: usize,

    /// Number of files failed
    pub files_failed: usize,

    /// Total lines of code processed
    pub total_loc: usize,

    /// Processing rate (LOC/s)
    pub loc_per_second: f64,

    /// Memory usage peak (bytes)
    pub peak_memory_bytes: usize,

    /// Cache hit rate (0.0-1.0)
    pub cache_hit_rate: f64,

    /// Per-file processing times (for debugging)
    pub file_times: HashMap<String, Duration>,

    /// Error messages
    pub errors: Vec<String>,
}

impl PipelineStats {
    /// Create new empty stats
    pub fn new() -> Self {
        Self::default()
    }

    /// Calculate LOC per second
    pub fn calculate_rate(&mut self) {
        let seconds = self.total_duration.as_secs_f64();
        if seconds > 0.0 {
            self.loc_per_second = self.total_loc as f64 / seconds;
        }
    }

    /// Calculate cache hit rate
    pub fn calculate_cache_hit_rate(&mut self) {
        if self.files_processed > 0 {
            self.cache_hit_rate = self.files_cached as f64 / self.files_processed as f64;
        }
    }

    /// Add an error message
    pub fn add_error(&mut self, error: String) {
        self.errors.push(error);
    }

    /// Record stage duration
    pub fn record_stage(&mut self, stage_name: impl Into<String>, duration: Duration) {
        self.stage_durations.insert(stage_name.into(), duration);
    }

    /// Record file processing time
    pub fn record_file(&mut self, file_path: impl Into<String>, duration: Duration) {
        self.file_times.insert(file_path.into(), duration);
    }
}

impl E2EPipelineResult {
    /// Create empty result
    pub fn new() -> Self {
        Self {
            nodes: Vec::new(),
            edges: Vec::new(),
            chunks: Vec::new(),
            symbols: Vec::new(),
            occurrences: Vec::new(),
            cross_file_context: None,
            cfg_edges: Vec::new(),
            bfg_graphs: Vec::new(),
            types: Vec::new(),
            dfg_graphs: Vec::new(),
            ssa_graphs: Vec::new(),
            pdg_graphs: Vec::new(),
            taint_results: Vec::new(),
            slice_results: Vec::new(),
            memory_safety_issues: Vec::new(),
            security_vulnerabilities: Vec::new(),
            effect_results: Vec::new(),
            smt_results: Vec::new(),
            clone_pairs: Vec::new(),
            concurrency_results: Vec::new(),
            cost_analysis_results: Vec::new(),
            ir_documents: HashMap::new(),
            points_to_summary: None,
            repomap_snapshot: None,          // L16 RepoMap
            git_history_results: Vec::new(), // L33 Git History
            query_engine_stats: None,        // L37 Query Engine
            stats: PipelineStats::new(),
        }
    }

    /// Get total number of entities
    pub fn total_entities(&self) -> usize {
        self.nodes.len() + self.edges.len() + self.chunks.len() + self.symbols.len()
    }

    /// Print summary
    pub fn summary(&self) -> String {
        format!(
            "Pipeline Result: {} files, {} nodes, {} edges, {} chunks, {} symbols, {} occurrences ({:.1} LOC/s)",
            self.stats.files_processed,
            self.nodes.len(),
            self.edges.len(),
            self.chunks.len(),
            self.symbols.len(),
            self.occurrences.len(),
            self.stats.loc_per_second
        )
    }
}

impl Default for E2EPipelineResult {
    fn default() -> Self {
        Self::new()
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Phase 4: Advanced Security & Analysis Summary Types
// ═══════════════════════════════════════════════════════════════════════════

/// Memory safety issue summary (from heap analysis)
#[derive(Debug, Clone)]
pub struct MemorySafetyIssueSummary {
    /// Issue type (e.g., "UseAfterFree", "DoubleFree", "MemoryLeak")
    pub issue_type: String,
    /// File path
    pub file_path: String,
    /// Function where issue was found
    pub function_id: String,
    /// Line number
    pub line: u32,
    /// Severity (Low, Medium, High, Critical)
    pub severity: String,
    /// Description
    pub description: String,
}

/// Security vulnerability summary (from deep security analysis)
#[derive(Debug, Clone)]
pub struct SecurityVulnerabilitySummary {
    /// Vulnerability type (e.g., "SQLInjection", "XSS", "CommandInjection")
    pub vuln_type: String,
    /// CWE ID (if applicable)
    pub cwe_id: Option<String>,
    /// File path
    pub file_path: String,
    /// Function where vulnerability was found
    pub function_id: String,
    /// Line number
    pub line: u32,
    /// Severity (Low, Medium, High, Critical)
    pub severity: String,
    /// Description
    pub description: String,
    /// Suggested fix
    pub suggested_fix: Option<String>,
}

/// Effect analysis summary
#[derive(Debug, Clone)]
pub struct EffectSummary {
    /// Function ID
    pub function_id: String,
    /// File path
    pub file_path: String,
    /// Effect types detected (e.g., ["Pure", "IO", "StateWrite"])
    pub effects: Vec<String>,
    /// Is pure function (no side effects)
    pub is_pure: bool,
    /// Confidence score (0.0 - 1.0)
    pub confidence: f32,
}

/// SMT verification summary
#[derive(Debug, Clone)]
pub struct SMTVerificationSummary {
    /// Function ID
    pub function_id: String,
    /// File path
    pub file_path: String,
    /// Verification result (Verified, Failed, Unknown, Timeout)
    pub result: String,
    /// Number of assertions checked
    pub assertions_checked: usize,
    /// Number of assertions proven
    pub assertions_proven: usize,
    /// Verification time (milliseconds)
    pub verification_time_ms: u64,
    /// Counterexample (if verification failed)
    pub counterexample: Option<String>,
}

/// Clone pair summary (from clone detection)
#[derive(Debug, Clone)]
pub struct ClonePairSummary {
    /// Clone type (Type1, Type2, Type3, Type4)
    pub clone_type: String,
    /// Source code fragment
    pub source_file: String,
    pub source_start_line: u32,
    pub source_end_line: u32,
    /// Target code fragment
    pub target_file: String,
    pub target_start_line: u32,
    pub target_end_line: u32,
    /// Similarity score (0.0 - 1.0)
    pub similarity: f32,
    /// Number of tokens
    pub token_count: usize,
    /// Lines of code
    pub loc: usize,
}

/// L15: Cost analysis summary (computational complexity)
#[derive(Debug, Clone)]
pub struct CostAnalysisSummary {
    /// Function ID (FQN)
    pub function_id: String,

    /// File path
    pub file_path: String,

    /// Complexity class (O(1), O(n), O(n²), etc.)
    pub complexity: String,

    /// Verdict (Proven/Likely/Heuristic/Unknown)
    pub verdict: String,

    /// Confidence score (0.0 - 1.0)
    pub confidence: f64,

    /// Human-readable explanation
    pub explanation: String,

    /// Number of loops detected
    pub loop_count: usize,

    /// Cost term (symbolic expression: "n", "n * m", etc.)
    pub cost_term: String,
}

// ═══════════════════════════════════════════════════════════════════════════
// Phase 7: Repository Structure & Navigation Summary Types
// ═══════════════════════════════════════════════════════════════════════════

/// RepoMap snapshot summary (from L16)
#[derive(Debug, Clone)]
pub struct RepoMapSnapshotSummary {
    /// Repository ID
    pub repo_id: String,

    /// Snapshot ID (version/commit hash)
    pub snapshot_id: String,

    /// Total number of nodes in the tree
    pub total_nodes: usize,

    /// Root node ID
    pub root_id: String,

    /// Nodes with their importance scores
    pub nodes: Vec<RepoMapNodeSummary>,

    /// Total metrics (aggregated)
    pub total_loc: usize,
    pub total_symbols: usize,
    pub total_files: usize,

    /// Snapshot creation timestamp
    pub created_at: u64,
}

/// RepoMap node summary
#[derive(Debug, Clone)]
pub struct RepoMapNodeSummary {
    /// Node ID
    pub id: String,

    /// Node type (Repository, Directory, File, Class, Function)
    pub kind: String,

    /// Node name
    pub name: String,

    /// Full path
    pub path: String,

    /// Parent ID (None for root)
    pub parent_id: Option<String>,

    /// Number of children
    pub children_count: usize,

    /// Tree depth (root = 0)
    pub depth: usize,

    /// Importance scores
    pub pagerank: f64,
    pub authority: f64,
    pub hub: f64,
    pub combined_importance: f64,

    /// Basic metrics
    pub loc: usize,
    pub symbol_count: usize,
}

/// Concurrency issue summary (L18: Concurrency Analysis)
#[derive(Debug, Clone)]
pub struct ConcurrencyIssueSummary {
    /// Issue type (RaceCondition, Deadlock, etc.)
    pub issue_type: String,

    /// Shared variable name
    pub shared_variable: String,

    /// File path
    pub file_path: String,

    /// Function name
    pub function_name: String,

    /// First access line
    pub access1_line: u32,

    /// Second access line
    pub access2_line: u32,

    /// Severity (Critical, High, Medium, Low)
    pub severity: String,

    /// Verdict (Proven, Likely, Possible)
    pub verdict: String,

    /// Proof trace (human-readable explanation)
    pub proof_trace: String,

    /// Fix suggestion
    pub fix_suggestion: String,
}

/// Git history summary (L33: Git History)
#[derive(Debug, Clone)]
pub struct GitHistorySummary {
    /// File path
    pub file_path: String,

    /// Total number of commits modifying this file
    pub total_commits: u32,

    /// Total lines added across all commits
    pub total_additions: u32,

    /// Total lines deleted across all commits
    pub total_deletions: u32,

    /// Churn rate (changes per day)
    pub churn_rate: f64,

    /// Commit frequency (commits per week)
    pub commit_frequency: f64,

    /// Days between first and last commit
    pub days_active: u32,
}
