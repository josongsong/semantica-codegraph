/// Separation Logic Foundation for Bi-Abduction
///
/// Implements symbolic heap model for compositional effect analysis.
/// Based on industry SOTA: Facebook Infer's approach.
///
/// References:
/// - "Compositional Shape Analysis by means of Bi-Abduction" (Calcagno et al.)
/// - Facebook Infer implementation
use std::collections::{HashMap, HashSet};
use std::fmt;

// ==================== Symbolic Variables ====================

/// Symbolic variable (program variable or generated)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum SymbolicVar {
    /// Program variable (x, y, z)
    ProgramVar(String),
    /// Generated existential variable (?v1, ?v2)
    Existential(usize),
    /// Return value placeholder
    ReturnValue,
    /// Null pointer
    Null,
}

impl fmt::Display for SymbolicVar {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SymbolicVar::ProgramVar(name) => write!(f, "{}", name),
            SymbolicVar::Existential(id) => write!(f, "?v{}", id),
            SymbolicVar::ReturnValue => write!(f, "ret"),
            SymbolicVar::Null => write!(f, "null"),
        }
    }
}

// ==================== Pure Formulas (π) ====================

/// Pure formula (arithmetic/logical constraints)
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PureFormula {
    /// True (always holds)
    True,
    /// False (contradiction)
    False,
    /// Equality: v1 = v2
    Equal(SymbolicVar, SymbolicVar),
    /// Inequality: v1 ≠ v2
    NotEqual(SymbolicVar, SymbolicVar),
    /// Conjunction: φ1 ∧ φ2
    And(Box<PureFormula>, Box<PureFormula>),
    /// Disjunction: φ1 ∨ φ2
    Or(Box<PureFormula>, Box<PureFormula>),
    /// Negation: ¬φ
    Not(Box<PureFormula>),
}

impl PureFormula {
    pub fn and(self, other: PureFormula) -> Self {
        match (&self, &other) {
            (PureFormula::True, _) => other,
            (_, PureFormula::True) => self,
            (PureFormula::False, _) | (_, PureFormula::False) => PureFormula::False,
            _ => PureFormula::And(Box::new(self), Box::new(other)),
        }
    }

    pub fn or(self, other: PureFormula) -> Self {
        match (&self, &other) {
            (PureFormula::True, _) | (_, PureFormula::True) => PureFormula::True,
            (PureFormula::False, _) => other,
            (_, PureFormula::False) => self,
            _ => PureFormula::Or(Box::new(self), Box::new(other)),
        }
    }

    /// Check if formula is satisfiable (simple check, can be enhanced with SMT)
    pub fn is_satisfiable(&self) -> bool {
        match self {
            PureFormula::True => true,
            PureFormula::False => false,
            PureFormula::Equal(v1, v2) => v1 != &SymbolicVar::Null || v2 != &SymbolicVar::Null,
            PureFormula::NotEqual(_, _) => true,
            PureFormula::And(p1, p2) => p1.is_satisfiable() && p2.is_satisfiable(),
            PureFormula::Or(p1, p2) => p1.is_satisfiable() || p2.is_satisfiable(),
            PureFormula::Not(p) => !matches!(**p, PureFormula::True),
        }
    }
}

impl fmt::Display for PureFormula {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PureFormula::True => write!(f, "true"),
            PureFormula::False => write!(f, "false"),
            PureFormula::Equal(v1, v2) => write!(f, "{} = {}", v1, v2),
            PureFormula::NotEqual(v1, v2) => write!(f, "{} ≠ {}", v1, v2),
            PureFormula::And(p1, p2) => write!(f, "({} ∧ {})", p1, p2),
            PureFormula::Or(p1, p2) => write!(f, "({} ∨ {})", p1, p2),
            PureFormula::Not(p) => write!(f, "¬{}", p),
        }
    }
}

// ==================== Spatial Formulas (σ) ====================

/// Heap predicate (points-to, predicate abstraction)
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum HeapPredicate {
    /// Empty heap
    Emp,

    /// Points-to: x ↦ {f1: v1, f2: v2, ...}
    /// Example: obj ↦ {name: "foo", value: 42}
    PointsTo {
        base: SymbolicVar,
        fields: HashMap<String, SymbolicVar>,
    },

    /// List segment: ls(x, y) means linked list from x to y
    ListSegment { from: SymbolicVar, to: SymbolicVar },

    /// Abstract predicate (for abstraction)
    /// Example: Tree(root), Queue(head, tail)
    Predicate {
        name: String,
        args: Vec<SymbolicVar>,
    },

    /// Separating conjunction: σ1 * σ2 (heap split)
    SepConj(Box<HeapPredicate>, Box<HeapPredicate>),
}

impl HeapPredicate {
    /// Separating conjunction (σ1 * σ2)
    pub fn sep_conj(self, other: HeapPredicate) -> Self {
        match (&self, &other) {
            (HeapPredicate::Emp, _) => other,
            (_, HeapPredicate::Emp) => self,
            _ => HeapPredicate::SepConj(Box::new(self), Box::new(other)),
        }
    }

    /// Get all variables mentioned in heap predicate
    pub fn get_vars(&self) -> HashSet<SymbolicVar> {
        let mut vars = HashSet::new();
        match self {
            HeapPredicate::Emp => {}
            HeapPredicate::PointsTo { base, fields } => {
                vars.insert(base.clone());
                for v in fields.values() {
                    vars.insert(v.clone());
                }
            }
            HeapPredicate::ListSegment { from, to } => {
                vars.insert(from.clone());
                vars.insert(to.clone());
            }
            HeapPredicate::Predicate { args, .. } => {
                for v in args {
                    vars.insert(v.clone());
                }
            }
            HeapPredicate::SepConj(h1, h2) => {
                vars.extend(h1.get_vars());
                vars.extend(h2.get_vars());
            }
        }
        vars
    }
}

impl fmt::Display for HeapPredicate {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            HeapPredicate::Emp => write!(f, "emp"),
            HeapPredicate::PointsTo { base, fields } => {
                write!(f, "{} ↦ {{", base)?;
                let mut first = true;
                for (field, val) in fields {
                    if !first {
                        write!(f, ", ")?;
                    }
                    write!(f, "{}: {}", field, val)?;
                    first = false;
                }
                write!(f, "}}")
            }
            HeapPredicate::ListSegment { from, to } => {
                write!(f, "ls({}, {})", from, to)
            }
            HeapPredicate::Predicate { name, args } => {
                write!(f, "{}(", name)?;
                for (i, arg) in args.iter().enumerate() {
                    if i > 0 {
                        write!(f, ", ")?;
                    }
                    write!(f, "{}", arg)?;
                }
                write!(f, ")")
            }
            HeapPredicate::SepConj(h1, h2) => write!(f, "{} * {}", h1, h2),
        }
    }
}

// ==================== Symbolic Heap (π ∧ σ) ====================

/// Symbolic heap: conjunction of pure formula and spatial formula
///
/// Format: ∃ v1, v2, ... . π ∧ σ
/// - Existentials: existentially quantified variables
/// - Pure: arithmetic/logical constraints
/// - Spatial: heap shape constraints
#[derive(Debug, Clone, PartialEq)]
pub struct SymbolicHeap {
    /// Existentially quantified variables
    pub existentials: HashSet<SymbolicVar>,
    /// Pure formula (constraints)
    pub pure: PureFormula,
    /// Spatial formula (heap shape)
    pub spatial: HeapPredicate,
}

impl SymbolicHeap {
    /// Create empty symbolic heap (emp)
    pub fn emp() -> Self {
        Self {
            existentials: HashSet::new(),
            pure: PureFormula::True,
            spatial: HeapPredicate::Emp,
        }
    }

    /// Create symbolic heap with only spatial part
    pub fn from_spatial(spatial: HeapPredicate) -> Self {
        Self {
            existentials: HashSet::new(),
            pure: PureFormula::True,
            spatial,
        }
    }

    /// Add pure constraint
    pub fn add_pure(mut self, constraint: PureFormula) -> Self {
        self.pure = self.pure.and(constraint);
        self
    }

    /// Add existential variable
    pub fn add_existential(mut self, var: SymbolicVar) -> Self {
        self.existentials.insert(var);
        self
    }

    /// Separating conjunction with another symbolic heap
    pub fn sep_conj(mut self, other: SymbolicHeap) -> Self {
        // Merge existentials
        self.existentials.extend(other.existentials);
        // Conjoin pure formulas
        self.pure = self.pure.and(other.pure);
        // Separating conjunction of spatial
        self.spatial = self.spatial.sep_conj(other.spatial);
        self
    }

    /// Check if heap is empty
    pub fn is_emp(&self) -> bool {
        matches!(self.spatial, HeapPredicate::Emp)
    }

    /// Get all free variables (program variables only)
    pub fn get_free_vars(&self) -> HashSet<SymbolicVar> {
        let mut vars = self.spatial.get_vars();
        // Remove existentials
        vars.retain(|v| !self.existentials.contains(v));
        vars
    }
}

impl fmt::Display for SymbolicHeap {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        // Print existentials
        if !self.existentials.is_empty() {
            write!(f, "∃ ")?;
            for (i, v) in self.existentials.iter().enumerate() {
                if i > 0 {
                    write!(f, ", ")?;
                }
                write!(f, "{}", v)?;
            }
            write!(f, " . ")?;
        }

        // Print pure formula if not True
        if !matches!(self.pure, PureFormula::True) {
            write!(f, "{} ∧ ", self.pure)?;
        }

        // Print spatial formula
        write!(f, "{}", self.spatial)
    }
}

// ==================== Specification (Hoare Triple) ====================

/// Function specification: {P} f(x) {Q}
/// - Precondition P: Required heap state before call
/// - Postcondition Q: Guaranteed heap state after call
#[derive(Debug, Clone, PartialEq)]
pub struct FunctionSpec {
    /// Function identifier
    pub function_id: String,
    /// Precondition (required state)
    pub precondition: SymbolicHeap,
    /// Postcondition (guaranteed state)
    pub postcondition: SymbolicHeap,
}

impl FunctionSpec {
    pub fn new(
        function_id: String,
        precondition: SymbolicHeap,
        postcondition: SymbolicHeap,
    ) -> Self {
        Self {
            function_id,
            precondition,
            postcondition,
        }
    }

    /// Create trivial spec (emp -> emp)
    pub fn trivial(function_id: String) -> Self {
        Self {
            function_id,
            precondition: SymbolicHeap::emp(),
            postcondition: SymbolicHeap::emp(),
        }
    }
}

impl fmt::Display for FunctionSpec {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{{{}}} {}() {{{}}}",
            self.precondition, self.function_id, self.postcondition
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_symbolic_var() {
        let var = SymbolicVar::ProgramVar("x".to_string());
        assert_eq!(var.to_string(), "x");

        let exist = SymbolicVar::Existential(1);
        assert_eq!(exist.to_string(), "?v1");
    }

    #[test]
    fn test_pure_formula() {
        let x = SymbolicVar::ProgramVar("x".to_string());
        let y = SymbolicVar::ProgramVar("y".to_string());

        let eq = PureFormula::Equal(x.clone(), y.clone());
        assert!(eq.is_satisfiable());

        let and = PureFormula::True.and(eq);
        assert!(and.is_satisfiable());
    }

    #[test]
    fn test_points_to() {
        let x = SymbolicVar::ProgramVar("x".to_string());
        let v1 = SymbolicVar::Existential(1);

        let mut fields = HashMap::new();
        fields.insert("next".to_string(), v1.clone());

        let pointsto = HeapPredicate::PointsTo {
            base: x.clone(),
            fields,
        };

        assert!(pointsto.to_string().contains("x ↦"));
    }

    #[test]
    fn test_symbolic_heap_emp() {
        let heap = SymbolicHeap::emp();
        assert!(heap.is_emp());
        assert_eq!(heap.to_string(), "emp");
    }

    #[test]
    fn test_symbolic_heap_with_existentials() {
        let x = SymbolicVar::ProgramVar("x".to_string());
        let v1 = SymbolicVar::Existential(1);

        let mut fields = HashMap::new();
        fields.insert("data".to_string(), v1.clone());

        let spatial = HeapPredicate::PointsTo {
            base: x.clone(),
            fields,
        };

        let heap = SymbolicHeap::from_spatial(spatial).add_existential(v1.clone());

        assert!(heap.to_string().contains("∃"));
    }

    #[test]
    fn test_sep_conj() {
        let x = SymbolicVar::ProgramVar("x".to_string());
        let y = SymbolicVar::ProgramVar("y".to_string());

        let h1 = HeapPredicate::PointsTo {
            base: x,
            fields: HashMap::new(),
        };

        let h2 = HeapPredicate::PointsTo {
            base: y,
            fields: HashMap::new(),
        };

        let combined = h1.sep_conj(h2);
        assert!(combined.to_string().contains("*"));
    }

    #[test]
    fn test_function_spec() {
        let spec = FunctionSpec::trivial("test_func".to_string());
        assert!(spec.precondition.is_emp());
        assert!(spec.postcondition.is_emp());
    }
}
