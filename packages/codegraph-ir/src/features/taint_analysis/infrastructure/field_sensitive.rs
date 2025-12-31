/*
 * Field-Sensitive Taint Analysis
 *
 * Tracks taint at field/element granularity:
 * - Object fields: obj.field1 vs obj.field2
 * - Array elements: arr[0] vs arr[1]
 * - Container values: dict['key1'] vs dict['key2']
 *
 * Key insight: Different fields can have different taint status!
 *
 * Performance target: 10-20x faster than Python implementation
 * - Python: ~2000 LOC with dict-based state tracking
 * - Rust: FxHashMap + memory-efficient field tracking
 *
 * Reference:
 * - Python: field_sensitive_taint.py
 * - "Field-Sensitive Program Analysis" (Whaley & Lam, 2004)
 * - "Effective Field-Sensitive Taint Analysis" (Tripp et al., 2014)
 */

use rustc_hash::FxHashMap;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};

use crate::features::data_flow::infrastructure::dfg::DataFlowGraph;
use crate::features::flow_graph::infrastructure::cfg::{CFGEdge, CFGEdgeType};

/// Field or array element identifier
///
/// Examples:
/// - Field(var="user", field="name") → user.name
/// - Element(var="arr", index=0) → arr[0]
/// - NestedField(var="obj", path=["a", "b"]) → obj.a.b
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum FieldIdentifier {
    /// Object field access: obj.field
    Field { var: String, field: String },

    /// Array element access: arr[index]
    Element { var: String, index: i64 },

    /// Nested field access: obj.a.b.c
    NestedField { var: String, path: Vec<String> },

    /// Variable itself (whole object)
    Variable(String),
}

impl FieldIdentifier {
    /// Create field identifier
    pub fn field(var: impl Into<String>, field: impl Into<String>) -> Self {
        Self::Field {
            var: var.into(),
            field: field.into(),
        }
    }

    /// Create element identifier
    pub fn element(var: impl Into<String>, index: i64) -> Self {
        Self::Element {
            var: var.into(),
            index,
        }
    }

    /// Create variable identifier
    pub fn variable(var: impl Into<String>) -> Self {
        Self::Variable(var.into())
    }

    /// Get the base variable name
    pub fn base_var(&self) -> &str {
        match self {
            Self::Field { var, .. } => var,
            Self::Element { var, .. } => var,
            Self::NestedField { var, .. } => var,
            Self::Variable(var) => var,
        }
    }
}

/// Field-level taint state
///
/// Tracks taint for:
/// - Variables (whole objects)
/// - Fields (object.field)
/// - Elements (array[index])
///
/// Example:
///   user = get_user()          # user is clean
///   user.name = tainted        # user.name is TAINTED
///   user.id = 123              # user.id is CLEAN
#[derive(Debug, Clone, Default)]
pub struct FieldTaintState {
    /// Variable-level taint (whole object)
    variable_taint: FxHashMap<String, bool>,

    /// Field-level taint: {(var, field): is_tainted}
    field_taint: FxHashMap<(String, String), bool>,

    /// Element-level taint: {(var, index): is_tainted}
    element_taint: FxHashMap<(String, i64), bool>,

    /// Nested field taint: {(var, path): is_tainted}
    nested_field_taint: FxHashMap<(String, Vec<String>), bool>,

    /// Taint sources for debugging
    taint_sources: FxHashMap<String, Vec<String>>,
}

impl FieldTaintState {
    /// Create new empty state
    pub fn new() -> Self {
        Self::default()
    }

    /// Check if identifier is tainted
    ///
    /// Priority:
    /// 1. Most specific (nested field, element, field)
    /// 2. Variable-level (whole object)
    ///
    /// Examples:
    ///   is_tainted(&Field{var: "user", field: "name"})  // user.name
    ///   is_tainted(&Element{var: "arr", index: 0})      // arr[0]
    ///   is_tainted(&Variable("user"))                   // whole user object
    pub fn is_tainted(&self, ident: &FieldIdentifier) -> bool {
        match ident {
            FieldIdentifier::Field { var, field } => {
                // Check field-level first (most precise)
                if let Some(&tainted) = self.field_taint.get(&(var.clone(), field.clone())) {
                    return tainted;
                }
                // Fallback to variable-level
                self.variable_taint.get(var).copied().unwrap_or(false)
            }

            FieldIdentifier::Element { var, index } => {
                // Check element-level first
                if let Some(&tainted) = self.element_taint.get(&(var.clone(), *index)) {
                    return tainted;
                }
                // Fallback to variable-level
                self.variable_taint.get(var).copied().unwrap_or(false)
            }

            FieldIdentifier::NestedField { var, path } => {
                // Check nested field first
                if let Some(&tainted) = self.nested_field_taint.get(&(var.clone(), path.clone())) {
                    return tainted;
                }
                // Try parent paths (e.g., obj.a if obj.a.b not found)
                for i in (1..path.len()).rev() {
                    let parent_path = path[..i].to_vec();
                    if let Some(&tainted) = self.nested_field_taint.get(&(var.clone(), parent_path))
                    {
                        return tainted;
                    }
                }
                // Fallback to variable-level
                self.variable_taint.get(var).copied().unwrap_or(false)
            }

            FieldIdentifier::Variable(var) => {
                self.variable_taint.get(var).copied().unwrap_or(false)
            }
        }
    }

    /// Set taint status for identifier
    pub fn set_taint(&mut self, ident: &FieldIdentifier, is_tainted: bool) {
        match ident {
            FieldIdentifier::Field { var, field } => {
                self.field_taint
                    .insert((var.clone(), field.clone()), is_tainted);
            }

            FieldIdentifier::Element { var, index } => {
                self.element_taint.insert((var.clone(), *index), is_tainted);
            }

            FieldIdentifier::NestedField { var, path } => {
                self.nested_field_taint
                    .insert((var.clone(), path.clone()), is_tainted);
            }

            FieldIdentifier::Variable(var) => {
                self.variable_taint.insert(var.clone(), is_tainted);
            }
        }
    }

    /// Record taint source for debugging
    pub fn add_source(&mut self, var: &str, source: String) {
        self.taint_sources
            .entry(var.to_string())
            .or_default()
            .push(source);
    }

    /// Merge another state (for join points in CFG)
    ///
    /// Strategy: Conservative merge (union of tainted fields)
    pub fn merge(&mut self, other: &FieldTaintState) {
        // Merge variable taint
        for (var, &tainted) in &other.variable_taint {
            if tainted {
                self.variable_taint.insert(var.clone(), true);
            }
        }

        // Merge field taint
        for (key, &tainted) in &other.field_taint {
            if tainted {
                self.field_taint.insert(key.clone(), true);
            }
        }

        // Merge element taint
        for (key, &tainted) in &other.element_taint {
            if tainted {
                self.element_taint.insert(key.clone(), true);
            }
        }

        // Merge nested field taint
        for (key, &tainted) in &other.nested_field_taint {
            if tainted {
                self.nested_field_taint.insert(key.clone(), true);
            }
        }

        // Merge sources
        for (var, sources) in &other.taint_sources {
            self.taint_sources
                .entry(var.clone())
                .or_default()
                .extend(sources.clone());
        }
    }

    /// Get all tainted variables (for reporting)
    pub fn get_tainted_vars(&self) -> Vec<String> {
        let mut result = HashSet::new();

        // Variable-level
        for (var, &tainted) in &self.variable_taint {
            if tainted {
                result.insert(var.clone());
            }
        }

        // Field-level
        for ((var, _), &tainted) in &self.field_taint {
            if tainted {
                result.insert(var.clone());
            }
        }

        // Element-level
        for ((var, _), &tainted) in &self.element_taint {
            if tainted {
                result.insert(var.clone());
            }
        }

        // Nested field-level
        for ((var, _), &tainted) in &self.nested_field_taint {
            if tainted {
                result.insert(var.clone());
            }
        }

        result.into_iter().collect()
    }
}

/// Vulnerability with field-level precision
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FieldSensitiveVulnerability {
    /// Sink node ID
    pub sink: String,

    /// Tainted variable
    pub tainted_var: String,

    /// Tainted field (if applicable)
    pub tainted_field: Option<String>,

    /// Tainted element index (if applicable)
    pub tainted_index: Option<i64>,

    /// Nested field path (if applicable)
    pub nested_path: Option<Vec<String>>,

    /// Taint sources
    pub sources: Vec<String>,

    /// Severity (high, medium, low)
    pub severity: String,

    /// Path from source to sink
    pub path: Vec<String>,
}

/// Field-Sensitive Taint Analyzer
///
/// Tracks taint at field/element granularity for higher precision.
///
/// Example:
///   user = get_user()          // user is clean
///   user.name = tainted        // user.name is TAINTED
///   user.id = 123              // user.id is CLEAN
///
///   execute(user.id)           // Safe! (user.id is clean)
///   execute(user.name)         // Vulnerable! (user.name is tainted)
pub struct FieldSensitiveTaintAnalyzer {
    /// Control Flow Graph edges
    cfg_edges: Vec<CFGEdge>,

    /// Data Flow Graph
    dfg: Option<DataFlowGraph>,

    /// States at each CFG node
    states: FxHashMap<String, FieldTaintState>,

    /// Worklist for fixpoint iteration
    worklist: VecDeque<String>,

    /// Parent map for path reconstruction (child → parent)
    parent_map: FxHashMap<String, String>,
}

impl FieldSensitiveTaintAnalyzer {
    /// Create new analyzer
    pub fn new(cfg_edges: Option<Vec<CFGEdge>>, dfg: Option<DataFlowGraph>) -> Self {
        Self {
            cfg_edges: cfg_edges.unwrap_or_default(),
            dfg,
            states: FxHashMap::default(),
            worklist: VecDeque::new(),
            parent_map: FxHashMap::default(),
        }
    }

    /// Run field-sensitive taint analysis
    ///
    /// Args:
    ///   sources: Taint sources with field info
    ///     Example: {Variable("user"): ["request.get('name')"]}
    ///              {Field{var: "user", field: "password"}: ["env.get('PWD')"]}
    ///   sinks: Sink node IDs
    ///   sanitizers: Sanitizing functions (optional)
    ///
    /// Returns:
    ///   List of vulnerabilities with field-level precision
    pub fn analyze(
        &mut self,
        sources: HashMap<FieldIdentifier, Vec<String>>,
        sinks: HashSet<String>,
        sanitizers: Option<HashSet<String>>,
    ) -> Result<Vec<FieldSensitiveVulnerability>, String> {
        if self.cfg_edges.is_empty() || self.dfg.is_none() {
            return Err("CFG edges and DFG are required for analysis".to_string());
        }

        let sanitizers = sanitizers.unwrap_or_default();

        // Initialize entry state
        let mut entry_state = FieldTaintState::new();
        for (ident, source_list) in &sources {
            entry_state.set_taint(ident, true);
            for source in source_list {
                entry_state.add_source(ident.base_var(), source.clone());
            }
        }

        // Get entry node from CFG
        let entry_node = self.get_entry_node()?;
        self.states.insert(entry_node.clone(), entry_state);
        self.worklist.push_back(entry_node.clone());

        // Fixpoint iteration
        while let Some(node_id) = self.worklist.pop_front() {
            let current_state = self
                .states
                .get(&node_id)
                .cloned()
                .ok_or_else(|| format!("No state for node {}", node_id))?;

            // Transfer function (process node)
            let new_state = self.transfer(&node_id, &current_state, &sanitizers)?;

            // Propagate to successors
            for succ in self.get_successors(&node_id)? {
                // Record parent for path reconstruction
                self.parent_map
                    .entry(succ.clone())
                    .or_insert_with(|| node_id.clone());

                let changed = self.propagate_state(&succ, &new_state);
                if changed && !self.worklist.contains(&succ) {
                    self.worklist.push_back(succ);
                }
            }
        }

        // Detect vulnerabilities at sinks
        let mut vulnerabilities = Vec::new();
        for sink in &sinks {
            if let Some(state) = self.states.get(sink) {
                for tainted_var in state.get_tainted_vars() {
                    // Check field-level details
                    let (field, index, nested) = self.get_field_details(&tainted_var, state);

                    let vuln = FieldSensitiveVulnerability {
                        sink: sink.clone(),
                        tainted_var: tainted_var.clone(),
                        tainted_field: field,
                        tainted_index: index,
                        nested_path: nested,
                        sources: state
                            .taint_sources
                            .get(&tainted_var)
                            .cloned()
                            .unwrap_or_default(),
                        severity: "high".to_string(),
                        path: self.reconstruct_path(sink),
                    };

                    vulnerabilities.push(vuln);
                }
            }
        }

        Ok(vulnerabilities)
    }

    /// Transfer function: Process a single node (SOTA-grade)
    ///
    /// Implements field-sensitive taint propagation using DFG:
    /// 1. Assignment: x.field = y.field → field-level taint transfer
    /// 2. Sanitizer calls: sanitize(x.field) → untaint specific field
    /// 3. Field access: z = x.field → propagate field taint to variable
    /// 4. Field assignment: x.field = tainted → taint only that field
    fn transfer(
        &self,
        node_id: &str,
        state: &FieldTaintState,
        sanitizers: &HashSet<String>,
    ) -> Result<FieldTaintState, String> {
        let mut new_state = state.clone();

        // Use DFG to analyze data flow at this node
        if let Some(dfg) = &self.dfg {
            // Process all def-use edges that involve this node
            for (def_idx, use_idx) in &dfg.def_use_edges {
                let def_node = &dfg.nodes[*def_idx];
                let use_node = &dfg.nodes[*use_idx];

                // Extract variable names and field info
                let def_var = &def_node.variable_name;
                let use_var = &use_node.variable_name;

                // CASE 1: Assignment propagation (x = y)
                // If RHS (use) is tainted, LHS (def) becomes tainted
                if use_node.span.start_line.to_string().contains(node_id) {
                    // Check if source variable is tainted
                    let use_ident = FieldIdentifier::variable(use_var);
                    if new_state.is_tainted(&use_ident) {
                        // Propagate taint to destination
                        let def_ident = FieldIdentifier::variable(def_var);
                        new_state.set_taint(&def_ident, true);
                    }
                }

                // CASE 2: Field-level assignment (x.field = y.field)
                // Parse field access from variable name (e.g., "user.name")
                if def_var.contains('.') {
                    let parts: Vec<&str> = def_var.split('.').collect();
                    if parts.len() == 2 {
                        let base = parts[0];
                        let field = parts[1];

                        // Check if RHS is tainted
                        if use_var.contains('.') {
                            let use_parts: Vec<&str> = use_var.split('.').collect();
                            if use_parts.len() == 2 {
                                let use_ident = FieldIdentifier::field(use_parts[0], use_parts[1]);
                                if new_state.is_tainted(&use_ident) {
                                    // Taint only the specific field
                                    let def_ident = FieldIdentifier::field(base, field);
                                    new_state.set_taint(&def_ident, true);
                                }
                            }
                        } else {
                            // Whole variable → field assignment
                            let use_ident = FieldIdentifier::variable(use_var);
                            if new_state.is_tainted(&use_ident) {
                                let def_ident = FieldIdentifier::field(base, field);
                                new_state.set_taint(&def_ident, true);
                            }
                        }
                    }
                }

                // CASE 3: Field read (y = x.field)
                // Extract taint from specific field to whole variable
                if use_var.contains('.') {
                    let parts: Vec<&str> = use_var.split('.').collect();
                    if parts.len() == 2 {
                        let use_ident = FieldIdentifier::field(parts[0], parts[1]);
                        if new_state.is_tainted(&use_ident) {
                            // Field is tainted → destination becomes tainted
                            let def_ident = FieldIdentifier::variable(def_var);
                            new_state.set_taint(&def_ident, true);
                        }
                    }
                }

                // CASE 4: Sanitizer detection
                // Check if this is a sanitizer call affecting a variable
                for sanitizer in sanitizers {
                    if use_var.contains(sanitizer) || def_var.contains(sanitizer) {
                        // Sanitizer called on this variable → untaint it
                        if use_var.contains('.') {
                            let parts: Vec<&str> = use_var.split('.').collect();
                            if parts.len() == 2 {
                                let ident = FieldIdentifier::field(parts[0], parts[1]);
                                new_state.set_taint(&ident, false);
                            }
                        } else {
                            let ident = FieldIdentifier::variable(use_var);
                            new_state.set_taint(&ident, false);
                        }
                    }
                }
            }

            // CASE 5: Array element tracking (arr[0] = tainted)
            for node in &dfg.nodes {
                let var_name = &node.variable_name;

                // Detect array indexing pattern: "arr[0]"
                if var_name.contains('[') && var_name.contains(']') {
                    if let Some(start) = var_name.find('[') {
                        if let Some(end) = var_name.find(']') {
                            let base = &var_name[..start];
                            let index_str = &var_name[start + 1..end];

                            if let Ok(index) = index_str.parse::<i64>() {
                                // Check if element is tainted
                                let base_ident = FieldIdentifier::variable(base);
                                if new_state.is_tainted(&base_ident) {
                                    // Propagate to element
                                    let elem_ident = FieldIdentifier::element(base, index);
                                    new_state.set_taint(&elem_ident, true);
                                }
                            }
                        }
                    }
                }
            }
        }

        Ok(new_state)
    }

    /// Propagate state to successor node
    fn propagate_state(&mut self, succ: &str, state: &FieldTaintState) -> bool {
        if let Some(existing) = self.states.get_mut(succ) {
            let old_size = existing.variable_taint.len() + existing.field_taint.len();
            existing.merge(state);
            let new_size = existing.variable_taint.len() + existing.field_taint.len();
            new_size > old_size
        } else {
            self.states.insert(succ.to_string(), state.clone());
            true
        }
    }

    /// Get entry node from CFG
    fn get_entry_node(&self) -> Result<String, String> {
        // Entry is the source of the first unconditional edge or first edge
        for edge in &self.cfg_edges {
            if matches!(edge.edge_type, CFGEdgeType::Unconditional) {
                return Ok(edge.source_block_id.clone());
            }
        }

        // Fallback: first edge source
        self.cfg_edges
            .first()
            .map(|e| e.source_block_id.clone())
            .ok_or_else(|| "No entry node found in CFG".to_string())
    }

    /// Get successors of a node
    fn get_successors(&self, node_id: &str) -> Result<Vec<String>, String> {
        // Find all edges from this node
        let successors: Vec<String> = self
            .cfg_edges
            .iter()
            .filter(|e| e.source_block_id == node_id)
            .map(|e| e.target_block_id.clone())
            .collect();

        Ok(successors)
    }

    /// Reconstruct path from source to sink using parent map
    ///
    /// Performs backward slicing from sink to entry node.
    ///
    /// Returns: Ordered list of node IDs (Source → ... → Sink)
    fn reconstruct_path(&self, sink: &str) -> Vec<String> {
        let mut path = vec![sink.to_string()];
        let mut current = sink;

        // Backtrack using parent map
        while let Some(parent) = self.parent_map.get(current) {
            path.push(parent.clone());
            current = parent;

            // Prevent infinite loops (cycle detection)
            if path.len() > 1000 {
                break;
            }
        }

        // Reverse to get Source → Sink order
        path.reverse();
        path
    }

    /// Get field-level details for reporting
    fn get_field_details(
        &self,
        var: &str,
        state: &FieldTaintState,
    ) -> (Option<String>, Option<i64>, Option<Vec<String>>) {
        // Check if specific field is tainted
        for ((v, field), &tainted) in &state.field_taint {
            if v == var && tainted {
                return (Some(field.clone()), None, None);
            }
        }

        // Check if specific element is tainted
        for ((v, index), &tainted) in &state.element_taint {
            if v == var && tainted {
                return (None, Some(*index), None);
            }
        }

        // Check if nested field is tainted
        for ((v, path), &tainted) in &state.nested_field_taint {
            if v == var && tainted {
                return (None, None, Some(path.clone()));
            }
        }

        (None, None, None)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_field_identifier() {
        let ident = FieldIdentifier::field("user", "name");
        assert_eq!(ident.base_var(), "user");

        let ident = FieldIdentifier::element("arr", 0);
        assert_eq!(ident.base_var(), "arr");
    }

    #[test]
    fn test_field_taint_state() {
        let mut state = FieldTaintState::new();

        // Set variable-level taint
        state.set_taint(&FieldIdentifier::variable("user"), true);
        assert!(state.is_tainted(&FieldIdentifier::variable("user")));

        // Set field-level taint
        state.set_taint(&FieldIdentifier::field("user", "name"), true);
        assert!(state.is_tainted(&FieldIdentifier::field("user", "name")));

        // Clean field should not be tainted (even if variable is)
        state.set_taint(&FieldIdentifier::field("user", "id"), false);
        assert!(!state.is_tainted(&FieldIdentifier::field("user", "id")));
    }

    #[test]
    fn test_state_merge() {
        let mut state1 = FieldTaintState::new();
        state1.set_taint(&FieldIdentifier::field("user", "name"), true);

        let mut state2 = FieldTaintState::new();
        state2.set_taint(&FieldIdentifier::field("user", "id"), true);

        state1.merge(&state2);

        // Both fields should be tainted after merge
        assert!(state1.is_tainted(&FieldIdentifier::field("user", "name")));
        assert!(state1.is_tainted(&FieldIdentifier::field("user", "id")));
    }
}
