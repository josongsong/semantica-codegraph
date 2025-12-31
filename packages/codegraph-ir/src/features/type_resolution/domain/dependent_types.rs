//! Dependent Types System (Basic Structure)
//!
//! Implements basic dependent types based on:
//! - Pierce, "Types and Programming Languages"
//! - Xi & Pfenning (1999): "Dependent Types in Practical Programming"
//!
//! ## Key Concepts
//!
//! 1. **Dependent Function (Π-type)**: Return type depends on argument value
//!    - `Π(n: Nat). Vec[n] → Vec[n+1]` (append function type)
//!
//! 2. **Dependent Pair (Σ-type)**: Second component type depends on first
//!    - `Σ(n: Nat). Vec[n]` (vector with its length)
//!
//! 3. **Indexed Types**: Types parameterized by values
//!    - `Vec[3, int]` - exactly 3 integers
//!    - `Matrix[m, n, float]` - m×n float matrix
//!
//! ## Limitations
//!
//! This is a simplified implementation suitable for common cases:
//! - Index expressions limited to linear arithmetic
//! - No full dependent type checking (would require SMT)
//! - Focus on practical patterns (length-indexed vectors, sized arrays)
//!
//! ## Performance
//! - Index evaluation: O(1) for simple indices
//! - Type equality with indices: O(index complexity)

use super::{Type, TypeKind};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fmt;

// ==================== Index Expressions ====================

/// Index variable (value-level parameter)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct IndexVar {
    pub name: String,
}

impl IndexVar {
    pub fn new(name: impl Into<String>) -> Self {
        Self { name: name.into() }
    }
}

impl fmt::Display for IndexVar {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.name)
    }
}

/// Index expression (value-level term in types)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum IndexExpr {
    /// Constant index
    Const(i64),
    /// Index variable
    Var(IndexVar),
    /// Addition
    Add(Box<IndexExpr>, Box<IndexExpr>),
    /// Subtraction
    Sub(Box<IndexExpr>, Box<IndexExpr>),
    /// Multiplication
    Mul(Box<IndexExpr>, Box<IndexExpr>),
    /// Length of variable (for arrays/strings)
    Length(IndexVar),
}

impl IndexExpr {
    /// Create constant index
    pub fn constant(n: i64) -> Self {
        IndexExpr::Const(n)
    }

    /// Create variable index
    pub fn var(name: impl Into<String>) -> Self {
        IndexExpr::Var(IndexVar::new(name))
    }

    /// Create length expression
    pub fn length(name: impl Into<String>) -> Self {
        IndexExpr::Length(IndexVar::new(name))
    }

    /// n + 1
    pub fn plus_one(self) -> Self {
        IndexExpr::Add(Box::new(self), Box::new(IndexExpr::Const(1)))
    }

    /// n - 1
    pub fn minus_one(self) -> Self {
        IndexExpr::Sub(Box::new(self), Box::new(IndexExpr::Const(1)))
    }

    /// Addition
    pub fn add(self, other: IndexExpr) -> Self {
        IndexExpr::Add(Box::new(self), Box::new(other))
    }

    /// Subtraction
    pub fn sub(self, other: IndexExpr) -> Self {
        IndexExpr::Sub(Box::new(self), Box::new(other))
    }

    /// Multiplication
    pub fn mul(self, other: IndexExpr) -> Self {
        IndexExpr::Mul(Box::new(self), Box::new(other))
    }

    /// Evaluate with given bindings
    pub fn evaluate(&self, bindings: &HashMap<String, i64>) -> Option<i64> {
        match self {
            IndexExpr::Const(n) => Some(*n),
            IndexExpr::Var(v) => bindings.get(&v.name).copied(),
            IndexExpr::Add(l, r) => Some(l.evaluate(bindings)? + r.evaluate(bindings)?),
            IndexExpr::Sub(l, r) => Some(l.evaluate(bindings)? - r.evaluate(bindings)?),
            IndexExpr::Mul(l, r) => Some(l.evaluate(bindings)? * r.evaluate(bindings)?),
            IndexExpr::Length(v) => bindings.get(&format!("len_{}", v.name)).copied(),
        }
    }

    /// Substitute variable with expression
    pub fn substitute(&self, var: &str, expr: &IndexExpr) -> IndexExpr {
        match self {
            IndexExpr::Const(n) => IndexExpr::Const(*n),
            IndexExpr::Var(v) if v.name == var => expr.clone(),
            IndexExpr::Var(v) => IndexExpr::Var(v.clone()),
            IndexExpr::Add(l, r) => IndexExpr::Add(
                Box::new(l.substitute(var, expr)),
                Box::new(r.substitute(var, expr)),
            ),
            IndexExpr::Sub(l, r) => IndexExpr::Sub(
                Box::new(l.substitute(var, expr)),
                Box::new(r.substitute(var, expr)),
            ),
            IndexExpr::Mul(l, r) => IndexExpr::Mul(
                Box::new(l.substitute(var, expr)),
                Box::new(r.substitute(var, expr)),
            ),
            IndexExpr::Length(v) => IndexExpr::Length(v.clone()),
        }
    }

    /// Simplify constant expressions
    pub fn simplify(&self) -> IndexExpr {
        match self {
            IndexExpr::Const(_) | IndexExpr::Var(_) | IndexExpr::Length(_) => self.clone(),
            IndexExpr::Add(l, r) => {
                let l = l.simplify();
                let r = r.simplify();
                if let (IndexExpr::Const(a), IndexExpr::Const(b)) = (&l, &r) {
                    IndexExpr::Const(a + b)
                } else if let IndexExpr::Const(0) = l {
                    r
                } else if let IndexExpr::Const(0) = r {
                    l
                } else {
                    IndexExpr::Add(Box::new(l), Box::new(r))
                }
            }
            IndexExpr::Sub(l, r) => {
                let l = l.simplify();
                let r = r.simplify();
                if let (IndexExpr::Const(a), IndexExpr::Const(b)) = (&l, &r) {
                    IndexExpr::Const(a - b)
                } else if let IndexExpr::Const(0) = r {
                    l
                } else {
                    IndexExpr::Sub(Box::new(l), Box::new(r))
                }
            }
            IndexExpr::Mul(l, r) => {
                let l = l.simplify();
                let r = r.simplify();
                if let (IndexExpr::Const(a), IndexExpr::Const(b)) = (&l, &r) {
                    IndexExpr::Const(a * b)
                } else if let IndexExpr::Const(0) = l {
                    IndexExpr::Const(0)
                } else if let IndexExpr::Const(0) = r {
                    IndexExpr::Const(0)
                } else if let IndexExpr::Const(1) = l {
                    r
                } else if let IndexExpr::Const(1) = r {
                    l
                } else {
                    IndexExpr::Mul(Box::new(l), Box::new(r))
                }
            }
        }
    }

    /// Get all free variables
    pub fn free_vars(&self) -> Vec<String> {
        match self {
            IndexExpr::Const(_) => Vec::new(),
            IndexExpr::Var(v) => vec![v.name.clone()],
            IndexExpr::Add(l, r) | IndexExpr::Sub(l, r) | IndexExpr::Mul(l, r) => {
                let mut vars = l.free_vars();
                vars.extend(r.free_vars());
                vars.sort();
                vars.dedup();
                vars
            }
            IndexExpr::Length(v) => vec![v.name.clone()],
        }
    }
}

impl fmt::Display for IndexExpr {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            IndexExpr::Const(n) => write!(f, "{}", n),
            IndexExpr::Var(v) => write!(f, "{}", v),
            IndexExpr::Add(l, r) => write!(f, "({} + {})", l, r),
            IndexExpr::Sub(l, r) => write!(f, "({} - {})", l, r),
            IndexExpr::Mul(l, r) => write!(f, "({} * {})", l, r),
            IndexExpr::Length(v) => write!(f, "len({})", v),
        }
    }
}

// ==================== Indexed Types ====================

/// Indexed type: Type parameterized by index expressions
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IndexedType {
    /// Base type name (e.g., "Vec", "Matrix", "Array")
    pub base: String,
    /// Index expressions (e.g., [3], [m, n])
    pub indices: Vec<IndexExpr>,
    /// Element type (if applicable)
    pub element_type: Option<Box<Type>>,
}

impl IndexedType {
    /// Create new indexed type
    pub fn new(base: impl Into<String>, indices: Vec<IndexExpr>, element: Option<Type>) -> Self {
        Self {
            base: base.into(),
            indices,
            element_type: element.map(Box::new),
        }
    }

    /// Vec[n, T] - vector of n elements of type T
    pub fn vec(size: IndexExpr, element: Type) -> Self {
        Self::new("Vec", vec![size], Some(element))
    }

    /// Array[n, T] - fixed-size array
    pub fn array(size: IndexExpr, element: Type) -> Self {
        Self::new("Array", vec![size], Some(element))
    }

    /// Matrix[m, n, T] - m×n matrix
    pub fn matrix(rows: IndexExpr, cols: IndexExpr, element: Type) -> Self {
        Self::new("Matrix", vec![rows, cols], Some(element))
    }

    /// String[n] - string of length n
    pub fn sized_string(size: IndexExpr) -> Self {
        Self::new("String", vec![size], None)
    }

    /// Tuple with specific arity
    pub fn sized_tuple(arity: IndexExpr) -> Self {
        Self::new("Tuple", vec![arity], None)
    }

    /// Check if two indexed types are equal (may be undecidable in general)
    pub fn is_equal(&self, other: &IndexedType, bindings: &HashMap<String, i64>) -> Option<bool> {
        if self.base != other.base {
            return Some(false);
        }
        if self.indices.len() != other.indices.len() {
            return Some(false);
        }

        for (i1, i2) in self.indices.iter().zip(other.indices.iter()) {
            let v1 = i1.evaluate(bindings)?;
            let v2 = i2.evaluate(bindings)?;
            if v1 != v2 {
                return Some(false);
            }
        }

        // Check element type if present
        match (&self.element_type, &other.element_type) {
            (Some(t1), Some(t2)) => Some(t1 == t2),
            (None, None) => Some(true),
            _ => Some(false),
        }
    }

    /// Substitute index variable
    pub fn substitute(&self, var: &str, expr: &IndexExpr) -> IndexedType {
        IndexedType {
            base: self.base.clone(),
            indices: self
                .indices
                .iter()
                .map(|i| i.substitute(var, expr))
                .collect(),
            element_type: self.element_type.clone(),
        }
    }

    /// Get all free index variables
    pub fn free_index_vars(&self) -> Vec<String> {
        let mut vars = Vec::new();
        for idx in &self.indices {
            vars.extend(idx.free_vars());
        }
        vars.sort();
        vars.dedup();
        vars
    }
}

impl fmt::Display for IndexedType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.base)?;
        if !self.indices.is_empty() {
            write!(f, "[")?;
            for (i, idx) in self.indices.iter().enumerate() {
                if i > 0 {
                    write!(f, ", ")?;
                }
                write!(f, "{}", idx)?;
            }
            if let Some(elem) = &self.element_type {
                write!(f, ", {}", elem)?;
            }
            write!(f, "]")?;
        }
        Ok(())
    }
}

// ==================== Dependent Function Type (Π-type) ====================

/// Dependent function type: Π(x: A). B(x)
///
/// The return type B can depend on the argument value x.
#[derive(Debug, Clone)]
pub struct PiType {
    /// Parameter name
    pub param_name: String,
    /// Parameter type
    pub param_type: Type,
    /// Return type (may reference param_name)
    pub return_type: DependentReturnType,
}

/// Return type that may depend on argument
#[derive(Debug, Clone)]
pub enum DependentReturnType {
    /// Simple return type (no dependency)
    Simple(Type),
    /// Indexed return type (depends on argument)
    Indexed(IndexedType),
}

impl PiType {
    /// Create non-dependent function type (ordinary function)
    pub fn simple(param_type: Type, return_type: Type) -> Self {
        Self {
            param_name: "_".to_string(),
            param_type,
            return_type: DependentReturnType::Simple(return_type),
        }
    }

    /// Create dependent function type
    pub fn dependent(
        param_name: impl Into<String>,
        param_type: Type,
        return_type: IndexedType,
    ) -> Self {
        Self {
            param_name: param_name.into(),
            param_type,
            return_type: DependentReturnType::Indexed(return_type),
        }
    }

    /// Example: head : Π(n: Nat). Vec[n+1, T] → T
    pub fn head_type(element_type: Type) -> Self {
        Self {
            param_name: "n".to_string(),
            param_type: Type::simple("Nat"),
            return_type: DependentReturnType::Simple(element_type),
        }
    }

    /// Example: append : Π(n: Nat). Vec[n, T] → T → Vec[n+1, T]
    pub fn append_type(element_type: Type) -> Self {
        let n = IndexExpr::var("n");
        let n_plus_1 = n.plus_one();
        Self {
            param_name: "n".to_string(),
            param_type: Type::simple("Nat"),
            return_type: DependentReturnType::Indexed(IndexedType::vec(n_plus_1, element_type)),
        }
    }

    /// Instantiate with a specific index value
    pub fn instantiate(&self, value: &IndexExpr) -> DependentReturnType {
        match &self.return_type {
            DependentReturnType::Simple(t) => DependentReturnType::Simple(t.clone()),
            DependentReturnType::Indexed(idx) => {
                DependentReturnType::Indexed(idx.substitute(&self.param_name, value))
            }
        }
    }
}

impl fmt::Display for PiType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.return_type {
            DependentReturnType::Simple(ret) => {
                write!(f, "{} → {}", self.param_type, ret)
            }
            DependentReturnType::Indexed(ret) => {
                write!(f, "Π({}: {}). {}", self.param_name, self.param_type, ret)
            }
        }
    }
}

// ==================== Dependent Pair Type (Σ-type) ====================

/// Dependent pair type: Σ(x: A). B(x)
///
/// A pair where the type of the second component depends on the value of the first.
#[derive(Debug, Clone)]
pub struct SigmaType {
    /// First component name
    pub fst_name: String,
    /// First component type
    pub fst_type: Type,
    /// Second component type (may reference fst_name)
    pub snd_type: DependentReturnType,
}

impl SigmaType {
    /// Create simple pair (non-dependent)
    pub fn simple(fst_type: Type, snd_type: Type) -> Self {
        Self {
            fst_name: "_".to_string(),
            fst_type,
            snd_type: DependentReturnType::Simple(snd_type),
        }
    }

    /// Create dependent pair
    pub fn dependent(fst_name: impl Into<String>, fst_type: Type, snd_type: IndexedType) -> Self {
        Self {
            fst_name: fst_name.into(),
            fst_type,
            snd_type: DependentReturnType::Indexed(snd_type),
        }
    }

    /// Example: Σ(n: Nat). Vec[n, T] - a vector paired with its length
    pub fn sized_vec(element_type: Type) -> Self {
        let n = IndexExpr::var("n");
        Self {
            fst_name: "n".to_string(),
            fst_type: Type::simple("Nat"),
            snd_type: DependentReturnType::Indexed(IndexedType::vec(n, element_type)),
        }
    }

    /// Instantiate with a specific first value
    pub fn instantiate(&self, value: &IndexExpr) -> DependentReturnType {
        match &self.snd_type {
            DependentReturnType::Simple(t) => DependentReturnType::Simple(t.clone()),
            DependentReturnType::Indexed(idx) => {
                DependentReturnType::Indexed(idx.substitute(&self.fst_name, value))
            }
        }
    }
}

impl fmt::Display for SigmaType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.snd_type {
            DependentReturnType::Simple(snd) => {
                write!(f, "({} × {})", self.fst_type, snd)
            }
            DependentReturnType::Indexed(snd) => {
                write!(f, "Σ({}: {}). {}", self.fst_name, self.fst_type, snd)
            }
        }
    }
}

// ==================== Common Dependent Type Patterns ====================

/// Registry of common dependent type patterns
#[derive(Debug, Default)]
pub struct DependentTypePatterns {
    patterns: HashMap<String, DependentTypePattern>,
}

/// A dependent type pattern
#[derive(Debug, Clone)]
pub struct DependentTypePattern {
    pub name: String,
    pub description: String,
    pub example: String,
}

impl DependentTypePatterns {
    pub fn new() -> Self {
        let mut patterns = HashMap::new();

        patterns.insert(
            "SizedVec".to_string(),
            DependentTypePattern {
                name: "SizedVec".to_string(),
                description: "Vector with statically known length".to_string(),
                example: "Vec[3, int] - exactly 3 integers".to_string(),
            },
        );

        patterns.insert(
            "BoundedString".to_string(),
            DependentTypePattern {
                name: "BoundedString".to_string(),
                description: "String with bounded length".to_string(),
                example: "String[<=255] - string up to 255 chars".to_string(),
            },
        );

        patterns.insert(
            "Matrix".to_string(),
            DependentTypePattern {
                name: "Matrix".to_string(),
                description: "Matrix with dimension constraints".to_string(),
                example: "Matrix[m, n, float] - m×n float matrix".to_string(),
            },
        );

        patterns.insert(
            "NonEmpty".to_string(),
            DependentTypePattern {
                name: "NonEmpty".to_string(),
                description: "Collection guaranteed to be non-empty".to_string(),
                example: "Vec[n+1, T] where n >= 0".to_string(),
            },
        );

        Self { patterns }
    }

    pub fn get(&self, name: &str) -> Option<&DependentTypePattern> {
        self.patterns.get(name)
    }

    pub fn list(&self) -> Vec<&DependentTypePattern> {
        self.patterns.values().collect()
    }
}

// ==================== Index Constraint Checking ====================

/// Constraint on index expressions
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum IndexConstraint {
    /// i == j
    Equal(IndexExpr, IndexExpr),
    /// i < j
    LessThan(IndexExpr, IndexExpr),
    /// i <= j
    LessOrEqual(IndexExpr, IndexExpr),
    /// i >= 0 (non-negative)
    NonNegative(IndexExpr),
}

impl IndexConstraint {
    /// Check if constraint is satisfied with given bindings
    pub fn check(&self, bindings: &HashMap<String, i64>) -> Option<bool> {
        match self {
            IndexConstraint::Equal(l, r) => Some(l.evaluate(bindings)? == r.evaluate(bindings)?),
            IndexConstraint::LessThan(l, r) => Some(l.evaluate(bindings)? < r.evaluate(bindings)?),
            IndexConstraint::LessOrEqual(l, r) => {
                Some(l.evaluate(bindings)? <= r.evaluate(bindings)?)
            }
            IndexConstraint::NonNegative(e) => Some(e.evaluate(bindings)? >= 0),
        }
    }
}

impl fmt::Display for IndexConstraint {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            IndexConstraint::Equal(l, r) => write!(f, "{} = {}", l, r),
            IndexConstraint::LessThan(l, r) => write!(f, "{} < {}", l, r),
            IndexConstraint::LessOrEqual(l, r) => write!(f, "{} <= {}", l, r),
            IndexConstraint::NonNegative(e) => write!(f, "{} >= 0", e),
        }
    }
}

/// Index constraint solver (simple version)
#[derive(Debug, Default)]
pub struct IndexConstraintSolver {
    constraints: Vec<IndexConstraint>,
    bindings: HashMap<String, i64>,
}

impl IndexConstraintSolver {
    pub fn new() -> Self {
        Self {
            constraints: Vec::new(),
            bindings: HashMap::new(),
        }
    }

    /// Add a constraint
    pub fn add_constraint(&mut self, constraint: IndexConstraint) {
        self.constraints.push(constraint);
    }

    /// Add a binding
    pub fn bind(&mut self, var: impl Into<String>, value: i64) {
        self.bindings.insert(var.into(), value);
    }

    /// Check all constraints
    pub fn check_all(&self) -> bool {
        self.constraints
            .iter()
            .all(|c| c.check(&self.bindings).unwrap_or(false))
    }

    /// Get unsatisfied constraints
    pub fn unsatisfied(&self) -> Vec<&IndexConstraint> {
        self.constraints
            .iter()
            .filter(|c| !c.check(&self.bindings).unwrap_or(true))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_index_expr_eval() {
        let expr = IndexExpr::var("n").add(IndexExpr::constant(1));
        let mut bindings = HashMap::new();
        bindings.insert("n".to_string(), 5);

        assert_eq!(expr.evaluate(&bindings), Some(6));
    }

    #[test]
    fn test_index_expr_simplify() {
        let expr = IndexExpr::constant(2).add(IndexExpr::constant(3));
        assert_eq!(expr.simplify(), IndexExpr::Const(5));

        let expr2 = IndexExpr::var("n").add(IndexExpr::constant(0));
        assert_eq!(expr2.simplify(), IndexExpr::Var(IndexVar::new("n")));
    }

    #[test]
    fn test_indexed_type() {
        let vec_3_int = IndexedType::vec(IndexExpr::constant(3), Type::simple("int"));
        assert_eq!(vec_3_int.to_string(), "Vec[3, int]");

        let matrix = IndexedType::matrix(
            IndexExpr::var("m"),
            IndexExpr::var("n"),
            Type::simple("float"),
        );
        assert_eq!(matrix.to_string(), "Matrix[m, n, float]");
    }

    #[test]
    fn test_indexed_type_equality() {
        let t1 = IndexedType::vec(IndexExpr::var("n"), Type::simple("int"));
        let t2 = IndexedType::vec(IndexExpr::constant(5), Type::simple("int"));

        let mut bindings = HashMap::new();
        bindings.insert("n".to_string(), 5);

        assert_eq!(t1.is_equal(&t2, &bindings), Some(true));

        bindings.insert("n".to_string(), 3);
        assert_eq!(t1.is_equal(&t2, &bindings), Some(false));
    }

    #[test]
    fn test_pi_type() {
        let append = PiType::append_type(Type::simple("int"));
        assert!(append.to_string().contains("Π"));
        assert!(append.to_string().contains("n"));
    }

    #[test]
    fn test_pi_instantiate() {
        let pi = PiType::append_type(Type::simple("int"));
        let instantiated = pi.instantiate(&IndexExpr::constant(5));

        if let DependentReturnType::Indexed(idx) = instantiated {
            // Should be Vec[6, int] (5 + 1)
            assert_eq!(idx.indices.len(), 1);
            let simplified = idx.indices[0].simplify();
            assert_eq!(simplified, IndexExpr::Const(6));
        } else {
            panic!("Expected indexed return type");
        }
    }

    #[test]
    fn test_sigma_type() {
        let sized_vec = SigmaType::sized_vec(Type::simple("int"));
        assert!(sized_vec.to_string().contains("Σ"));
    }

    #[test]
    fn test_index_constraint() {
        let constraint = IndexConstraint::LessThan(IndexExpr::var("i"), IndexExpr::var("n"));

        let mut bindings = HashMap::new();
        bindings.insert("i".to_string(), 3);
        bindings.insert("n".to_string(), 10);

        assert_eq!(constraint.check(&bindings), Some(true));

        bindings.insert("i".to_string(), 10);
        assert_eq!(constraint.check(&bindings), Some(false));
    }

    #[test]
    fn test_constraint_solver() {
        let mut solver = IndexConstraintSolver::new();

        solver.add_constraint(IndexConstraint::NonNegative(IndexExpr::var("n")));
        solver.add_constraint(IndexConstraint::LessThan(
            IndexExpr::var("i"),
            IndexExpr::var("n"),
        ));

        solver.bind("n", 10);
        solver.bind("i", 5);

        assert!(solver.check_all());

        solver.bind("i", 15);
        assert!(!solver.check_all());
        assert_eq!(solver.unsatisfied().len(), 1);
    }

    #[test]
    fn test_substitution() {
        let expr = IndexExpr::var("n").add(IndexExpr::constant(1));
        let substituted = expr.substitute("n", &IndexExpr::constant(5));
        let simplified = substituted.simplify();

        assert_eq!(simplified, IndexExpr::Const(6));
    }

    #[test]
    fn test_patterns() {
        let patterns = DependentTypePatterns::new();
        assert!(patterns.get("SizedVec").is_some());
        assert!(patterns.get("Matrix").is_some());
    }
}
