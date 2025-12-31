//! L7: Heap Analysis - Memory Safety & Security & Escape Analysis
//!
//! Now uses Hexagonal Architecture with HeapAnalysisService.
//!
//! This stage handles:
//! - Memory safety analysis (use-after-free, double-free, buffer overflow, spatial safety)
//! - Security vulnerability detection (injection, XSS, etc.)
//! - Escape analysis (determines if objects escape their allocation context)
//! - Ownership tracking (Rust-style use-after-move, borrow conflicts)
//!
//! # Architecture (Hexagonal)
//! - `HeapAnalysisService` orchestrates all analyzers via port interfaces
//! - Infrastructure adapters bridge legacy implementations to ports
//! - Config-driven: HeapConfig controls which analyzers run
//!
//! # Functions
//! - `run_heap_analysis()` - Legacy tuple API (backward compatible)
//! - `run_heap_analysis_full()` - Full result struct
//! - `run_heap_analysis_with_config()` - Hexagonal service with config
//!
//! # SOLID Compliance
//! - D: Pipeline depends on HeapAnalysisService, not concrete analyzers
//! - O: New analyzers added via port implementations

use crate::config::{HeapConfig, Preset};
use crate::features::heap_analysis::{
    // Hexagonal architecture
    HeapAnalysisService,
    NullCheckerAdapter, UAFCheckerAdapter, DoubleFreeCheckerAdapter,
    BufferOverflowCheckerAdapter, SpatialCheckerAdapter,
    EscapeAnalyzerAdapter, OwnershipAnalyzerAdapter, SecurityAnalyzerAdapter,
    // Legacy (for backward compatibility)
    DeepSecurityAnalyzer, EscapeAnalyzer, EscapeNode, FunctionEscapeInfo, MemorySafetyAnalyzer,
    MemorySafetyIssue, OwnershipAnalyzer, OwnershipViolation, SecurityVulnerability,
};
use crate::shared::models::{Edge, EdgeKind, Node};
use std::collections::{HashMap, HashSet};

/// Heap Analysis Result - comprehensive heap analysis results
#[derive(Debug, Clone, Default)]
pub struct HeapAnalysisResult {
    /// Memory safety issues (null, UAF, double-free, buffer overflow)
    pub memory_issues: Vec<MemorySafetyIssue>,

    /// Security vulnerabilities
    pub security_vulnerabilities: Vec<SecurityVulnerability>,

    /// Escape analysis per function
    pub escape_info: Vec<FunctionEscapeInfo>,

    /// Ownership violations (use-after-move, borrow conflicts)
    pub ownership_violations: Vec<OwnershipViolation>,
}

/// Run heap analysis - memory safety + security + escape + ownership (L7)
///
/// Combines four SOTA analyzers:
/// 1. MemorySafetyAnalyzer - detects memory issues (null, UAF, double-free, buffer overflow)
/// 2. DeepSecurityAnalyzer - detects security vulnerabilities
/// 3. EscapeAnalyzer - determines object escape behavior (RFC-074)
/// 4. OwnershipAnalyzer - Rust-style ownership tracking (use-after-move, borrow conflicts)
///
/// # Early Exit
/// Skips analysis if fewer than 3 nodes (not worth overhead)
///
/// # Arguments
/// * `nodes` - IR nodes
/// * `edges` - IR edges (now used for DFG-based defs/uses extraction)
///
/// # Returns
/// Tuple of (memory_issues, security_vulnerabilities, escape_info_per_function)
///
/// # RFC-074 Integration
/// Escape analysis results can be used by concurrency analyzer to reduce FP by 40-60%:
/// - NoEscape/ArgEscape → No race condition possible
/// - ThreadEscape/GlobalEscape → Requires race detection
///
/// # DFG Integration
/// Now extracts defs/uses from Edge relationships:
/// - EdgeKind::Defines/Writes → defs
/// - EdgeKind::Reads/DefUse → uses
pub fn run_heap_analysis(
    nodes: &[Node],
    edges: &[Edge],
) -> (
    Vec<MemorySafetyIssue>,
    Vec<SecurityVulnerability>,
    Vec<FunctionEscapeInfo>,
) {
    let result = run_heap_analysis_full(nodes, edges);
    (
        result.memory_issues,
        result.security_vulnerabilities,
        result.escape_info,
    )
}

/// Run full heap analysis including ownership tracking
///
/// Returns comprehensive HeapAnalysisResult with all analysis types.
pub fn run_heap_analysis_full(nodes: &[Node], edges: &[Edge]) -> HeapAnalysisResult {
    // Skip if too few nodes
    if nodes.len() < 3 {
        return HeapAnalysisResult::default();
    }

    // Memory Safety Analysis with Spatial Memory Safety (edge-based bounds checking)
    let mut memory_analyzer = MemorySafetyAnalyzer::new();
    let memory_issues = memory_analyzer.analyze_with_edges(nodes, edges);

    // Security Analysis
    let mut security_analyzer = DeepSecurityAnalyzer::new();
    let security_vulnerabilities = security_analyzer.analyze(nodes, edges);

    // Escape Analysis (RFC-074 Phase 1) - now with DFG integration
    let escape_analyzer = EscapeAnalyzer::new();
    let escape_info = run_escape_analysis_per_function(&escape_analyzer, nodes, edges);

    // Ownership Analysis (Rust-style memory safety)
    let mut ownership_analyzer = OwnershipAnalyzer::new();
    let ownership_violations = ownership_analyzer.analyze(nodes, edges);

    HeapAnalysisResult {
        memory_issues,
        security_vulnerabilities,
        escape_info,
        ownership_violations,
    }
}

/// Run heap analysis with Hexagonal Architecture and config (RECOMMENDED)
///
/// This is the preferred entry point for heap analysis.
/// Uses HeapAnalysisService with proper dependency injection via adapters.
///
/// # Arguments
/// * `nodes` - IR nodes
/// * `edges` - IR edges
/// * `config` - HeapConfig from RFC-001 config system
///
/// # Example
/// ```rust,ignore
/// use config::{HeapConfig, Preset};
///
/// let config = HeapConfig::from_preset(Preset::Balanced);
/// let result = run_heap_analysis_with_config(&nodes, &edges, &config);
/// ```
///
/// # SOLID Compliance
/// - **D**: Depends on HeapAnalysisService, not concrete analyzers
/// - **O**: New analyzers can be added via adapters
pub fn run_heap_analysis_with_config(
    nodes: &[Node],
    edges: &[Edge],
    config: &HeapConfig,
) -> crate::features::heap_analysis::ports::HeapAnalysisResult {
    use crate::features::heap_analysis::ports::HeapAnalysisResult as HexResult;

    // Early exit for minimal input
    if nodes.len() < 3 {
        return HexResult::new();
    }

    // Build service with configured adapters (DIP: depend on abstractions)
    let mut service = HeapAnalysisService::new(config.clone());

    // Add memory checkers if enabled
    if config.enable_memory_safety {
        service = service
            .with_memory_checker(Box::new(NullCheckerAdapter::new()))
            .with_memory_checker(Box::new(UAFCheckerAdapter::new()))
            .with_memory_checker(Box::new(DoubleFreeCheckerAdapter::new()))
            .with_memory_checker(Box::new(BufferOverflowCheckerAdapter::new()))
            .with_memory_checker(Box::new(SpatialCheckerAdapter::new()));
    }

    // Add escape analyzer if enabled
    if config.enable_escape {
        service = service.with_escape_analyzer(Box::new(EscapeAnalyzerAdapter::new()));
    }

    // Add ownership analyzer if enabled
    if config.enable_ownership {
        let ownership_adapter = OwnershipAnalyzerAdapter::new()
            .with_copy_types(config.copy_types.clone())
            .with_move_types(config.move_types.clone());
        service = service.with_ownership_analyzer(Box::new(ownership_adapter));
    }

    // Add security analyzer if enabled
    if config.enable_security {
        service = service.with_security_analyzer(Box::new(SecurityAnalyzerAdapter::new()));
    }

    // Run analysis
    service.analyze(nodes, edges)
}

/// Convenience function: run with default Balanced config
pub fn run_heap_analysis_balanced(
    nodes: &[Node],
    edges: &[Edge],
) -> crate::features::heap_analysis::ports::HeapAnalysisResult {
    let config = HeapConfig::from_preset(Preset::Balanced);
    run_heap_analysis_with_config(nodes, edges, &config)
}

/// Build def-use map from edges
///
/// Extracts definitions and uses for each node based on edge relationships.
///
/// # Edge → Def/Use Mapping
/// - `EdgeKind::Defines` (source → target): source defines target
/// - `EdgeKind::Writes` (source → target): source writes to target (def)
/// - `EdgeKind::Reads` (source → target): source reads target (use)
/// - `EdgeKind::DefUse` (def → use): def defines, use uses
///
/// # Returns
/// Tuple of (defs_map, uses_map) where each maps node_id → Set<var_name>
fn build_def_use_map(
    edges: &[Edge],
) -> (
    HashMap<String, HashSet<String>>,
    HashMap<String, HashSet<String>>,
) {
    let mut defs_map: HashMap<String, HashSet<String>> = HashMap::new();
    let mut uses_map: HashMap<String, HashSet<String>> = HashMap::new();

    for edge in edges {
        match edge.kind {
            // Defines: source defines target
            EdgeKind::Defines => {
                defs_map
                    .entry(edge.source_id.clone())
                    .or_default()
                    .insert(edge.target_id.clone());
            }

            // Writes: source writes to target (treat as def)
            EdgeKind::Writes => {
                defs_map
                    .entry(edge.source_id.clone())
                    .or_default()
                    .insert(edge.target_id.clone());
            }

            // Reads: source reads target (treat as use)
            EdgeKind::Reads => {
                uses_map
                    .entry(edge.source_id.clone())
                    .or_default()
                    .insert(edge.target_id.clone());
            }

            // DefUse: source (def) → target (use)
            // The source node defines something, target node uses it
            EdgeKind::DefUse => {
                // Extract variable name from edge metadata or target_id
                let var_name = edge
                    .metadata
                    .as_ref()
                    .and_then(|m| m.context.clone())
                    .unwrap_or_else(|| edge.target_id.clone());

                defs_map
                    .entry(edge.source_id.clone())
                    .or_default()
                    .insert(var_name.clone());
                uses_map
                    .entry(edge.target_id.clone())
                    .or_default()
                    .insert(var_name);
            }

            // DataFlow: implies use at source, potential def at target
            EdgeKind::DataFlow => {
                // Use target_id as variable being flowed
                uses_map
                    .entry(edge.source_id.clone())
                    .or_default()
                    .insert(edge.target_id.clone());
            }

            // Calls: function call - uses the callee
            EdgeKind::Calls | EdgeKind::Invokes => {
                uses_map
                    .entry(edge.source_id.clone())
                    .or_default()
                    .insert(edge.target_id.clone());
            }

            _ => {}
        }
    }

    (defs_map, uses_map)
}

/// Run escape analysis for each function in the IR
///
/// Converts IR nodes to EscapeNode format and analyzes escape behavior.
///
/// # Algorithm
/// 1. Build def-use map from edges (NEW: DFG integration)
/// 2. Group nodes by function_id
/// 3. For each function:
///    a. Convert Nodes → EscapeNodes (with defs/uses from DFG)
///    b. Run EscapeAnalyzer::analyze()
///    c. Store FunctionEscapeInfo
///
/// # Arguments
/// * `analyzer` - EscapeAnalyzer instance
/// * `nodes` - IR nodes
/// * `edges` - IR edges (NEW: for DFG information)
///
/// # Returns
/// Vec of FunctionEscapeInfo (one per function)
fn run_escape_analysis_per_function(
    analyzer: &EscapeAnalyzer,
    nodes: &[Node],
    edges: &[Edge],
) -> Vec<FunctionEscapeInfo> {
    // Build def-use map from edges (DFG integration)
    let (defs_map, uses_map) = build_def_use_map(edges);

    // Group nodes by function_id
    let mut functions: HashMap<String, Vec<&Node>> = HashMap::new();
    for node in nodes {
        // Extract function_id from node.id (format: "func:function_name:...")
        if let Some(func_id) = extract_function_id(&node.id) {
            functions.entry(func_id).or_default().push(node);
        }
    }

    // Analyze each function
    let mut results = Vec::new();
    for (function_id, func_nodes) in functions {
        // Convert to EscapeNode with DFG info
        let escape_nodes: Vec<EscapeNode> = func_nodes
            .iter()
            .map(|node| node_to_escape_node(node, &defs_map, &uses_map))
            .collect();

        // Run escape analysis
        match analyzer.analyze(function_id.clone(), &escape_nodes) {
            Ok(info) => results.push(info),
            Err(e) => {
                eprintln!("Escape analysis failed for {}: {:?}", function_id, e);
            }
        }
    }

    results
}

/// Extract function_id from node.id
///
/// # Format
/// - Node.id: "func:function_name:..." → "function_name"
/// - If not a function node, returns None
fn extract_function_id(node_id: &str) -> Option<String> {
    if node_id.starts_with("func:") {
        node_id.split(':').nth(1).map(|s| s.to_string())
    } else {
        None
    }
}

/// Convert IR Node to EscapeNode
///
/// # Mapping
/// - node.id → id
/// - node.file_path → file_path
/// - node.span.start_line → start_line
/// - node.kind → node_kind (NodeKind → String)
/// - defs_map[node.id] → defs (from DFG)
/// - uses_map[node.id] → uses (from DFG)
///
/// # DFG Integration
/// Now extracts defs/uses from pre-built def-use maps derived from edges.
fn node_to_escape_node(
    node: &Node,
    defs_map: &HashMap<String, HashSet<String>>,
    uses_map: &HashMap<String, HashSet<String>>,
) -> EscapeNode {
    // Extract defs from DFG map
    let defs: Vec<String> = defs_map
        .get(&node.id)
        .map(|s| s.iter().cloned().collect())
        .unwrap_or_default();

    // Extract uses from DFG map
    let uses: Vec<String> = uses_map
        .get(&node.id)
        .map(|s| s.iter().cloned().collect())
        .unwrap_or_default();

    // Extract type from annotation if available
    let type_name = node.type_annotation.clone();

    EscapeNode {
        id: node.id.clone(),
        file_path: node.file_path.clone(),
        start_line: node.span.start_line as usize,
        node_kind: format!("{:?}", node.kind),
        type_name,
        defs,
        uses,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{NodeKind, Span};

    #[test]
    fn test_heap_analysis_empty() {
        let nodes = vec![];
        let edges = vec![];

        let (memory, security, escape) = run_heap_analysis(&nodes, &edges);

        // Empty input → empty output
        assert_eq!(memory.len(), 0);
        assert_eq!(security.len(), 0);
        assert_eq!(escape.len(), 0);
    }

    #[test]
    fn test_heap_analysis_too_few_nodes() {
        let node = Node::new(
            "func:test".to_string(),
            NodeKind::Function,
            "test".to_string(),    // fqn
            "test.py".to_string(), // file_path
            Span::new(1, 0, 1, 10),
        );

        let nodes = vec![node];
        let edges = vec![];

        let (memory, security, escape) = run_heap_analysis(&nodes, &edges);

        // <3 nodes → skip analysis
        assert_eq!(memory.len(), 0);
        assert_eq!(security.len(), 0);
        assert_eq!(escape.len(), 0);
    }

    #[test]
    fn test_extract_function_id() {
        assert_eq!(
            extract_function_id("func:test_function:123"),
            Some("test_function".to_string())
        );
        assert_eq!(extract_function_id("var:x"), None);
    }

    #[test]
    fn test_node_to_escape_node_without_dfg() {
        let node = Node::new(
            "func:test:var:x".to_string(),
            NodeKind::Variable,
            "x".to_string(),
            "test.py".to_string(),
            Span::new(1, 0, 1, 5),
        );

        let defs_map = HashMap::new();
        let uses_map = HashMap::new();
        let escape_node = node_to_escape_node(&node, &defs_map, &uses_map);

        assert_eq!(escape_node.id, "func:test:var:x");
        assert_eq!(escape_node.file_path, "test.py");
        assert_eq!(escape_node.start_line, 1);
        assert!(escape_node.node_kind.contains("Variable"));
        assert!(escape_node.defs.is_empty());
        assert!(escape_node.uses.is_empty());
    }

    #[test]
    fn test_node_to_escape_node_with_dfg() {
        let node = Node::new(
            "func:test:assign:1".to_string(),
            NodeKind::Expression,
            "x = y + z".to_string(),
            "test.py".to_string(),
            Span::new(5, 0, 5, 10),
        );

        let mut defs_map = HashMap::new();
        let mut uses_map = HashMap::new();

        // Node defines "x"
        let mut defs = HashSet::new();
        defs.insert("x".to_string());
        defs_map.insert(node.id.clone(), defs);

        // Node uses "y" and "z"
        let mut uses = HashSet::new();
        uses.insert("y".to_string());
        uses.insert("z".to_string());
        uses_map.insert(node.id.clone(), uses);

        let escape_node = node_to_escape_node(&node, &defs_map, &uses_map);

        assert_eq!(escape_node.defs.len(), 1);
        assert!(escape_node.defs.contains(&"x".to_string()));
        assert_eq!(escape_node.uses.len(), 2);
        assert!(escape_node.uses.contains(&"y".to_string()));
        assert!(escape_node.uses.contains(&"z".to_string()));
    }

    #[test]
    fn test_build_def_use_map_defines() {
        let edges = vec![Edge::new(
            "node1".to_string(),
            "var_x".to_string(),
            EdgeKind::Defines,
        )];

        let (defs_map, uses_map) = build_def_use_map(&edges);

        assert!(defs_map.get("node1").unwrap().contains("var_x"));
        assert!(uses_map.is_empty());
    }

    #[test]
    fn test_build_def_use_map_reads() {
        let edges = vec![Edge::new(
            "node1".to_string(),
            "var_y".to_string(),
            EdgeKind::Reads,
        )];

        let (defs_map, uses_map) = build_def_use_map(&edges);

        assert!(defs_map.is_empty());
        assert!(uses_map.get("node1").unwrap().contains("var_y"));
    }

    #[test]
    fn test_build_def_use_map_defuse() {
        let edges = vec![Edge::new(
            "def_node".to_string(),
            "use_node".to_string(),
            EdgeKind::DefUse,
        )];

        let (defs_map, uses_map) = build_def_use_map(&edges);

        // DefUse uses target_id as variable name when no metadata
        assert!(defs_map.get("def_node").unwrap().contains("use_node"));
        assert!(uses_map.get("use_node").unwrap().contains("use_node"));
    }
}
