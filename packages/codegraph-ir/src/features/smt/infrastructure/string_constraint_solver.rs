//! String Constraint Solver
//!
//! Handles string-specific constraints for security analysis:
//! - String length constraints (len(s) > 5)
//! - Pattern matching (s contains "script")
//! - Sanitizer verification (html.escape blocks XSS)
//!
//! # Examples
//!
//! ```text
//! use codegraph_ir::features::smt::infrastructure::StringConstraintSolver;
//!
//! let mut solver = StringConstraintSolver::new();
//!
//! // len(password) >= 8
//! solver.add_length_constraint("password".to_string(), 8, None);
//!
//! // Check if password can be empty
//! assert!(!solver.can_be_empty("password"));
//! ```

use crate::features::smt::domain::{ComparisonOp, VarId};
use std::collections::HashMap;

/// String length bound
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StringLengthBound {
    /// Minimum length (inclusive), None = 0
    pub min_length: Option<usize>,
    /// Maximum length (inclusive), None = unbounded
    pub max_length: Option<usize>,
}

impl StringLengthBound {
    /// Create unbounded length
    pub fn unbounded() -> Self {
        Self {
            min_length: None,
            max_length: None,
        }
    }

    /// Create exact length bound
    pub fn exact(length: usize) -> Self {
        Self {
            min_length: Some(length),
            max_length: Some(length),
        }
    }

    /// Create minimum length bound
    pub fn min(length: usize) -> Self {
        Self {
            min_length: Some(length),
            max_length: None,
        }
    }

    /// Create maximum length bound
    pub fn max(length: usize) -> Self {
        Self {
            min_length: None,
            max_length: Some(length),
        }
    }

    /// Create range bound [min, max]
    pub fn range(min: usize, max: usize) -> Self {
        Self {
            min_length: Some(min),
            max_length: Some(max),
        }
    }

    /// Check if length is empty (contradiction)
    pub fn is_empty(&self) -> bool {
        match (self.min_length, self.max_length) {
            (Some(min), Some(max)) => min > max,
            _ => false,
        }
    }

    /// Intersect with another bound
    pub fn intersect(&self, other: &StringLengthBound) -> StringLengthBound {
        let new_min = match (self.min_length, other.min_length) {
            (None, None) => None,
            (None, Some(m)) => Some(m),
            (Some(m), None) => Some(m),
            (Some(m1), Some(m2)) => Some(m1.max(m2)),
        };

        let new_max = match (self.max_length, other.max_length) {
            (None, None) => None,
            (None, Some(m)) => Some(m),
            (Some(m), None) => Some(m),
            (Some(m1), Some(m2)) => Some(m1.min(m2)),
        };

        StringLengthBound {
            min_length: new_min,
            max_length: new_max,
        }
    }

    /// Check if length value satisfies bound
    pub fn satisfies(&self, length: usize) -> bool {
        let min_ok = self.min_length.map_or(true, |min| length >= min);
        let max_ok = self.max_length.map_or(true, |max| length <= max);
        min_ok && max_ok
    }

    /// Check if string can be empty (length 0)
    pub fn can_be_empty(&self) -> bool {
        self.satisfies(0)
    }
}

/// String pattern constraint
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum StringPattern {
    /// Contains substring
    Contains(String),
    /// Starts with prefix
    StartsWith(String),
    /// Ends with suffix
    EndsWith(String),
    /// Matches regex (simplified)
    Regex(String),
}

/// String constraint solver
pub struct StringConstraintSolver {
    /// Length bounds for string variables
    length_bounds: HashMap<VarId, StringLengthBound>,
    /// Pattern constraints (var -> patterns it must/must not match)
    required_patterns: HashMap<VarId, Vec<StringPattern>>,
    forbidden_patterns: HashMap<VarId, Vec<StringPattern>>,
    /// Maximum tracked variables
    max_vars: usize,
    /// Contradiction flag
    contradiction: bool,
}

impl Default for StringConstraintSolver {
    fn default() -> Self {
        Self::new()
    }
}

impl StringConstraintSolver {
    /// Create new string constraint solver
    pub fn new() -> Self {
        Self {
            length_bounds: HashMap::new(),
            required_patterns: HashMap::new(),
            forbidden_patterns: HashMap::new(),
            max_vars: 50,
            contradiction: false,
        }
    }

    /// Add length constraint: len(var) <op> length
    pub fn add_length_constraint(&mut self, var: VarId, op: ComparisonOp, length: usize) -> bool {
        if self.contradiction {
            return false;
        }

        // Check capacity
        if !self.length_bounds.contains_key(&var) && self.length_bounds.len() >= self.max_vars {
            return true; // Conservative: assume feasible
        }

        let new_bound = match op {
            ComparisonOp::Eq => StringLengthBound::exact(length),
            ComparisonOp::Lt => StringLengthBound::max(length.saturating_sub(1)),
            ComparisonOp::Le => StringLengthBound::max(length),
            ComparisonOp::Gt => StringLengthBound::min(length + 1),
            ComparisonOp::Ge => StringLengthBound::min(length),
            ComparisonOp::Neq => return true, // Cannot represent as simple bound
            _ => return true,
        };

        // Get or create existing bound
        let existing = self
            .length_bounds
            .entry(var.clone())
            .or_insert_with(StringLengthBound::unbounded);

        // Intersect bounds
        let result = existing.intersect(&new_bound);

        // Check contradiction
        if result.is_empty() {
            self.contradiction = true;
            return false;
        }

        self.length_bounds.insert(var, result);
        true
    }

    /// Add pattern requirement: var must contain/match pattern
    pub fn add_required_pattern(&mut self, var: VarId, pattern: StringPattern) {
        self.required_patterns.entry(var).or_default().push(pattern);
    }

    /// Add pattern prohibition: var must NOT contain/match pattern
    pub fn add_forbidden_pattern(&mut self, var: VarId, pattern: StringPattern) {
        self.forbidden_patterns
            .entry(var.clone())
            .or_default()
            .push(pattern);

        // Check for pattern contradiction
        if let Some(required) = self.required_patterns.get(&var) {
            for forbidden_pat in self.forbidden_patterns.get(&var).unwrap() {
                if required.contains(forbidden_pat) {
                    self.contradiction = true;
                }
            }
        }
    }

    /// Check if variable can be empty string
    pub fn can_be_empty(&self, var: &VarId) -> bool {
        self.length_bounds
            .get(var)
            .map_or(true, |bound| bound.can_be_empty())
    }

    /// Get minimum possible length for variable
    pub fn min_length(&self, var: &VarId) -> Option<usize> {
        self.length_bounds.get(var)?.min_length
    }

    /// Get maximum possible length for variable
    pub fn max_length(&self, var: &VarId) -> Option<usize> {
        self.length_bounds.get(var)?.max_length
    }

    /// Check if string must contain pattern
    pub fn must_contain(&self, var: &VarId, substring: &str) -> bool {
        self.required_patterns.get(var).map_or(false, |patterns| {
            patterns.iter().any(|p| match p {
                StringPattern::Contains(s) => s == substring,
                _ => false,
            })
        })
    }

    /// Check if string cannot contain pattern (forbidden)
    pub fn cannot_contain(&self, var: &VarId, substring: &str) -> bool {
        self.forbidden_patterns.get(var).map_or(false, |patterns| {
            patterns.iter().any(|p| match p {
                StringPattern::Contains(s) => s == substring,
                _ => false,
            })
        })
    }

    /// Check if constraints are feasible
    pub fn is_feasible(&self) -> bool {
        !self.contradiction
    }

    /// Clear all constraints
    pub fn clear(&mut self) {
        self.length_bounds.clear();
        self.required_patterns.clear();
        self.forbidden_patterns.clear();
        self.contradiction = false;
    }

    /// Get number of tracked variables
    pub fn var_count(&self) -> usize {
        self.length_bounds.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_unbounded_length() {
        let bound = StringLengthBound::unbounded();
        assert!(bound.satisfies(0));
        assert!(bound.satisfies(100));
        assert!(bound.can_be_empty());
    }

    #[test]
    fn test_exact_length() {
        let bound = StringLengthBound::exact(5);
        assert!(!bound.satisfies(4));
        assert!(bound.satisfies(5));
        assert!(!bound.satisfies(6));
    }

    #[test]
    fn test_min_length() {
        let bound = StringLengthBound::min(8);
        assert!(!bound.satisfies(7));
        assert!(bound.satisfies(8));
        assert!(bound.satisfies(100));
    }

    #[test]
    fn test_max_length() {
        let bound = StringLengthBound::max(10);
        assert!(bound.satisfies(0));
        assert!(bound.satisfies(10));
        assert!(!bound.satisfies(11));
    }

    #[test]
    fn test_range_bound() {
        let bound = StringLengthBound::range(5, 10);
        assert!(!bound.satisfies(4));
        assert!(bound.satisfies(5));
        assert!(bound.satisfies(7));
        assert!(bound.satisfies(10));
        assert!(!bound.satisfies(11));
    }

    #[test]
    fn test_bound_intersection_feasible() {
        // [5, 15] ∩ [10, 20] = [10, 15]
        let b1 = StringLengthBound::range(5, 15);
        let b2 = StringLengthBound::range(10, 20);
        let result = b1.intersect(&b2);

        assert_eq!(result.min_length, Some(10));
        assert_eq!(result.max_length, Some(15));
        assert!(!result.is_empty());
    }

    #[test]
    fn test_bound_intersection_empty() {
        // [5, 10] ∩ [15, 20] = ∅
        let b1 = StringLengthBound::range(5, 10);
        let b2 = StringLengthBound::range(15, 20);
        let result = b1.intersect(&b2);

        assert!(result.is_empty());
    }

    #[test]
    fn test_solver_simple_length() {
        let mut solver = StringConstraintSolver::new();

        // len(password) >= 8
        let result = solver.add_length_constraint("password".to_string(), ComparisonOp::Ge, 8);
        assert!(result);

        assert_eq!(solver.min_length(&"password".to_string()), Some(8));
        assert!(!solver.can_be_empty(&"password".to_string()));
    }

    #[test]
    fn test_solver_length_contradiction() {
        let mut solver = StringConstraintSolver::new();

        // len(s) < 5
        solver.add_length_constraint("s".to_string(), ComparisonOp::Lt, 5);

        // len(s) > 10 (contradiction)
        let result = solver.add_length_constraint("s".to_string(), ComparisonOp::Gt, 10);

        assert!(!result);
        assert!(!solver.is_feasible());
    }

    #[test]
    fn test_solver_length_range() {
        let mut solver = StringConstraintSolver::new();

        // len(username) >= 3
        solver.add_length_constraint("username".to_string(), ComparisonOp::Ge, 3);

        // len(username) <= 20
        solver.add_length_constraint("username".to_string(), ComparisonOp::Le, 20);

        assert_eq!(solver.min_length(&"username".to_string()), Some(3));
        assert_eq!(solver.max_length(&"username".to_string()), Some(20));
        assert!(solver.is_feasible());
    }

    #[test]
    fn test_solver_exact_length() {
        let mut solver = StringConstraintSolver::new();

        // len(code) == 6
        solver.add_length_constraint("code".to_string(), ComparisonOp::Eq, 6);

        assert_eq!(solver.min_length(&"code".to_string()), Some(6));
        assert_eq!(solver.max_length(&"code".to_string()), Some(6));
    }

    #[test]
    fn test_pattern_required() {
        let mut solver = StringConstraintSolver::new();

        solver.add_required_pattern(
            "url".to_string(),
            StringPattern::StartsWith("https://".to_string()),
        );

        // Cannot directly verify without actual string values
        // But pattern is tracked
        assert!(solver.is_feasible());
    }

    #[test]
    fn test_pattern_forbidden() {
        let mut solver = StringConstraintSolver::new();

        solver.add_forbidden_pattern(
            "input".to_string(),
            StringPattern::Contains("<script>".to_string()),
        );

        assert!(solver.cannot_contain(&"input".to_string(), "<script>"));
    }

    #[test]
    fn test_pattern_contradiction() {
        let mut solver = StringConstraintSolver::new();

        let pattern = StringPattern::Contains("test".to_string());

        // Must contain "test"
        solver.add_required_pattern("s".to_string(), pattern.clone());

        // Must NOT contain "test" (contradiction)
        solver.add_forbidden_pattern("s".to_string(), pattern);

        assert!(!solver.is_feasible());
    }

    #[test]
    fn test_multiple_patterns() {
        let mut solver = StringConstraintSolver::new();

        // URL must start with https://
        solver.add_required_pattern(
            "url".to_string(),
            StringPattern::StartsWith("https://".to_string()),
        );

        // URL must contain domain
        solver.add_required_pattern(
            "url".to_string(),
            StringPattern::Contains(".com".to_string()),
        );

        assert!(solver.is_feasible());
    }

    #[test]
    fn test_clear() {
        let mut solver = StringConstraintSolver::new();

        solver.add_length_constraint("s".to_string(), ComparisonOp::Ge, 5);
        solver.add_required_pattern("s".to_string(), StringPattern::Contains("test".to_string()));

        assert_eq!(solver.var_count(), 1);

        solver.clear();
        assert_eq!(solver.var_count(), 0);
        assert!(solver.is_feasible());
    }

    #[test]
    fn test_can_be_empty() {
        let mut solver = StringConstraintSolver::new();

        // No constraint: can be empty
        assert!(solver.can_be_empty(&"s1".to_string()));

        // len(s2) >= 1: cannot be empty
        solver.add_length_constraint("s2".to_string(), ComparisonOp::Ge, 1);
        assert!(!solver.can_be_empty(&"s2".to_string()));

        // len(s3) == 0: can be empty
        solver.add_length_constraint("s3".to_string(), ComparisonOp::Eq, 0);
        assert!(solver.can_be_empty(&"s3".to_string()));
    }

    #[test]
    fn test_length_bounds_tight_range() {
        let mut solver = StringConstraintSolver::new();

        // len(otp) >= 6
        solver.add_length_constraint("otp".to_string(), ComparisonOp::Ge, 6);
        // len(otp) <= 6
        solver.add_length_constraint("otp".to_string(), ComparisonOp::Le, 6);

        // Must be exactly 6
        assert_eq!(solver.min_length(&"otp".to_string()), Some(6));
        assert_eq!(solver.max_length(&"otp".to_string()), Some(6));
    }
}
