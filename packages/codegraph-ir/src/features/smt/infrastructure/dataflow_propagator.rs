//! Dataflow Constraint Propagation
//!
//! Propagates constraints along dataflow paths and integrates with SCCP.
//!
//! ## Overview
//!
//! This module connects SMT constraint solving with dataflow analysis:
//! 1. Track constraints along control flow paths
//! 2. Integrate with SCCP for constant propagation
//! 3. Propagate constraints through assignments
//! 4. Check path feasibility at branches
//!
//! ## Example
//!
//! ```text
//! x = 5             ← SCCP: x = Constant(5)
//! y = x + 10        ← Dataflow: y ∈ [15, 15]
//! if (y < 20):      ← SMT: Check y < 20 with y = 15 → Feasible
//!     use(y)        ← This path is reachable
//! else:
//!     use(x)        ← This path is INFEASIBLE (y = 15 NOT < 20)
//! ```

use super::orchestrator::SmtOrchestrator;
use super::{LatticeValue, PathFeasibility};
use crate::features::smt::domain::constraint::Constraint;
use crate::features::smt::domain::path_condition::{ComparisonOp, ConstValue, PathCondition};
use std::collections::HashMap;

/// Dataflow constraint propagator
///
/// Tracks and propagates constraints along dataflow edges.
pub struct DataflowConstraintPropagator {
    /// SMT orchestrator for constraint solving
    orchestrator: SmtOrchestrator,

    /// Current path constraints (accumulated along path)
    path_constraints: Vec<PathCondition>,

    /// Variable definitions (var → defining expression)
    var_defs: HashMap<String, Definition>,

    /// SCCP integration: known constant values
    sccp_values: HashMap<String, LatticeValue>,
}

/// Variable definition
#[derive(Debug, Clone)]
pub enum Definition {
    /// Constant value
    Constant(ConstValue),

    /// Binary operation: var = left op right
    BinaryOp {
        left: String,
        op: BinaryOperator,
        right: String,
    },

    /// Phi node: var = phi(v1, v2, ...)
    Phi(Vec<String>),

    /// Unknown/external
    Unknown,
}

/// Binary operators for dataflow
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinaryOperator {
    Add,
    Sub,
    Mul,
    Div,
}

impl Default for DataflowConstraintPropagator {
    fn default() -> Self {
        Self::new()
    }
}

impl DataflowConstraintPropagator {
    /// Create new dataflow propagator
    pub fn new() -> Self {
        Self {
            orchestrator: SmtOrchestrator::new(),
            path_constraints: Vec::new(),
            var_defs: HashMap::new(),
            sccp_values: HashMap::new(),
        }
    }

    /// Set SCCP values (from constant propagation analysis)
    pub fn set_sccp_values(&mut self, values: HashMap<String, LatticeValue>) {
        self.sccp_values = values.clone();
        // Also update orchestrator's lightweight checker
        for (var, value) in values {
            self.orchestrator
                .lightweight_mut()
                .add_sccp_value(var, value);
        }
    }

    /// Add variable definition
    pub fn add_definition(&mut self, var: String, def: Definition) {
        self.var_defs.insert(var, def);
    }

    /// Add path constraint (from conditional branch)
    pub fn add_constraint(&mut self, condition: PathCondition) {
        self.path_constraints.push(condition);
    }

    /// Clear path constraints (when entering new path)
    pub fn clear_constraints(&mut self) {
        self.path_constraints.clear();
    }

    /// Check if current path is feasible
    pub fn is_path_feasible(&mut self) -> PathFeasibility {
        // First, check against known SCCP values (constant propagation)
        for constraint in &self.path_constraints {
            if let Some(lattice_val) = self.sccp_values.get(&constraint.var) {
                if let Some(const_val) = lattice_val.as_const() {
                    // We have a concrete value for this variable
                    if let Some(ref rhs_val) = constraint.value {
                        if !Self::eval_constraint(const_val, constraint.op, rhs_val) {
                            return PathFeasibility::Infeasible;
                        }
                    }
                }
            }
        }

        // If SCCP values don't prove infeasibility, use orchestrator
        self.orchestrator
            .check_path_feasibility(&self.path_constraints)
    }

    /// Evaluate if const_val op value holds
    fn eval_constraint(left: &ConstValue, op: ComparisonOp, right: &ConstValue) -> bool {
        match (left, right) {
            (ConstValue::Int(l), ConstValue::Int(r)) => match op {
                ComparisonOp::Lt => *l < *r,
                ComparisonOp::Le => *l <= *r,
                ComparisonOp::Gt => *l > *r,
                ComparisonOp::Ge => *l >= *r,
                ComparisonOp::Eq => *l == *r,
                ComparisonOp::Neq => *l != *r,
                _ => true, // Conservative
            },
            _ => true, // Conservative for non-int types
        }
    }

    /// Propagate constraints through assignment: var = expr
    pub fn propagate_assignment(&mut self, var: &str, expr: &Definition) -> Option<LatticeValue> {
        match expr {
            Definition::Constant(val) => {
                let lattice_val = LatticeValue::Constant(val.clone());
                self.sccp_values
                    .insert(var.to_string(), lattice_val.clone());
                Some(lattice_val)
            }

            Definition::BinaryOp { left, op, right } => {
                // Try to evaluate if both operands are constants
                let left_val = self.sccp_values.get(left)?;
                let right_val = self.sccp_values.get(right)?;

                if let (Some(l_const), Some(r_const)) = (left_val.as_const(), right_val.as_const())
                {
                    if let Some(result) = Self::eval_binary_op(l_const, *op, r_const) {
                        let lattice_val = LatticeValue::Constant(result);
                        self.sccp_values
                            .insert(var.to_string(), lattice_val.clone());
                        return Some(lattice_val);
                    }
                }

                // Cannot evaluate - mark as Top (non-constant)
                self.sccp_values.insert(var.to_string(), LatticeValue::Top);
                Some(LatticeValue::Top)
            }

            Definition::Phi(values) => {
                // Phi node: check if all inputs are same constant
                let mut common_value: Option<&ConstValue> = None;

                for val_var in values {
                    if let Some(lattice) = self.sccp_values.get(val_var) {
                        if let Some(const_val) = lattice.as_const() {
                            if let Some(existing) = common_value {
                                if existing != const_val {
                                    // Different values - result is Top
                                    self.sccp_values.insert(var.to_string(), LatticeValue::Top);
                                    return Some(LatticeValue::Top);
                                }
                            } else {
                                common_value = Some(const_val);
                            }
                        } else {
                            // Non-constant input - result is Top
                            self.sccp_values.insert(var.to_string(), LatticeValue::Top);
                            return Some(LatticeValue::Top);
                        }
                    }
                }

                // All inputs are same constant
                if let Some(val) = common_value {
                    let lattice_val = LatticeValue::Constant(val.clone());
                    self.sccp_values
                        .insert(var.to_string(), lattice_val.clone());
                    Some(lattice_val)
                } else {
                    None
                }
            }

            Definition::Unknown => {
                self.sccp_values.insert(var.to_string(), LatticeValue::Top);
                Some(LatticeValue::Top)
            }
        }
    }

    /// Evaluate binary operation on constants
    fn eval_binary_op(
        left: &ConstValue,
        op: BinaryOperator,
        right: &ConstValue,
    ) -> Option<ConstValue> {
        match (left, right) {
            (ConstValue::Int(l), ConstValue::Int(r)) => {
                let result = match op {
                    BinaryOperator::Add => l.checked_add(*r)?,
                    BinaryOperator::Sub => l.checked_sub(*r)?,
                    BinaryOperator::Mul => l.checked_mul(*r)?,
                    BinaryOperator::Div => {
                        if *r == 0 {
                            return None;
                        }
                        l.checked_div(*r)?
                    }
                };
                Some(ConstValue::Int(result))
            }
            (ConstValue::Float(l), ConstValue::Float(r)) => {
                let result = match op {
                    BinaryOperator::Add => l + r,
                    BinaryOperator::Sub => l - r,
                    BinaryOperator::Mul => l * r,
                    BinaryOperator::Div => {
                        if r.abs() < 1e-10 {
                            return None;
                        }
                        l / r
                    }
                };
                Some(ConstValue::Float(result))
            }
            _ => None, // Type mismatch
        }
    }

    /// Get current path constraints
    pub fn current_constraints(&self) -> &[PathCondition] {
        &self.path_constraints
    }

    /// Get variable definition
    pub fn get_definition(&self, var: &str) -> Option<&Definition> {
        self.var_defs.get(var)
    }

    /// Get SCCP value for variable
    pub fn get_sccp_value(&self, var: &str) -> Option<&LatticeValue> {
        self.sccp_values.get(var)
    }

    /// Create constraint from path condition
    pub fn to_constraint(&self, condition: &PathCondition) -> Constraint {
        Constraint::simple(condition.var.clone(), condition.op, condition.value.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_constant_propagation() {
        let mut propagator = DataflowConstraintPropagator::new();

        // x = 5
        let def = Definition::Constant(ConstValue::Int(5));
        let result = propagator.propagate_assignment("x", &def);

        assert!(matches!(result, Some(LatticeValue::Constant(_))));
        assert_eq!(
            propagator.get_sccp_value("x"),
            Some(&LatticeValue::Constant(ConstValue::Int(5)))
        );
    }

    #[test]
    fn test_binary_op_propagation() {
        let mut propagator = DataflowConstraintPropagator::new();

        // x = 5
        propagator.propagate_assignment("x", &Definition::Constant(ConstValue::Int(5)));

        // y = 10
        propagator.propagate_assignment("y", &Definition::Constant(ConstValue::Int(10)));

        // z = x + y
        let def = Definition::BinaryOp {
            left: "x".to_string(),
            op: BinaryOperator::Add,
            right: "y".to_string(),
        };
        propagator.propagate_assignment("z", &def);

        // z should be 15
        assert_eq!(
            propagator.get_sccp_value("z"),
            Some(&LatticeValue::Constant(ConstValue::Int(15)))
        );
    }

    #[test]
    fn test_path_feasibility_check() {
        let mut propagator = DataflowConstraintPropagator::new();

        // x = 5
        propagator.propagate_assignment("x", &Definition::Constant(ConstValue::Int(5)));

        // Add constraint: x < 10
        propagator.add_constraint(PathCondition::lt("x".to_string(), ConstValue::Int(10)));

        // Should be feasible (5 < 10)
        assert_eq!(propagator.is_path_feasible(), PathFeasibility::Feasible);
    }

    #[test]
    fn test_path_infeasibility() {
        let mut propagator = DataflowConstraintPropagator::new();

        // x = 5
        propagator.propagate_assignment("x", &Definition::Constant(ConstValue::Int(5)));

        // Add constraint: x > 10
        propagator.add_constraint(PathCondition::gt("x".to_string(), ConstValue::Int(10)));

        // Should be infeasible (5 NOT > 10)
        assert_eq!(propagator.is_path_feasible(), PathFeasibility::Infeasible);
    }

    #[test]
    fn test_phi_node_same_values() {
        let mut propagator = DataflowConstraintPropagator::new();

        // v1 = 5, v2 = 5
        propagator.propagate_assignment("v1", &Definition::Constant(ConstValue::Int(5)));
        propagator.propagate_assignment("v2", &Definition::Constant(ConstValue::Int(5)));

        // x = phi(v1, v2)
        let def = Definition::Phi(vec!["v1".to_string(), "v2".to_string()]);
        propagator.propagate_assignment("x", &def);

        // x should be 5 (both inputs are 5)
        assert_eq!(
            propagator.get_sccp_value("x"),
            Some(&LatticeValue::Constant(ConstValue::Int(5)))
        );
    }

    #[test]
    fn test_phi_node_different_values() {
        let mut propagator = DataflowConstraintPropagator::new();

        // v1 = 5, v2 = 10
        propagator.propagate_assignment("v1", &Definition::Constant(ConstValue::Int(5)));
        propagator.propagate_assignment("v2", &Definition::Constant(ConstValue::Int(10)));

        // x = phi(v1, v2)
        let def = Definition::Phi(vec!["v1".to_string(), "v2".to_string()]);
        propagator.propagate_assignment("x", &def);

        // x should be Top (different values)
        assert_eq!(propagator.get_sccp_value("x"), Some(&LatticeValue::Top));
    }
}
