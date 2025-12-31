//! Refinement Types System
//!
//! Implements SOTA refinement types based on:
//! - Rondon et al. (2008): "Liquid Types"
//! - Vazou et al. (2014): "Refinement Types for Haskell"
//!
//! ## Key Concepts
//!
//! 1. **Refinement Types**: Base types refined by predicates
//!    - `{x: int | x > 0}` - positive integers
//!    - `{s: str | len(s) <= 255}` - bounded strings
//!
//! 2. **Predicate Language**: Logical formulas over values
//!    - Arithmetic: `x + 1`, `x * 2`, `x / y`
//!    - Comparison: `x < y`, `x == y`, `x != y`
//!    - Logical: `p && q`, `p || q`, `!p`
//!
//! 3. **Subtyping**: Refinement subtyping via implication
//!    - `{x: int | x > 0} <: {x: int | x >= 0}` because `x > 0 ⟹ x >= 0`
//!
//! ## Performance
//! - Predicate evaluation: O(predicate size)
//! - Subtype check: O(predicate complexity) - may use SMT
//! - Refinement inference: O(constraints) with liquid type inference

use super::{Type, TypeKind};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::fmt;

// ==================== Predicate Language ====================

/// Variable reference in predicates
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Var {
    /// The refined value itself (ν or "nu")
    Value,
    /// Named variable
    Named(String),
    /// Length of a collection/string
    Length(Box<Var>),
}

impl fmt::Display for Var {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Var::Value => write!(f, "ν"),
            Var::Named(name) => write!(f, "{}", name),
            Var::Length(var) => write!(f, "len({})", var),
        }
    }
}

/// Arithmetic expression
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ArithExpr {
    /// Constant value
    Const(i64),
    /// Variable reference
    Var(Var),
    /// Addition
    Add(Box<ArithExpr>, Box<ArithExpr>),
    /// Subtraction
    Sub(Box<ArithExpr>, Box<ArithExpr>),
    /// Multiplication
    Mul(Box<ArithExpr>, Box<ArithExpr>),
    /// Division
    Div(Box<ArithExpr>, Box<ArithExpr>),
    /// Modulo
    Mod(Box<ArithExpr>, Box<ArithExpr>),
    /// Negation
    Neg(Box<ArithExpr>),
}

impl ArithExpr {
    pub fn constant(value: i64) -> Self {
        ArithExpr::Const(value)
    }

    pub fn var(v: Var) -> Self {
        ArithExpr::Var(v)
    }

    pub fn value() -> Self {
        ArithExpr::Var(Var::Value)
    }

    pub fn named(name: impl Into<String>) -> Self {
        ArithExpr::Var(Var::Named(name.into()))
    }

    pub fn length(var: Var) -> Self {
        ArithExpr::Var(Var::Length(Box::new(var)))
    }

    pub fn add(self, other: ArithExpr) -> Self {
        ArithExpr::Add(Box::new(self), Box::new(other))
    }

    pub fn sub(self, other: ArithExpr) -> Self {
        ArithExpr::Sub(Box::new(self), Box::new(other))
    }

    pub fn mul(self, other: ArithExpr) -> Self {
        ArithExpr::Mul(Box::new(self), Box::new(other))
    }

    /// Evaluate expression with given variable bindings
    pub fn evaluate(&self, bindings: &HashMap<Var, i64>) -> Option<i64> {
        match self {
            ArithExpr::Const(v) => Some(*v),
            ArithExpr::Var(var) => bindings.get(var).copied(),
            ArithExpr::Add(l, r) => Some(l.evaluate(bindings)? + r.evaluate(bindings)?),
            ArithExpr::Sub(l, r) => Some(l.evaluate(bindings)? - r.evaluate(bindings)?),
            ArithExpr::Mul(l, r) => Some(l.evaluate(bindings)? * r.evaluate(bindings)?),
            ArithExpr::Div(l, r) => {
                let rv = r.evaluate(bindings)?;
                if rv == 0 {
                    None
                } else {
                    Some(l.evaluate(bindings)? / rv)
                }
            }
            ArithExpr::Mod(l, r) => {
                let rv = r.evaluate(bindings)?;
                if rv == 0 {
                    None
                } else {
                    Some(l.evaluate(bindings)? % rv)
                }
            }
            ArithExpr::Neg(e) => Some(-e.evaluate(bindings)?),
        }
    }

    /// Get all free variables in expression
    pub fn free_vars(&self) -> HashSet<Var> {
        let mut vars = HashSet::new();
        self.collect_vars(&mut vars);
        vars
    }

    fn collect_vars(&self, vars: &mut HashSet<Var>) {
        match self {
            ArithExpr::Const(_) => {}
            ArithExpr::Var(v) => {
                vars.insert(v.clone());
            }
            ArithExpr::Add(l, r)
            | ArithExpr::Sub(l, r)
            | ArithExpr::Mul(l, r)
            | ArithExpr::Div(l, r)
            | ArithExpr::Mod(l, r) => {
                l.collect_vars(vars);
                r.collect_vars(vars);
            }
            ArithExpr::Neg(e) => e.collect_vars(vars),
        }
    }
}

impl fmt::Display for ArithExpr {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ArithExpr::Const(v) => write!(f, "{}", v),
            ArithExpr::Var(v) => write!(f, "{}", v),
            ArithExpr::Add(l, r) => write!(f, "({} + {})", l, r),
            ArithExpr::Sub(l, r) => write!(f, "({} - {})", l, r),
            ArithExpr::Mul(l, r) => write!(f, "({} * {})", l, r),
            ArithExpr::Div(l, r) => write!(f, "({} / {})", l, r),
            ArithExpr::Mod(l, r) => write!(f, "({} % {})", l, r),
            ArithExpr::Neg(e) => write!(f, "-{}", e),
        }
    }
}

/// Comparison operator
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum CompOp {
    Lt, // <
    Le, // <=
    Gt, // >
    Ge, // >=
    Eq, // ==
    Ne, // !=
}

impl CompOp {
    pub fn evaluate(&self, left: i64, right: i64) -> bool {
        match self {
            CompOp::Lt => left < right,
            CompOp::Le => left <= right,
            CompOp::Gt => left > right,
            CompOp::Ge => left >= right,
            CompOp::Eq => left == right,
            CompOp::Ne => left != right,
        }
    }

    /// Negate the operator
    pub fn negate(&self) -> Self {
        match self {
            CompOp::Lt => CompOp::Ge,
            CompOp::Le => CompOp::Gt,
            CompOp::Gt => CompOp::Le,
            CompOp::Ge => CompOp::Lt,
            CompOp::Eq => CompOp::Ne,
            CompOp::Ne => CompOp::Eq,
        }
    }
}

impl fmt::Display for CompOp {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CompOp::Lt => write!(f, "<"),
            CompOp::Le => write!(f, "<="),
            CompOp::Gt => write!(f, ">"),
            CompOp::Ge => write!(f, ">="),
            CompOp::Eq => write!(f, "=="),
            CompOp::Ne => write!(f, "!="),
        }
    }
}

/// Predicate (logical formula)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Predicate {
    /// True (tautology)
    True,
    /// False (contradiction)
    False,
    /// Comparison: e1 op e2
    Cmp(ArithExpr, CompOp, ArithExpr),
    /// Logical AND
    And(Box<Predicate>, Box<Predicate>),
    /// Logical OR
    Or(Box<Predicate>, Box<Predicate>),
    /// Logical NOT
    Not(Box<Predicate>),
    /// Implication: p ⟹ q
    Implies(Box<Predicate>, Box<Predicate>),
}

impl Predicate {
    /// Create a comparison predicate
    pub fn cmp(left: ArithExpr, op: CompOp, right: ArithExpr) -> Self {
        Predicate::Cmp(left, op, right)
    }

    /// ν > 0
    pub fn positive() -> Self {
        Predicate::cmp(ArithExpr::value(), CompOp::Gt, ArithExpr::constant(0))
    }

    /// ν >= 0
    pub fn non_negative() -> Self {
        Predicate::cmp(ArithExpr::value(), CompOp::Ge, ArithExpr::constant(0))
    }

    /// ν != 0
    pub fn non_zero() -> Self {
        Predicate::cmp(ArithExpr::value(), CompOp::Ne, ArithExpr::constant(0))
    }

    /// ν < n
    pub fn less_than(n: i64) -> Self {
        Predicate::cmp(ArithExpr::value(), CompOp::Lt, ArithExpr::constant(n))
    }

    /// ν <= n
    pub fn at_most(n: i64) -> Self {
        Predicate::cmp(ArithExpr::value(), CompOp::Le, ArithExpr::constant(n))
    }

    /// ν > n
    pub fn greater_than(n: i64) -> Self {
        Predicate::cmp(ArithExpr::value(), CompOp::Gt, ArithExpr::constant(n))
    }

    /// ν >= n
    pub fn at_least(n: i64) -> Self {
        Predicate::cmp(ArithExpr::value(), CompOp::Ge, ArithExpr::constant(n))
    }

    /// n <= ν <= m (range)
    pub fn in_range(min: i64, max: i64) -> Self {
        Predicate::And(
            Box::new(Predicate::at_least(min)),
            Box::new(Predicate::at_most(max)),
        )
    }

    /// len(ν) <= n
    pub fn max_length(n: i64) -> Self {
        Predicate::cmp(
            ArithExpr::length(Var::Value),
            CompOp::Le,
            ArithExpr::constant(n),
        )
    }

    /// len(ν) >= n
    pub fn min_length(n: i64) -> Self {
        Predicate::cmp(
            ArithExpr::length(Var::Value),
            CompOp::Ge,
            ArithExpr::constant(n),
        )
    }

    /// len(ν) == n
    pub fn exact_length(n: i64) -> Self {
        Predicate::cmp(
            ArithExpr::length(Var::Value),
            CompOp::Eq,
            ArithExpr::constant(n),
        )
    }

    /// Logical AND
    pub fn and(self, other: Predicate) -> Self {
        match (&self, &other) {
            (Predicate::True, _) => other,
            (_, Predicate::True) => self,
            (Predicate::False, _) | (_, Predicate::False) => Predicate::False,
            _ => Predicate::And(Box::new(self), Box::new(other)),
        }
    }

    /// Logical OR
    pub fn or(self, other: Predicate) -> Self {
        match (&self, &other) {
            (Predicate::True, _) | (_, Predicate::True) => Predicate::True,
            (Predicate::False, _) => other,
            (_, Predicate::False) => self,
            _ => Predicate::Or(Box::new(self), Box::new(other)),
        }
    }

    /// Logical NOT
    pub fn not(self) -> Self {
        match self {
            Predicate::True => Predicate::False,
            Predicate::False => Predicate::True,
            Predicate::Not(inner) => *inner,
            _ => Predicate::Not(Box::new(self)),
        }
    }

    /// Implication
    pub fn implies(self, other: Predicate) -> Self {
        Predicate::Implies(Box::new(self), Box::new(other))
    }

    /// Evaluate predicate with given bindings
    pub fn evaluate(&self, bindings: &HashMap<Var, i64>) -> Option<bool> {
        match self {
            Predicate::True => Some(true),
            Predicate::False => Some(false),
            Predicate::Cmp(l, op, r) => {
                let lv = l.evaluate(bindings)?;
                let rv = r.evaluate(bindings)?;
                Some(op.evaluate(lv, rv))
            }
            Predicate::And(p, q) => Some(p.evaluate(bindings)? && q.evaluate(bindings)?),
            Predicate::Or(p, q) => Some(p.evaluate(bindings)? || q.evaluate(bindings)?),
            Predicate::Not(p) => Some(!p.evaluate(bindings)?),
            Predicate::Implies(p, q) => {
                let pv = p.evaluate(bindings)?;
                let qv = q.evaluate(bindings)?;
                Some(!pv || qv)
            }
        }
    }

    /// Get all free variables
    pub fn free_vars(&self) -> HashSet<Var> {
        let mut vars = HashSet::new();
        self.collect_vars(&mut vars);
        vars
    }

    fn collect_vars(&self, vars: &mut HashSet<Var>) {
        match self {
            Predicate::True | Predicate::False => {}
            Predicate::Cmp(l, _, r) => {
                vars.extend(l.free_vars());
                vars.extend(r.free_vars());
            }
            Predicate::And(p, q) | Predicate::Or(p, q) | Predicate::Implies(p, q) => {
                p.collect_vars(vars);
                q.collect_vars(vars);
            }
            Predicate::Not(p) => p.collect_vars(vars),
        }
    }

    /// Check if predicate is satisfiable (simple check)
    pub fn is_satisfiable(&self) -> bool {
        match self {
            Predicate::False => false,
            Predicate::True => true,
            Predicate::Cmp(ArithExpr::Const(l), op, ArithExpr::Const(r)) => op.evaluate(*l, *r),
            Predicate::And(p, q) => p.is_satisfiable() && q.is_satisfiable(),
            Predicate::Or(p, q) => p.is_satisfiable() || q.is_satisfiable(),
            Predicate::Not(p) => !matches!(p.as_ref(), Predicate::True),
            _ => true, // Conservative: assume satisfiable
        }
    }
}

impl fmt::Display for Predicate {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Predicate::True => write!(f, "true"),
            Predicate::False => write!(f, "false"),
            Predicate::Cmp(l, op, r) => write!(f, "{} {} {}", l, op, r),
            Predicate::And(p, q) => write!(f, "({} ∧ {})", p, q),
            Predicate::Or(p, q) => write!(f, "({} ∨ {})", p, q),
            Predicate::Not(p) => write!(f, "¬{}", p),
            Predicate::Implies(p, q) => write!(f, "({} ⟹ {})", p, q),
        }
    }
}

// ==================== Refinement Types ====================

/// Refinement type: {ν: T | φ}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RefinementType {
    /// Base type
    pub base: Type,
    /// Refinement predicate
    pub predicate: Predicate,
}

impl RefinementType {
    /// Create a new refinement type
    pub fn new(base: Type, predicate: Predicate) -> Self {
        Self { base, predicate }
    }

    /// Create unrefined type (predicate = true)
    pub fn unrefined(base: Type) -> Self {
        Self {
            base,
            predicate: Predicate::True,
        }
    }

    /// Positive int: {ν: int | ν > 0}
    pub fn positive_int() -> Self {
        Self::new(Type::simple("int"), Predicate::positive())
    }

    /// Non-negative int: {ν: int | ν >= 0}
    pub fn nat() -> Self {
        Self::new(Type::simple("int"), Predicate::non_negative())
    }

    /// Non-zero int: {ν: int | ν != 0}
    pub fn non_zero_int() -> Self {
        Self::new(Type::simple("int"), Predicate::non_zero())
    }

    /// Bounded int: {ν: int | min <= ν <= max}
    pub fn bounded_int(min: i64, max: i64) -> Self {
        Self::new(Type::simple("int"), Predicate::in_range(min, max))
    }

    /// Bounded string: {ν: str | len(ν) <= max}
    pub fn bounded_string(max_len: i64) -> Self {
        Self::new(Type::simple("str"), Predicate::max_length(max_len))
    }

    /// Non-empty string: {ν: str | len(ν) > 0}
    pub fn non_empty_string() -> Self {
        Self::new(
            Type::simple("str"),
            Predicate::cmp(
                ArithExpr::length(Var::Value),
                CompOp::Gt,
                ArithExpr::constant(0),
            ),
        )
    }

    /// Fixed-length string: {ν: str | len(ν) == n}
    pub fn fixed_length_string(len: i64) -> Self {
        Self::new(Type::simple("str"), Predicate::exact_length(len))
    }

    /// Check if a value satisfies the refinement
    pub fn check(&self, value: i64) -> bool {
        let mut bindings = HashMap::new();
        bindings.insert(Var::Value, value);
        self.predicate.evaluate(&bindings).unwrap_or(false)
    }

    /// Check if a string value satisfies the refinement (using length)
    pub fn check_string(&self, value: &str) -> bool {
        let mut bindings = HashMap::new();
        bindings.insert(Var::Length(Box::new(Var::Value)), value.len() as i64);
        self.predicate.evaluate(&bindings).unwrap_or(false)
    }

    /// Conjoin with another predicate
    pub fn with_predicate(mut self, pred: Predicate) -> Self {
        self.predicate = self.predicate.and(pred);
        self
    }
}

impl fmt::Display for RefinementType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if matches!(self.predicate, Predicate::True) {
            write!(f, "{}", self.base)
        } else {
            write!(f, "{{ν: {} | {}}}", self.base, self.predicate)
        }
    }
}

// ==================== Refinement Subtyping ====================

/// Subtyping result
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SubtypeResult {
    /// Subtype relation holds
    Subtype,
    /// Not a subtype
    NotSubtype(String),
    /// Unknown (can't determine statically)
    Unknown,
}

/// Check if t1 is a subtype of t2 under refinement subtyping
///
/// `{ν: T | φ} <: {ν: T | ψ}` iff `φ ⟹ ψ`
pub fn is_subtype(t1: &RefinementType, t2: &RefinementType) -> SubtypeResult {
    // Base types must be compatible
    if t1.base != t2.base {
        // Check if base types are in subtype relation (for classes)
        // For now, require exact match
        return SubtypeResult::NotSubtype(format!(
            "Base type mismatch: {} vs {}",
            t1.base, t2.base
        ));
    }

    // Check if φ ⟹ ψ (simple cases)
    match (&t1.predicate, &t2.predicate) {
        // T <: {ν: T | true}
        (_, Predicate::True) => SubtypeResult::Subtype,

        // {ν: T | false} <: T
        (Predicate::False, _) => SubtypeResult::Subtype,

        // Same predicate
        (p1, p2) if p1 == p2 => SubtypeResult::Subtype,

        // Check numeric range implications
        (
            Predicate::Cmp(_, op1, ArithExpr::Const(v1)),
            Predicate::Cmp(_, op2, ArithExpr::Const(v2)),
        ) => {
            if implies_comparison(*op1, *v1, *op2, *v2) {
                SubtypeResult::Subtype
            } else {
                SubtypeResult::NotSubtype(format!(
                    "Predicate {} does not imply {}",
                    t1.predicate, t2.predicate
                ))
            }
        }

        // Default: can't determine
        _ => SubtypeResult::Unknown,
    }
}

/// Check if comparison (op1, v1) implies (op2, v2)
/// e.g., ν > 5 implies ν > 0
fn implies_comparison(op1: CompOp, v1: i64, op2: CompOp, v2: i64) -> bool {
    match (op1, op2) {
        // x > v1 implies x > v2 if v1 >= v2
        (CompOp::Gt, CompOp::Gt) => v1 >= v2,
        // x > v1 implies x >= v2 if v1 >= v2
        (CompOp::Gt, CompOp::Ge) => v1 >= v2,
        // x >= v1 implies x >= v2 if v1 >= v2
        (CompOp::Ge, CompOp::Ge) => v1 >= v2,
        // x >= v1 implies x > v2 if v1 > v2
        (CompOp::Ge, CompOp::Gt) => v1 > v2,

        // x < v1 implies x < v2 if v1 <= v2
        (CompOp::Lt, CompOp::Lt) => v1 <= v2,
        // x < v1 implies x <= v2 if v1 <= v2
        (CompOp::Lt, CompOp::Le) => v1 <= v2,
        // x <= v1 implies x <= v2 if v1 <= v2
        (CompOp::Le, CompOp::Le) => v1 <= v2,
        // x <= v1 implies x < v2 if v1 < v2
        (CompOp::Le, CompOp::Lt) => v1 < v2,

        // x == v1 implies x == v2 if v1 == v2
        (CompOp::Eq, CompOp::Eq) => v1 == v2,
        // x == v1 implies x >= v2 if v1 >= v2
        (CompOp::Eq, CompOp::Ge) => v1 >= v2,
        // x == v1 implies x <= v2 if v1 <= v2
        (CompOp::Eq, CompOp::Le) => v1 <= v2,
        // x == v1 implies x > v2 if v1 > v2
        (CompOp::Eq, CompOp::Gt) => v1 > v2,
        // x == v1 implies x < v2 if v1 < v2
        (CompOp::Eq, CompOp::Lt) => v1 < v2,

        // x != v1 does not generally imply other constraints
        (CompOp::Ne, _) => false,
        // Other combinations don't imply
        _ => false,
    }
}

// ==================== Common Refinement Type Aliases ====================

/// Type alias registry for common refinements
#[derive(Debug, Default)]
pub struct RefinementAliases {
    aliases: HashMap<String, RefinementType>,
}

impl RefinementAliases {
    pub fn new() -> Self {
        let mut aliases = HashMap::new();

        // Common numeric types
        aliases.insert("Nat".to_string(), RefinementType::nat());
        aliases.insert("Pos".to_string(), RefinementType::positive_int());
        aliases.insert("NonZero".to_string(), RefinementType::non_zero_int());

        // Common string types
        aliases.insert(
            "NonEmptyStr".to_string(),
            RefinementType::non_empty_string(),
        );

        // Bounded types
        aliases.insert("Byte".to_string(), RefinementType::bounded_int(0, 255));
        aliases.insert("Port".to_string(), RefinementType::bounded_int(0, 65535));
        aliases.insert(
            "Percentage".to_string(),
            RefinementType::bounded_int(0, 100),
        );

        Self { aliases }
    }

    /// Add a type alias
    pub fn add(&mut self, name: impl Into<String>, ty: RefinementType) {
        self.aliases.insert(name.into(), ty);
    }

    /// Get a type alias
    pub fn get(&self, name: &str) -> Option<&RefinementType> {
        self.aliases.get(name)
    }

    /// List all aliases
    pub fn list(&self) -> Vec<(&String, &RefinementType)> {
        self.aliases.iter().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_arithmetic_expr() {
        let expr = ArithExpr::value().add(ArithExpr::constant(1));
        let mut bindings = HashMap::new();
        bindings.insert(Var::Value, 5);

        assert_eq!(expr.evaluate(&bindings), Some(6));
    }

    #[test]
    fn test_predicate_positive() {
        let pred = Predicate::positive();
        let mut bindings = HashMap::new();

        bindings.insert(Var::Value, 5);
        assert_eq!(pred.evaluate(&bindings), Some(true));

        bindings.insert(Var::Value, 0);
        assert_eq!(pred.evaluate(&bindings), Some(false));

        bindings.insert(Var::Value, -1);
        assert_eq!(pred.evaluate(&bindings), Some(false));
    }

    #[test]
    fn test_predicate_range() {
        let pred = Predicate::in_range(0, 100);
        let mut bindings = HashMap::new();

        bindings.insert(Var::Value, 50);
        assert_eq!(pred.evaluate(&bindings), Some(true));

        bindings.insert(Var::Value, -1);
        assert_eq!(pred.evaluate(&bindings), Some(false));

        bindings.insert(Var::Value, 101);
        assert_eq!(pred.evaluate(&bindings), Some(false));
    }

    #[test]
    fn test_refinement_type_check() {
        let pos_int = RefinementType::positive_int();

        assert!(pos_int.check(1));
        assert!(pos_int.check(100));
        assert!(!pos_int.check(0));
        assert!(!pos_int.check(-5));
    }

    #[test]
    fn test_bounded_string() {
        let bounded = RefinementType::bounded_string(10);

        assert!(bounded.check_string("hello"));
        assert!(bounded.check_string(""));
        // Length check uses len(ν) <= 10
    }

    #[test]
    fn test_subtyping() {
        let pos = RefinementType::positive_int();
        let nat = RefinementType::nat();

        // {ν: int | ν > 0} <: {ν: int | ν >= 0}
        assert_eq!(is_subtype(&pos, &nat), SubtypeResult::Subtype);

        // {ν: int | ν >= 0} NOT <: {ν: int | ν > 0}
        assert!(matches!(
            is_subtype(&nat, &pos),
            SubtypeResult::NotSubtype(_)
        ));
    }

    #[test]
    fn test_subtyping_bounded() {
        let narrow = RefinementType::bounded_int(10, 20);
        let wide = RefinementType::bounded_int(0, 100);

        // Can't directly compare ranges in simple check
        // This returns Unknown
        let result = is_subtype(&narrow, &wide);
        assert!(matches!(result, SubtypeResult::Unknown));
    }

    #[test]
    fn test_aliases() {
        let aliases = RefinementAliases::new();

        let nat = aliases.get("Nat").unwrap();
        assert!(nat.check(0));
        assert!(nat.check(100));
        assert!(!nat.check(-1));

        let byte = aliases.get("Byte").unwrap();
        assert!(byte.check(0));
        assert!(byte.check(255));
        assert!(!byte.check(256));
        assert!(!byte.check(-1));
    }

    #[test]
    fn test_display() {
        let pos = RefinementType::positive_int();
        assert!(pos.to_string().contains("ν > 0"));

        let bounded = RefinementType::bounded_int(0, 100);
        assert!(bounded.to_string().contains("ν >= 0"));
    }

    #[test]
    fn test_predicate_logic() {
        let p1 = Predicate::positive();
        let p2 = Predicate::less_than(100);

        let combined = p1.and(p2);
        let mut bindings = HashMap::new();

        bindings.insert(Var::Value, 50);
        assert_eq!(combined.evaluate(&bindings), Some(true));

        bindings.insert(Var::Value, 0);
        assert_eq!(combined.evaluate(&bindings), Some(false));

        bindings.insert(Var::Value, 100);
        assert_eq!(combined.evaluate(&bindings), Some(false));
    }

    #[test]
    fn test_implication() {
        // ν > 5 implies ν > 0
        assert!(implies_comparison(CompOp::Gt, 5, CompOp::Gt, 0));

        // ν > 5 implies ν >= 0
        assert!(implies_comparison(CompOp::Gt, 5, CompOp::Ge, 0));

        // ν > 0 does NOT imply ν > 5
        assert!(!implies_comparison(CompOp::Gt, 0, CompOp::Gt, 5));

        // ν == 10 implies ν > 5
        assert!(implies_comparison(CompOp::Eq, 10, CompOp::Gt, 5));
    }
}
