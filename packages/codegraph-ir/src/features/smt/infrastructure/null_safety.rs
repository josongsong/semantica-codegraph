//! Null Safety Checker
//!
//! Tracks nullable/non-null states to detect null pointer dereferences.
//!
//! ## Overview
//!
//! This checker maintains nullability information for variables:
//! - `Null`: Variable is definitely null
//! - `NotNull`: Variable is definitely not null
//! - `MaybeNull`: Variable might be null (unknown)
//!
//! ## Example
//!
//! ```text
//! x = get_user()       ← x is MaybeNull (function might return null)
//! if (x == null):      ← Check: x is Null on true branch
//!     return           ← Safe: no dereference
//! // After check: x is NotNull (null was ruled out)
//! name = x.name        ← Safe: x is NotNull
//! ```
//!
//! ## Integration with Path Conditions
//!
//! Uses ComparisonOp::Null and ComparisonOp::NotNull from path conditions.

use super::LatticeValue;
use crate::features::smt::domain::path_condition::{ComparisonOp, PathCondition};
use std::collections::HashMap;

/// Nullability state for a variable
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Nullability {
    /// Definitely null
    Null,
    /// Definitely not null
    NotNull,
    /// Might be null (unknown)
    MaybeNull,
}

impl Nullability {
    /// Meet operation for lattice (join at merge points)
    pub fn meet(&self, other: &Nullability) -> Nullability {
        match (self, other) {
            (Nullability::Null, Nullability::Null) => Nullability::Null,
            (Nullability::NotNull, Nullability::NotNull) => Nullability::NotNull,
            _ => Nullability::MaybeNull, // Different states → unknown
        }
    }

    /// Check if definitely null
    pub fn is_null(&self) -> bool {
        matches!(self, Nullability::Null)
    }

    /// Check if definitely not null
    pub fn is_not_null(&self) -> bool {
        matches!(self, Nullability::NotNull)
    }

    /// Check if might be null
    pub fn is_maybe_null(&self) -> bool {
        matches!(self, Nullability::MaybeNull)
    }
}

/// Null safety checker
pub struct NullSafetyChecker {
    /// Nullability state for each variable
    states: HashMap<String, Nullability>,
}

impl Default for NullSafetyChecker {
    fn default() -> Self {
        Self::new()
    }
}

impl NullSafetyChecker {
    /// Create new null safety checker
    pub fn new() -> Self {
        Self {
            states: HashMap::new(),
        }
    }

    /// Set nullability state for variable
    pub fn set_state(&mut self, var: String, state: Nullability) {
        self.states.insert(var, state);
    }

    /// Get nullability state for variable
    pub fn get_state(&self, var: &str) -> Nullability {
        self.states
            .get(var)
            .copied()
            .unwrap_or(Nullability::MaybeNull)
    }

    /// Mark variable as definitely null
    pub fn mark_null(&mut self, var: String) {
        self.set_state(var, Nullability::Null);
    }

    /// Mark variable as definitely not null
    pub fn mark_not_null(&mut self, var: String) {
        self.set_state(var, Nullability::NotNull);
    }

    /// Mark variable as maybe null
    pub fn mark_maybe_null(&mut self, var: String) {
        self.set_state(var, Nullability::MaybeNull);
    }

    /// Apply path condition to update nullability
    pub fn apply_condition(&mut self, condition: &PathCondition) {
        let var = &condition.var;

        match condition.op {
            ComparisonOp::Null => {
                // x == null on true branch
                self.mark_null(var.clone());
            }
            ComparisonOp::NotNull => {
                // x != null on true branch
                self.mark_not_null(var.clone());
            }
            _ => {
                // Other comparisons don't affect nullability
            }
        }
    }

    /// Apply negated path condition (for else branch)
    pub fn apply_negated_condition(&mut self, condition: &PathCondition) {
        let var = &condition.var;

        match condition.op {
            ComparisonOp::Null => {
                // NOT (x == null) → x != null
                self.mark_not_null(var.clone());
            }
            ComparisonOp::NotNull => {
                // NOT (x != null) → x == null
                self.mark_null(var.clone());
            }
            _ => {
                // Other comparisons don't affect nullability
            }
        }
    }

    /// Check if dereferencing variable is safe
    pub fn check_dereference(&self, var: &str) -> DereferenceCheck {
        match self.get_state(var) {
            Nullability::Null => DereferenceCheck::DefinitelyUnsafe,
            Nullability::NotNull => DereferenceCheck::Safe,
            Nullability::MaybeNull => DereferenceCheck::PossiblyUnsafe,
        }
    }

    /// Merge states at join point (e.g., after if-else)
    pub fn merge(&mut self, other: &NullSafetyChecker) {
        // Merge states for all variables
        for (var, other_state) in &other.states {
            let current_state = self.get_state(var);
            let merged_state = current_state.meet(other_state);
            self.set_state(var.clone(), merged_state);
        }

        // Add variables only in other
        for (var, state) in &other.states {
            if !self.states.contains_key(var) {
                self.set_state(var.clone(), *state);
            }
        }
    }

    /// Load SCCP values (null constants)
    pub fn load_sccp_values(&mut self, values: &HashMap<String, LatticeValue>) {
        for (var, lattice) in values {
            // ConstValue::Null exists - see path_condition.rs
            // SCCP integration deferred: requires LatticeValue → ConstValue mapping
            let _ = (var, lattice); // Suppress unused warning
        }
    }

    /// Clone checker (for branching analysis)
    pub fn clone_state(&self) -> NullSafetyChecker {
        NullSafetyChecker {
            states: self.states.clone(),
        }
    }
}

/// Dereference safety check result
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DereferenceCheck {
    /// Safe: variable is definitely not null
    Safe,
    /// Possibly unsafe: variable might be null
    PossiblyUnsafe,
    /// Definitely unsafe: variable is definitely null
    DefinitelyUnsafe,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_nullability() {
        let mut checker = NullSafetyChecker::new();

        // Initially unknown
        assert_eq!(checker.get_state("x"), Nullability::MaybeNull);

        // Mark as null
        checker.mark_null("x".to_string());
        assert_eq!(checker.get_state("x"), Nullability::Null);

        // Mark as not null
        checker.mark_not_null("x".to_string());
        assert_eq!(checker.get_state("x"), Nullability::NotNull);
    }

    #[test]
    fn test_apply_null_condition() {
        let mut checker = NullSafetyChecker::new();

        // Apply: x == null
        let condition = PathCondition::null("x".to_string());
        checker.apply_condition(&condition);

        assert_eq!(checker.get_state("x"), Nullability::Null);
    }

    #[test]
    fn test_apply_not_null_condition() {
        let mut checker = NullSafetyChecker::new();

        // Apply: x != null
        let condition = PathCondition::not_null("x".to_string());
        checker.apply_condition(&condition);

        assert_eq!(checker.get_state("x"), Nullability::NotNull);
    }

    #[test]
    fn test_negated_condition() {
        let mut checker = NullSafetyChecker::new();

        // Apply negated: NOT (x == null) → x != null
        let condition = PathCondition::null("x".to_string());
        checker.apply_negated_condition(&condition);

        assert_eq!(checker.get_state("x"), Nullability::NotNull);
    }

    #[test]
    fn test_dereference_check() {
        let mut checker = NullSafetyChecker::new();

        // Unknown state
        assert_eq!(
            checker.check_dereference("x"),
            DereferenceCheck::PossiblyUnsafe
        );

        // Null state
        checker.mark_null("x".to_string());
        assert_eq!(
            checker.check_dereference("x"),
            DereferenceCheck::DefinitelyUnsafe
        );

        // Not null state
        checker.mark_not_null("x".to_string());
        assert_eq!(checker.check_dereference("x"), DereferenceCheck::Safe);
    }

    #[test]
    fn test_merge_states() {
        let mut checker1 = NullSafetyChecker::new();
        checker1.mark_null("x".to_string());

        let mut checker2 = NullSafetyChecker::new();
        checker2.mark_not_null("x".to_string());

        // Merge: Null ∪ NotNull → MaybeNull
        checker1.merge(&checker2);
        assert_eq!(checker1.get_state("x"), Nullability::MaybeNull);
    }

    #[test]
    fn test_merge_same_states() {
        let mut checker1 = NullSafetyChecker::new();
        checker1.mark_not_null("x".to_string());

        let mut checker2 = NullSafetyChecker::new();
        checker2.mark_not_null("x".to_string());

        // Merge: NotNull ∪ NotNull → NotNull
        checker1.merge(&checker2);
        assert_eq!(checker1.get_state("x"), Nullability::NotNull);
    }
}
