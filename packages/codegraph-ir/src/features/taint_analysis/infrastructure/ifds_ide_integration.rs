/*
 * IFDS/IDE Integration and Usage Examples
 *
 * This module provides practical examples of how to use the IFDS/IDE framework
 * for real-world taint analysis scenarios.
 *
 * Key Features:
 * - Complete taint analysis problem implementation
 * - Integration with existing IR
 * - Practical usage examples
 * - Best practices and patterns
 */

use rustc_hash::FxHashMap;
use std::collections::HashSet;

use super::ide_framework::{EdgeFunction, IDEProblem, IDEValue};
use super::ide_solver::IDESolver;
use super::ifds_framework::{DataflowFact, FlowFunction, IFDSProblem};
use super::ifds_solver::{CFGEdge, IFDSSolver, CFG};

/// Example: Complete Taint Fact for Production Use
///
/// Represents a tainted variable with source information.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum TaintFact {
    /// Zero fact (IFDS requirement)
    Zero,

    /// Tainted variable with source
    Tainted {
        /// Variable name
        variable: String,
        /// Taint source (e.g., "user_input", "network", "file")
        source: String,
    },
}

impl DataflowFact for TaintFact {
    fn is_zero(&self) -> bool {
        matches!(self, TaintFact::Zero)
    }

    fn zero() -> Self {
        TaintFact::Zero
    }
}

/// Example: Taint Severity Level (IDE Value)
///
/// Represents how dangerous a tainted value is.
/// - 0: Clean (no taint)
/// - 1-3: Low risk (sanitized input)
/// - 4-7: Medium risk (partially validated)
/// - 8-10: High risk (direct user input)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct TaintSeverity(pub u8);

impl IDEValue for TaintSeverity {
    fn top() -> Self {
        TaintSeverity(10) // Maximum severity
    }

    fn bottom() -> Self {
        TaintSeverity(0) // No taint
    }

    fn meet(&self, other: &Self) -> Self {
        // Conservative: take maximum severity
        TaintSeverity(self.0.max(other.0))
    }

    fn is_top(&self) -> bool {
        self.0 == 10
    }

    fn is_bottom(&self) -> bool {
        self.0 == 0
    }
}

/// Example: Sanitizer Edge Function
///
/// Reduces taint severity when data passes through a sanitizer.
#[derive(Debug, Clone)]
pub struct SanitizerEdgeFunction {
    /// Severity reduction amount
    pub reduction: u8,
}

impl EdgeFunction<TaintSeverity> for SanitizerEdgeFunction {
    fn apply(&self, input: &TaintSeverity) -> TaintSeverity {
        // Reduce severity, minimum 0
        let new_severity = input.0.saturating_sub(self.reduction);
        TaintSeverity(new_severity)
    }

    fn compose(
        &self,
        _other: &dyn EdgeFunction<TaintSeverity>,
    ) -> Box<dyn EdgeFunction<TaintSeverity>> {
        // Simplified: just return self
        Box::new(SanitizerEdgeFunction {
            reduction: self.reduction,
        })
    }
}

/// Example: Complete Taint Analysis Problem (IFDS)
///
/// This demonstrates how to implement a full taint analysis using IFDS.
pub struct TaintAnalysisProblem {
    /// Entry points with taint sources
    pub entry_points: Vec<(String, TaintFact)>,

    /// Sanitizer locations (node → sanitized variables)
    pub sanitizers: FxHashMap<String, HashSet<String>>,
}

impl TaintAnalysisProblem {
    pub fn new() -> Self {
        Self {
            entry_points: Vec::new(),
            sanitizers: FxHashMap::default(),
        }
    }

    /// Add taint source at entry point
    pub fn add_source(&mut self, node: String, variable: String, source: String) {
        self.entry_points
            .push((node, TaintFact::Tainted { variable, source }));
    }

    /// Add sanitizer for a variable at a node
    pub fn add_sanitizer(&mut self, node: String, variable: String) {
        self.sanitizers
            .entry(node)
            .or_insert_with(HashSet::new)
            .insert(variable);
    }
}

impl IFDSProblem<TaintFact> for TaintAnalysisProblem {
    fn initial_seeds(&self) -> Vec<(String, TaintFact)> {
        self.entry_points.clone()
    }

    fn normal_flow(&self, _from: &str, to: &str) -> Box<dyn FlowFunction<TaintFact>> {
        // Check if 'to' node has sanitizers
        if let Some(sanitized_vars) = self.sanitizers.get(to) {
            // Kill flow function for sanitized variables
            let sanitized = sanitized_vars.clone();
            Box::new(SanitizerFlowFunction { sanitized })
        } else {
            // Identity: taint propagates unchanged
            Box::new(super::ifds_framework::IdentityFlowFunction)
        }
    }

    fn call_flow(&self, _call_site: &str, _callee_entry: &str) -> Box<dyn FlowFunction<TaintFact>> {
        // Identity: taint flows into function
        Box::new(super::ifds_framework::IdentityFlowFunction)
    }

    fn return_flow(
        &self,
        _callee_exit: &str,
        _return_site: &str,
        _call_site: &str,
    ) -> Box<dyn FlowFunction<TaintFact>> {
        // Identity: taint flows out of function
        Box::new(super::ifds_framework::IdentityFlowFunction)
    }

    fn call_to_return_flow(
        &self,
        _call_site: &str,
        _return_site: &str,
    ) -> Box<dyn FlowFunction<TaintFact>> {
        // Identity: local variables pass through
        Box::new(super::ifds_framework::IdentityFlowFunction)
    }
}

/// Sanitizer flow function: kills taint for specific variables
struct SanitizerFlowFunction {
    sanitized: HashSet<String>,
}

impl FlowFunction<TaintFact> for SanitizerFlowFunction {
    fn compute(&self, input: &TaintFact) -> HashSet<TaintFact> {
        match input {
            TaintFact::Zero => HashSet::from([TaintFact::Zero]),
            TaintFact::Tainted { variable, .. } => {
                if self.sanitized.contains(variable) {
                    // Kill this taint
                    HashSet::new()
                } else {
                    // Preserve taint
                    HashSet::from([input.clone()])
                }
            }
        }
    }
}

/// Example: Complete Taint Severity Analysis Problem (IDE)
///
/// This demonstrates how to implement taint analysis with severity tracking using IDE.
pub struct TaintSeverityProblem {
    /// Entry points with initial severity
    pub entry_points: Vec<(String, TaintFact, TaintSeverity)>,

    /// Sanitizers: node → (variable → severity reduction)
    pub sanitizers: FxHashMap<String, FxHashMap<String, u8>>,
}

impl TaintSeverityProblem {
    pub fn new() -> Self {
        Self {
            entry_points: Vec::new(),
            sanitizers: FxHashMap::default(),
        }
    }

    /// Add taint source with initial severity
    pub fn add_source(&mut self, node: String, variable: String, source: String, severity: u8) {
        self.entry_points.push((
            node,
            TaintFact::Tainted { variable, source },
            TaintSeverity(severity),
        ));
    }

    /// Add sanitizer that reduces severity
    pub fn add_sanitizer(&mut self, node: String, variable: String, reduction: u8) {
        self.sanitizers
            .entry(node)
            .or_insert_with(FxHashMap::default)
            .insert(variable, reduction);
    }
}

impl IDEProblem<TaintFact, TaintSeverity> for TaintSeverityProblem {
    fn initial_seeds(&self) -> Vec<(String, TaintFact, TaintSeverity)> {
        self.entry_points.clone()
    }

    fn normal_edge_function(
        &self,
        _from: &str,
        to: &str,
        _source: &TaintFact,
        target: &TaintFact,
    ) -> Box<dyn EdgeFunction<TaintSeverity>> {
        // Check if target variable is sanitized at 'to' node
        if let TaintFact::Tainted { variable, .. } = target {
            if let Some(node_sanitizers) = self.sanitizers.get(to) {
                if let Some(&reduction) = node_sanitizers.get(variable) {
                    // Apply sanitizer
                    return Box::new(SanitizerEdgeFunction { reduction });
                }
            }
        }

        // Identity: severity unchanged
        Box::new(super::ide_framework::IdentityEdgeFunction)
    }

    fn call_edge_function(
        &self,
        _call_site: &str,
        _callee_entry: &str,
        _source: &TaintFact,
        _target: &TaintFact,
    ) -> Box<dyn EdgeFunction<TaintSeverity>> {
        Box::new(super::ide_framework::IdentityEdgeFunction)
    }

    fn return_edge_function(
        &self,
        _callee_exit: &str,
        _return_site: &str,
        _call_site: &str,
        _source: &TaintFact,
        _target: &TaintFact,
    ) -> Box<dyn EdgeFunction<TaintSeverity>> {
        Box::new(super::ide_framework::IdentityEdgeFunction)
    }

    fn call_to_return_edge_function(
        &self,
        _call_site: &str,
        _return_site: &str,
        _source: &TaintFact,
        _target: &TaintFact,
    ) -> Box<dyn EdgeFunction<TaintSeverity>> {
        Box::new(super::ide_framework::IdentityEdgeFunction)
    }
}

/// Example Usage: Complete workflow for IFDS taint analysis
///
/// This function demonstrates the complete workflow from building a CFG
/// to running IFDS analysis and interpreting results.
pub fn run_ifds_taint_analysis_example() -> String {
    // 1. Build CFG
    let mut cfg = CFG::new();
    cfg.add_entry("main_entry");
    cfg.add_edge(CFGEdge::normal("main_entry", "line_1")); // x = user_input()
    cfg.add_edge(CFGEdge::normal("line_1", "line_2")); // y = x
    cfg.add_edge(CFGEdge::normal("line_2", "line_3")); // sanitize(y)
    cfg.add_edge(CFGEdge::normal("line_3", "line_4")); // z = y
    cfg.add_edge(CFGEdge::normal("line_4", "exit"));

    // 2. Define problem
    let mut problem = TaintAnalysisProblem::new();

    // Add taint source
    problem.add_source(
        "main_entry".to_string(),
        "x".to_string(),
        "user_input".to_string(),
    );

    // Add sanitizer at line_3
    problem.add_sanitizer("line_3".to_string(), "y".to_string());

    // 3. Run IFDS solver
    let solver = IFDSSolver::new(Box::new(problem), cfg);
    let result = solver.solve();

    // 4. Interpret results
    let mut output = String::new();
    output.push_str("IFDS Taint Analysis Results:\n");
    output.push_str("============================\n\n");

    let tainted_x = TaintFact::Tainted {
        variable: "x".to_string(),
        source: "user_input".to_string(),
    };
    let tainted_y = TaintFact::Tainted {
        variable: "y".to_string(),
        source: "user_input".to_string(),
    };

    output.push_str(&format!(
        "Tainted at main_entry: {:?}\n",
        result.is_fact_reachable("main_entry", &TaintFact::zero(), &tainted_x)
    ));
    output.push_str(&format!(
        "Tainted at line_2 (before sanitizer): {:?}\n",
        result.is_fact_reachable("line_2", &TaintFact::zero(), &tainted_y)
    ));
    output.push_str(&format!(
        "Tainted at line_4 (after sanitizer): {:?}\n",
        result.is_fact_reachable("line_4", &TaintFact::zero(), &tainted_y)
    ));

    output.push_str(&format!("\nStatistics:\n"));
    output.push_str(&format!(
        "- Exploded nodes: {}\n",
        result.stats.num_exploded_nodes
    ));
    output.push_str(&format!(
        "- Exploded edges: {}\n",
        result.stats.num_exploded_edges
    ));
    output.push_str(&format!("- Iterations: {}\n", result.stats.num_iterations));

    output
}

/// Example Usage: Complete workflow for IDE taint severity analysis
pub fn run_ide_taint_severity_example() -> String {
    // 1. Build CFG
    let mut cfg = CFG::new();
    cfg.add_entry("main_entry");
    cfg.add_edge(CFGEdge::normal("main_entry", "line_1")); // x = user_input() [severity: 10]
    cfg.add_edge(CFGEdge::normal("line_1", "line_2")); // y = x
    cfg.add_edge(CFGEdge::normal("line_2", "line_3")); // basic_sanitize(y) [reduce: 3]
    cfg.add_edge(CFGEdge::normal("line_3", "line_4")); // z = y
    cfg.add_edge(CFGEdge::normal("line_4", "line_5")); // strong_sanitize(z) [reduce: 5]
    cfg.add_edge(CFGEdge::normal("line_5", "exit"));

    // 2. Define problem
    let mut problem = TaintSeverityProblem::new();

    // Add taint source with high severity
    problem.add_source(
        "main_entry".to_string(),
        "x".to_string(),
        "user_input".to_string(),
        10, // Maximum severity
    );

    // Add sanitizers with different reduction amounts
    problem.add_sanitizer("line_3".to_string(), "y".to_string(), 3); // Basic sanitization
    problem.add_sanitizer("line_5".to_string(), "z".to_string(), 5); // Strong sanitization

    // 3. Run IDE solver
    let solver = IDESolver::new(Box::new(problem), cfg);
    let result = solver.solve();

    // 4. Interpret results
    let mut output = String::new();
    output.push_str("IDE Taint Severity Analysis Results:\n");
    output.push_str("=====================================\n\n");

    let tainted_x = TaintFact::Tainted {
        variable: "x".to_string(),
        source: "user_input".to_string(),
    };
    let tainted_y = TaintFact::Tainted {
        variable: "y".to_string(),
        source: "user_input".to_string(),
    };
    let tainted_z = TaintFact::Tainted {
        variable: "z".to_string(),
        source: "user_input".to_string(),
    };

    if let Some(severity) = result.get_value("main_entry", &tainted_x) {
        output.push_str(&format!("Severity at main_entry (x): {}\n", severity.0));
    }
    if let Some(severity) = result.get_value("line_2", &tainted_y) {
        output.push_str(&format!(
            "Severity at line_2 (y, before sanitizer): {}\n",
            severity.0
        ));
    }
    if let Some(severity) = result.get_value("line_4", &tainted_y) {
        output.push_str(&format!(
            "Severity at line_4 (y, after basic sanitizer): {}\n",
            severity.0
        ));
    }
    if let Some(severity) = result.get_value("exit", &tainted_z) {
        output.push_str(&format!(
            "Severity at exit (z, after strong sanitizer): {}\n",
            severity.0
        ));
    }

    output.push_str(&format!("\nStatistics:\n"));
    output.push_str(&format!(
        "- Value propagations: {}\n",
        result.stats.num_value_propagations
    ));
    output.push_str(&format!(
        "- Meet operations: {}\n",
        result.stats.num_meet_operations
    ));

    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_taint_fact_zero() {
        let zero = TaintFact::zero();
        assert!(zero.is_zero());
    }

    #[test]
    fn test_taint_severity_lattice() {
        let bottom = TaintSeverity::bottom();
        let top = TaintSeverity::top();
        let mid = TaintSeverity(5);

        assert!(bottom.is_bottom());
        assert!(top.is_top());
        assert!(!mid.is_bottom());
        assert!(!mid.is_top());
    }

    #[test]
    fn test_taint_severity_meet() {
        let s1 = TaintSeverity(5);
        let s2 = TaintSeverity(7);

        let result = s1.meet(&s2);
        assert_eq!(result, TaintSeverity(7)); // Max
    }

    #[test]
    fn test_sanitizer_edge_function() {
        let sanitizer = SanitizerEdgeFunction { reduction: 3 };
        let high_severity = TaintSeverity(8);

        let result = sanitizer.apply(&high_severity);
        assert_eq!(result, TaintSeverity(5)); // 8 - 3 = 5
    }

    #[test]
    fn test_sanitizer_edge_function_underflow() {
        let sanitizer = SanitizerEdgeFunction { reduction: 10 };
        let low_severity = TaintSeverity(3);

        let result = sanitizer.apply(&low_severity);
        assert_eq!(result, TaintSeverity(0)); // Saturating sub: 3 - 10 = 0
    }

    #[test]
    fn test_ifds_example_runs() {
        let output = run_ifds_taint_analysis_example();
        assert!(output.contains("IFDS Taint Analysis Results"));
        assert!(output.contains("Statistics"));
    }

    #[test]
    fn test_ide_example_runs() {
        let output = run_ide_taint_severity_example();
        assert!(output.contains("IDE Taint Severity Analysis Results"));
        assert!(output.contains("Severity"));
    }
}
