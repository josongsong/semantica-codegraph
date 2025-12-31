//! Lightweight Constraint Checker
//!
//! Provides basic path feasibility checking without requiring Z3.
//! Integrates with SCCP for constant propagation results.

use super::{LatticeValue, PathFeasibility}; // Use shared types from mod.rs
use crate::features::smt::domain::{
    ComparisonOp, ConstValue, PathCondition, SanitizerDB, TaintType, VarId,
};
use std::collections::HashMap;

/// Lightweight constraint checker
pub struct LightweightConstraintChecker {
    /// SCCP constant propagation results
    sccp_values: HashMap<VarId, LatticeValue>,

    /// Sanitizer database
    sanitizer_db: SanitizerDB,

    /// Maximum conditions to analyze (complexity limit)
    max_conditions: usize,
}

impl Default for LightweightConstraintChecker {
    fn default() -> Self {
        Self::new()
    }
}

impl LightweightConstraintChecker {
    /// Create new lightweight checker
    pub fn new() -> Self {
        Self {
            sccp_values: HashMap::new(),
            sanitizer_db: SanitizerDB::new(),
            max_conditions: 10, // Conservative limit
        }
    }

    /// Set SCCP constant values
    pub fn set_sccp_values(&mut self, values: HashMap<VarId, LatticeValue>) {
        self.sccp_values = values;
    }

    /// Add single SCCP value
    pub fn add_sccp_value(&mut self, var: VarId, value: LatticeValue) {
        self.sccp_values.insert(var, value);
    }

    /// Check if path is feasible
    pub fn is_path_feasible(&self, conditions: &[PathCondition]) -> PathFeasibility {
        // Empty path is always feasible
        if conditions.is_empty() {
            return PathFeasibility::Feasible;
        }

        // Too many conditions - conservative Unknown
        if conditions.len() > self.max_conditions {
            return PathFeasibility::Unknown;
        }

        let mut evaluated_conditions = Vec::new();

        for condition in conditions {
            // Try to evaluate with SCCP constant
            if let Some(lattice_value) = self.sccp_values.get(&condition.var) {
                if let Some(const_value) = lattice_value.as_const() {
                    // Condition can be evaluated with constant
                    if !condition.evaluate(const_value) {
                        // Condition is false - path infeasible
                        return PathFeasibility::Infeasible;
                    }
                    // Condition is true - continue to next
                    continue;
                }
            }

            // Cannot evaluate with SCCP - check for contradictions
            if self.contradicts_previous(condition, &evaluated_conditions) {
                return PathFeasibility::Infeasible;
            }

            evaluated_conditions.push(condition.clone());
        }

        // No contradictions found - feasible
        PathFeasibility::Feasible
    }

    /// Check if new condition contradicts previous conditions
    fn contradicts_previous(&self, new: &PathCondition, previous: &[PathCondition]) -> bool {
        for prev in previous {
            // Only check conditions on same variable
            if new.var != prev.var {
                continue;
            }

            // Check for obvious contradictions
            if self.is_contradiction(prev, new) {
                return true;
            }
        }

        false
    }

    /// Check if two conditions contradict each other
    fn is_contradiction(&self, c1: &PathCondition, c2: &PathCondition) -> bool {
        use ComparisonOp::*;

        // Null vs NotNull
        if matches!((c1.op, c2.op), (Null, NotNull) | (NotNull, Null)) {
            return true;
        }

        // Need values for comparison contradictions
        let (v1, v2) = match (&c1.value, &c2.value) {
            (Some(v1), Some(v2)) => (v1, v2),
            _ => return false,
        };

        // Only handle integer contradictions for now
        let (i1, i2) = match (v1, v2) {
            (ConstValue::Int(i1), ConstValue::Int(i2)) => (*i1, *i2),
            _ => return false,
        };

        match (c1.op, c2.op) {
            // x < a && x > b → contradiction iff a <= b (no integers in range)
            // e.g., x < 5 && x > 10 → contradiction (5 <= 10: no x satisfies both)
            // e.g., x < 10 && x > 5 → NOT contradiction (e.g., x = 7 works)
            (Lt, Gt) => i1 <= i2, // c1: x < i1, c2: x > i2 → need i2 < x < i1, impossible if i1 <= i2
            (Gt, Lt) => i2 <= i1, // c1: x > i1, c2: x < i2 → need i1 < x < i2, impossible if i2 <= i1

            // x == 5 && x == 10
            (Eq, Eq) => i1 != i2,

            // x == 5 && x != 5
            (Eq, Neq) | (Neq, Eq) => i1 == i2,

            // x < a && x >= a → contradiction
            // x < 10 && x >= 10 → impossible
            (Lt, Ge) => i1 <= i2, // c1: x < i1, c2: x >= i2 → impossible if i1 <= i2
            (Ge, Lt) => i2 <= i1, // c1: x >= i1, c2: x < i2 → impossible if i2 <= i1

            // x > a && x <= a → contradiction
            // x > 10 && x <= 10 → impossible
            (Gt, Le) => i1 >= i2, // c1: x > i1, c2: x <= i2 → impossible if i1 >= i2
            (Le, Gt) => i2 >= i1, // c1: x <= i1, c2: x > i2 → impossible if i2 >= i1

            _ => false,
        }
    }

    /// Verify if sanitizer blocks taint
    pub fn verify_sanitizer_blocks_taint(
        &self,
        sanitizer_name: &str,
        taint_type: &TaintType,
    ) -> bool {
        self.sanitizer_db.blocks_taint(sanitizer_name, taint_type)
    }

    /// Check if function is a known sanitizer
    pub fn is_sanitizer(&self, function_name: &str) -> bool {
        self.sanitizer_db.is_sanitizer(function_name)
    }

    /// Get sanitizer database (for advanced usage)
    pub fn sanitizer_db(&self) -> &SanitizerDB {
        &self.sanitizer_db
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_path_is_feasible() {
        let checker = LightweightConstraintChecker::new();
        assert_eq!(checker.is_path_feasible(&[]), PathFeasibility::Feasible);
    }

    #[test]
    fn test_obvious_contradiction() {
        let checker = LightweightConstraintChecker::new();

        // x < 10 && x > 20
        let conditions = vec![
            PathCondition::lt("x".to_string(), ConstValue::Int(10)),
            PathCondition::gt("x".to_string(), ConstValue::Int(20)),
        ];

        assert_eq!(
            checker.is_path_feasible(&conditions),
            PathFeasibility::Infeasible
        );
    }

    #[test]
    fn test_null_vs_not_null_contradiction() {
        let checker = LightweightConstraintChecker::new();

        let conditions = vec![
            PathCondition::null("x".to_string()),
            PathCondition::not_null("x".to_string()),
        ];

        assert_eq!(
            checker.is_path_feasible(&conditions),
            PathFeasibility::Infeasible
        );
    }

    #[test]
    fn test_sccp_integration() {
        let mut checker = LightweightConstraintChecker::new();

        // SCCP determined x = 5
        checker.add_sccp_value("x".to_string(), LatticeValue::Constant(ConstValue::Int(5)));

        // x < 10 should be feasible (5 < 10 = true)
        let conditions = vec![PathCondition::lt("x".to_string(), ConstValue::Int(10))];
        assert_eq!(
            checker.is_path_feasible(&conditions),
            PathFeasibility::Feasible
        );

        // x > 10 should be infeasible (5 > 10 = false)
        let conditions = vec![PathCondition::gt("x".to_string(), ConstValue::Int(10))];
        assert_eq!(
            checker.is_path_feasible(&conditions),
            PathFeasibility::Infeasible
        );
    }

    #[test]
    fn test_equality_contradiction() {
        let checker = LightweightConstraintChecker::new();

        // x == 5 && x == 10
        let conditions = vec![
            PathCondition::eq("x".to_string(), ConstValue::Int(5)),
            PathCondition::eq("x".to_string(), ConstValue::Int(10)),
        ];

        assert_eq!(
            checker.is_path_feasible(&conditions),
            PathFeasibility::Infeasible
        );
    }

    #[test]
    fn test_eq_neq_contradiction() {
        let checker = LightweightConstraintChecker::new();

        // x == 5 && x != 5
        let conditions = vec![
            PathCondition::eq("x".to_string(), ConstValue::Int(5)),
            PathCondition::neq("x".to_string(), ConstValue::Int(5)),
        ];

        assert_eq!(
            checker.is_path_feasible(&conditions),
            PathFeasibility::Infeasible
        );
    }

    #[test]
    fn test_compatible_conditions() {
        let checker = LightweightConstraintChecker::new();

        // x > 5 && x < 10 (feasible range)
        let conditions = vec![
            PathCondition::gt("x".to_string(), ConstValue::Int(5)),
            PathCondition::lt("x".to_string(), ConstValue::Int(10)),
        ];

        assert_eq!(
            checker.is_path_feasible(&conditions),
            PathFeasibility::Feasible
        );
    }

    #[test]
    fn test_too_many_conditions() {
        let mut checker = LightweightConstraintChecker::new();
        checker.max_conditions = 3;

        // 5 conditions exceeds limit
        let conditions = vec![
            PathCondition::gt("x".to_string(), ConstValue::Int(0)),
            PathCondition::lt("x".to_string(), ConstValue::Int(100)),
            PathCondition::gt("y".to_string(), ConstValue::Int(0)),
            PathCondition::lt("y".to_string(), ConstValue::Int(100)),
            PathCondition::gt("z".to_string(), ConstValue::Int(0)),
        ];

        assert_eq!(
            checker.is_path_feasible(&conditions),
            PathFeasibility::Unknown
        );
    }

    #[test]
    fn test_sanitizer_blocks_xss() {
        let checker = LightweightConstraintChecker::new();
        assert!(checker.verify_sanitizer_blocks_taint("html.escape", &TaintType::Xss));
        assert!(!checker.verify_sanitizer_blocks_taint("html.escape", &TaintType::SqlInjection));
    }

    #[test]
    fn test_sanitizer_detection() {
        let checker = LightweightConstraintChecker::new();
        assert!(checker.is_sanitizer("html.escape"));
        assert!(checker.is_sanitizer("sql_escape"));
        assert!(!checker.is_sanitizer("unknown_function"));
    }
}
