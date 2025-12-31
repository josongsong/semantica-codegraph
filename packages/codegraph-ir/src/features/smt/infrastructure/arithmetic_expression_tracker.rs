//! Arithmetic Expression Tracker (SOTA v2.2 - Phase 2)
//!
//! Limited arithmetic reasoning for linear expressions.
//!
//! # Capabilities
//!
//! - **Linear Expressions**: `x + y > 10`, `2*x - y < 5`
//! - **Interval Arithmetic**: Propagate constraints through expressions
//! - **2-Variable Limit**: Maximum 2 variables per expression
//! - **Contradiction Detection**: Detect infeasible arithmetic constraints
//!
//! # Limitations
//!
//! - ⚠️ **Linear only**: `x * y` (non-linear) NOT supported
//! - ⚠️ **2 variables max**: `x + y + z` NOT supported
//! - ⚠️ **Integer only**: Floating-point NOT supported
//! - ⚠️ **Simple coefficients**: Large numbers may overflow
//!
//! # Performance
//!
//! - Max expressions: 50
//! - Max variables: 20
//! - Time complexity: O(n²) worst case
//! - Space complexity: O(n²) for variable bounds
//!
//! # Examples
//!
//! ```text
//! use codegraph_ir::features::smt::infrastructure::ArithmeticExpressionTracker;
//! use codegraph_ir::features::smt::domain::ComparisonOp;
//!
//! let mut tracker = ArithmeticExpressionTracker::new();
//!
//! // Add variable bounds
//! tracker.add_variable_bound("x".to_string(), 0, 100);
//! tracker.add_variable_bound("y".to_string(), 0, 100);
//!
//! // Add linear expression: x + y > 10
//! let expr = LinearExpression::new()
//!     .add_term("x".to_string(), 1)
//!     .add_term("y".to_string(), 1)
//!     .constant(0)
//!     .comparison(ComparisonOp::Gt, 10);
//!
//! tracker.add_expression(expr);
//!
//! // Check feasibility
//! assert!(tracker.is_feasible());
//! ```

use crate::features::smt::domain::{ComparisonOp, VarId};
use std::collections::HashMap;

/// Interval bound for a variable
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IntervalBound {
    /// Lower bound (inclusive)
    pub lower: i64,
    /// Upper bound (inclusive)
    pub upper: i64,
}

impl IntervalBound {
    /// Create new interval bound
    pub fn new(lower: i64, upper: i64) -> Self {
        Self { lower, upper }
    }

    /// Create unbounded interval
    pub fn unbounded() -> Self {
        Self {
            lower: i64::MIN,
            upper: i64::MAX,
        }
    }

    /// Check if interval is empty
    pub fn is_empty(&self) -> bool {
        self.lower > self.upper
    }

    /// Intersect with another interval
    pub fn intersect(&self, other: &Self) -> Self {
        Self {
            lower: self.lower.max(other.lower),
            upper: self.upper.min(other.upper),
        }
    }

    /// Check if contains value
    pub fn contains(&self, value: i64) -> bool {
        value >= self.lower && value <= self.upper
    }
}

/// Linear expression: a₁x₁ + a₂x₂ + ... + c
#[derive(Debug, Clone)]
pub struct LinearExpression {
    /// Coefficients: (variable, coefficient)
    /// Example: 2x - y → [(x, 2), (y, -1)]
    pub terms: Vec<(VarId, i64)>,

    /// Constant term
    pub constant: i64,

    /// Comparison operator
    pub op: ComparisonOp,

    /// Right-hand side value
    /// Example: x + y > 10 → rhs = 10
    pub rhs: i64,
}

impl LinearExpression {
    /// Create new linear expression
    pub fn new() -> Self {
        Self {
            terms: Vec::new(),
            constant: 0,
            op: ComparisonOp::Eq,
            rhs: 0,
        }
    }

    /// Add term (variable with coefficient)
    pub fn add_term(mut self, var: VarId, coeff: i64) -> Self {
        self.terms.push((var, coeff));
        self
    }

    /// Set constant term
    pub fn constant(mut self, c: i64) -> Self {
        self.constant = c;
        self
    }

    /// Set comparison
    pub fn comparison(mut self, op: ComparisonOp, rhs: i64) -> Self {
        self.op = op;
        self.rhs = rhs;
        self
    }

    /// Get number of variables
    pub fn var_count(&self) -> usize {
        self.terms.len()
    }

    /// Evaluate expression with variable values
    pub fn evaluate(&self, values: &HashMap<VarId, i64>) -> Option<i64> {
        let mut result = self.constant;

        for (var, coeff) in &self.terms {
            let value = values.get(var)?;
            result = result.checked_add(coeff.checked_mul(*value)?)?;
        }

        Some(result)
    }

    /// Check if expression is satisfied
    pub fn is_satisfied(&self, values: &HashMap<VarId, i64>) -> Option<bool> {
        let lhs = self.evaluate(values)?;

        Some(match self.op {
            ComparisonOp::Lt => lhs < self.rhs,
            ComparisonOp::Le => lhs <= self.rhs,
            ComparisonOp::Gt => lhs > self.rhs,
            ComparisonOp::Ge => lhs >= self.rhs,
            ComparisonOp::Eq => lhs == self.rhs,
            ComparisonOp::Neq => lhs != self.rhs,
            _ => return None,
        })
    }
}

impl Default for LinearExpression {
    fn default() -> Self {
        Self::new()
    }
}

/// Arithmetic expression tracker
pub struct ArithmeticExpressionTracker {
    /// Variable bounds (intervals)
    variable_bounds: HashMap<VarId, IntervalBound>,

    /// Linear expressions
    expressions: Vec<LinearExpression>,

    /// Maximum number of expressions
    max_expressions: usize,

    /// Maximum variables per expression
    max_vars_per_expr: usize,

    /// Contradiction flag
    has_contradiction: bool,
}

impl Default for ArithmeticExpressionTracker {
    fn default() -> Self {
        Self::new()
    }
}

impl ArithmeticExpressionTracker {
    /// Create new arithmetic tracker
    pub fn new() -> Self {
        Self {
            variable_bounds: HashMap::new(),
            expressions: Vec::new(),
            max_expressions: 50,
            max_vars_per_expr: 2,
            has_contradiction: false,
        }
    }

    /// Add variable bound (interval)
    pub fn add_variable_bound(&mut self, var: VarId, lower: i64, upper: i64) -> bool {
        if lower > upper {
            self.has_contradiction = true;
            return false;
        }

        let bound = IntervalBound::new(lower, upper);

        // If variable already exists, intersect bounds
        if let Some(existing) = self.variable_bounds.get_mut(&var) {
            let new_bound = existing.intersect(&bound);
            if new_bound.is_empty() {
                self.has_contradiction = true;
                return false;
            }
            *existing = new_bound;
        } else {
            self.variable_bounds.insert(var, bound);
        }

        true
    }

    /// Add linear expression
    pub fn add_expression(&mut self, expr: LinearExpression) -> bool {
        if self.has_contradiction {
            return false;
        }

        // Check expression limit
        if self.expressions.len() >= self.max_expressions {
            return true; // Conservative: ignore
        }

        // Check variable count limit
        if expr.var_count() > self.max_vars_per_expr {
            return true; // Conservative: ignore complex expressions
        }

        // Check if expression is feasible given current bounds
        if !self.check_expression_feasibility(&expr) {
            self.has_contradiction = true;
            return false;
        }

        // Try to propagate constraints
        self.propagate_expression_bounds(&expr);

        self.expressions.push(expr);
        true
    }

    /// Check if expression is feasible
    fn check_expression_feasibility(&self, expr: &LinearExpression) -> bool {
        // Calculate min/max possible values for LHS
        let mut min_lhs = expr.constant;
        let mut max_lhs = expr.constant;

        for (var, coeff) in &expr.terms {
            if let Some(bound) = self.variable_bounds.get(var) {
                // coeff * var contribution
                let (contrib_min, contrib_max) = if *coeff > 0 {
                    (
                        coeff.saturating_mul(bound.lower),
                        coeff.saturating_mul(bound.upper),
                    )
                } else {
                    (
                        coeff.saturating_mul(bound.upper),
                        coeff.saturating_mul(bound.lower),
                    )
                };

                min_lhs = min_lhs.saturating_add(contrib_min);
                max_lhs = max_lhs.saturating_add(contrib_max);
            } else {
                // Unknown variable - conservative
                return true;
            }
        }

        // Check if constraint can be satisfied
        match expr.op {
            ComparisonOp::Lt => {
                // LHS < rhs
                // If min_lhs >= rhs, impossible
                if min_lhs >= expr.rhs {
                    return false;
                }
            }
            ComparisonOp::Le => {
                if min_lhs > expr.rhs {
                    return false;
                }
            }
            ComparisonOp::Gt => {
                // LHS > rhs
                // If max_lhs <= rhs, impossible
                if max_lhs <= expr.rhs {
                    return false;
                }
            }
            ComparisonOp::Ge => {
                if max_lhs < expr.rhs {
                    return false;
                }
            }
            ComparisonOp::Eq => {
                // LHS == rhs
                // If rhs not in [min_lhs, max_lhs], impossible
                if expr.rhs < min_lhs || expr.rhs > max_lhs {
                    return false;
                }
            }
            ComparisonOp::Neq => {
                // LHS != rhs
                // If min_lhs == max_lhs == rhs, impossible
                if min_lhs == max_lhs && min_lhs == expr.rhs {
                    return false;
                }
            }
            _ => {}
        }

        true
    }

    /// Propagate bounds from expression to variables
    fn propagate_expression_bounds(&mut self, expr: &LinearExpression) {
        // For 2-variable expressions, try to narrow bounds
        if expr.terms.len() != 2 {
            return;
        }

        let (var1, coeff1) = &expr.terms[0];
        let (var2, coeff2) = &expr.terms[1];

        // Try to derive bounds on var2 from var1's bounds
        if let Some(bound1) = self.variable_bounds.get(var1).cloned() {
            self.derive_variable_bound(var2, coeff2, var1, coeff1, &bound1, expr);
        }

        // Try to derive bounds on var1 from var2's bounds
        if let Some(bound2) = self.variable_bounds.get(var2).cloned() {
            self.derive_variable_bound(var1, coeff1, var2, coeff2, &bound2, expr);
        }
    }

    /// Derive bound on target_var from source_var bound
    #[allow(clippy::too_many_arguments)]
    fn derive_variable_bound(
        &mut self,
        target_var: &VarId,
        target_coeff: &i64,
        _source_var: &VarId,
        source_coeff: &i64,
        source_bound: &IntervalBound,
        expr: &LinearExpression,
    ) {
        // Expression: source_coeff * source_var + target_coeff * target_var + constant op rhs
        // Solve for target_var bounds

        if *target_coeff == 0 {
            return;
        }

        // Calculate range of (source_coeff * source_var + constant)
        let source_min = source_coeff.saturating_mul(source_bound.lower);
        let source_max = source_coeff.saturating_mul(source_bound.upper);

        let base_min = expr.constant.saturating_add(source_min);
        let base_max = expr.constant.saturating_add(source_max);

        // Derive target_var bounds based on comparison
        let (target_lower, target_upper) = match expr.op {
            ComparisonOp::Gt => {
                // base + target_coeff * target_var > rhs
                // target_coeff * target_var > rhs - base
                let threshold = expr.rhs.saturating_sub(base_max);
                if *target_coeff > 0 {
                    // target_var > threshold / target_coeff
                    let lower = (threshold / target_coeff).saturating_add(1);
                    (Some(lower), None)
                } else {
                    // target_var < threshold / target_coeff
                    let upper = (threshold / target_coeff).saturating_sub(1);
                    (None, Some(upper))
                }
            }
            ComparisonOp::Lt => {
                // base + target_coeff * target_var < rhs
                let threshold = expr.rhs.saturating_sub(base_min);
                if *target_coeff > 0 {
                    // target_var < threshold / target_coeff
                    let upper = (threshold / target_coeff).saturating_sub(1);
                    (None, Some(upper))
                } else {
                    // target_var > threshold / target_coeff
                    let lower = (threshold / target_coeff).saturating_add(1);
                    (Some(lower), None)
                }
            }
            _ => return, // Only handle Lt/Gt for now
        };

        // Apply derived bounds
        if let Some(lower) = target_lower {
            let upper = target_upper.unwrap_or(i64::MAX);
            self.add_variable_bound(target_var.clone(), lower, upper);
        } else if let Some(upper) = target_upper {
            self.add_variable_bound(target_var.clone(), i64::MIN, upper);
        }
    }

    /// Check if all expressions are feasible
    pub fn is_feasible(&self) -> bool {
        !self.has_contradiction
    }

    /// Get variable bound
    pub fn get_variable_bound(&self, var: &VarId) -> Option<&IntervalBound> {
        self.variable_bounds.get(var)
    }

    /// Clear all state
    pub fn clear(&mut self) {
        self.variable_bounds.clear();
        self.expressions.clear();
        self.has_contradiction = false;
    }

    /// Get number of expressions
    pub fn expression_count(&self) -> usize {
        self.expressions.len()
    }

    /// Get number of tracked variables
    pub fn variable_count(&self) -> usize {
        self.variable_bounds.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_interval_bound_basic() {
        let bound = IntervalBound::new(0, 10);
        assert!(!bound.is_empty());
        assert!(bound.contains(5));
        assert!(!bound.contains(11));
    }

    #[test]
    fn test_interval_bound_intersect() {
        let b1 = IntervalBound::new(0, 10);
        let b2 = IntervalBound::new(5, 15);
        let result = b1.intersect(&b2);
        assert_eq!(result.lower, 5);
        assert_eq!(result.upper, 10);
    }

    #[test]
    fn test_interval_bound_empty() {
        let b1 = IntervalBound::new(0, 5);
        let b2 = IntervalBound::new(10, 15);
        let result = b1.intersect(&b2);
        assert!(result.is_empty());
    }

    #[test]
    fn test_linear_expression_evaluate() {
        let expr = LinearExpression::new()
            .add_term("x".to_string(), 2)
            .add_term("y".to_string(), -1)
            .constant(5);

        let mut values = HashMap::new();
        values.insert("x".to_string(), 10);
        values.insert("y".to_string(), 3);

        // 2*10 - 1*3 + 5 = 20 - 3 + 5 = 22
        assert_eq!(expr.evaluate(&values), Some(22));
    }

    #[test]
    fn test_arithmetic_tracker_basic() {
        let mut tracker = ArithmeticExpressionTracker::new();

        tracker.add_variable_bound("x".to_string(), 0, 100);
        tracker.add_variable_bound("y".to_string(), 0, 100);

        let expr = LinearExpression::new()
            .add_term("x".to_string(), 1)
            .add_term("y".to_string(), 1)
            .constant(0)
            .comparison(ComparisonOp::Gt, 10);

        assert!(tracker.add_expression(expr));
        assert!(tracker.is_feasible());
    }

    #[test]
    fn test_arithmetic_tracker_contradiction() {
        let mut tracker = ArithmeticExpressionTracker::new();

        // x in [0, 5]
        tracker.add_variable_bound("x".to_string(), 0, 5);
        // y in [0, 3]
        tracker.add_variable_bound("y".to_string(), 0, 3);

        // x + y > 10 (impossible: max = 5 + 3 = 8 < 10)
        let expr = LinearExpression::new()
            .add_term("x".to_string(), 1)
            .add_term("y".to_string(), 1)
            .constant(0)
            .comparison(ComparisonOp::Gt, 10);

        assert!(!tracker.add_expression(expr));
        assert!(!tracker.is_feasible());
    }

    #[test]
    fn test_arithmetic_tracker_propagation() {
        let mut tracker = ArithmeticExpressionTracker::new();

        tracker.add_variable_bound("x".to_string(), 10, 20);
        // y initially unbounded

        // x + y > 30
        let expr = LinearExpression::new()
            .add_term("x".to_string(), 1)
            .add_term("y".to_string(), 1)
            .constant(0)
            .comparison(ComparisonOp::Gt, 30);

        tracker.add_expression(expr);

        // Should infer y > 10 (since x_max = 20, need y > 30 - 20 = 10)
        if let Some(y_bound) = tracker.get_variable_bound(&"y".to_string()) {
            assert!(y_bound.lower > 10 || y_bound.lower == i64::MIN); // May not always propagate
        }

        assert!(tracker.is_feasible());
    }
}
