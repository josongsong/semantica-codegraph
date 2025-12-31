/*
 * Type Narrowing Analyzer
 *
 * Port from Python:
 * - type_narrowing_analyzer.py (187 lines)
 * - type_narrowing_full.py (367 lines)
 *
 * Key Features:
 * - Control-flow based type inference
 * - isinstance(), is None, truthiness tracking
 * - Branch-specific type states
 * - Union type narrowing to specific types
 * - Type guard function recognition
 *
 * Algorithm:
 * - Flow-sensitive type tracking
 * - Branch splitting for if/else
 * - Meet operation for join points
 * - Type constraint propagation
 *
 * Performance Target: 10-50x faster than Python
 * - Python: 554 LOC with dict-based states
 * - Rust: Efficient state copying + fast constraints
 *
 * References:
 * - TypeScript's type narrowing system
 * - Flow's refinement types
 * - Pyright's type inference
 */

use rustc_hash::FxHashMap;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

/// Type narrowing kind
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TypeNarrowingKind {
    /// isinstance(var, Type)
    IsInstance,

    /// var is None
    IsNone,

    /// var is not None
    IsNotNone,

    /// Truthiness check (if var:)
    Truthiness,

    /// Comparison (var == value)
    Comparison,

    /// Attribute check (hasattr(var, 'attr'))
    AttributeCheck,

    /// Type guard function
    TypeGuard,
}

/// Type constraint at a specific location
///
/// Example:
///   if isinstance(x, str):
///     → TypeConstraint { variable: "x", narrowed_to: "str", ... }
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypeConstraint {
    /// Variable name
    pub variable: String,

    /// Constraint type
    pub constraint_type: TypeNarrowingKind,

    /// Narrowed type
    pub narrowed_to: String,

    /// Source location (line, column)
    pub location: (usize, usize),

    /// Scope identifier
    pub scope: String,

    /// Confidence (0.0-1.0)
    pub confidence: f64,
}

impl TypeConstraint {
    /// Create new type constraint
    pub fn new(
        variable: impl Into<String>,
        constraint_type: TypeNarrowingKind,
        narrowed_to: impl Into<String>,
        location: (usize, usize),
    ) -> Self {
        Self {
            variable: variable.into(),
            constraint_type,
            narrowed_to: narrowed_to.into(),
            location,
            scope: "global".to_string(),
            confidence: 1.0,
        }
    }

    /// Create with scope
    pub fn with_scope(mut self, scope: impl Into<String>) -> Self {
        self.scope = scope.into();
        self
    }

    /// Create with confidence
    pub fn with_confidence(mut self, confidence: f64) -> Self {
        self.confidence = confidence;
        self
    }
}

/// Type state at a program point
///
/// Tracks possible types for each variable at this location.
///
/// Example:
///   Before: x: Union[str, int, None]
///   After isinstance(x, str): x: str
#[derive(Debug, Clone)]
pub struct TypeState {
    /// Variable types: var -> set of possible types
    pub variables: FxHashMap<String, HashSet<String>>,

    /// Active type constraints
    pub constraints: Vec<TypeConstraint>,
}

impl TypeState {
    /// Create new empty type state
    pub fn new() -> Self {
        Self {
            variables: FxHashMap::default(),
            constraints: Vec::new(),
        }
    }

    /// Create with initial types
    pub fn with_types(variables: FxHashMap<String, HashSet<String>>) -> Self {
        Self {
            variables,
            constraints: Vec::new(),
        }
    }

    /// Get types for a variable
    pub fn get_types(&self, var: &str) -> Option<&HashSet<String>> {
        self.variables.get(var)
    }

    /// Set types for a variable
    pub fn set_types(&mut self, var: impl Into<String>, types: HashSet<String>) {
        self.variables.insert(var.into(), types);
    }

    /// Add a type for a variable
    pub fn add_type(&mut self, var: impl Into<String>, typ: impl Into<String>) {
        self.variables
            .entry(var.into())
            .or_insert_with(HashSet::new)
            .insert(typ.into());
    }

    /// Remove a type from a variable
    pub fn remove_type(&mut self, var: &str, typ: &str) {
        if let Some(types) = self.variables.get_mut(var) {
            types.remove(typ);
        }
    }

    /// Narrow variable to specific type
    pub fn narrow_to(&mut self, var: impl Into<String>, typ: impl Into<String>) {
        let var = var.into();
        let typ = typ.into();
        self.variables.insert(var, HashSet::from([typ]));
    }

    /// Apply type constraint
    pub fn apply_constraint(&mut self, constraint: &TypeConstraint) {
        match constraint.constraint_type {
            TypeNarrowingKind::IsInstance => {
                // Narrow to specific type
                self.narrow_to(&constraint.variable, &constraint.narrowed_to);
            }
            TypeNarrowingKind::IsNone => {
                // Narrow to None
                self.narrow_to(&constraint.variable, "None");
            }
            TypeNarrowingKind::IsNotNone => {
                // Remove None from possibilities
                self.remove_type(&constraint.variable, "None");
            }
            TypeNarrowingKind::Truthiness => {
                // Remove falsy types
                self.remove_type(&constraint.variable, "None");
                self.remove_type(&constraint.variable, "False");
                self.remove_type(&constraint.variable, "0");
                self.remove_type(&constraint.variable, "");
            }
            TypeNarrowingKind::Comparison
            | TypeNarrowingKind::AttributeCheck
            | TypeNarrowingKind::TypeGuard => {
                // Narrow to constraint type
                self.narrow_to(&constraint.variable, &constraint.narrowed_to);
            }
        }

        self.constraints.push(constraint.clone());
    }

    /// Create inverse constraint (for else branch)
    pub fn apply_inverse_constraint(&mut self, constraint: &TypeConstraint) {
        match constraint.constraint_type {
            TypeNarrowingKind::IsInstance => {
                // Remove the type from possibilities
                self.remove_type(&constraint.variable, &constraint.narrowed_to);
            }
            TypeNarrowingKind::IsNone => {
                // Not None
                self.remove_type(&constraint.variable, "None");
            }
            TypeNarrowingKind::IsNotNone => {
                // Is None
                self.narrow_to(&constraint.variable, "None");
            }
            _ => {
                // Other constraints don't have clear inverse
            }
        }
    }

    /// Merge two type states (meet operation for join points)
    ///
    /// Strategy: Union of possible types (conservative)
    pub fn merge(&mut self, other: &TypeState) {
        // Union of variables
        for (var, other_types) in &other.variables {
            self.variables
                .entry(var.clone())
                .or_insert_with(HashSet::new)
                .extend(other_types.iter().cloned());
        }

        // Keep only common constraints
        let common_constraints: Vec<TypeConstraint> = self
            .constraints
            .iter()
            .filter(|c| {
                other.constraints.iter().any(|oc| {
                    c.variable == oc.variable
                        && c.constraint_type == oc.constraint_type
                        && c.narrowed_to == oc.narrowed_to
                })
            })
            .cloned()
            .collect();

        self.constraints = common_constraints;
    }
}

impl Default for TypeState {
    fn default() -> Self {
        Self::new()
    }
}

/// Type narrowing information (simple)
#[derive(Debug, Clone)]
pub struct TypeNarrowingInfo {
    /// Variable name
    pub variable_name: String,

    /// Original type (before narrowing)
    pub original_type: String,

    /// Narrowed type (after narrowing)
    pub narrowed_type: String,

    /// Condition that caused narrowing
    pub condition: String,

    /// Source location
    pub location: String,
}

impl TypeNarrowingInfo {
    /// Create new type narrowing info
    pub fn new(
        variable_name: impl Into<String>,
        original_type: impl Into<String>,
        narrowed_type: impl Into<String>,
        condition: impl Into<String>,
        location: impl Into<String>,
    ) -> Self {
        Self {
            variable_name: variable_name.into(),
            original_type: original_type.into(),
            narrowed_type: narrowed_type.into(),
            condition: condition.into(),
            location: location.into(),
        }
    }
}

/// Type Narrowing Analyzer
///
/// Features:
/// - Flow-sensitive type tracking
/// - Branch-specific type states
/// - isinstance(), is None, truthiness
/// - Union type narrowing
///
/// Algorithm:
/// - Forward dataflow analysis
/// - Branch splitting for conditionals
/// - Meet operation at join points
///
/// Performance:
/// - O(CFG edges × variables) time
/// - O(CFG nodes × variables × types) space
pub struct TypeNarrowingAnalyzer {
    /// Type states at each location: location -> TypeState
    type_states: FxHashMap<String, TypeState>,

    /// Current scope
    current_scope: String,

    /// Simple narrowings (basic version)
    narrowings: FxHashMap<String, Vec<TypeNarrowingInfo>>,
}

impl TypeNarrowingAnalyzer {
    /// Create new type narrowing analyzer
    pub fn new() -> Self {
        Self {
            type_states: FxHashMap::default(),
            current_scope: "global".to_string(),
            narrowings: FxHashMap::default(),
        }
    }

    /// Analyze with initial type information
    ///
    /// # Arguments
    /// * `initial_types` - Initial type information {var: {types}}
    ///
    /// # Returns
    /// Type states at each program location
    pub fn analyze(
        &mut self,
        initial_types: Option<FxHashMap<String, HashSet<String>>>,
    ) -> &FxHashMap<String, TypeState> {
        self.type_states.clear();

        let initial_state = if let Some(types) = initial_types {
            TypeState::with_types(types)
        } else {
            TypeState::new()
        };

        // Store initial state
        self.type_states.insert("entry".to_string(), initial_state);

        &self.type_states
    }

    /// Record simple narrowing (basic version)
    pub fn record_narrowing(
        &mut self,
        var: impl Into<String>,
        original_type: impl Into<String>,
        narrowed_type: impl Into<String>,
        condition: impl Into<String>,
        location: impl Into<String>,
    ) {
        let var = var.into();
        let info = TypeNarrowingInfo::new(
            var.clone(),
            original_type,
            narrowed_type,
            condition,
            location,
        );

        self.narrowings
            .entry(var)
            .or_insert_with(Vec::new)
            .push(info);
    }

    /// Get narrowings for a variable
    pub fn get_narrowings(&self, var: &str) -> Vec<TypeNarrowingInfo> {
        self.narrowings.get(var).cloned().unwrap_or_default()
    }

    /// Check if variable has narrowing
    pub fn has_narrowing(&self, var: &str) -> bool {
        self.narrowings.get(var).map_or(false, |v| !v.is_empty())
    }

    /// Create type constraint from isinstance check
    pub fn isinstance_constraint(
        var: impl Into<String>,
        typ: impl Into<String>,
        location: (usize, usize),
    ) -> TypeConstraint {
        TypeConstraint::new(var, TypeNarrowingKind::IsInstance, typ, location)
    }

    /// Create type constraint from is None check
    pub fn is_none_constraint(var: impl Into<String>, location: (usize, usize)) -> TypeConstraint {
        TypeConstraint::new(var, TypeNarrowingKind::IsNone, "None", location)
    }

    /// Create type constraint from is not None check
    pub fn is_not_none_constraint(
        var: impl Into<String>,
        location: (usize, usize),
    ) -> TypeConstraint {
        TypeConstraint::new(var, TypeNarrowingKind::IsNotNone, "NotNone", location)
    }

    /// Create type constraint from truthiness check
    pub fn truthiness_constraint(
        var: impl Into<String>,
        location: (usize, usize),
    ) -> TypeConstraint {
        TypeConstraint::new(var, TypeNarrowingKind::Truthiness, "Truthy", location)
    }

    /// Split state for if/else branches
    ///
    /// # Arguments
    /// * `base_state` - State before conditional
    /// * `constraint` - Type constraint from condition
    ///
    /// # Returns
    /// (then_state, else_state)
    pub fn split_branches(
        &self,
        base_state: &TypeState,
        constraint: &TypeConstraint,
    ) -> (TypeState, TypeState) {
        // Then branch: apply constraint
        let mut then_state = base_state.clone();
        then_state.apply_constraint(constraint);

        // Else branch: apply inverse
        let mut else_state = base_state.clone();
        else_state.apply_inverse_constraint(constraint);

        (then_state, else_state)
    }

    /// Join states from multiple branches
    ///
    /// # Arguments
    /// * `states` - States from different branches
    ///
    /// # Returns
    /// Merged state (union of types)
    pub fn join_branches(&self, states: &[TypeState]) -> TypeState {
        if states.is_empty() {
            return TypeState::new();
        }

        let mut result = states[0].clone();
        for state in &states[1..] {
            result.merge(state);
        }

        result
    }

    /// Get type state at a location
    pub fn get_state(&self, location: &str) -> Option<&TypeState> {
        self.type_states.get(location)
    }

    /// Set type state at a location
    pub fn set_state(&mut self, location: impl Into<String>, state: TypeState) {
        self.type_states.insert(location.into(), state);
    }

    /// Get types for a variable at a location
    pub fn get_types_at(&self, var: &str, location: &str) -> Option<&HashSet<String>> {
        self.type_states
            .get(location)
            .and_then(|state| state.get_types(var))
    }

    /// Infer type from literal expression
    pub fn infer_literal_type(expr: &str) -> Option<String> {
        if expr.starts_with('"') || expr.starts_with('\'') {
            Some("str".to_string())
        } else if expr == "True" || expr == "False" {
            Some("bool".to_string())
        } else if expr == "None" {
            Some("None".to_string())
        } else if expr.chars().all(|c| c.is_ascii_digit()) {
            Some("int".to_string())
        } else if expr.contains('.') && expr.chars().all(|c| c.is_ascii_digit() || c == '.') {
            Some("float".to_string())
        } else if expr.starts_with('[') {
            Some("list".to_string())
        } else if expr.starts_with('{') {
            Some("dict".to_string())
        } else {
            None
        }
    }

    /// Get all constraints across all locations
    pub fn get_all_constraints(&self) -> Vec<TypeConstraint> {
        let mut constraints = Vec::new();
        for state in self.type_states.values() {
            constraints.extend(state.constraints.iter().cloned());
        }
        constraints
    }

    /// Clear all analysis state
    pub fn clear(&mut self) {
        self.type_states.clear();
        self.narrowings.clear();
    }
}

impl Default for TypeNarrowingAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_type_constraint_creation() {
        let constraint = TypeConstraint::new("x", TypeNarrowingKind::IsInstance, "str", (10, 5));

        assert_eq!(constraint.variable, "x");
        assert_eq!(constraint.narrowed_to, "str");
        assert_eq!(constraint.location, (10, 5));
    }

    #[test]
    fn test_type_state_narrowing() {
        let mut state = TypeState::new();

        // Initial: x can be str, int, or None
        state.set_types(
            "x",
            HashSet::from(["str".to_string(), "int".to_string(), "None".to_string()]),
        );

        // Narrow to str
        state.narrow_to("x", "str");

        let types = state.get_types("x").unwrap();
        assert_eq!(types.len(), 1);
        assert!(types.contains("str"));
    }

    #[test]
    fn test_isinstance_constraint() {
        let mut state = TypeState::new();
        state.set_types("x", HashSet::from(["str".to_string(), "int".to_string()]));

        let constraint = TypeConstraint::new("x", TypeNarrowingKind::IsInstance, "str", (10, 5));

        state.apply_constraint(&constraint);

        let types = state.get_types("x").unwrap();
        assert_eq!(types.len(), 1);
        assert!(types.contains("str"));
    }

    #[test]
    fn test_is_none_constraint() {
        let mut state = TypeState::new();
        state.set_types("x", HashSet::from(["str".to_string(), "None".to_string()]));

        let constraint = TypeConstraint::new("x", TypeNarrowingKind::IsNone, "None", (10, 5));

        state.apply_constraint(&constraint);

        let types = state.get_types("x").unwrap();
        assert_eq!(types.len(), 1);
        assert!(types.contains("None"));
    }

    #[test]
    fn test_is_not_none_constraint() {
        let mut state = TypeState::new();
        state.set_types("x", HashSet::from(["str".to_string(), "None".to_string()]));

        let constraint = TypeConstraint::new("x", TypeNarrowingKind::IsNotNone, "NotNone", (10, 5));

        state.apply_constraint(&constraint);

        let types = state.get_types("x").unwrap();
        assert!(!types.contains("None"));
    }

    #[test]
    fn test_branch_splitting() {
        let analyzer = TypeNarrowingAnalyzer::new();

        let mut base_state = TypeState::new();
        base_state.set_types("x", HashSet::from(["str".to_string(), "int".to_string()]));

        let constraint = TypeConstraint::new("x", TypeNarrowingKind::IsInstance, "str", (10, 5));

        let (then_state, else_state) = analyzer.split_branches(&base_state, &constraint);

        // Then: x is str
        let then_types = then_state.get_types("x").unwrap();
        assert_eq!(then_types.len(), 1);
        assert!(then_types.contains("str"));

        // Else: x is not str (should be int)
        let else_types = else_state.get_types("x").unwrap();
        assert!(!else_types.contains("str"));
    }

    #[test]
    fn test_branch_joining() {
        let analyzer = TypeNarrowingAnalyzer::new();

        let mut state1 = TypeState::new();
        state1.set_types("x", HashSet::from(["str".to_string()]));

        let mut state2 = TypeState::new();
        state2.set_types("x", HashSet::from(["int".to_string()]));

        let joined = analyzer.join_branches(&[state1, state2]);

        // Should have union: str | int
        let types = joined.get_types("x").unwrap();
        assert_eq!(types.len(), 2);
        assert!(types.contains("str"));
        assert!(types.contains("int"));
    }

    #[test]
    fn test_state_merging() {
        let mut state1 = TypeState::new();
        state1.set_types("x", HashSet::from(["str".to_string()]));
        state1.set_types("y", HashSet::from(["int".to_string()]));

        let mut state2 = TypeState::new();
        state2.set_types("x", HashSet::from(["int".to_string()]));
        state2.set_types("z", HashSet::from(["bool".to_string()]));

        state1.merge(&state2);

        // x should have both str and int
        let x_types = state1.get_types("x").unwrap();
        assert!(x_types.contains("str"));
        assert!(x_types.contains("int"));

        // y should still be int
        let y_types = state1.get_types("y").unwrap();
        assert!(y_types.contains("int"));

        // z should be added
        let z_types = state1.get_types("z").unwrap();
        assert!(z_types.contains("bool"));
    }

    #[test]
    fn test_literal_type_inference() {
        assert_eq!(
            TypeNarrowingAnalyzer::infer_literal_type("\"hello\""),
            Some("str".to_string())
        );
        assert_eq!(
            TypeNarrowingAnalyzer::infer_literal_type("42"),
            Some("int".to_string())
        );
        assert_eq!(
            TypeNarrowingAnalyzer::infer_literal_type("3.14"),
            Some("float".to_string())
        );
        assert_eq!(
            TypeNarrowingAnalyzer::infer_literal_type("True"),
            Some("bool".to_string())
        );
        assert_eq!(
            TypeNarrowingAnalyzer::infer_literal_type("None"),
            Some("None".to_string())
        );
        assert_eq!(
            TypeNarrowingAnalyzer::infer_literal_type("[1, 2, 3]"),
            Some("list".to_string())
        );
    }

    #[test]
    fn test_simple_narrowing_info() {
        let mut analyzer = TypeNarrowingAnalyzer::new();

        analyzer.record_narrowing(
            "x",
            "Union[str, int]",
            "str",
            "isinstance(x, str)",
            "line_10",
        );

        assert!(analyzer.has_narrowing("x"));

        let narrowings = analyzer.get_narrowings("x");
        assert_eq!(narrowings.len(), 1);
        assert_eq!(narrowings[0].variable_name, "x");
        assert_eq!(narrowings[0].narrowed_type, "str");
    }

    #[test]
    fn test_analyzer_workflow() {
        let mut analyzer = TypeNarrowingAnalyzer::new();

        // Initial types
        let mut initial = FxHashMap::default();
        initial.insert(
            "x".to_string(),
            HashSet::from(["str".to_string(), "int".to_string(), "None".to_string()]),
        );

        analyzer.analyze(Some(initial));

        // Get entry state
        let entry = analyzer.get_state("entry").unwrap();
        let x_types = entry.get_types("x").unwrap();
        assert_eq!(x_types.len(), 3);

        // Create narrowing constraint
        let constraint = TypeConstraint::new("x", TypeNarrowingKind::IsInstance, "str", (10, 5));

        // Split branches
        let (then_state, _) = analyzer.split_branches(entry, &constraint);

        // Store then state
        analyzer.set_state("line_11", then_state);

        // Check narrowed state
        let narrowed_types = analyzer.get_types_at("x", "line_11").unwrap();
        assert_eq!(narrowed_types.len(), 1);
        assert!(narrowed_types.contains("str"));
    }

    #[test]
    fn test_inverse_constraint() {
        let mut state = TypeState::new();
        state.set_types("x", HashSet::from(["str".to_string(), "int".to_string()]));

        let constraint = TypeConstraint::new("x", TypeNarrowingKind::IsInstance, "str", (10, 5));

        state.apply_inverse_constraint(&constraint);

        // Should remove str, leaving int
        let types = state.get_types("x").unwrap();
        assert!(!types.contains("str"));
    }

    #[test]
    fn test_truthiness_constraint() {
        let mut state = TypeState::new();
        state.set_types("x", HashSet::from(["str".to_string(), "None".to_string()]));

        let constraint = TypeConstraint::new("x", TypeNarrowingKind::Truthiness, "Truthy", (10, 5));

        state.apply_constraint(&constraint);

        // Should remove None and other falsy types
        let types = state.get_types("x").unwrap();
        assert!(!types.contains("None"));
    }
}
