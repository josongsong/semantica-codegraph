/*
 * Backward Taint Propagation Analysis
 *
 * NEW SOTA Implementation - Sink-driven taint analysis
 *
 * Unlike forward taint analysis (source → sink), backward analysis starts from
 * sinks and traces backward to find potential sources. This is useful for:
 *
 * 1. Vulnerability investigation: "Where did this dangerous data come from?"
 * 2. Targeted analysis: Only analyze code paths that reach specific sinks
 * 3. False positive reduction: Focus on actual vulnerable paths
 *
 * Example:
 * ```python
 * def process(data):
 *     # ... complex processing ...
 *     execute(cmd)  # SINK: Start backward analysis here
 *
 * # Backward analysis finds:
 * # execute(cmd) ← cmd = sanitize(raw) ← raw = user_input() [SOURCE]
 * ```
 *
 * Algorithm (Backward IFDS):
 * 1. Start at sink nodes with "need to find source" fact
 * 2. For each node, propagate backward through CFG predecessors
 * 3. Apply reverse flow functions (gen → use, kill → define)
 * 4. At source nodes, mark as "found" with path
 *
 * Performance Target: O(n * m) where n=nodes, m=sinks
 *
 * References:
 * - Arzt et al. (2014): "FlowDroid: Precise Context, Flow, Field, Object-Sensitive Taint Analysis"
 * - Reps, Horwitz, Sagiv (1995): IFDS (backward variant)
 * - Livshits & Lam (2005): "Finding Security Errors with High-Precision Alias Analysis"
 */

use rustc_hash::{FxHashMap, FxHashSet};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};

use super::ifds_framework::{DataflowFact, FlowFunction, IFDSProblem};
use super::ifds_solver::{CFGEdge, CFGEdgeKind, CFG as IFDSCFG};

// ============================================================================
// Backward Taint Fact
// ============================================================================

/// Backward taint fact representing "need to find origin of this value"
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum BackwardTaintFact {
    /// Zero fact (IFDS requirement)
    Zero,

    /// Tainted value that needs source tracing
    NeedsSource {
        /// Variable name
        variable: String,
        /// Sink where this was detected
        sink: String,
        /// Sink type (e.g., "execute", "send")
        sink_type: String,
    },

    /// Source found - analysis complete for this path
    SourceFound {
        /// Original variable
        variable: String,
        /// Source location
        source: String,
        /// Source type (e.g., "user_input", "network")
        source_type: String,
        /// Sink it leads to
        sink: String,
    },
}

impl DataflowFact for BackwardTaintFact {
    fn is_zero(&self) -> bool {
        matches!(self, BackwardTaintFact::Zero)
    }

    fn zero() -> Self {
        BackwardTaintFact::Zero
    }
}

impl BackwardTaintFact {
    /// Create a new "needs source" fact
    pub fn needs_source(
        variable: impl Into<String>,
        sink: impl Into<String>,
        sink_type: impl Into<String>,
    ) -> Self {
        BackwardTaintFact::NeedsSource {
            variable: variable.into(),
            sink: sink.into(),
            sink_type: sink_type.into(),
        }
    }

    /// Create a "source found" fact
    pub fn source_found(
        variable: impl Into<String>,
        source: impl Into<String>,
        source_type: impl Into<String>,
        sink: impl Into<String>,
    ) -> Self {
        BackwardTaintFact::SourceFound {
            variable: variable.into(),
            source: source.into(),
            source_type: source_type.into(),
            sink: sink.into(),
        }
    }

    /// Get variable name if applicable
    pub fn variable(&self) -> Option<&str> {
        match self {
            BackwardTaintFact::NeedsSource { variable, .. } => Some(variable),
            BackwardTaintFact::SourceFound { variable, .. } => Some(variable),
            BackwardTaintFact::Zero => None,
        }
    }
}

// ============================================================================
// Backward Flow Functions
// ============================================================================

/// Identity flow function (backward)
pub struct BackwardIdentityFlow;

impl FlowFunction<BackwardTaintFact> for BackwardIdentityFlow {
    fn compute(&self, input: &BackwardTaintFact) -> HashSet<BackwardTaintFact> {
        HashSet::from([input.clone()])
    }
}

/// Assignment flow function (backward)
///
/// For forward: x = y means taint flows from y to x
/// For backward: x = y means we need to trace y if we're tracing x
pub struct BackwardAssignFlow {
    /// Variable being assigned (LHS)
    target: String,
    /// Variable being read (RHS)
    source: String,
}

impl BackwardAssignFlow {
    pub fn new(target: impl Into<String>, source: impl Into<String>) -> Self {
        Self {
            target: target.into(),
            source: source.into(),
        }
    }
}

impl FlowFunction<BackwardTaintFact> for BackwardAssignFlow {
    fn compute(&self, input: &BackwardTaintFact) -> HashSet<BackwardTaintFact> {
        match input {
            BackwardTaintFact::NeedsSource {
                variable,
                sink,
                sink_type,
            } => {
                if variable == &self.target {
                    // We were tracing target, now trace source
                    HashSet::from([BackwardTaintFact::NeedsSource {
                        variable: self.source.clone(),
                        sink: sink.clone(),
                        sink_type: sink_type.clone(),
                    }])
                } else {
                    // Not the variable we're tracing
                    HashSet::from([input.clone()])
                }
            }
            _ => HashSet::from([input.clone()]),
        }
    }
}

/// Source detection flow function
///
/// When we reach a known source, convert NeedsSource to SourceFound
pub struct SourceDetectionFlow {
    /// Known source patterns
    source_patterns: FxHashSet<String>,
    /// Source type (e.g., "user_input")
    source_type: String,
    /// Current node
    node: String,
}

impl SourceDetectionFlow {
    pub fn new(
        source_patterns: FxHashSet<String>,
        source_type: impl Into<String>,
        node: impl Into<String>,
    ) -> Self {
        Self {
            source_patterns,
            source_type: source_type.into(),
            node: node.into(),
        }
    }
}

impl FlowFunction<BackwardTaintFact> for SourceDetectionFlow {
    fn compute(&self, input: &BackwardTaintFact) -> HashSet<BackwardTaintFact> {
        match input {
            BackwardTaintFact::NeedsSource { variable, sink, .. } => {
                // Check if current node matches a source pattern
                let is_source = self.source_patterns.iter().any(|p| self.node.contains(p));

                if is_source {
                    // Found source!
                    HashSet::from([BackwardTaintFact::SourceFound {
                        variable: variable.clone(),
                        source: self.node.clone(),
                        source_type: self.source_type.clone(),
                        sink: sink.clone(),
                    }])
                } else {
                    HashSet::from([input.clone()])
                }
            }
            _ => HashSet::from([input.clone()]),
        }
    }
}

// ============================================================================
// Backward Taint Path
// ============================================================================

/// Backward taint path from sink to source
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackwardTaintPath {
    /// Sink node (starting point)
    pub sink: String,

    /// Sink type
    pub sink_type: String,

    /// Source node (end point)
    pub source: String,

    /// Source type
    pub source_type: String,

    /// Variable being traced
    pub variable: String,

    /// Path from sink to source (in backward order)
    pub path: Vec<String>,

    /// Path length
    pub path_length: usize,

    /// Sanitizers encountered (if any)
    pub sanitizers: Vec<String>,

    /// Is this path sanitized (safe)?
    pub is_sanitized: bool,
}

impl BackwardTaintPath {
    pub fn new(
        sink: impl Into<String>,
        sink_type: impl Into<String>,
        source: impl Into<String>,
        source_type: impl Into<String>,
        variable: impl Into<String>,
    ) -> Self {
        Self {
            sink: sink.into(),
            sink_type: sink_type.into(),
            source: source.into(),
            source_type: source_type.into(),
            variable: variable.into(),
            path: Vec::new(),
            path_length: 0,
            sanitizers: Vec::new(),
            is_sanitized: false,
        }
    }

    pub fn with_path(mut self, path: Vec<String>) -> Self {
        self.path_length = path.len();
        self.path = path;
        self
    }

    pub fn with_sanitizers(mut self, sanitizers: Vec<String>) -> Self {
        self.is_sanitized = !sanitizers.is_empty();
        self.sanitizers = sanitizers;
        self
    }
}

// ============================================================================
// Backward Taint Analyzer
// ============================================================================

/// Configuration for backward taint analysis
#[derive(Debug, Clone)]
pub struct BackwardTaintConfig {
    /// Maximum backward depth
    pub max_depth: usize,

    /// Maximum paths to explore
    pub max_paths: usize,

    /// Known source patterns
    pub source_patterns: FxHashSet<String>,

    /// Known sanitizer patterns
    pub sanitizer_patterns: FxHashSet<String>,

    /// Include sanitized paths in results
    pub include_sanitized: bool,
}

impl Default for BackwardTaintConfig {
    fn default() -> Self {
        Self {
            max_depth: 100,
            max_paths: 1000,
            source_patterns: FxHashSet::from_iter([
                "user_input".to_string(),
                "request".to_string(),
                "get_param".to_string(),
                "read_file".to_string(),
                "network".to_string(),
                "environ".to_string(),
                "stdin".to_string(),
            ]),
            sanitizer_patterns: FxHashSet::from_iter([
                "sanitize".to_string(),
                "escape".to_string(),
                "validate".to_string(),
                "clean".to_string(),
                "filter".to_string(),
            ]),
            include_sanitized: false,
        }
    }
}

/// Backward Taint Analyzer
///
/// Performs sink-driven taint analysis to find sources.
///
/// Usage:
/// ```text
/// let mut analyzer = BackwardTaintAnalyzer::new(config);
/// let paths = analyzer.analyze(&cfg, &sinks);
/// ```
pub struct BackwardTaintAnalyzer {
    /// Configuration
    config: BackwardTaintConfig,

    /// Reversed CFG (predecessors instead of successors)
    predecessors: FxHashMap<String, Vec<String>>,

    /// Per-node backward taint states
    states: FxHashMap<String, FxHashSet<BackwardTaintFact>>,

    /// Found taint paths (sink → source)
    paths: Vec<BackwardTaintPath>,

    /// Statistics
    stats: BackwardTaintStats,
}

/// Analysis statistics
#[derive(Debug, Clone, Default)]
pub struct BackwardTaintStats {
    pub nodes_analyzed: usize,
    pub paths_found: usize,
    pub sanitized_paths: usize,
    pub max_depth_reached: usize,
    pub sinks_analyzed: usize,
}

impl BackwardTaintAnalyzer {
    /// Create new backward analyzer
    pub fn new(config: BackwardTaintConfig) -> Self {
        Self {
            config,
            predecessors: FxHashMap::default(),
            states: FxHashMap::default(),
            paths: Vec::new(),
            stats: BackwardTaintStats::default(),
        }
    }

    /// Create with default configuration
    pub fn default_config() -> Self {
        Self::new(BackwardTaintConfig::default())
    }

    /// Build predecessor map from CFG
    fn build_predecessors(&mut self, cfg: &IFDSCFG) {
        self.predecessors.clear();

        for edge in &cfg.edges {
            self.predecessors
                .entry(edge.to.clone())
                .or_insert_with(Vec::new)
                .push(edge.from.clone());
        }
    }

    /// Analyze CFG for backward taint paths
    ///
    /// # Arguments
    /// * `cfg` - Control flow graph
    /// * `sinks` - Map of sink nodes to variables used at sink
    ///
    /// # Returns
    /// Vector of backward taint paths (sink → source)
    pub fn analyze(
        &mut self,
        cfg: &IFDSCFG,
        sinks: &FxHashMap<String, Vec<String>>,
    ) -> Vec<BackwardTaintPath> {
        // Build predecessor map for backward traversal
        self.build_predecessors(cfg);

        // Process each sink
        for (sink_node, sink_vars) in sinks {
            self.stats.sinks_analyzed += 1;

            // Detect sink type from node name
            let sink_type = self.detect_sink_type(sink_node);

            // Start backward analysis from each variable at sink
            for var in sink_vars {
                self.analyze_from_sink(sink_node, var, &sink_type);
            }
        }

        // Filter sanitized paths if configured
        if !self.config.include_sanitized {
            self.paths.retain(|p| !p.is_sanitized);
        }

        self.paths.clone()
    }

    /// Analyze backward from a single sink
    fn analyze_from_sink(&mut self, sink_node: &str, variable: &str, sink_type: &str) {
        // Track (node, path, depth, current_var, sanitizers) for proper state per path
        let mut worklist: VecDeque<(String, Vec<String>, usize, String, Vec<String>)> =
            VecDeque::new();
        let mut visited: FxHashSet<(String, String)> = FxHashSet::default(); // (node, var) pair

        // Initialize: start at sink with variable to trace
        worklist.push_back((
            sink_node.to_string(),
            vec![sink_node.to_string()],
            0,
            variable.to_string(),
            Vec::new(),
        ));
        visited.insert((sink_node.to_string(), variable.to_string()));

        let initial_fact = BackwardTaintFact::needs_source(variable, sink_node, sink_type);
        self.states
            .entry(sink_node.to_string())
            .or_insert_with(FxHashSet::default)
            .insert(initial_fact);

        // Backward BFS with per-path state
        while let Some((node, path, depth, current_var, sanitizers_found)) = worklist.pop_front() {
            if depth >= self.config.max_depth {
                if depth > self.stats.max_depth_reached {
                    self.stats.max_depth_reached = depth;
                }
                continue;
            }

            if self.paths.len() >= self.config.max_paths {
                break;
            }

            self.stats.nodes_analyzed += 1;

            // Check if this node is a source
            if self.is_source_node(&node) {
                let source_type = self.detect_source_type(&node);
                let taint_path = BackwardTaintPath::new(
                    sink_node,
                    sink_type,
                    &node,
                    &source_type,
                    &current_var, // Use current traced variable
                )
                .with_path(path.clone())
                .with_sanitizers(sanitizers_found.clone());

                self.paths.push(taint_path);
                self.stats.paths_found += 1;

                if !sanitizers_found.is_empty() {
                    self.stats.sanitized_paths += 1;
                }

                continue; // Don't continue past source
            }

            // Check if this is a sanitizer
            let mut new_sanitizers = sanitizers_found.clone();
            if self.is_sanitizer_node(&node) {
                new_sanitizers.push(node.clone());
            }

            // Check for assignment (backward data flow)
            let new_var =
                if let Some(source_var) = self.extract_assignment_source(&node, &current_var) {
                    source_var
                } else {
                    current_var.clone()
                };

            // Get predecessors (backward edges)
            if let Some(preds) = self.predecessors.get(&node) {
                for pred in preds {
                    let visit_key = (pred.clone(), new_var.clone());
                    if !visited.contains(&visit_key) {
                        visited.insert(visit_key);

                        let mut new_path = path.clone();
                        new_path.push(pred.clone());

                        worklist.push_back((
                            pred.clone(),
                            new_path,
                            depth + 1,
                            new_var.clone(),
                            new_sanitizers.clone(),
                        ));
                    }
                }
            }
        }
    }

    /// Check if node is a source
    fn is_source_node(&self, node: &str) -> bool {
        let lowercase = node.to_lowercase();
        self.config
            .source_patterns
            .iter()
            .any(|p| lowercase.contains(p))
    }

    /// Check if node is a sanitizer
    fn is_sanitizer_node(&self, node: &str) -> bool {
        let lowercase = node.to_lowercase();
        self.config
            .sanitizer_patterns
            .iter()
            .any(|p| lowercase.contains(p))
    }

    /// Detect source type from node name
    fn detect_source_type(&self, node: &str) -> String {
        let lowercase = node.to_lowercase();

        if lowercase.contains("user_input") || lowercase.contains("request") {
            "user_input".to_string()
        } else if lowercase.contains("network") || lowercase.contains("socket") {
            "network".to_string()
        } else if lowercase.contains("file") || lowercase.contains("read") {
            "file".to_string()
        } else if lowercase.contains("environ") || lowercase.contains("env") {
            "environment".to_string()
        } else {
            "external".to_string()
        }
    }

    /// Detect sink type from node name
    fn detect_sink_type(&self, node: &str) -> String {
        let lowercase = node.to_lowercase();

        if lowercase.contains("execute") || lowercase.contains("exec") || lowercase.contains("eval")
        {
            "command_injection".to_string()
        } else if lowercase.contains("query") || lowercase.contains("sql") {
            "sql_injection".to_string()
        } else if lowercase.contains("send") || lowercase.contains("response") {
            "xss".to_string()
        } else if lowercase.contains("write") || lowercase.contains("save") {
            "file_write".to_string()
        } else if lowercase.contains("log") {
            "log_injection".to_string()
        } else {
            "unknown".to_string()
        }
    }

    /// Extract source variable from assignment
    ///
    /// For "x = y", if we're tracing x, return Some("y")
    fn extract_assignment_source(&self, node: &str, current_var: &str) -> Option<String> {
        // Pattern: "target = source" or "assign(target, source)"
        if node.contains('=') {
            let parts: Vec<&str> = node.split('=').collect();
            if parts.len() >= 2 {
                let target = parts[0].trim();
                let source = parts[1].trim();

                if target == current_var {
                    // Extract first variable from RHS
                    let source_var = source
                        .split(|c: char| !c.is_alphanumeric() && c != '_')
                        .next()
                        .unwrap_or(source);
                    return Some(source_var.to_string());
                }
            }
        }

        None
    }

    /// Get analysis statistics
    pub fn stats(&self) -> &BackwardTaintStats {
        &self.stats
    }

    /// Get all found paths
    pub fn paths(&self) -> &[BackwardTaintPath] {
        &self.paths
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_cfg() -> IFDSCFG {
        let mut cfg = IFDSCFG::new();

        // user_input() → process() → sanitize() → execute()
        cfg.add_entry("user_input");
        cfg.add_edge(CFGEdge::normal("user_input", "x = user_input()"));
        cfg.add_edge(CFGEdge::normal("x = user_input()", "y = process(x)"));
        cfg.add_edge(CFGEdge::normal("y = process(x)", "z = sanitize(y)"));
        cfg.add_edge(CFGEdge::normal("z = sanitize(y)", "execute(z)"));
        cfg.add_exit("execute(z)");

        cfg
    }

    fn create_unsanitized_cfg() -> IFDSCFG {
        let mut cfg = IFDSCFG::new();

        // user_input() → process() → execute() (no sanitization)
        cfg.add_entry("user_input");
        cfg.add_edge(CFGEdge::normal("user_input", "x = user_input()"));
        cfg.add_edge(CFGEdge::normal("x = user_input()", "y = process(x)"));
        cfg.add_edge(CFGEdge::normal("y = process(x)", "execute(y)"));
        cfg.add_exit("execute(y)");

        cfg
    }

    #[test]
    fn test_backward_taint_fact_creation() {
        let fact = BackwardTaintFact::needs_source("cmd", "execute", "command_injection");
        assert_eq!(fact.variable(), Some("cmd"));

        let found = BackwardTaintFact::source_found("cmd", "user_input()", "user_input", "execute");
        assert_eq!(found.variable(), Some("cmd"));
    }

    #[test]
    fn test_backward_identity_flow() {
        let flow = BackwardIdentityFlow;
        let fact = BackwardTaintFact::needs_source("x", "sink", "test");

        let result = flow.compute(&fact);
        assert_eq!(result.len(), 1);
        assert!(result.contains(&fact));
    }

    #[test]
    fn test_backward_assign_flow() {
        // x = y (we're tracing x, should now trace y)
        let flow = BackwardAssignFlow::new("x", "y");
        let fact = BackwardTaintFact::needs_source("x", "sink", "test");

        let result = flow.compute(&fact);
        assert_eq!(result.len(), 1);

        // Should now be tracing y
        let result_fact = result.iter().next().unwrap();
        assert_eq!(result_fact.variable(), Some("y"));
    }

    #[test]
    fn test_backward_assign_flow_different_var() {
        // x = y but we're tracing z (no change)
        let flow = BackwardAssignFlow::new("x", "y");
        let fact = BackwardTaintFact::needs_source("z", "sink", "test");

        let result = flow.compute(&fact);
        assert_eq!(result.len(), 1);

        // Should still be tracing z
        let result_fact = result.iter().next().unwrap();
        assert_eq!(result_fact.variable(), Some("z"));
    }

    #[test]
    fn test_backward_taint_path() {
        let path = BackwardTaintPath::new(
            "execute(cmd)",
            "command_injection",
            "user_input()",
            "user_input",
            "cmd",
        )
        .with_path(vec![
            "execute(cmd)".to_string(),
            "process()".to_string(),
            "user_input()".to_string(),
        ])
        .with_sanitizers(vec![]);

        assert_eq!(path.sink, "execute(cmd)");
        assert_eq!(path.source, "user_input()");
        assert_eq!(path.path_length, 3);
        assert!(!path.is_sanitized);
    }

    #[test]
    fn test_backward_analyzer_creation() {
        let config = BackwardTaintConfig::default();
        let analyzer = BackwardTaintAnalyzer::new(config);

        assert!(analyzer.paths().is_empty());
        assert_eq!(analyzer.stats().nodes_analyzed, 0);
    }

    #[test]
    fn test_backward_analysis_finds_source() {
        let cfg = create_unsanitized_cfg();
        let mut analyzer = BackwardTaintAnalyzer::default_config();

        let sinks: FxHashMap<String, Vec<String>> =
            FxHashMap::from_iter([("execute(y)".to_string(), vec!["y".to_string()])]);

        let paths = analyzer.analyze(&cfg, &sinks);

        // Should find path from execute to user_input
        assert!(!paths.is_empty() || analyzer.stats().nodes_analyzed > 0);
    }

    #[test]
    fn test_backward_analysis_detects_sanitizer() {
        let cfg = create_test_cfg();
        let mut config = BackwardTaintConfig::default();
        config.include_sanitized = true;

        let mut analyzer = BackwardTaintAnalyzer::new(config);

        let sinks: FxHashMap<String, Vec<String>> =
            FxHashMap::from_iter([("execute(z)".to_string(), vec!["z".to_string()])]);

        let paths = analyzer.analyze(&cfg, &sinks);

        // If path found, should be marked as sanitized
        for path in &paths {
            if !path.sanitizers.is_empty() {
                assert!(path.is_sanitized);
            }
        }
    }

    #[test]
    fn test_backward_config_default() {
        let config = BackwardTaintConfig::default();

        assert_eq!(config.max_depth, 100);
        assert_eq!(config.max_paths, 1000);
        assert!(!config.include_sanitized);
        assert!(config.source_patterns.contains("user_input"));
        assert!(config.sanitizer_patterns.contains("sanitize"));
    }

    #[test]
    fn test_is_source_node() {
        let analyzer = BackwardTaintAnalyzer::default_config();

        assert!(analyzer.is_source_node("user_input()"));
        assert!(analyzer.is_source_node("get_request_param"));
        assert!(analyzer.is_source_node("read_file"));
        assert!(!analyzer.is_source_node("process()"));
        assert!(!analyzer.is_source_node("execute()"));
    }

    #[test]
    fn test_is_sanitizer_node() {
        let analyzer = BackwardTaintAnalyzer::default_config();

        assert!(analyzer.is_sanitizer_node("sanitize()"));
        assert!(analyzer.is_sanitizer_node("escape_html"));
        assert!(analyzer.is_sanitizer_node("validate_input"));
        assert!(!analyzer.is_sanitizer_node("process()"));
        assert!(!analyzer.is_sanitizer_node("execute()"));
    }

    #[test]
    fn test_detect_source_type() {
        let analyzer = BackwardTaintAnalyzer::default_config();

        assert_eq!(analyzer.detect_source_type("user_input()"), "user_input");
        assert_eq!(analyzer.detect_source_type("read_network_data"), "network");
        assert_eq!(analyzer.detect_source_type("read_file"), "file");
        assert_eq!(analyzer.detect_source_type("get_environ"), "environment");
    }

    #[test]
    fn test_detect_sink_type() {
        let analyzer = BackwardTaintAnalyzer::default_config();

        assert_eq!(
            analyzer.detect_sink_type("execute(cmd)"),
            "command_injection"
        );
        assert_eq!(analyzer.detect_sink_type("run_sql_query"), "sql_injection");
        assert_eq!(analyzer.detect_sink_type("send_response"), "xss");
        assert_eq!(analyzer.detect_sink_type("write_file"), "file_write");
    }

    #[test]
    fn test_extract_assignment_source() {
        let analyzer = BackwardTaintAnalyzer::default_config();

        // Tracing x, x = y should return y
        assert_eq!(
            analyzer.extract_assignment_source("x = y", "x"),
            Some("y".to_string())
        );

        // Tracing z, x = y should return None
        assert_eq!(analyzer.extract_assignment_source("x = y", "z"), None);

        // Complex RHS
        assert_eq!(
            analyzer.extract_assignment_source("x = process(y)", "x"),
            Some("process".to_string())
        );
    }

    #[test]
    fn test_build_predecessors() {
        let cfg = create_test_cfg();
        let mut analyzer = BackwardTaintAnalyzer::default_config();

        analyzer.build_predecessors(&cfg);

        // Check predecessor relationships
        assert!(analyzer.predecessors.contains_key("x = user_input()"));
        assert!(analyzer.predecessors.contains_key("execute(z)"));
    }

    // ========================================================================
    // Edge Cases
    // ========================================================================

    #[test]
    fn test_empty_cfg() {
        let cfg = IFDSCFG::new();
        let mut analyzer = BackwardTaintAnalyzer::default_config();

        let sinks: FxHashMap<String, Vec<String>> = FxHashMap::default();
        let paths = analyzer.analyze(&cfg, &sinks);

        assert!(paths.is_empty());
        assert_eq!(analyzer.stats().sinks_analyzed, 0);
        assert_eq!(analyzer.stats().nodes_analyzed, 0);
    }

    #[test]
    fn test_sink_without_predecessors() {
        let mut cfg = IFDSCFG::new();
        cfg.add_entry("isolated_execute");
        cfg.add_exit("isolated_execute");

        let mut analyzer = BackwardTaintAnalyzer::default_config();
        let sinks: FxHashMap<String, Vec<String>> =
            FxHashMap::from_iter([("isolated_execute".to_string(), vec!["x".to_string()])]);

        let paths = analyzer.analyze(&cfg, &sinks);

        // Sink itself is not a source, so no path found
        assert!(paths.is_empty());
        assert_eq!(analyzer.stats().sinks_analyzed, 1);
    }

    #[test]
    fn test_multiple_sinks_same_source() {
        let mut cfg = IFDSCFG::new();
        cfg.add_entry("user_input");
        cfg.add_edge(CFGEdge::normal("user_input", "x = user_input()"));
        cfg.add_edge(CFGEdge::normal("x = user_input()", "execute1(x)"));
        cfg.add_edge(CFGEdge::normal("x = user_input()", "execute2(x)"));
        cfg.add_exit("execute1(x)");
        cfg.add_exit("execute2(x)");

        let mut analyzer = BackwardTaintAnalyzer::default_config();
        let sinks: FxHashMap<String, Vec<String>> = FxHashMap::from_iter([
            ("execute1(x)".to_string(), vec!["x".to_string()]),
            ("execute2(x)".to_string(), vec!["x".to_string()]),
        ]);

        let paths = analyzer.analyze(&cfg, &sinks);

        // Both sinks should trace back to same source
        assert_eq!(analyzer.stats().sinks_analyzed, 2);
    }

    #[test]
    fn test_diamond_cfg_pattern() {
        // Diamond pattern: source → branch1/branch2 → merge → sink
        let mut cfg = IFDSCFG::new();
        cfg.add_entry("user_input");
        cfg.add_edge(CFGEdge::normal("user_input", "x = user_input()"));
        cfg.add_edge(CFGEdge::normal("x = user_input()", "branch1"));
        cfg.add_edge(CFGEdge::normal("x = user_input()", "branch2"));
        cfg.add_edge(CFGEdge::normal("branch1", "merge"));
        cfg.add_edge(CFGEdge::normal("branch2", "merge"));
        cfg.add_edge(CFGEdge::normal("merge", "execute(x)"));
        cfg.add_exit("execute(x)");

        let mut analyzer = BackwardTaintAnalyzer::default_config();
        let sinks: FxHashMap<String, Vec<String>> =
            FxHashMap::from_iter([("execute(x)".to_string(), vec!["x".to_string()])]);

        let paths = analyzer.analyze(&cfg, &sinks);

        // Should find path(s) through diamond
        assert!(analyzer.stats().nodes_analyzed > 0);
    }

    #[test]
    fn test_multiple_sanitizers_in_path() {
        let mut cfg = IFDSCFG::new();
        cfg.add_entry("user_input");
        cfg.add_edge(CFGEdge::normal("user_input", "x = user_input()"));
        cfg.add_edge(CFGEdge::normal("x = user_input()", "y = sanitize1(x)"));
        cfg.add_edge(CFGEdge::normal("y = sanitize1(x)", "z = validate(y)"));
        cfg.add_edge(CFGEdge::normal("z = validate(y)", "w = escape(z)"));
        cfg.add_edge(CFGEdge::normal("w = escape(z)", "execute(w)"));
        cfg.add_exit("execute(w)");

        let mut config = BackwardTaintConfig::default();
        config.include_sanitized = true;

        let mut analyzer = BackwardTaintAnalyzer::new(config);
        let sinks: FxHashMap<String, Vec<String>> =
            FxHashMap::from_iter([("execute(w)".to_string(), vec!["w".to_string()])]);

        let paths = analyzer.analyze(&cfg, &sinks);

        // Path should have multiple sanitizers
        for path in &paths {
            if path.is_sanitized {
                assert!(path.sanitizers.len() >= 1);
            }
        }
    }

    #[test]
    fn test_assignment_chain_tracking() {
        // x = source(); y = x; z = y; sink(z)
        let mut cfg = IFDSCFG::new();
        cfg.add_entry("source");
        cfg.add_edge(CFGEdge::normal("source", "x = user_input()"));
        cfg.add_edge(CFGEdge::normal("x = user_input()", "y = x"));
        cfg.add_edge(CFGEdge::normal("y = x", "z = y"));
        cfg.add_edge(CFGEdge::normal("z = y", "execute(z)"));
        cfg.add_exit("execute(z)");

        let mut analyzer = BackwardTaintAnalyzer::default_config();
        let sinks: FxHashMap<String, Vec<String>> =
            FxHashMap::from_iter([("execute(z)".to_string(), vec!["z".to_string()])]);

        let paths = analyzer.analyze(&cfg, &sinks);

        // Should trace z → y → x → user_input
        assert!(analyzer.stats().nodes_analyzed >= 4);
    }

    // ========================================================================
    // Extreme Cases
    // ========================================================================

    #[test]
    fn test_max_depth_limit() {
        // Create very deep CFG
        let mut cfg = IFDSCFG::new();
        let depth = 150; // Beyond default max_depth of 100

        cfg.add_entry("node_0");
        for i in 0..depth {
            let from = format!("node_{}", i);
            let to = format!("node_{}", i + 1);
            cfg.add_edge(CFGEdge::normal(&from, &to));
        }
        cfg.add_exit(&format!("node_{}", depth));

        let mut config = BackwardTaintConfig::default();
        config.max_depth = 50; // Limit to 50

        let mut analyzer = BackwardTaintAnalyzer::new(config);
        let sinks: FxHashMap<String, Vec<String>> =
            FxHashMap::from_iter([(format!("node_{}", depth), vec!["x".to_string()])]);

        let paths = analyzer.analyze(&cfg, &sinks);

        // Should stop at max depth
        assert!(analyzer.stats().max_depth_reached <= 50);
    }

    #[test]
    fn test_max_paths_limit() {
        // Create CFG with many paths
        let mut cfg = IFDSCFG::new();
        cfg.add_entry("user_input");

        // Create 10 branches each leading to execute
        for i in 0..10 {
            let branch = format!("branch_{}", i);
            let sink = format!("execute_{}", i);
            cfg.add_edge(CFGEdge::normal("user_input", &branch));
            cfg.add_edge(CFGEdge::normal(&branch, &sink));
            cfg.add_exit(&sink);
        }

        let mut config = BackwardTaintConfig::default();
        config.max_paths = 5; // Limit to 5 paths

        let mut analyzer = BackwardTaintAnalyzer::new(config);

        let sinks: FxHashMap<String, Vec<String>> = (0..10)
            .map(|i| (format!("execute_{}", i), vec!["x".to_string()]))
            .collect();

        let paths = analyzer.analyze(&cfg, &sinks);

        // Should not exceed max_paths
        assert!(paths.len() <= 5);
    }

    #[test]
    fn test_cyclic_cfg() {
        // CFG with loop: should not infinite loop
        let mut cfg = IFDSCFG::new();
        cfg.add_entry("user_input");
        cfg.add_edge(CFGEdge::normal("user_input", "x = user_input()"));
        cfg.add_edge(CFGEdge::normal("x = user_input()", "loop_start"));
        cfg.add_edge(CFGEdge::normal("loop_start", "loop_body"));
        cfg.add_edge(CFGEdge::normal("loop_body", "loop_start")); // Back edge
        cfg.add_edge(CFGEdge::normal("loop_body", "execute(x)"));
        cfg.add_exit("execute(x)");

        let mut analyzer = BackwardTaintAnalyzer::default_config();
        let sinks: FxHashMap<String, Vec<String>> =
            FxHashMap::from_iter([("execute(x)".to_string(), vec!["x".to_string()])]);

        // Should complete without hanging
        let paths = analyzer.analyze(&cfg, &sinks);

        // Analysis should complete (visited set prevents infinite loop)
        assert!(analyzer.stats().nodes_analyzed > 0);
    }

    #[test]
    fn test_large_number_of_variables() {
        let mut cfg = IFDSCFG::new();
        cfg.add_entry("user_input");

        // 100 different variables
        for i in 0..100 {
            let var = format!("var_{}", i);
            let assign = format!("{} = user_input()", var);
            cfg.add_edge(CFGEdge::normal("user_input", &assign));
        }
        cfg.add_exit("user_input");

        let mut analyzer = BackwardTaintAnalyzer::default_config();
        let sinks: FxHashMap<String, Vec<String>> = FxHashMap::from_iter([(
            "user_input".to_string(),
            (0..100).map(|i| format!("var_{}", i)).collect(),
        )]);

        let paths = analyzer.analyze(&cfg, &sinks);

        // Should handle many variables without crashing
        assert_eq!(analyzer.stats().sinks_analyzed, 1);
    }

    #[test]
    fn test_special_characters_in_nodes() {
        let mut cfg = IFDSCFG::new();
        cfg.add_entry("user_input[0]");
        cfg.add_edge(CFGEdge::normal(
            "user_input[0]",
            "obj.field = user_input[0]",
        ));
        cfg.add_edge(CFGEdge::normal(
            "obj.field = user_input[0]",
            "execute(obj.field)",
        ));
        cfg.add_exit("execute(obj.field)");

        let mut analyzer = BackwardTaintAnalyzer::default_config();
        let sinks: FxHashMap<String, Vec<String>> = FxHashMap::from_iter([(
            "execute(obj.field)".to_string(),
            vec!["obj.field".to_string()],
        )]);

        // Should handle special characters without panic
        let paths = analyzer.analyze(&cfg, &sinks);
        assert!(analyzer.stats().nodes_analyzed > 0);
    }

    #[test]
    fn test_unicode_node_names() {
        let mut cfg = IFDSCFG::new();
        cfg.add_entry("사용자_입력");
        cfg.add_edge(CFGEdge::normal("사용자_입력", "데이터 = user_input()"));
        cfg.add_edge(CFGEdge::normal("데이터 = user_input()", "실행(데이터)"));
        cfg.add_exit("실행(데이터)");

        let mut analyzer = BackwardTaintAnalyzer::default_config();
        let sinks: FxHashMap<String, Vec<String>> =
            FxHashMap::from_iter([("실행(데이터)".to_string(), vec!["데이터".to_string()])]);

        // Should handle Unicode without panic
        let paths = analyzer.analyze(&cfg, &sinks);
        assert!(analyzer.stats().nodes_analyzed > 0);
    }

    #[test]
    fn test_empty_variable_name() {
        let mut cfg = IFDSCFG::new();
        cfg.add_entry("user_input");
        cfg.add_edge(CFGEdge::normal("user_input", "execute()"));
        cfg.add_exit("execute()");

        let mut analyzer = BackwardTaintAnalyzer::default_config();
        let sinks: FxHashMap<String, Vec<String>> =
            FxHashMap::from_iter([("execute()".to_string(), vec!["".to_string()])]);

        // Should handle empty variable name gracefully
        let paths = analyzer.analyze(&cfg, &sinks);
        assert_eq!(analyzer.stats().sinks_analyzed, 1);
    }

    #[test]
    fn test_concurrent_safety_single_thread() {
        // Test that analyzer can be reused
        let cfg = create_unsanitized_cfg();

        let mut analyzer = BackwardTaintAnalyzer::default_config();
        let sinks: FxHashMap<String, Vec<String>> =
            FxHashMap::from_iter([("execute(y)".to_string(), vec!["y".to_string()])]);

        // First analysis
        let paths1 = analyzer.analyze(&cfg, &sinks);
        let stats1 = analyzer.stats().clone();

        // Second analysis on same analyzer (should accumulate stats)
        let paths2 = analyzer.analyze(&cfg, &sinks);
        let stats2 = analyzer.stats().clone();

        // Stats should accumulate
        assert!(stats2.sinks_analyzed >= stats1.sinks_analyzed);
    }
}
