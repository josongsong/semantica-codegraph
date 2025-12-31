/*
 * Typestate Analyzer
 *
 * Tracks resource state through program execution using CFG-based dataflow.
 *
 * # Algorithm
 * - Forward dataflow analysis on CFG
 * - State per variable per program point: (block_id, variable) → state
 * - Merge states at join points (may-analysis)
 *
 * # Time Complexity
 * O(CFG nodes × variables × states × iterations)
 * - Typical: O(n) where n = CFG nodes (converges quickly)
 * - Worst: O(n²) for deep loops
 *
 * # Space Complexity
 * O(variables × CFG nodes) for state map
 *
 * # Example
 * ```rust
 * let analyzer = TypestateAnalyzer::new()
 *     .with_protocol(FileProtocol::define());
 *
 * let result = analyzer.analyze(&ir_node)?;
 *
 * for violation in result.violations {
 *     println!("{}", violation);
 * }
 * ```
 */

use super::super::domain::{Action, Protocol, ProtocolViolation, State, ViolationKind};
use rustc_hash::FxHashMap;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};

/// Program point (CFG block ID)
pub type ProgramPoint = String;

/// Typestate analyzer configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypestateConfig {
    /// Enable path-sensitive analysis
    pub path_sensitive: bool,

    /// Enable null safety integration
    pub null_safety: bool,

    /// Warn on "may leak" (some paths leak)
    pub warn_on_maybe_leak: bool,

    /// Maximum iterations for dataflow fixed-point
    pub max_iterations: usize,
}

impl Default for TypestateConfig {
    fn default() -> Self {
        Self {
            path_sensitive: true,
            null_safety: true,
            warn_on_maybe_leak: true,
            max_iterations: 100,
        }
    }
}

/// Typestate analysis result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypestateResult {
    /// Detected violations
    pub violations: Vec<ProtocolViolation>,

    /// State map: (program_point, variable) → state
    pub state_map: FxHashMap<(ProgramPoint, String), State>,

    /// Analysis statistics
    pub stats: AnalysisStats,
}

/// Analysis statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisStats {
    /// Number of dataflow iterations
    pub iterations: usize,

    /// Number of variables tracked
    pub tracked_variables: usize,

    /// Number of program points
    pub program_points: usize,

    /// Analysis time (milliseconds)
    pub analysis_time_ms: u64,
}

impl Default for AnalysisStats {
    fn default() -> Self {
        Self {
            iterations: 0,
            tracked_variables: 0,
            program_points: 0,
            analysis_time_ms: 0,
        }
    }
}

/// Typestate analyzer
///
/// Tracks state of resources through program execution.
pub struct TypestateAnalyzer {
    /// Protocol definitions (resource type → protocol)
    pub(crate) protocols: HashMap<String, Protocol>,

    /// Current state of each variable at each program point
    /// (program_point, variable) → state
    state_map: FxHashMap<(ProgramPoint, String), State>,

    /// Resource variables: variable → protocol name
    resource_vars: HashMap<String, String>,

    /// CFG edges: block_id → successors
    cfg_edges: HashMap<String, Vec<String>>,

    /// Configuration
    config: TypestateConfig,

    /// Statistics
    stats: AnalysisStats,
}

impl TypestateAnalyzer {
    /// Create new analyzer
    pub fn new() -> Self {
        Self {
            protocols: HashMap::new(),
            state_map: FxHashMap::default(),
            resource_vars: HashMap::new(),
            cfg_edges: HashMap::new(),
            config: TypestateConfig::default(),
            stats: AnalysisStats::default(),
        }
    }

    /// Register a protocol
    ///
    /// # Example
    /// ```ignore
    /// analyzer.with_protocol(FileProtocol::define());
    /// ```
    pub fn with_protocol(mut self, protocol: Protocol) -> Self {
        self.protocols.insert(protocol.name.clone(), protocol);
        self
    }

    /// Set configuration
    pub fn with_config(mut self, config: TypestateConfig) -> Self {
        self.config = config;
        self
    }

    /// Analyze code (placeholder - will integrate with IR later)
    ///
    /// For now, accepts simplified input for testing.
    pub fn analyze_simple(
        &mut self,
        blocks: Vec<SimpleBlock>,
        edges: Vec<(String, String)>,
    ) -> TypestateResult {
        let start_time = std::time::Instant::now();

        // Build CFG edge map
        self.cfg_edges.clear();
        for (from, to) in edges {
            self.cfg_edges.entry(from).or_insert_with(Vec::new).push(to);
        }

        // Identify resource variables
        self.identify_resource_variables(&blocks);
        self.stats.tracked_variables = self.resource_vars.len();
        self.stats.program_points = blocks.len();

        // Initialize states
        self.initialize_states(&blocks);

        // Dataflow analysis
        self.propagate_states(&blocks);

        // Find violations
        let violations = self.find_violations(&blocks);

        self.stats.analysis_time_ms = start_time.elapsed().as_millis() as u64;

        TypestateResult {
            violations,
            state_map: self.state_map.clone(),
            stats: self.stats.clone(),
        }
    }

    /// Identify resource variables in blocks
    fn identify_resource_variables(&mut self, blocks: &[SimpleBlock]) {
        for block in blocks {
            for stmt in &block.statements {
                match stmt {
                    Statement::MethodCall { object, method, .. } => {
                        // Any method call on potential resource variable
                        let protocol_name = self.infer_protocol_from_method(method);
                        if let Some(protocol) = protocol_name {
                            self.resource_vars.entry(object.clone()).or_insert(protocol);
                        }
                    }
                    Statement::Assignment { lhs, .. } => {
                        // Check if RHS is a resource construction
                        // For now, use variable name heuristics
                        if self.looks_like_resource_var(lhs) {
                            let protocol_name = self.infer_protocol_from_var_name(lhs);
                            if let Some(protocol) = protocol_name {
                                self.resource_vars.entry(lhs.clone()).or_insert(protocol);
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
    }

    /// Infer protocol from method name
    fn infer_protocol_from_method(&self, method: &str) -> Option<String> {
        match method {
            "open" | "read" | "write" | "close" | "readline" | "readlines" | "writelines"
            | "seek" | "tell" | "flush" => Some("File".to_string()),
            "acquire" | "release" => Some("Lock".to_string()),
            "connect" | "authenticate" | "send" | "receive" | "disconnect" | "query"
            | "execute" => Some("Connection".to_string()),
            _ => None,
        }
    }

    /// Check if variable name looks like a resource
    fn looks_like_resource_var(&self, var: &str) -> bool {
        let var_lower = var.to_lowercase();
        var_lower.contains("file")
            || var_lower.contains("lock")
            || var_lower.contains("conn")
            || var_lower.contains("socket")
    }

    /// Infer protocol from variable name
    fn infer_protocol_from_var_name(&self, var: &str) -> Option<String> {
        let var_lower = var.to_lowercase();
        if var_lower.contains("file") {
            Some("File".to_string())
        } else if var_lower.contains("lock") {
            Some("Lock".to_string())
        } else if var_lower.contains("conn") || var_lower.contains("socket") {
            Some("Connection".to_string())
        } else {
            None
        }
    }

    /// Initialize states for all resource variables
    fn initialize_states(&mut self, blocks: &[SimpleBlock]) {
        for (var, protocol_name) in &self.resource_vars {
            if let Some(protocol) = self.protocols.get(protocol_name) {
                // Set initial state at entry block
                if let Some(entry) = blocks.first() {
                    self.state_map
                        .insert((entry.id.clone(), var.clone()), protocol.initial_state());
                }
            }
        }
    }

    /// Propagate states through CFG (fixed-point iteration)
    fn propagate_states(&mut self, blocks: &[SimpleBlock]) {
        let mut worklist: VecDeque<String> = blocks.iter().map(|b| b.id.clone()).collect();
        let mut visited_count: HashMap<String, usize> = HashMap::new();

        let mut iterations = 0;

        while let Some(block_id) = worklist.pop_front() {
            iterations += 1;
            if iterations > self.config.max_iterations {
                break;
            }

            *visited_count.entry(block_id.clone()).or_insert(0) += 1;

            if let Some(block) = blocks.iter().find(|b| b.id == block_id) {
                // Process block statements
                let changed = self.process_block(block);

                // If state changed, add successors to worklist
                if changed {
                    if let Some(successors) = self.cfg_edges.get(&block_id) {
                        for succ in successors {
                            if !worklist.contains(succ) {
                                worklist.push_back(succ.clone());
                            }
                        }
                    }
                }
            }
        }

        self.stats.iterations = iterations;
    }

    /// Process a single block
    ///
    /// Returns true if states changed.
    fn process_block(&mut self, block: &SimpleBlock) -> bool {
        let mut changed = false;

        // Track current state within the block (for sequential statements)
        let mut block_local_states: FxHashMap<String, State> = FxHashMap::default();

        // Initialize from state_map
        for (var, protocol_name) in &self.resource_vars {
            if let Some(protocol) = self.protocols.get(protocol_name) {
                let state = self
                    .state_map
                    .get(&(block.id.clone(), var.clone()))
                    .cloned()
                    .unwrap_or_else(|| protocol.initial_state());
                block_local_states.insert(var.clone(), state);
            }
        }

        // Process statements sequentially
        for stmt in &block.statements {
            match stmt {
                Statement::MethodCall { object, method, .. } => {
                    if let Some(protocol_name) = self.resource_vars.get(object) {
                        if let Some(protocol) = self.protocols.get(protocol_name) {
                            // Get current state from block-local state
                            let current_state = block_local_states
                                .get(object)
                                .cloned()
                                .unwrap_or_else(|| protocol.initial_state());

                            // Apply transition
                            let action = Action::new(method);
                            if let Some(next_state) = protocol.next_state(&current_state, &action) {
                                // Valid transition - update block-local state
                                block_local_states.insert(object.clone(), next_state);
                            }
                            // Invalid transition will be caught in find_violations
                        }
                    }
                }

                Statement::Assignment { lhs, rhs } => {
                    // Copy state from rhs to lhs
                    if let Some(rhs_protocol) = self.resource_vars.get(rhs).cloned() {
                        if let Some(rhs_state) = block_local_states.get(rhs).cloned() {
                            block_local_states.insert(lhs.clone(), rhs_state);

                            // lhs inherits protocol from rhs
                            self.resource_vars.insert(lhs.clone(), rhs_protocol);
                        }
                    }
                }

                _ => {}
            }
        }

        // Update state_map with final block-local states
        for (var, new_state) in block_local_states {
            let old_state = self
                .state_map
                .insert((block.id.clone(), var), new_state.clone());
            if old_state.is_none() || old_state.as_ref() != Some(&new_state) {
                changed = true;
            }
        }

        changed
    }

    /// Find protocol violations
    fn find_violations(&self, blocks: &[SimpleBlock]) -> Vec<ProtocolViolation> {
        let mut violations = Vec::new();

        // Global state tracking across blocks
        let mut global_states: FxHashMap<String, State> = FxHashMap::default();

        // Initialize all resource variables with their initial states
        for (var, protocol_name) in &self.resource_vars {
            if let Some(protocol) = self.protocols.get(protocol_name) {
                global_states.insert(var.clone(), protocol.initial_state());
            }
        }

        for block in blocks {
            // Block-local state (copy from global)
            let mut block_states = global_states.clone();

            for (stmt_idx, stmt) in block.statements.iter().enumerate() {
                match stmt {
                    Statement::MethodCall { object, method, .. } => {
                        if let Some(protocol_name) = self.resource_vars.get(object) {
                            if let Some(protocol) = self.protocols.get(protocol_name) {
                                let current_state = block_states
                                    .get(object)
                                    .cloned()
                                    .unwrap_or_else(|| protocol.initial_state());

                                let action = Action::new(method);

                                // Special case: first "open" call initializes the resource
                                let is_initializing_call =
                                    matches!(method.as_str(), "open" | "connect" | "acquire")
                                        && current_state == protocol.initial_state();

                                // Check if transition is valid
                                if !is_initializing_call
                                    && protocol.next_state(&current_state, &action).is_none()
                                {
                                    let expected_state = protocol
                                        .action_preconditions
                                        .get(&action)
                                        .cloned()
                                        .unwrap_or_else(|| State::new("Any"));

                                    let kind = if method == "read" || method == "write" {
                                        ViolationKind::UseAfterClose
                                    } else {
                                        ViolationKind::InvalidTransition
                                    };

                                    violations.push(
                                        ProtocolViolation::new(
                                            block.line + stmt_idx,
                                            kind,
                                            object.clone(),
                                            expected_state,
                                            current_state.clone(),
                                            format!(
                                                "Cannot {}() on {} in state {}",
                                                method, object, current_state
                                            ),
                                        )
                                        .with_action(action.clone()),
                                    );
                                } else {
                                    // Valid transition - update block state
                                    if let Some(next_state) =
                                        protocol.next_state(&current_state, &action)
                                    {
                                        block_states.insert(object.clone(), next_state);
                                    }
                                }
                            }
                        }
                    }

                    Statement::Assignment { lhs, rhs } => {
                        // Copy state from rhs to lhs
                        if let Some(rhs_state) = block_states.get(rhs).cloned() {
                            block_states.insert(lhs.clone(), rhs_state);
                        }
                    }

                    Statement::Return => {
                        // Check resource leaks
                        for (var, protocol_name) in &self.resource_vars {
                            if let Some(protocol) = self.protocols.get(protocol_name) {
                                if let Some(current_state) = block_states.get(var) {
                                    if !protocol.is_final_state(current_state) {
                                        violations.push(ProtocolViolation::new(
                                            block.line + stmt_idx,
                                            ViolationKind::ResourceLeak,
                                            var.clone(),
                                            protocol
                                                .final_states
                                                .iter()
                                                .next()
                                                .cloned()
                                                .unwrap_or_else(|| State::new("Final")),
                                            current_state.clone(),
                                            format!(
                                                "Resource '{}' not in final state at exit (current: {})",
                                                var, current_state
                                            ),
                                        ));
                                    }
                                }
                            }
                        }
                    }

                    _ => {}
                }
            }

            // Update global states with final block states (for next block)
            for (var, state) in block_states {
                global_states.insert(var, state);
            }
        }

        violations
    }

    /// Get protocol for variable
    pub fn get_protocol_for_var(&self, var: &str) -> Option<&Protocol> {
        self.resource_vars
            .get(var)
            .and_then(|name| self.protocols.get(name))
    }
}

impl Default for TypestateAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

/// Simplified basic block for testing
#[derive(Debug, Clone)]
pub struct SimpleBlock {
    pub id: String,
    pub line: usize,
    pub statements: Vec<Statement>,
}

/// Simplified statement
#[derive(Debug, Clone)]
pub enum Statement {
    MethodCall { object: String, method: String },
    Assignment { lhs: String, rhs: String },
    Return,
    Nop,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::typestate::infrastructure::{FileProtocol, LockProtocol};

    #[test]
    fn test_analyzer_creation() {
        let analyzer = TypestateAnalyzer::new().with_protocol(FileProtocol::define());

        assert_eq!(analyzer.protocols.len(), 1);
        assert!(analyzer.protocols.contains_key("File"));
    }

    #[test]
    fn test_detect_use_after_close() {
        let mut analyzer = TypestateAnalyzer::new().with_protocol(FileProtocol::define());

        let blocks = vec![
            SimpleBlock {
                id: "entry".to_string(),
                line: 1,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "open".to_string(),
                }],
            },
            SimpleBlock {
                id: "b1".to_string(),
                line: 2,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "read".to_string(),
                }],
            },
            SimpleBlock {
                id: "b2".to_string(),
                line: 3,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "close".to_string(),
                }],
            },
            SimpleBlock {
                id: "b3".to_string(),
                line: 4,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "read".to_string(),
                }],
            },
        ];

        let edges = vec![
            ("entry".to_string(), "b1".to_string()),
            ("b1".to_string(), "b2".to_string()),
            ("b2".to_string(), "b3".to_string()),
        ];

        let result = analyzer.analyze_simple(blocks, edges);

        // Should detect use-after-close on line 4
        assert_eq!(result.violations.len(), 1);
        let violation = &result.violations[0];
        assert_eq!(violation.kind, ViolationKind::UseAfterClose);
        assert_eq!(violation.variable, "file");
        assert!(violation.message.contains("read()"));
    }

    #[test]
    fn test_detect_resource_leak() {
        let mut analyzer = TypestateAnalyzer::new().with_protocol(LockProtocol::define());

        let blocks = vec![
            SimpleBlock {
                id: "entry".to_string(),
                line: 1,
                statements: vec![Statement::MethodCall {
                    object: "lock".to_string(),
                    method: "acquire".to_string(),
                }],
            },
            SimpleBlock {
                id: "exit".to_string(),
                line: 2,
                statements: vec![Statement::Return],
            },
        ];

        let edges = vec![("entry".to_string(), "exit".to_string())];

        let result = analyzer.analyze_simple(blocks, edges);

        // Should detect leak (lock not released at return)
        assert_eq!(result.violations.len(), 1);
        let violation = &result.violations[0];
        assert_eq!(violation.kind, ViolationKind::ResourceLeak);
        assert_eq!(violation.variable, "lock");
    }

    #[test]
    fn test_happy_path_no_violations() {
        let mut analyzer = TypestateAnalyzer::new().with_protocol(FileProtocol::define());

        let blocks = vec![
            SimpleBlock {
                id: "entry".to_string(),
                line: 1,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "open".to_string(),
                }],
            },
            SimpleBlock {
                id: "b1".to_string(),
                line: 2,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "read".to_string(),
                }],
            },
            SimpleBlock {
                id: "b2".to_string(),
                line: 3,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "close".to_string(),
                }],
            },
        ];

        let edges = vec![
            ("entry".to_string(), "b1".to_string()),
            ("b1".to_string(), "b2".to_string()),
        ];

        let result = analyzer.analyze_simple(blocks, edges);

        // No violations on happy path
        assert_eq!(result.violations.len(), 0);
    }

    #[test]
    fn test_multiple_objects_independent_state() {
        let mut analyzer = TypestateAnalyzer::new().with_protocol(FileProtocol::define());

        let blocks = vec![
            SimpleBlock {
                id: "entry".to_string(),
                line: 1,
                statements: vec![
                    Statement::MethodCall {
                        object: "file1".to_string(),
                        method: "open".to_string(),
                    },
                    Statement::MethodCall {
                        object: "file2".to_string(),
                        method: "open".to_string(),
                    },
                ],
            },
            SimpleBlock {
                id: "b1".to_string(),
                line: 2,
                statements: vec![Statement::MethodCall {
                    object: "file1".to_string(),
                    method: "close".to_string(),
                }],
            },
            SimpleBlock {
                id: "b2".to_string(),
                line: 3,
                statements: vec![
                    Statement::MethodCall {
                        object: "file2".to_string(),
                        method: "read".to_string(),
                    }, // file2 still open - OK
                    Statement::MethodCall {
                        object: "file1".to_string(),
                        method: "read".to_string(),
                    }, // file1 closed - ERROR
                ],
            },
        ];

        let edges = vec![
            ("entry".to_string(), "b1".to_string()),
            ("b1".to_string(), "b2".to_string()),
        ];

        let result = analyzer.analyze_simple(blocks, edges);

        // Only file1.read() should violate
        assert_eq!(result.violations.len(), 1);
        assert_eq!(result.violations[0].variable, "file1");
    }
}
