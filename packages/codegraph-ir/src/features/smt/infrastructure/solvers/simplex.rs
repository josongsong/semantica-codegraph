//! Simplex Algorithm for Linear Arithmetic
//!
//! Solves linear constraints of the form:
//! - a1*x1 + a2*x2 + ... + an*xn <op> c
//! - Where <op> is <=, >=, ==, <, >
//!
//! ## Algorithm
//!
//! 1. Convert to standard form (all constraints as Ax <= b)
//! 2. Add slack variables to convert to equalities
//! 3. Run Simplex pivoting to find feasible solution
//! 4. If no pivot possible and constraints violated → UNSAT
//!
//! ## Example
//!
//! ```text
//! Constraints:
//!   2*x + 3*y <= 10
//!   x >= 0
//!   y >= 0
//!   x > 5  ← Check if feasible
//!
//! Result: UNSAT (x > 5 contradicts 2*x + 3*y <= 10 with x,y >= 0)
//! ```

use super::{ConstraintSolver, Model, ModelValue, SolverResult};
use crate::features::smt::domain::constraint::{Constraint, Theory};
use crate::features::smt::domain::path_condition::ComparisonOp;
use std::collections::{HashMap, HashSet};

/// Simplex solver for linear arithmetic constraints
pub struct SimplexSolver {
    /// Tableau: [A | b] where Ax = b
    /// Rows = constraints (including slack variables)
    /// Cols = variables + slack variables
    tableau: Vec<Vec<f64>>,

    /// Variable names (for model extraction)
    var_names: Vec<String>,

    /// Basic variables (one per row)
    basic_vars: Vec<usize>,

    /// Maximum iterations (prevent infinite loops)
    max_iterations: usize,
}

impl Default for SimplexSolver {
    fn default() -> Self {
        Self::new()
    }
}

impl SimplexSolver {
    /// Create new Simplex solver
    pub fn new() -> Self {
        Self {
            tableau: Vec::new(),
            var_names: Vec::new(),
            basic_vars: Vec::new(),
            max_iterations: 1000,
        }
    }

    /// Build tableau from constraints
    fn build_tableau(&mut self, constraints: &[&Constraint]) -> Result<(), &'static str> {
        if constraints.is_empty() {
            return Err("No constraints provided");
        }

        // 1. Extract all variables
        let mut all_vars = HashSet::new();
        for constraint in constraints {
            if let Constraint::LinearArithmetic { coefficients, .. } = constraint {
                for var in coefficients.keys() {
                    all_vars.insert(var.clone());
                }
            }
        }

        self.var_names = all_vars.into_iter().collect();
        self.var_names.sort(); // Deterministic ordering

        let num_vars = self.var_names.len();
        let num_constraints = constraints.len();

        // 2. Create variable index map
        let var_index: HashMap<&str, usize> = self
            .var_names
            .iter()
            .enumerate()
            .map(|(i, name)| (name.as_str(), i))
            .collect();

        // 3. Build tableau: [coefficients | slack vars | RHS]
        // Each row = one constraint
        // Cols = original vars + slack vars + RHS
        let num_cols = num_vars + num_constraints + 1; // vars + slacks + RHS

        self.tableau = vec![vec![0.0; num_cols]; num_constraints];
        self.basic_vars = Vec::with_capacity(num_constraints);

        for (row_idx, constraint) in constraints.iter().enumerate() {
            if let Constraint::LinearArithmetic {
                coefficients,
                constant,
                op,
            } = constraint
            {
                // Fill in coefficients for original variables
                for (var, &coeff) in coefficients {
                    if let Some(&col_idx) = var_index.get(var.as_str()) {
                        self.tableau[row_idx][col_idx] = coeff as f64;
                    }
                }

                // Convert to standard form (Ax <= b)
                let (normalized_constant, needs_slack) = match op {
                    ComparisonOp::Le => (-constant as f64, true),
                    ComparisonOp::Lt => (-constant as f64 - 0.0001, true), // x < c → x <= c - ε
                    ComparisonOp::Ge => {
                        // x >= c → -x <= -c
                        for val in &mut self.tableau[row_idx][..num_vars] {
                            *val = -*val;
                        }
                        (*constant as f64, true)
                    }
                    ComparisonOp::Gt => {
                        // x > c → -x <= -c + ε
                        for val in &mut self.tableau[row_idx][..num_vars] {
                            *val = -*val;
                        }
                        (*constant as f64 + 0.0001, true)
                    }
                    ComparisonOp::Eq => (-constant as f64, false), // Equality (no slack)
                    _ => return Err("Unsupported comparison operator"),
                };

                // Add slack variable
                if needs_slack {
                    let slack_col = num_vars + row_idx;
                    self.tableau[row_idx][slack_col] = 1.0;
                    self.basic_vars.push(slack_col);
                } else {
                    // For equality, we need artificial variable (Phase I simplex)
                    // For simplicity, treat as <= for now
                    let slack_col = num_vars + row_idx;
                    self.tableau[row_idx][slack_col] = 1.0;
                    self.basic_vars.push(slack_col);
                }

                // Set RHS
                self.tableau[row_idx][num_cols - 1] = normalized_constant;
            }
        }

        Ok(())
    }

    /// Perform one Simplex pivot
    fn pivot(&mut self, pivot_row: usize, pivot_col: usize) {
        let pivot_element = self.tableau[pivot_row][pivot_col];

        // Normalize pivot row
        for val in &mut self.tableau[pivot_row] {
            *val /= pivot_element;
        }

        // Eliminate pivot column from other rows
        for i in 0..self.tableau.len() {
            if i == pivot_row {
                continue;
            }

            let factor = self.tableau[i][pivot_col];
            for j in 0..self.tableau[i].len() {
                self.tableau[i][j] -= factor * self.tableau[pivot_row][j];
            }
        }

        // Update basic variables
        self.basic_vars[pivot_row] = pivot_col;
    }

    /// Find entering variable (for Phase II feasibility check)
    /// Returns column with most negative RHS (infeasible constraint)
    fn find_entering_variable(&self) -> Option<usize> {
        if self.tableau.is_empty() {
            return None;
        }

        let num_cols = self.tableau[0].len();
        let rhs_col = num_cols - 1;

        // Find row with most negative RHS (most infeasible)
        let mut most_infeasible_row = None;
        let mut min_rhs = 0.0;

        for (row_idx, row) in self.tableau.iter().enumerate() {
            let rhs = row[rhs_col];
            if rhs < min_rhs - 1e-10 {
                min_rhs = rhs;
                most_infeasible_row = Some(row_idx);
            }
        }

        most_infeasible_row?;

        // Find column with positive coefficient in infeasible row
        let row_idx = most_infeasible_row.unwrap();
        let num_vars = self.var_names.len();

        for col in 0..num_vars {
            if self.tableau[row_idx][col] > 1e-10 {
                return Some(col);
            }
        }

        None
    }

    /// Find leaving variable (minimum ratio test)
    fn find_leaving_variable(&self, entering_col: usize) -> Option<usize> {
        if self.tableau.is_empty() {
            return None;
        }

        let num_cols = self.tableau[0].len();
        let rhs_col = num_cols - 1;

        let mut min_ratio = f64::INFINITY;
        let mut leaving_row = None;

        for (row_idx, row) in self.tableau.iter().enumerate() {
            let coeff = row[entering_col];

            // Only consider positive coefficients (entering variable increases)
            if coeff > 1e-10 {
                let rhs = row[rhs_col];
                let ratio = rhs / coeff;

                // Minimum ratio test
                if ratio < min_ratio {
                    min_ratio = ratio;
                    leaving_row = Some(row_idx);
                }
            }
        }

        leaving_row
    }

    /// Check if current solution is feasible
    fn is_feasible(&self) -> bool {
        // Check if all RHS values (last column) are non-negative
        self.tableau
            .iter()
            .all(|row| *row.last().unwrap() >= -1e-10)
    }

    /// Extract model from current tableau
    fn extract_model(&self) -> Model {
        let mut model = HashMap::new();
        let num_vars = self.var_names.len();

        // For each original variable (not slack), determine its value
        for (col_idx, var_name) in self.var_names.iter().enumerate() {
            // Check if this variable is basic (in some row)
            if let Some(row_idx) = self.basic_vars.iter().position(|&bv| bv == col_idx) {
                // Basic variable: its value is the RHS of its row
                let value = self.tableau[row_idx].last().unwrap();
                model.insert(var_name.clone(), ModelValue::Int(value.round() as i64));
            } else {
                // Non-basic variable: value is 0 in current solution
                // But for Le constraints, we should extract a valid value
                // Find which row can bound this variable and use that
                let mut best_value: f64 = 0.0;
                for (row_idx, row) in self.tableau.iter().enumerate() {
                    let coeff = row[col_idx];
                    if coeff > 0.0 {
                        let rhs = row.last().unwrap();
                        // This row gives: coeff * x <= rhs (after slack var)
                        let bound = rhs / coeff;
                        if bound >= 0.0 && (best_value == 0.0 || bound < best_value) {
                            best_value = bound;
                        }
                    }
                }
                // Return a satisfying value (anything <= bound works)
                model.insert(var_name.clone(), ModelValue::Int(best_value.round() as i64));
            }
        }

        model
    }
}

impl ConstraintSolver for SimplexSolver {
    fn name(&self) -> &'static str {
        "Simplex"
    }

    fn supported_theories(&self) -> &[Theory] {
        &[Theory::LinearArithmetic]
    }

    fn solve(&mut self, constraint: &Constraint) -> SolverResult {
        match constraint {
            Constraint::LinearArithmetic { .. } => {
                // Single constraint - try to build tableau
                if self.build_tableau(&[constraint]).is_err() {
                    return SolverResult::Unknown;
                }

                if self.is_feasible() {
                    let model = self.extract_model();
                    SolverResult::Sat(Some(model))
                } else {
                    SolverResult::Unsat
                }
            }
            _ => SolverResult::Unknown,
        }
    }

    fn solve_conjunction(&mut self, constraints: &[Constraint]) -> SolverResult {
        // Filter to only LinearArithmetic constraints
        let linear_constraints: Vec<&Constraint> = constraints
            .iter()
            .filter(|c| matches!(c, Constraint::LinearArithmetic { .. }))
            .collect();

        if linear_constraints.is_empty() {
            return SolverResult::Unknown;
        }

        // Build tableau from all constraints
        if self.build_tableau(&linear_constraints).is_err() {
            return SolverResult::Unknown;
        }

        // Run Simplex algorithm
        for _ in 0..self.max_iterations {
            if self.is_feasible() {
                let model = self.extract_model();
                return SolverResult::Sat(Some(model));
            }

            // Find pivot
            if let Some(entering) = self.find_entering_variable() {
                if let Some(leaving) = self.find_leaving_variable(entering) {
                    self.pivot(leaving, entering);
                    continue;
                }
            }

            // No pivot found - either optimal or unbounded
            break;
        }

        if self.is_feasible() {
            let model = self.extract_model();
            SolverResult::Sat(Some(model))
        } else {
            SolverResult::Unsat
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simplex_solver_creation() {
        let solver = SimplexSolver::new();
        assert_eq!(solver.name(), "Simplex");
        assert_eq!(solver.supported_theories(), &[Theory::LinearArithmetic]);
    }

    #[test]
    fn test_simplex_feasible_constraint() {
        let mut solver = SimplexSolver::new();

        // 2*x + 3*y <= 10
        let mut coeffs = HashMap::new();
        coeffs.insert("x".to_string(), 2);
        coeffs.insert("y".to_string(), 3);

        let constraint = Constraint::linear_arithmetic(coeffs, -10, ComparisonOp::Le);

        // Should be SAT (feasible region exists)
        let result = solver.solve(&constraint);
        assert!(matches!(result, SolverResult::Sat(_)));
    }

    #[test]
    fn test_simplex_infeasible_constraints() {
        let mut solver = SimplexSolver::new();

        // x >= 10 AND x <= 5 (contradiction)
        let constraints = vec![
            {
                let mut coeffs = HashMap::new();
                coeffs.insert("x".to_string(), 1);
                Constraint::linear_arithmetic(coeffs, -10, ComparisonOp::Ge)
            },
            {
                let mut coeffs = HashMap::new();
                coeffs.insert("x".to_string(), 1);
                Constraint::linear_arithmetic(coeffs, -5, ComparisonOp::Le)
            },
        ];

        let result = solver.solve_conjunction(&constraints);
        // Should be UNSAT (no solution)
        assert_eq!(result, SolverResult::Unsat);
    }

    #[test]
    fn test_simplex_multiple_variables() {
        let mut solver = SimplexSolver::new();

        // x + y <= 10
        // x >= 0
        // y >= 0
        let constraints = vec![
            {
                let mut coeffs = HashMap::new();
                coeffs.insert("x".to_string(), 1);
                coeffs.insert("y".to_string(), 1);
                Constraint::linear_arithmetic(coeffs, -10, ComparisonOp::Le)
            },
            {
                let mut coeffs = HashMap::new();
                coeffs.insert("x".to_string(), 1);
                Constraint::linear_arithmetic(coeffs, 0, ComparisonOp::Ge)
            },
            {
                let mut coeffs = HashMap::new();
                coeffs.insert("y".to_string(), 1);
                Constraint::linear_arithmetic(coeffs, 0, ComparisonOp::Ge)
            },
        ];

        let result = solver.solve_conjunction(&constraints);
        assert!(matches!(result, SolverResult::Sat(_)));
    }

    #[test]
    fn test_simplex_equality_constraint() {
        let mut solver = SimplexSolver::new();

        // x + y == 10
        let mut coeffs = HashMap::new();
        coeffs.insert("x".to_string(), 1);
        coeffs.insert("y".to_string(), 1);

        let constraint = Constraint::linear_arithmetic(coeffs, -10, ComparisonOp::Eq);

        let result = solver.solve(&constraint);
        assert!(matches!(result, SolverResult::Sat(_)));
    }

    #[test]
    fn test_simplex_model_extraction() {
        let mut solver = SimplexSolver::new();

        // Simple constraint: x <= 5
        let mut coeffs = HashMap::new();
        coeffs.insert("x".to_string(), 1);

        let constraint = Constraint::linear_arithmetic(coeffs, -5, ComparisonOp::Le);

        if let SolverResult::Sat(Some(model)) = solver.solve(&constraint) {
            // Model should contain x with some value <= 5
            assert!(model.contains_key("x"));
        } else {
            panic!("Expected SAT result with model");
        }
    }
}
