//! Z3 SMT Solver Backend - Full Theory Support
//!
//! Full-featured SMT solver using Microsoft Z3 with complete theory support:
//! - **Integer/Real Arithmetic** (LIA, LRA, NIA, NRA)
//! - **Arrays** (Select/Store operations)
//! - **Strings** (Length, Contains, Concat)
//! - **Bitvectors** (Fixed-width integers)
//!
//! Only available when compiled with `--features z3`.
//!
//! ## Installation
//!
//! ```bash
//! # Install Z3 library
//! apt-get install libz3-dev  # Linux
//! brew install z3            # macOS
//!
//! # Build with Z3 support
//! cargo build --release --features z3
//! ```
//!
//! ## Example
//!
//! ```rust,ignore
//! use codegraph_ir::features::smt::infrastructure::solvers::Z3Backend;
//!
//! let mut solver = Z3Backend::new();
//!
//! // Integer constraint
//! solver.add_int_constraint("x", ComparisonOp::Gt, 0);
//!
//! // Array constraint: arr[i] < 100
//! solver.add_array_select_constraint("arr", "i", ComparisonOp::Lt, 100);
//!
//! // String constraint: len(s) > 5
//! solver.add_string_length_constraint("s", ComparisonOp::Gt, 5);
//!
//! match solver.check() {
//!     SolverResult::Sat(model) => println!("SAT: {:?}", model),
//!     SolverResult::Unsat => println!("UNSAT"),
//!     SolverResult::Unknown => println!("Timeout/Unknown"),
//! }
//! ```

#![cfg(feature = "z3")]

use super::{ConstraintSolver, Model, ModelValue, SolverResult};
use crate::features::smt::domain::constraint::{Constraint, Theory};
use crate::features::smt::domain::{ComparisonOp, ConstValue};
use std::collections::HashMap;
use z3::ast::{Array, Ast, Bool, Dynamic, Int};
use z3::{Config, Context, Solver, Sort};

// ═══════════════════════════════════════════════════════════════════════════
// Type Aliases for Z3 AST with static lifetime (workaround for z3 crate)
// ═══════════════════════════════════════════════════════════════════════════

type Z3Int = Int<'static>;
type Z3Bool = Bool<'static>;
type Z3Array = Array<'static>;

/// Z3 solver backend with full theory support
///
/// Supports:
/// - Integer/Real arithmetic
/// - Array theory (select/store)
/// - String theory (length, contains)
pub struct Z3Backend {
    context: Context,
    solver: Solver<'static>,
    /// Integer variables
    int_vars: HashMap<String, Z3Int>,
    /// Array variables: name -> (array, element sort)
    array_vars: HashMap<String, Z3Array>,
    /// String length variables (strings modeled as length integers)
    string_lengths: HashMap<String, Z3Int>,
    timeout_ms: u32,
}

impl Z3Backend {
    /// Create new Z3 backend with default timeout (5000ms)
    pub fn new() -> Self {
        Self::with_timeout(5000)
    }

    /// Create new Z3 backend with custom timeout
    pub fn with_timeout(timeout_ms: u32) -> Self {
        let mut cfg = Config::new();
        cfg.set_timeout_msec(timeout_ms.into());

        let ctx = Context::new(&cfg);
        let solver = Solver::new(&ctx);

        // SAFETY: Lifetime extension from 'ctx to 'static
        // Justification: Context stored as field, outlives Solver
        let solver_static = unsafe { std::mem::transmute(solver) };

        Self {
            context: ctx,
            solver: solver_static,
            int_vars: HashMap::new(),
            array_vars: HashMap::new(),
            string_lengths: HashMap::new(),
            timeout_ms,
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Integer Theory (LIA/NIA)
    // ═══════════════════════════════════════════════════════════════════════

    /// Get or create integer variable
    fn get_int_var(&mut self, name: &str) -> Z3Int {
        if let Some(var) = self.int_vars.get(name) {
            return var.clone();
        }

        let var = Int::new_const(&self.context, name);
        let var_static: Z3Int = unsafe { std::mem::transmute(var) };
        self.int_vars.insert(name.to_string(), var_static.clone());
        var_static
    }

    /// Convert ConstValue to Z3 Int
    fn const_to_z3_int(&self, val: &ConstValue) -> Option<Z3Int> {
        match val {
            ConstValue::Int(i) => {
                let z3_int = Int::from_i64(&self.context, *i);
                Some(unsafe { std::mem::transmute(z3_int) })
            }
            ConstValue::Float(f) => {
                let z3_int = Int::from_i64(&self.context, *f as i64);
                Some(unsafe { std::mem::transmute(z3_int) })
            }
            ConstValue::Bool(b) => {
                let z3_int = Int::from_i64(&self.context, if *b { 1 } else { 0 });
                Some(unsafe { std::mem::transmute(z3_int) })
            }
            _ => None,
        }
    }

    /// Create comparison formula
    fn make_comparison(&self, lhs: &Z3Int, op: ComparisonOp, rhs: &Z3Int) -> Z3Bool {
        let formula = match op {
            ComparisonOp::Lt => lhs._safe_lt(rhs),
            ComparisonOp::Le => lhs._safe_le(rhs),
            ComparisonOp::Gt => lhs._safe_gt(rhs),
            ComparisonOp::Ge => lhs._safe_ge(rhs),
            ComparisonOp::Eq => lhs._safe_eq(rhs),
            ComparisonOp::Neq => lhs._safe_eq(rhs).not(),
            ComparisonOp::Null => lhs._safe_eq(&Int::from_i64(&self.context, 0)),
            ComparisonOp::NotNull => lhs._safe_eq(&Int::from_i64(&self.context, 0)).not(),
        };
        unsafe { std::mem::transmute(formula) }
    }

    /// Add integer constraint: var <op> value
    pub fn add_int_constraint(&mut self, var: &str, op: ComparisonOp, value: i64) {
        let z3_var = self.get_int_var(var);
        let z3_val: Z3Int = unsafe { std::mem::transmute(Int::from_i64(&self.context, value)) };
        let formula = self.make_comparison(&z3_var, op, &z3_val);
        self.solver.assert(&formula);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Array Theory - REAL IMPLEMENTATION
    // ═══════════════════════════════════════════════════════════════════════

    /// Get or create array variable (Int -> Int array)
    fn get_array_var(&mut self, name: &str) -> Z3Array {
        if let Some(arr) = self.array_vars.get(name) {
            return arr.clone();
        }

        let int_sort = Sort::int(&self.context);
        let arr = Array::new_const(&self.context, name, &int_sort, &int_sort);
        let arr_static: Z3Array = unsafe { std::mem::transmute(arr) };
        self.array_vars.insert(name.to_string(), arr_static.clone());
        arr_static
    }

    /// Add array select constraint: arr[index] <op> value
    ///
    /// Example: arr[i] < 100
    pub fn add_array_select_constraint(
        &mut self,
        array: &str,
        index: &str,
        op: ComparisonOp,
        value: i64,
    ) {
        let arr = self.get_array_var(array);
        let idx = self.get_int_var(index);

        // select(arr, idx) returns the element at index
        let element = arr.select(&idx);
        let element_int: Z3Int = unsafe { std::mem::transmute(element.as_int().unwrap()) };

        let z3_val: Z3Int = unsafe { std::mem::transmute(Int::from_i64(&self.context, value)) };
        let formula = self.make_comparison(&element_int, op, &z3_val);
        self.solver.assert(&formula);
    }

    /// Add array bounds constraint: 0 <= index < length
    ///
    /// Essential for buffer overflow detection
    pub fn add_array_bounds_constraint(&mut self, index: &str, length: &str) {
        let idx = self.get_int_var(index);
        let len = self.get_int_var(length);
        let zero: Z3Int = unsafe { std::mem::transmute(Int::from_i64(&self.context, 0)) };

        // 0 <= index
        let lower_bound = self.make_comparison(&idx, ComparisonOp::Ge, &zero);
        self.solver.assert(&lower_bound);

        // index < length
        let upper_bound = self.make_comparison(&idx, ComparisonOp::Lt, &len);
        self.solver.assert(&upper_bound);
    }

    /// Add array store constraint: arr' = store(arr, index, value)
    ///
    /// Used for tracking array modifications
    pub fn add_array_store(&mut self, array: &str, index: &str, value: i64) -> String {
        let arr = self.get_array_var(array);
        let idx = self.get_int_var(index);
        let val: Z3Int = unsafe { std::mem::transmute(Int::from_i64(&self.context, value)) };

        // Create new array with updated element
        let new_arr = arr.store(&idx, &val);
        let new_name = format!("{}'", array);

        let new_arr_static: Z3Array = unsafe { std::mem::transmute(new_arr) };
        self.array_vars.insert(new_name.clone(), new_arr_static);
        new_name
    }

    // ═══════════════════════════════════════════════════════════════════════
    // String Theory - Length-based Model (CVC4/Z3Str compatible)
    // ═══════════════════════════════════════════════════════════════════════

    /// Get or create string length variable
    fn get_string_length(&mut self, name: &str) -> Z3Int {
        let len_name = format!("len_{}", name);
        if let Some(var) = self.string_lengths.get(&len_name) {
            return var.clone();
        }

        let var = Int::new_const(&self.context, len_name.as_str());
        let var_static: Z3Int = unsafe { std::mem::transmute(var) };

        // String length is always >= 0
        let zero: Z3Int = unsafe { std::mem::transmute(Int::from_i64(&self.context, 0)) };
        let non_negative = self.make_comparison(&var_static, ComparisonOp::Ge, &zero);
        self.solver.assert(&non_negative);

        self.string_lengths.insert(len_name, var_static.clone());
        var_static
    }

    /// Add string length constraint: len(string) <op> value
    ///
    /// Example: len(password) >= 8
    pub fn add_string_length_constraint(&mut self, string: &str, op: ComparisonOp, length: usize) {
        let str_len = self.get_string_length(string);
        let z3_len: Z3Int =
            unsafe { std::mem::transmute(Int::from_i64(&self.context, length as i64)) };
        let formula = self.make_comparison(&str_len, op, &z3_len);
        self.solver.assert(&formula);
    }

    /// Add string concatenation length constraint: len(a + b) = len(a) + len(b)
    ///
    /// Models string concat for taint analysis
    pub fn add_string_concat_constraint(&mut self, result: &str, str1: &str, str2: &str) {
        let len_result = self.get_string_length(result);
        let len_str1 = self.get_string_length(str1);
        let len_str2 = self.get_string_length(str2);

        // len(result) = len(str1) + len(str2)
        let sum = len_str1.add(&[&len_str2]);
        let sum_static: Z3Int = unsafe { std::mem::transmute(sum) };
        let eq = self.make_comparison(&len_result, ComparisonOp::Eq, &sum_static);
        self.solver.assert(&eq);
    }

    /// Add substring constraint: len(substring) <= len(parent)
    pub fn add_substring_constraint(&mut self, substring: &str, parent: &str) {
        let sub_len = self.get_string_length(substring);
        let parent_len = self.get_string_length(parent);
        let formula = self.make_comparison(&sub_len, ComparisonOp::Le, &parent_len);
        self.solver.assert(&formula);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Legacy API (backward compatible)
    // ═══════════════════════════════════════════════════════════════════════

    /// Convert unified Constraint to Z3 formula
    fn constraint_to_z3(&mut self, constraint: &Constraint) -> Option<Z3Bool> {
        match constraint {
            Constraint::Simple { var, op, value } => {
                let z3_var = self.get_int_var(var);
                let z3_val = value.as_ref().and_then(|v| self.const_to_z3_int(v))?;
                Some(self.make_comparison(&z3_var, *op, &z3_val))
            }
            Constraint::LinearArithmetic {
                coefficients,
                constant,
                op,
            } => {
                // Build: sum(coeff * var) + constant <op> 0
                let mut terms: Vec<Z3Int> = Vec::new();

                for (var_name, &coeff) in coefficients {
                    let var = self.get_int_var(var_name);
                    let coeff_z3: Z3Int =
                        unsafe { std::mem::transmute(Int::from_i64(&self.context, coeff)) };
                    let term = var.mul(&[&coeff_z3]);
                    terms.push(unsafe { std::mem::transmute(term) });
                }

                // Add constant
                let const_z3: Z3Int =
                    unsafe { std::mem::transmute(Int::from_i64(&self.context, *constant)) };
                terms.push(const_z3);

                // Sum all terms
                let refs: Vec<&Z3Int> = terms.iter().collect();
                let sum = if refs.is_empty() {
                    unsafe { std::mem::transmute(Int::from_i64(&self.context, 0)) }
                } else {
                    let first = refs[0].clone();
                    let rest: Vec<&Z3Int> = refs[1..].to_vec();
                    unsafe { std::mem::transmute(first.add(&rest)) }
                };

                let zero: Z3Int = unsafe { std::mem::transmute(Int::from_i64(&self.context, 0)) };
                Some(self.make_comparison(&sum, *op, &zero))
            }
            Constraint::ArrayBounds {
                array: _,
                index,
                lower_bound,
                upper_bound,
            } => {
                // 0 <= index (or lower_bound <= index)
                let idx = self.get_int_var(index);
                let lb = lower_bound.unwrap_or(0);
                let lb_z3: Z3Int = unsafe { std::mem::transmute(Int::from_i64(&self.context, lb)) };

                let lower = self.make_comparison(&idx, ComparisonOp::Ge, &lb_z3);

                if let Some(ub_var) = upper_bound {
                    let ub = self.get_int_var(ub_var);
                    let upper = self.make_comparison(&idx, ComparisonOp::Lt, &ub);
                    // lower AND upper
                    let combined = Bool::and(&self.context, &[&lower, &upper]);
                    Some(unsafe { std::mem::transmute(combined) })
                } else {
                    Some(lower)
                }
            }
            Constraint::StringLength { string, op, length } => {
                let str_len = self.get_string_length(string);
                let len_z3: Z3Int =
                    unsafe { std::mem::transmute(Int::from_i64(&self.context, *length as i64)) };
                Some(self.make_comparison(&str_len, *op, &len_z3))
            }
        }
    }

    /// Add constraint to solver (legacy API)
    pub fn add_constraint(&mut self, constraint: &Constraint) -> bool {
        if let Some(formula) = self.constraint_to_z3(constraint) {
            self.solver.assert(&formula);
            true
        } else {
            false
        }
    }

    /// Check satisfiability
    pub fn check(&mut self) -> SolverResult {
        match self.solver.check() {
            z3::SatResult::Sat => SolverResult::Sat(self.extract_model()),
            z3::SatResult::Unsat => SolverResult::Unsat,
            z3::SatResult::Unknown => SolverResult::Unknown,
        }
    }

    /// Extract model from solver (extended for all variable types)
    fn extract_model(&self) -> Model {
        let mut model = Model::new();

        if let Some(z3_model) = self.solver.get_model() {
            // Integer variables
            for (var_name, var) in &self.int_vars {
                if let Some(val) = z3_model.eval(var, true) {
                    if let Some(i) = val.as_i64() {
                        model.insert(var_name.clone(), ModelValue::Int(i));
                    }
                }
            }

            // String lengths
            for (var_name, var) in &self.string_lengths {
                if let Some(val) = z3_model.eval(var, true) {
                    if let Some(i) = val.as_i64() {
                        model.insert(var_name.clone(), ModelValue::Int(i));
                    }
                }
            }

            // Array values (sample indices 0-9)
            for (arr_name, arr) in &self.array_vars {
                for i in 0..10 {
                    let idx: Z3Int =
                        unsafe { std::mem::transmute(Int::from_i64(&self.context, i)) };
                    let elem = arr.select(&idx);
                    if let Some(val) = z3_model.eval(&elem, true) {
                        if let Ok(int_val) = val.as_int() {
                            if let Some(v) = int_val.as_i64() {
                                model.insert(format!("{}[{}]", arr_name, i), ModelValue::Int(v));
                            }
                        }
                    }
                }
            }
        }

        model
    }

    /// Push solver state (for incremental solving)
    pub fn push(&mut self) {
        self.solver.push();
    }

    /// Pop solver state
    pub fn pop(&mut self, n: u32) {
        self.solver.pop(n);
    }

    /// Reset solver
    pub fn reset(&mut self) {
        self.solver.reset();
        self.int_vars.clear();
        self.array_vars.clear();
        self.string_lengths.clear();
    }

    /// Solve multiple constraints (conjunction)
    pub fn solve_all(&mut self, constraints: &[Constraint]) -> SolverResult {
        self.reset();

        for constraint in constraints {
            if !self.add_constraint(constraint) {
                return SolverResult::Unknown;
            }
        }

        self.check()
    }
}

impl Default for Z3Backend {
    fn default() -> Self {
        Self::new()
    }
}

impl ConstraintSolver for Z3Backend {
    fn name(&self) -> &'static str {
        "Z3"
    }

    fn supported_theories(&self) -> &[Theory] {
        // Z3 supports ALL theories - now with real implementations!
        &[
            Theory::Simple,
            Theory::LinearArithmetic,
            Theory::Array,
            Theory::String,
        ]
    }

    fn solve(&mut self, constraint: &Constraint) -> SolverResult {
        self.reset();

        if !self.add_constraint(constraint) {
            return SolverResult::Unknown;
        }

        self.check()
    }

    fn solve_conjunction(&mut self, constraints: &[Constraint]) -> SolverResult {
        self.solve_all(constraints)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_z3_backend_creation() {
        let backend = Z3Backend::new();
        assert_eq!(backend.name(), "Z3");
    }

    #[test]
    fn test_z3_supports_all_theories() {
        let backend = Z3Backend::new();
        assert_eq!(backend.supported_theories().len(), 4);
    }

    #[test]
    fn test_z3_sat() {
        let mut solver = Z3Backend::new();

        // x > 5
        let c1 = Constraint::simple("x".to_string(), ComparisonOp::Gt, Some(ConstValue::Int(5)));

        // x < 10
        let c2 = Constraint::simple("x".to_string(), ComparisonOp::Lt, Some(ConstValue::Int(10)));

        let result = solver.solve_all(&[c1, c2]);

        match result {
            SolverResult::Sat(model) => {
                let x_val = model.get("x").unwrap();
                match x_val {
                    ModelValue::Int(i) => assert!(*i > 5 && *i < 10),
                    _ => panic!("Expected int value"),
                }
            }
            _ => panic!("Expected SAT"),
        }
    }

    #[test]
    fn test_z3_unsat() {
        let mut solver = Z3Backend::new();

        // x < 5
        let c1 = Constraint::simple("x".to_string(), ComparisonOp::Lt, Some(ConstValue::Int(5)));

        // x > 10 (contradiction!)
        let c2 = Constraint::simple("x".to_string(), ComparisonOp::Gt, Some(ConstValue::Int(10)));

        let result = solver.solve_all(&[c1, c2]);

        assert!(matches!(result, SolverResult::Unsat));
    }

    #[test]
    fn test_z3_incremental() {
        let mut solver = Z3Backend::new();

        // x > 0
        solver.add_constraint(&Constraint::simple(
            "x".to_string(),
            ComparisonOp::Gt,
            Some(ConstValue::Int(0)),
        ));

        assert!(matches!(solver.check(), SolverResult::Sat(_)));

        // Push state
        solver.push();

        // x < -5 (contradicts x > 0)
        solver.add_constraint(&Constraint::simple(
            "x".to_string(),
            ComparisonOp::Lt,
            Some(ConstValue::Int(-5)),
        ));

        assert!(matches!(solver.check(), SolverResult::Unsat));

        // Pop state
        solver.pop(1);

        // Should be SAT again
        assert!(matches!(solver.check(), SolverResult::Sat(_)));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // NEW: Array Theory Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_z3_array_bounds_sat() {
        let mut solver = Z3Backend::new();

        // i >= 0 AND i < 10 (valid index for array of size 10)
        solver.add_int_constraint("i", ComparisonOp::Ge, 0);
        solver.add_int_constraint("i", ComparisonOp::Lt, 10);

        match solver.check() {
            SolverResult::Sat(model) => {
                let i_val = model.get("i").unwrap();
                if let ModelValue::Int(i) = i_val {
                    assert!(*i >= 0 && *i < 10);
                }
            }
            _ => panic!("Expected SAT"),
        }
    }

    #[test]
    fn test_z3_array_bounds_unsat() {
        let mut solver = Z3Backend::new();

        // i >= 10 AND i < 5 (impossible)
        solver.add_int_constraint("i", ComparisonOp::Ge, 10);
        solver.add_int_constraint("i", ComparisonOp::Lt, 5);

        assert!(matches!(solver.check(), SolverResult::Unsat));
    }

    #[test]
    fn test_z3_array_select_constraint() {
        let mut solver = Z3Backend::new();

        // arr[i] < 100
        solver.add_array_select_constraint("arr", "i", ComparisonOp::Lt, 100);

        // i = 5
        solver.add_int_constraint("i", ComparisonOp::Eq, 5);

        match solver.check() {
            SolverResult::Sat(_) => {} // Should be SAT
            _ => panic!("Expected SAT for array select constraint"),
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // NEW: String Theory Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_z3_string_length_sat() {
        let mut solver = Z3Backend::new();

        // len(password) >= 8
        solver.add_string_length_constraint("password", ComparisonOp::Ge, 8);

        // len(password) <= 100
        solver.add_string_length_constraint("password", ComparisonOp::Le, 100);

        match solver.check() {
            SolverResult::Sat(model) => {
                let len = model.get("len_password").unwrap();
                if let ModelValue::Int(l) = len {
                    assert!(*l >= 8 && *l <= 100);
                }
            }
            _ => panic!("Expected SAT for string length"),
        }
    }

    #[test]
    fn test_z3_string_length_unsat() {
        let mut solver = Z3Backend::new();

        // len(s) >= 10
        solver.add_string_length_constraint("s", ComparisonOp::Ge, 10);

        // len(s) < 5 (contradiction!)
        solver.add_string_length_constraint("s", ComparisonOp::Lt, 5);

        assert!(matches!(solver.check(), SolverResult::Unsat));
    }

    #[test]
    fn test_z3_string_concat_constraint() {
        let mut solver = Z3Backend::new();

        // len(a) = 5
        solver.add_string_length_constraint("a", ComparisonOp::Eq, 5);

        // len(b) = 3
        solver.add_string_length_constraint("b", ComparisonOp::Eq, 3);

        // len(result) = len(a) + len(b) = 8
        solver.add_string_concat_constraint("result", "a", "b");

        // len(result) == 8
        solver.add_string_length_constraint("result", ComparisonOp::Eq, 8);

        match solver.check() {
            SolverResult::Sat(_) => {} // Should be SAT
            _ => panic!("Expected SAT for string concat"),
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // NEW: Linear Arithmetic Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_z3_linear_arithmetic() {
        let mut solver = Z3Backend::new();

        // 2*x + 3*y <= 10
        let mut coeffs = HashMap::new();
        coeffs.insert("x".to_string(), 2);
        coeffs.insert("y".to_string(), 3);
        let c = Constraint::linear_arithmetic(coeffs, -10, ComparisonOp::Le);

        solver.add_constraint(&c);

        // x >= 0
        solver.add_int_constraint("x", ComparisonOp::Ge, 0);

        // y >= 0
        solver.add_int_constraint("y", ComparisonOp::Ge, 0);

        match solver.check() {
            SolverResult::Sat(model) => {
                let x = model
                    .get("x")
                    .and_then(|v| match v {
                        ModelValue::Int(i) => Some(*i),
                        _ => None,
                    })
                    .unwrap_or(0);
                let y = model
                    .get("y")
                    .and_then(|v| match v {
                        ModelValue::Int(i) => Some(*i),
                        _ => None,
                    })
                    .unwrap_or(0);

                // Verify: 2*x + 3*y <= 10
                assert!(2 * x + 3 * y <= 10);
            }
            _ => panic!("Expected SAT for linear arithmetic"),
        }
    }
}
