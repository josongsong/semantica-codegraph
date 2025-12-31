//! Inter-Variable Relationship Tracker (SOTA v2.1)
//!
//! Tracks relationships between variables for transitive inference.
//!
//! # Capabilities
//!
//! - **Transitive Inference**: x < y && y < z ⟹ x < z
//! - **Equality Propagation**: x == y && y == 5 ⟹ x == 5
//! - **Contradiction Detection**: x < y && y < x ⟹ Infeasible
//! - **Constant Propagation**: x == y, SCCP[y] = 5 ⟹ x = 5
//!
//! # Performance
//!
//! - Max variables: 20 (configurable)
//! - Max transitive depth: 3 (prevents exponential explosion)
//! - Time complexity: O(n²) worst case with depth limit
//! - Space complexity: O(n²) for relation graph
//!
//! # Examples
//!
//! ```text
//! use codegraph_ir::features::smt::infrastructure::InterVariableTracker;
//! use codegraph_ir::features::smt::domain::ComparisonOp;
//!
//! let mut tracker = InterVariableTracker::new();
//!
//! // Add relations
//! tracker.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
//! tracker.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());
//!
//! // Infer transitive relation
//! assert!(tracker.can_infer_lt("x", "z")); // x < y && y < z ⟹ x < z
//!
//! // Detect contradiction
//! let result = tracker.add_relation("z".to_string(), ComparisonOp::Lt, "x".to_string());
//! assert!(!result); // Cycle detected!
//! ```

use crate::features::smt::domain::{ComparisonOp, ConstValue, VarId};
use std::collections::{HashMap, HashSet};

/// Relationship type between two variables
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Relation {
    /// Less than: x < y
    Lt,
    /// Less than or equal: x <= y
    Le,
    /// Greater than: x > y
    Gt,
    /// Greater than or equal: x >= y
    Ge,
    /// Equal: x == y
    Eq,
    /// Not equal: x != y
    Neq,
}

impl Relation {
    /// Get inverse relation
    pub fn inverse(self) -> Self {
        match self {
            Relation::Lt => Relation::Gt,
            Relation::Le => Relation::Ge,
            Relation::Gt => Relation::Lt,
            Relation::Ge => Relation::Le,
            Relation::Eq => Relation::Eq,
            Relation::Neq => Relation::Neq,
        }
    }
}

/// Inter-variable relationship tracker
pub struct InterVariableTracker {
    /// Direct relations: (x, y) → Relation
    /// Invariant: If (x, y) → R exists, then (y, x) → R.inverse() exists
    relations: HashMap<(VarId, VarId), Relation>,

    /// Equality classes (Union-Find structure)
    /// All variables in same class are equal
    equality_classes: HashMap<VarId, HashSet<VarId>>,

    /// Inferred constants from equality propagation
    /// x == y && SCCP[y] = 5 ⟹ inferred_constants[x] = 5
    inferred_constants: HashMap<VarId, ConstValue>,

    /// Transitive closure cache for performance
    /// (x, y, depth) → can_infer_lt result
    transitive_cache: HashMap<(VarId, VarId), bool>,

    /// All tracked variables
    variables: HashSet<VarId>,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Performance limits
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    /// Maximum number of variables to track
    max_variables: usize,

    /// Maximum depth for transitive inference
    max_depth: usize,

    /// Contradiction flag
    has_contradiction: bool,
}

impl Default for InterVariableTracker {
    fn default() -> Self {
        Self::new()
    }
}

impl InterVariableTracker {
    /// Create new inter-variable tracker
    pub fn new() -> Self {
        Self {
            relations: HashMap::new(),
            equality_classes: HashMap::new(),
            inferred_constants: HashMap::new(),
            transitive_cache: HashMap::new(),
            variables: HashSet::new(),
            max_variables: 20,
            max_depth: 3,
            has_contradiction: false,
        }
    }

    /// Create with custom limits
    pub fn with_limits(max_variables: usize, max_depth: usize) -> Self {
        Self {
            max_variables,
            max_depth,
            ..Self::new()
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Core API
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Add relation between two variables
    ///
    /// Returns false if contradiction detected
    pub fn add_relation(&mut self, x: VarId, op: ComparisonOp, y: VarId) -> bool {
        if self.has_contradiction {
            return false;
        }

        // Check variable limit
        self.variables.insert(x.clone());
        self.variables.insert(y.clone());

        if self.variables.len() > self.max_variables {
            // Conservative: ignore new variables beyond limit
            return true;
        }

        // Convert to Relation
        let relation = match op {
            ComparisonOp::Lt => Relation::Lt,
            ComparisonOp::Le => Relation::Le,
            ComparisonOp::Gt => Relation::Gt,
            ComparisonOp::Ge => Relation::Ge,
            ComparisonOp::Eq => Relation::Eq,
            ComparisonOp::Neq => Relation::Neq,
            _ => return true, // Ignore other ops
        };

        // Handle equality specially (union-find)
        if relation == Relation::Eq {
            return self.add_equality(x, y);
        }

        // Check for contradictions before adding
        if !self.check_consistency(&x, &y, relation) {
            self.has_contradiction = true;
            return false;
        }

        // Add relation (bidirectional)
        self.relations.insert((x.clone(), y.clone()), relation);
        self.relations
            .insert((y.clone(), x.clone()), relation.inverse());

        // Invalidate cache
        self.transitive_cache.clear();

        true
    }

    /// Check if path is feasible
    pub fn is_feasible(&self) -> bool {
        !self.has_contradiction
    }

    /// Get inferred constant for variable (if any)
    pub fn get_inferred_constant(&self, var: &VarId) -> Option<&ConstValue> {
        self.inferred_constants.get(var)
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Transitive Inference
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Check if can infer x < y transitively
    pub fn can_infer_lt(&self, x: &VarId, y: &VarId) -> bool {
        self.can_infer_relation(x, y, Relation::Lt)
    }

    /// Check if can infer x > y transitively
    pub fn can_infer_gt(&self, x: &VarId, y: &VarId) -> bool {
        self.can_infer_relation(x, y, Relation::Gt)
    }

    /// Check if can infer x == y transitively
    pub fn can_infer_eq(&self, x: &VarId, y: &VarId) -> bool {
        // Same variable
        if x == y {
            return true;
        }

        // Check equality classes
        if let Some(class) = self.equality_classes.get(x) {
            if class.contains(y) {
                return true;
            }
        }

        false
    }

    /// Generic transitive inference with depth limit
    fn can_infer_relation(&self, x: &VarId, y: &VarId, target_rel: Relation) -> bool {
        // Check cache
        let cache_key = (x.clone(), y.clone());
        if target_rel == Relation::Lt {
            if let Some(&result) = self.transitive_cache.get(&cache_key) {
                return result;
            }
        }

        let result = self.can_infer_relation_recursive(x, y, target_rel, self.max_depth);

        // Cache result (only for Lt to avoid explosion)
        if target_rel == Relation::Lt {
            // Can't cache in immutable context - skip caching
        }

        result
    }

    /// Recursive transitive inference with depth limit
    fn can_infer_relation_recursive(
        &self,
        x: &VarId,
        y: &VarId,
        target_rel: Relation,
        depth: usize,
    ) -> bool {
        if depth == 0 {
            return false; // Depth limit reached
        }

        // Direct relation?
        if let Some(&rel) = self.relations.get(&(x.clone(), y.clone())) {
            if rel == target_rel {
                return true;
            }
        }

        // Transitive inference through intermediates
        // x < z && z < y ⟹ x < y
        for z in &self.variables {
            if z == x || z == y {
                continue;
            }

            // Check if x <target_rel> z && z <target_rel> y
            if self.has_direct_relation(x, z, target_rel)
                && self.can_infer_relation_recursive(z, y, target_rel, depth - 1)
            {
                return true;
            }
        }

        false
    }

    /// Check if direct relation exists (no inference)
    fn has_direct_relation(&self, x: &VarId, y: &VarId, rel: Relation) -> bool {
        self.relations.get(&(x.clone(), y.clone())) == Some(&rel)
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Equality Handling (Union-Find)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Add equality relation (union-find)
    fn add_equality(&mut self, x: VarId, y: VarId) -> bool {
        // Same variable
        if x == y {
            return true;
        }

        // Get or create equality classes
        self.equality_classes.entry(x.clone()).or_insert_with(|| {
            let mut set = HashSet::new();
            set.insert(x.clone());
            set
        });

        self.equality_classes.entry(y.clone()).or_insert_with(|| {
            let mut set = HashSet::new();
            set.insert(y.clone());
            set
        });

        // Check if already in same class
        let y_in_x_class = self.equality_classes.get(&x).unwrap().contains(&y);

        // Merge classes
        if !y_in_x_class {
            // Collect all members from both classes first
            let x_members: Vec<VarId> = self
                .equality_classes
                .get(&x)
                .unwrap()
                .iter()
                .cloned()
                .collect();
            let y_members: Vec<VarId> = self
                .equality_classes
                .get(&y)
                .unwrap()
                .iter()
                .cloned()
                .collect();

            // Create merged class containing all members
            let mut merged_class: HashSet<VarId> = HashSet::new();
            for member in &x_members {
                merged_class.insert(member.clone());
            }
            for member in &y_members {
                merged_class.insert(member.clone());
            }

            // Update all members to point to the same merged class
            for member in &merged_class {
                self.equality_classes
                    .insert(member.clone(), merged_class.clone());
            }
        }

        true
    }

    /// Propagate SCCP constants through equality classes
    pub fn propagate_constants(
        &mut self,
        sccp_values: &HashMap<VarId, crate::features::smt::infrastructure::LatticeValue>,
    ) {
        for (var, value) in sccp_values {
            if let Some(const_val) = value.as_const() {
                if let Some(class) = self.equality_classes.get(var) {
                    // Propagate to all members of equality class
                    for member in class {
                        if member != var && !sccp_values.contains_key(member) {
                            self.inferred_constants
                                .insert(member.clone(), const_val.clone());
                        }
                    }
                }
            }
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Consistency Checking
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Check if adding relation would create contradiction
    fn check_consistency(&self, x: &VarId, y: &VarId, new_rel: Relation) -> bool {
        // Check for direct contradictions
        if let Some(&existing_rel) = self.relations.get(&(x.clone(), y.clone())) {
            // Same relation - OK
            if existing_rel == new_rel {
                return true;
            }

            // Contradictory relations
            match (existing_rel, new_rel) {
                // x < y && x > y
                (Relation::Lt, Relation::Gt) | (Relation::Gt, Relation::Lt) => return false,
                // x < y && x >= y
                (Relation::Lt, Relation::Ge) | (Relation::Ge, Relation::Lt) => return false,
                // x > y && x <= y
                (Relation::Gt, Relation::Le) | (Relation::Le, Relation::Gt) => return false,
                // x == y && x != y
                (Relation::Eq, Relation::Neq) | (Relation::Neq, Relation::Eq) => return false,
                _ => {}
            }
        }

        // Check for transitive contradictions
        // If x < y and we already know y < x (transitively), it's a cycle
        match new_rel {
            Relation::Lt => {
                // Adding x < y, check if y < x already exists
                if self.can_infer_lt(y, x) {
                    return false; // Cycle: x < y < ... < x
                }
            }
            Relation::Gt => {
                // Adding x > y, check if x < y already exists
                if self.can_infer_lt(x, y) {
                    return false;
                }
            }
            Relation::Neq => {
                // Adding x != y, check if they are already in the same equality class
                if self.can_infer_eq(x, y) {
                    return false; // Contradiction: x == y && x != y
                }
            }
            _ => {}
        }

        true
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Utility
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Reset all state
    pub fn clear(&mut self) {
        self.relations.clear();
        self.equality_classes.clear();
        self.inferred_constants.clear();
        self.transitive_cache.clear();
        self.variables.clear();
        self.has_contradiction = false;
    }

    /// Get number of tracked variables
    pub fn variable_count(&self) -> usize {
        self.variables.len()
    }

    /// Get number of direct relations
    pub fn relation_count(&self) -> usize {
        self.relations.len() / 2 // Bidirectional, so divide by 2
    }

    /// Check if has contradiction
    pub fn has_contradiction(&self) -> bool {
        self.has_contradiction
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_transitive_inference_basic() {
        let mut tracker = InterVariableTracker::new();

        // x < y
        assert!(tracker.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string()));
        // y < z
        assert!(tracker.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string()));

        // Should infer x < z
        assert!(tracker.can_infer_lt(&"x".to_string(), &"z".to_string()));
        assert!(tracker.is_feasible());
    }

    #[test]
    fn test_cycle_detection() {
        let mut tracker = InterVariableTracker::new();

        // x < y
        tracker.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
        // y < z
        tracker.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());
        // z < x - CYCLE!
        let result = tracker.add_relation("z".to_string(), ComparisonOp::Lt, "x".to_string());

        assert!(!result);
        assert!(!tracker.is_feasible());
    }

    #[test]
    fn test_equality_propagation() {
        use crate::features::smt::infrastructure::LatticeValue;

        let mut tracker = InterVariableTracker::new();

        // x == y
        tracker.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());

        // SCCP: y = 5
        let mut sccp = HashMap::new();
        sccp.insert("y".to_string(), LatticeValue::Constant(ConstValue::Int(5)));

        tracker.propagate_constants(&sccp);

        // Should infer x = 5
        assert_eq!(
            tracker.get_inferred_constant(&"x".to_string()),
            Some(&ConstValue::Int(5))
        );
    }

    #[test]
    fn test_deep_transitive_chain() {
        let mut tracker = InterVariableTracker::new();

        // a < b < c < d
        tracker.add_relation("a".to_string(), ComparisonOp::Lt, "b".to_string());
        tracker.add_relation("b".to_string(), ComparisonOp::Lt, "c".to_string());
        tracker.add_relation("c".to_string(), ComparisonOp::Lt, "d".to_string());

        // Should infer a < d (depth 3)
        assert!(tracker.can_infer_lt(&"a".to_string(), &"d".to_string()));
    }

    #[test]
    fn test_equality_class_merge() {
        let mut tracker = InterVariableTracker::new();

        // x == y
        tracker.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
        // y == z
        tracker.add_relation("y".to_string(), ComparisonOp::Eq, "z".to_string());

        // Should infer x == z
        assert!(tracker.can_infer_eq(&"x".to_string(), &"z".to_string()));
        assert!(tracker.can_infer_eq(&"z".to_string(), &"x".to_string()));
    }

    #[test]
    fn test_variable_limit() {
        let mut tracker = InterVariableTracker::with_limits(3, 3);

        // Add 3 variables - OK
        tracker.add_relation("x1".to_string(), ComparisonOp::Lt, "x2".to_string());
        tracker.add_relation("x2".to_string(), ComparisonOp::Lt, "x3".to_string());

        assert_eq!(tracker.variable_count(), 3);

        // Try to add 4th - should be ignored conservatively
        tracker.add_relation("x3".to_string(), ComparisonOp::Lt, "x4".to_string());

        assert_eq!(tracker.variable_count(), 4); // Added but...
                                                 // Should still work conservatively
        assert!(tracker.is_feasible());
    }

    #[test]
    fn test_contradiction_neq_eq() {
        let mut tracker = InterVariableTracker::new();

        // x == y
        tracker.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
        // x != y - contradiction!
        let result = tracker.add_relation("x".to_string(), ComparisonOp::Neq, "y".to_string());

        assert!(!result);
        assert!(!tracker.is_feasible());
    }
}
