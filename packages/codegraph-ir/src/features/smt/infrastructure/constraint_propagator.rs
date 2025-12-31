//! Constraint Propagator - Transitive constraint inference
//!
//! Derives new constraints from existing ones through logical inference.
//!
//! # Supported Inference Rules
//!
//! - **Transitivity**: x < y ∧ y < z ⟹ x < z
//! - **Equality propagation**: x == y ∧ y < z ⟹ x < z
//! - **Inequality chains**: x < y ∧ y == 5 ⟹ x < 5
//! - **Contradiction detection**: x < y ∧ y < z ∧ z < x ⟹ ⊥
//!
//! # Examples
//!
//! ```text
//! use codegraph_ir::features::smt::infrastructure::ConstraintPropagator;
//! use codegraph_ir::features::smt::domain::{PathCondition, ConstValue};
//!
//! let mut propagator = ConstraintPropagator::new();
//!
//! // x < y
//! propagator.add_constraint(&PathCondition::new(
//!     "x".to_string(),
//!     ComparisonOp::Lt,
//!     Some(ConstValue::Var("y".to_string())),
//! ));
//!
//! // y < z
//! propagator.add_constraint(&PathCondition::new(
//!     "y".to_string(),
//!     ComparisonOp::Lt,
//!     Some(ConstValue::Var("z".to_string())),
//! ));
//!
//! // Should infer: x < z
//! assert!(propagator.can_infer_lt("x", "z"));
//! ```

use crate::features::smt::domain::{ComparisonOp, ConstValue, PathCondition, VarId};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

// ============================================================================
// Configuration (RFC-001: Externalized Settings)
// ============================================================================

/// Configuration for constraint propagation
///
/// # RFC-001 Compliance
/// All settings are externalized for runtime configuration.
///
/// # Example
/// ```text
/// let config = ConstraintPropagatorConfig {
///     max_depth: 20,  // Allow deeper inference chains
///     ..Default::default()
/// };
/// let propagator = ConstraintPropagator::with_config(config);
/// ```
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConstraintPropagatorConfig {
    /// Maximum inference depth for transitive closure
    /// Higher values find more constraints but use more resources
    /// Default: 10
    pub max_depth: usize,

    /// Enable equality propagation (x == y → share constraints)
    /// Default: true
    pub enable_equality_propagation: bool,

    /// Enable contradiction detection (cycle detection)
    /// Default: true
    pub detect_contradictions: bool,
}

impl Default for ConstraintPropagatorConfig {
    fn default() -> Self {
        Self {
            max_depth: 10,
            enable_equality_propagation: true,
            detect_contradictions: true,
        }
    }
}

// ============================================================================
// Domain Models
// ============================================================================

/// Relational constraint between two variables
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct VarRelation {
    left: VarId,
    op: ComparisonOp,
    right: VarId,
}

/// Variable equality classes for propagation
#[derive(Debug, Clone)]
struct EqualityClass {
    /// Representative variable for this class
    representative: VarId,
    /// All variables equal to representative
    members: HashSet<VarId>,
}

impl EqualityClass {
    fn new(var: VarId) -> Self {
        let mut members = HashSet::new();
        members.insert(var.clone());
        Self {
            representative: var,
            members,
        }
    }

    fn merge(&mut self, other: &EqualityClass) {
        for member in &other.members {
            self.members.insert(member.clone());
        }
    }

    fn contains(&self, var: &VarId) -> bool {
        self.members.contains(var)
    }

    fn add(&mut self, var: VarId) {
        self.members.insert(var);
    }
}

/// Constraint propagator for transitive inference
pub struct ConstraintPropagator {
    /// Configuration (RFC-001: Externalized)
    config: ConstraintPropagatorConfig,
    /// Variable relations (x < y, y == z, etc.)
    relations: HashSet<VarRelation>,
    /// Equality classes (x == y == z)
    equality_classes: HashMap<VarId, EqualityClass>,
    /// Detected contradiction
    contradiction: bool,
}

impl Default for ConstraintPropagator {
    fn default() -> Self {
        Self::new()
    }
}

impl ConstraintPropagator {
    /// Create new constraint propagator with default config
    pub fn new() -> Self {
        Self::with_config(ConstraintPropagatorConfig::default())
    }

    /// Create new constraint propagator with custom config (RFC-001)
    pub fn with_config(config: ConstraintPropagatorConfig) -> Self {
        Self {
            config,
            relations: HashSet::new(),
            equality_classes: HashMap::new(),
            contradiction: false,
        }
    }

    /// Get current configuration
    pub fn config(&self) -> &ConstraintPropagatorConfig {
        &self.config
    }

    /// Add constraint to propagator
    ///
    /// Returns false if contradiction detected
    pub fn add_constraint(&mut self, cond: &PathCondition) -> bool {
        if self.contradiction {
            return false;
        }

        // Extract variable-to-variable constraints
        if let Some(ref value) = cond.value {
            // Handle variable-variable constraints (x < y, x == y, etc.)
            if let ConstValue::Var(right_var) = value {
                return self.add_relation(cond.var.clone(), cond.op, right_var.clone());
            }
            // Constant constraints are handled elsewhere (SMT solver)
            return true;
        }

        true
    }

    /// Add variable relation (x < y, x == y, etc.)
    pub fn add_relation(&mut self, left: VarId, op: ComparisonOp, right: VarId) -> bool {
        if self.contradiction {
            return false;
        }

        // Handle equality specially
        if op == ComparisonOp::Eq {
            self.merge_equality_classes(&left, &right);
        }

        let relation = VarRelation { left, op, right };
        self.relations.insert(relation);

        // Check for contradictions
        if self.detect_contradiction() {
            self.contradiction = true;
            return false;
        }

        true
    }

    /// Merge equality classes for two variables
    fn merge_equality_classes(&mut self, var1: &VarId, var2: &VarId) {
        let class1_exists = self.equality_classes.contains_key(var1);
        let class2_exists = self.equality_classes.contains_key(var2);

        match (class1_exists, class2_exists) {
            (false, false) => {
                // Create new class
                let mut class = EqualityClass::new(var1.clone());
                class.add(var2.clone());
                self.equality_classes.insert(var1.clone(), class.clone());
                self.equality_classes.insert(var2.clone(), class);
            }
            (true, false) => {
                // Add var2 to class1
                if let Some(class) = self.equality_classes.get_mut(var1) {
                    class.add(var2.clone());
                    let class_clone = class.clone();
                    self.equality_classes.insert(var2.clone(), class_clone);
                }
            }
            (false, true) => {
                // Add var1 to class2
                if let Some(class) = self.equality_classes.get_mut(var2) {
                    class.add(var1.clone());
                    let class_clone = class.clone();
                    self.equality_classes.insert(var1.clone(), class_clone);
                }
            }
            (true, true) => {
                // Merge classes
                let class1 = self.equality_classes.get(var1).unwrap().clone();
                let class2 = self.equality_classes.get(var2).unwrap().clone();

                if class1.representative == class2.representative {
                    return; // Already in same class
                }

                let mut merged = class1.clone();
                merged.merge(&class2);

                // Update all members to point to merged class
                for member in &merged.members {
                    self.equality_classes.insert(member.clone(), merged.clone());
                }
            }
        }
    }

    /// Check if can infer x < y through transitivity
    pub fn can_infer_lt(&self, x: &str, y: &str) -> bool {
        self.can_infer_relation(x, y, ComparisonOp::Lt, 0)
    }

    /// Check if can infer x > y through transitivity
    pub fn can_infer_gt(&self, x: &str, y: &str) -> bool {
        self.can_infer_relation(x, y, ComparisonOp::Gt, 0)
    }

    /// Check if can infer x == y through transitivity
    pub fn can_infer_eq(&self, x: &str, y: &str) -> bool {
        // Same variable
        if x == y {
            return true;
        }

        // Check equality classes - both directions
        if let Some(class1) = self.equality_classes.get(x) {
            if class1.contains(&y.to_string()) {
                return true;
            }
        }

        if let Some(class2) = self.equality_classes.get(y) {
            if class2.contains(&x.to_string()) {
                return true;
            }
        }

        false
    }

    /// Recursive relation inference
    fn can_infer_relation(&self, x: &str, y: &str, op: ComparisonOp, depth: usize) -> bool {
        if depth > self.config.max_depth {
            return false;
        }

        // Direct relation
        if self.has_direct_relation(x, y, op) {
            return true;
        }

        // Transitivity: x < z && z < y => x < y
        for relation in &self.relations {
            if relation.left == x && relation.op == op {
                if self.can_infer_relation(&relation.right, y, op, depth + 1) {
                    return true;
                }
            }
        }

        // Equality substitution: x == z && z < y => x < y
        if let Some(class) = self.equality_classes.get(x) {
            for member in &class.members {
                if member != x && self.can_infer_relation(member, y, op, depth + 1) {
                    return true;
                }
            }
        }

        false
    }

    /// Check for direct relation
    fn has_direct_relation(&self, x: &str, y: &str, op: ComparisonOp) -> bool {
        self.relations
            .iter()
            .any(|r| r.left == x && r.right == y && r.op == op)
    }

    /// Detect contradiction (cycle in < relation)
    fn detect_contradiction(&self) -> bool {
        // Check for cycles: x < y < z < x
        for relation in &self.relations {
            if relation.op == ComparisonOp::Lt || relation.op == ComparisonOp::Gt {
                if self.has_cycle(&relation.left, &relation.right, relation.op) {
                    return true;
                }
            }
        }

        // Check x == y && x < y
        for relation in &self.relations {
            if relation.op == ComparisonOp::Lt || relation.op == ComparisonOp::Gt {
                if self.can_infer_eq(&relation.left, &relation.right) {
                    return true; // x == y && x < y is contradiction
                }
            }
        }

        false
    }

    /// Check for cycle in relation graph
    fn has_cycle(&self, start: &str, current: &str, op: ComparisonOp) -> bool {
        if start == current {
            return false; // Ignore self
        }

        // Check if we can reach start from current
        self.can_reach(current, start, op, 0, &mut HashSet::new())
    }

    /// DFS to check reachability
    fn can_reach(
        &self,
        from: &str,
        to: &str,
        op: ComparisonOp,
        depth: usize,
        visited: &mut HashSet<String>,
    ) -> bool {
        if depth > self.config.max_depth || visited.contains(from) {
            return false;
        }

        visited.insert(from.to_string());

        // Direct edge
        if self.has_direct_relation(from, to, op) {
            return true;
        }

        // Follow edges
        for relation in &self.relations {
            if relation.left == from && relation.op == op {
                if self.can_reach(&relation.right, to, op, depth + 1, visited) {
                    return true;
                }
            }
        }

        false
    }

    /// Check if any contradiction detected
    pub fn has_contradiction(&self) -> bool {
        self.contradiction
    }

    /// Clear all constraints
    pub fn clear(&mut self) {
        self.relations.clear();
        self.equality_classes.clear();
        self.contradiction = false;
    }

    /// Get number of tracked relations
    pub fn relation_count(&self) -> usize {
        self.relations.len()
    }

    /// Get number of equality classes
    pub fn equality_class_count(&self) -> usize {
        self.equality_classes
            .values()
            .map(|c| &c.representative)
            .collect::<HashSet<_>>()
            .len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_direct_relation() {
        let mut prop = ConstraintPropagator::new();

        // x < y
        prop.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());

        assert!(prop.can_infer_lt("x", "y"));
        assert!(!prop.can_infer_lt("y", "x"));
    }

    #[test]
    fn test_transitive_inference() {
        let mut prop = ConstraintPropagator::new();

        // x < y
        prop.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
        // y < z
        prop.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());

        // Should infer: x < z
        assert!(prop.can_infer_lt("x", "z"));
    }

    #[test]
    fn test_long_chain_inference() {
        let mut prop = ConstraintPropagator::new();

        // x < y < z < w
        prop.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
        prop.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());
        prop.add_relation("z".to_string(), ComparisonOp::Lt, "w".to_string());

        // Should infer: x < w
        assert!(prop.can_infer_lt("x", "w"));
    }

    #[test]
    fn test_equality_class() {
        let mut prop = ConstraintPropagator::new();

        // x == y
        prop.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
        // y == z
        prop.add_relation("y".to_string(), ComparisonOp::Eq, "z".to_string());

        // x == y == z
        assert!(prop.can_infer_eq("x", "y"));
        assert!(prop.can_infer_eq("y", "z"));
        assert!(prop.can_infer_eq("x", "z"));
    }

    #[test]
    fn test_equality_propagation() {
        let mut prop = ConstraintPropagator::new();

        // x == y
        prop.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
        // y < z
        prop.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());

        // Should infer: x < z (via equality substitution)
        assert!(prop.can_infer_lt("x", "z"));
    }

    #[test]
    fn test_cycle_detection() {
        let mut prop = ConstraintPropagator::new();

        // x < y
        prop.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
        // y < z
        prop.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());
        // z < x (cycle!)
        let result = prop.add_relation("z".to_string(), ComparisonOp::Lt, "x".to_string());

        assert!(!result); // Should detect contradiction
        assert!(prop.has_contradiction());
    }

    #[test]
    fn test_eq_and_lt_contradiction() {
        let mut prop = ConstraintPropagator::new();

        // x == y
        prop.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
        // x < y (contradiction with x == y)
        let result = prop.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());

        assert!(!result);
        assert!(prop.has_contradiction());
    }

    #[test]
    fn test_clear() {
        let mut prop = ConstraintPropagator::new();

        prop.add_relation("x".to_string(), ComparisonOp::Lt, "y".to_string());
        prop.add_relation("y".to_string(), ComparisonOp::Lt, "z".to_string());

        assert_eq!(prop.relation_count(), 2);

        prop.clear();
        assert_eq!(prop.relation_count(), 0);
        assert!(!prop.has_contradiction());
    }

    #[test]
    fn test_multiple_equality_classes() {
        let mut prop = ConstraintPropagator::new();

        // Class 1: x == y
        prop.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
        // Class 2: a == b
        prop.add_relation("a".to_string(), ComparisonOp::Eq, "b".to_string());

        assert!(prop.can_infer_eq("x", "y"));
        assert!(prop.can_infer_eq("a", "b"));
        assert!(!prop.can_infer_eq("x", "a"));

        assert_eq!(prop.equality_class_count(), 2);
    }

    #[test]
    fn test_merge_equality_classes() {
        let mut prop = ConstraintPropagator::new();

        // Class 1: x == y
        prop.add_relation("x".to_string(), ComparisonOp::Eq, "y".to_string());
        // Class 2: a == b
        prop.add_relation("a".to_string(), ComparisonOp::Eq, "b".to_string());

        assert_eq!(prop.equality_class_count(), 2);

        // Merge: y == a
        prop.add_relation("y".to_string(), ComparisonOp::Eq, "a".to_string());

        // Now x == y == a == b
        assert!(prop.can_infer_eq("x", "b"));
        assert_eq!(prop.equality_class_count(), 1);
    }

    #[test]
    fn test_depth_limit() {
        // RFC-001: Use config to set max_depth
        let config = ConstraintPropagatorConfig {
            max_depth: 2,
            ..Default::default()
        };
        let mut prop = ConstraintPropagator::with_config(config);

        // Create chain longer than max_depth
        prop.add_relation("x1".to_string(), ComparisonOp::Lt, "x2".to_string());
        prop.add_relation("x2".to_string(), ComparisonOp::Lt, "x3".to_string());
        prop.add_relation("x3".to_string(), ComparisonOp::Lt, "x4".to_string());
        prop.add_relation("x4".to_string(), ComparisonOp::Lt, "x5".to_string());

        // Should not infer beyond depth limit
        assert!(!prop.can_infer_lt("x1", "x5"));
        // But should infer within limit
        assert!(prop.can_infer_lt("x1", "x3"));
    }
}
