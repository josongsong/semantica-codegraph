//! Array Bounds Checker
//!
//! Verifies array access safety by tracking array sizes and index constraints.
//! Prevents buffer overflows and out-of-bounds access.
//!
//! # Examples
//!
//! ```text
//! use codegraph_ir::features::smt::infrastructure::ArrayBoundsChecker;
//!
//! let mut checker = ArrayBoundsChecker::new();
//!
//! // arr has size 10
//! checker.set_array_size("arr".to_string(), 10);
//!
//! // Check: arr[5] is safe
//! assert!(checker.is_access_safe("arr", 5));
//!
//! // Check: arr[15] is out of bounds
//! assert!(!checker.is_access_safe("arr", 15));
//! ```

use crate::features::smt::domain::{ComparisonOp, ConstValue, PathCondition, VarId};
use std::collections::HashMap;

/// Array size information
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ArraySize {
    /// Known constant size
    Constant(usize),
    /// Variable size (e.g., len(arr))
    Variable(VarId),
    /// Unknown size
    Unknown,
}

/// Index constraint for array access
#[derive(Debug, Clone)]
pub struct IndexConstraint {
    /// Index variable
    pub index: VarId,
    /// Lower bound (>= 0 for safety)
    pub lower_bound: Option<i64>,
    /// Upper bound (< array.len for safety)
    pub upper_bound: Option<i64>,
}

impl IndexConstraint {
    /// Create new index constraint with default bounds [0, +∞)
    pub fn new(index: VarId) -> Self {
        Self {
            index,
            lower_bound: Some(0), // Arrays are 0-indexed
            upper_bound: None,
        }
    }

    /// Check if index is guaranteed to be >= 0
    pub fn is_non_negative(&self) -> bool {
        self.lower_bound.map_or(false, |lb| lb >= 0)
    }

    /// Check if index is guaranteed to be < bound
    pub fn is_less_than(&self, bound: i64) -> bool {
        self.upper_bound.map_or(false, |ub| ub < bound)
    }

    /// Add constraint from PathCondition
    pub fn add_constraint(&mut self, cond: &PathCondition) -> bool {
        if cond.var != self.index {
            return true; // Not relevant to this index
        }

        let value = match &cond.value {
            Some(ConstValue::Int(i)) => *i,
            _ => return true, // Cannot process non-int constraints
        };

        match cond.op {
            ComparisonOp::Ge => {
                // index >= value
                self.lower_bound = Some(self.lower_bound.map_or(value, |lb| lb.max(value)));
            }
            ComparisonOp::Gt => {
                // index > value => index >= value + 1
                let new_lb = value + 1;
                self.lower_bound = Some(self.lower_bound.map_or(new_lb, |lb| lb.max(new_lb)));
            }
            ComparisonOp::Lt => {
                // index < value => index <= value - 1
                let new_ub = value - 1;
                self.upper_bound = Some(self.upper_bound.map_or(new_ub, |ub| ub.min(new_ub)));
            }
            ComparisonOp::Le => {
                // index <= value
                self.upper_bound = Some(self.upper_bound.map_or(value, |ub| ub.min(value)));
            }
            ComparisonOp::Eq => {
                // index == value
                self.lower_bound = Some(value);
                self.upper_bound = Some(value);
            }
            _ => {}
        }

        // Check for contradiction
        if let (Some(lb), Some(ub)) = (self.lower_bound, self.upper_bound) {
            if lb > ub {
                return false; // Contradiction
            }
        }

        true
    }
}

/// Array bounds checker
pub struct ArrayBoundsChecker {
    /// Array sizes
    array_sizes: HashMap<VarId, ArraySize>,
    /// Index constraints for array accesses
    index_constraints: HashMap<VarId, IndexConstraint>,
    /// Maximum tracked arrays
    max_arrays: usize,
    /// Contradiction flag
    contradiction: bool,
}

impl Default for ArrayBoundsChecker {
    fn default() -> Self {
        Self::new()
    }
}

impl ArrayBoundsChecker {
    /// Create new array bounds checker
    pub fn new() -> Self {
        Self {
            array_sizes: HashMap::new(),
            index_constraints: HashMap::new(),
            max_arrays: 50,
            contradiction: false,
        }
    }

    /// Set array size
    pub fn set_array_size(&mut self, array: VarId, size: usize) {
        if self.array_sizes.len() < self.max_arrays {
            self.array_sizes.insert(array, ArraySize::Constant(size));
        }
    }

    /// Set variable array size (e.g., len(arr))
    pub fn set_variable_size(&mut self, array: VarId, size_var: VarId) {
        if self.array_sizes.len() < self.max_arrays {
            self.array_sizes
                .insert(array, ArraySize::Variable(size_var));
        }
    }

    /// Add index constraint
    pub fn add_index_constraint(&mut self, index: VarId, cond: &PathCondition) -> bool {
        if self.contradiction {
            return false;
        }

        let constraint = self
            .index_constraints
            .entry(index)
            .or_insert_with_key(|k| IndexConstraint::new(k.clone()));

        if !constraint.add_constraint(cond) {
            self.contradiction = true;
            return false;
        }

        true
    }

    /// Check if array access is safe: arr[index]
    pub fn is_access_safe(&self, array: &VarId, index_value: i64) -> bool {
        // Get array size
        let size = match self.array_sizes.get(array) {
            Some(ArraySize::Constant(s)) => *s as i64,
            Some(ArraySize::Variable(_)) => return true, // Conservative: unknown
            Some(ArraySize::Unknown) => return true,     // Conservative
            None => return true,                         // Conservative: unknown array
        };

        // Check bounds: 0 <= index < size
        index_value >= 0 && index_value < size
    }

    /// Check if symbolic index access is safe: arr[idx] where idx is variable
    pub fn is_symbolic_access_safe(&self, array: &VarId, index: &VarId) -> bool {
        // Get array size
        let size = match self.array_sizes.get(array) {
            Some(ArraySize::Constant(s)) => *s as i64,
            Some(ArraySize::Variable(_)) => return true, // Conservative
            Some(ArraySize::Unknown) => return true,
            None => return true,
        };

        // Get index constraints
        let constraint = match self.index_constraints.get(index) {
            Some(c) => c,
            None => return true, // Conservative: no constraint info
        };

        // Verify: 0 <= idx < size
        constraint.is_non_negative() && constraint.is_less_than(size)
    }

    /// Get array size if known
    pub fn get_array_size(&self, array: &VarId) -> Option<&ArraySize> {
        self.array_sizes.get(array)
    }

    /// Get index constraint if exists
    pub fn get_index_constraint(&self, index: &VarId) -> Option<&IndexConstraint> {
        self.index_constraints.get(index)
    }

    /// Check if any contradiction detected
    pub fn has_contradiction(&self) -> bool {
        self.contradiction
    }

    /// Clear all constraints
    pub fn clear(&mut self) {
        self.array_sizes.clear();
        self.index_constraints.clear();
        self.contradiction = false;
    }

    /// Get number of tracked arrays
    pub fn array_count(&self) -> usize {
        self.array_sizes.len()
    }

    /// Get number of tracked indices
    pub fn index_count(&self) -> usize {
        self.index_constraints.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_index_constraint_creation() {
        let constraint = IndexConstraint::new("i".to_string());
        assert_eq!(constraint.index, "i");
        assert_eq!(constraint.lower_bound, Some(0));
        assert_eq!(constraint.upper_bound, None);
    }

    #[test]
    fn test_index_constraint_is_non_negative() {
        let constraint = IndexConstraint::new("i".to_string());
        assert!(constraint.is_non_negative()); // Default >= 0
    }

    #[test]
    fn test_index_constraint_add_ge() {
        let mut constraint = IndexConstraint::new("i".to_string());

        // i >= 5
        let cond = PathCondition::new("i".to_string(), ComparisonOp::Ge, Some(ConstValue::Int(5)));
        constraint.add_constraint(&cond);

        assert_eq!(constraint.lower_bound, Some(5));
    }

    #[test]
    fn test_index_constraint_add_lt() {
        let mut constraint = IndexConstraint::new("i".to_string());

        // i < 10
        let cond = PathCondition::lt("i".to_string(), ConstValue::Int(10));
        constraint.add_constraint(&cond);

        // i < 10 => i <= 9
        assert_eq!(constraint.upper_bound, Some(9));
    }

    #[test]
    fn test_index_constraint_range() {
        let mut constraint = IndexConstraint::new("i".to_string());

        // i >= 0
        constraint.add_constraint(&PathCondition::new(
            "i".to_string(),
            ComparisonOp::Ge,
            Some(ConstValue::Int(0)),
        ));

        // i < 10
        constraint.add_constraint(&PathCondition::lt("i".to_string(), ConstValue::Int(10)));

        assert_eq!(constraint.lower_bound, Some(0));
        assert_eq!(constraint.upper_bound, Some(9));
        assert!(constraint.is_less_than(10));
    }

    #[test]
    fn test_index_constraint_contradiction() {
        let mut constraint = IndexConstraint::new("i".to_string());

        // i < 5
        constraint.add_constraint(&PathCondition::lt("i".to_string(), ConstValue::Int(5)));

        // i > 10 (contradiction)
        let result =
            constraint.add_constraint(&PathCondition::gt("i".to_string(), ConstValue::Int(10)));

        assert!(!result);
    }

    #[test]
    fn test_checker_set_array_size() {
        let mut checker = ArrayBoundsChecker::new();

        checker.set_array_size("arr".to_string(), 10);

        match checker.get_array_size(&"arr".to_string()) {
            Some(ArraySize::Constant(size)) => assert_eq!(*size, 10),
            _ => panic!("Expected constant size"),
        }
    }

    #[test]
    fn test_checker_constant_access_safe() {
        let mut checker = ArrayBoundsChecker::new();

        checker.set_array_size("arr".to_string(), 10);

        // arr[5] is safe (0 <= 5 < 10)
        assert!(checker.is_access_safe(&"arr".to_string(), 5));

        // arr[0] is safe (edge case)
        assert!(checker.is_access_safe(&"arr".to_string(), 0));

        // arr[9] is safe (edge case)
        assert!(checker.is_access_safe(&"arr".to_string(), 9));
    }

    #[test]
    fn test_checker_constant_access_unsafe() {
        let mut checker = ArrayBoundsChecker::new();

        checker.set_array_size("arr".to_string(), 10);

        // arr[-1] is unsafe (negative index)
        assert!(!checker.is_access_safe(&"arr".to_string(), -1));

        // arr[10] is unsafe (>= size)
        assert!(!checker.is_access_safe(&"arr".to_string(), 10));

        // arr[15] is unsafe
        assert!(!checker.is_access_safe(&"arr".to_string(), 15));
    }

    #[test]
    fn test_checker_symbolic_access_safe() {
        let mut checker = ArrayBoundsChecker::new();

        checker.set_array_size("arr".to_string(), 10);

        // Add index constraints: 0 <= i < 10
        checker.add_index_constraint(
            "i".to_string(),
            &PathCondition::new("i".to_string(), ComparisonOp::Ge, Some(ConstValue::Int(0))),
        );
        checker.add_index_constraint(
            "i".to_string(),
            &PathCondition::lt("i".to_string(), ConstValue::Int(10)),
        );

        // arr[i] is safe
        assert!(checker.is_symbolic_access_safe(&"arr".to_string(), &"i".to_string()));
    }

    #[test]
    fn test_checker_symbolic_access_unsafe_no_lower_bound() {
        let mut checker = ArrayBoundsChecker::new();

        checker.set_array_size("arr".to_string(), 10);

        // Only upper bound: i < 10 (no guarantee i >= 0)
        checker.add_index_constraint(
            "i".to_string(),
            &PathCondition::lt("i".to_string(), ConstValue::Int(10)),
        );

        // Remove default lower bound to test
        if let Some(constraint) = checker.index_constraints.get_mut(&"i".to_string()) {
            constraint.lower_bound = None;
        }

        // arr[i] is unsafe (i might be negative)
        assert!(!checker.is_symbolic_access_safe(&"arr".to_string(), &"i".to_string()));
    }

    #[test]
    fn test_checker_symbolic_access_unsafe_out_of_bounds() {
        let mut checker = ArrayBoundsChecker::new();

        checker.set_array_size("arr".to_string(), 10);

        // Index range: 5 <= i < 20 (exceeds array size)
        checker.add_index_constraint(
            "i".to_string(),
            &PathCondition::new("i".to_string(), ComparisonOp::Ge, Some(ConstValue::Int(5))),
        );
        checker.add_index_constraint(
            "i".to_string(),
            &PathCondition::lt("i".to_string(), ConstValue::Int(20)),
        );

        // arr[i] is unsafe (i can be >= 10)
        assert!(!checker.is_symbolic_access_safe(&"arr".to_string(), &"i".to_string()));
    }

    #[test]
    fn test_checker_unknown_array_conservative() {
        let checker = ArrayBoundsChecker::new();

        // Unknown array: conservative (assume safe)
        assert!(checker.is_access_safe(&"unknown".to_string(), 100));
    }

    #[test]
    fn test_checker_variable_size() {
        let mut checker = ArrayBoundsChecker::new();

        // arr size is len(arr)
        checker.set_variable_size("arr".to_string(), "len_arr".to_string());

        // Conservative: cannot verify without knowing len_arr value
        assert!(checker.is_symbolic_access_safe(&"arr".to_string(), &"i".to_string()));
    }

    #[test]
    fn test_checker_multiple_arrays() {
        let mut checker = ArrayBoundsChecker::new();

        checker.set_array_size("arr1".to_string(), 5);
        checker.set_array_size("arr2".to_string(), 10);

        assert!(checker.is_access_safe(&"arr1".to_string(), 4));
        assert!(!checker.is_access_safe(&"arr1".to_string(), 5));

        assert!(checker.is_access_safe(&"arr2".to_string(), 9));
        assert!(!checker.is_access_safe(&"arr2".to_string(), 10));

        assert_eq!(checker.array_count(), 2);
    }

    #[test]
    fn test_checker_clear() {
        let mut checker = ArrayBoundsChecker::new();

        checker.set_array_size("arr".to_string(), 10);
        checker.add_index_constraint(
            "i".to_string(),
            &PathCondition::lt("i".to_string(), ConstValue::Int(10)),
        );

        assert_eq!(checker.array_count(), 1);
        assert_eq!(checker.index_count(), 1);

        checker.clear();
        assert_eq!(checker.array_count(), 0);
        assert_eq!(checker.index_count(), 0);
    }

    #[test]
    fn test_edge_case_zero_size_array() {
        let mut checker = ArrayBoundsChecker::new();

        checker.set_array_size("empty".to_string(), 0);

        // Any access to empty array is unsafe
        assert!(!checker.is_access_safe(&"empty".to_string(), 0));
        assert!(!checker.is_access_safe(&"empty".to_string(), -1));
    }

    #[test]
    fn test_edge_case_exact_index_value() {
        let mut checker = ArrayBoundsChecker::new();

        checker.set_array_size("arr".to_string(), 10);

        // i == 5
        checker.add_index_constraint(
            "i".to_string(),
            &PathCondition::eq("i".to_string(), ConstValue::Int(5)),
        );

        // arr[i] where i == 5 is safe
        assert!(checker.is_symbolic_access_safe(&"arr".to_string(), &"i".to_string()));
    }
}
