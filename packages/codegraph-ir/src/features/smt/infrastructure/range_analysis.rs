//! Range Analysis
//!
//! Tracks value ranges for variables to detect array bounds violations and overflows.
//!
//! ## Overview
//!
//! Range analysis maintains interval constraints for variables:
//! - `x ∈ [min, max]` represents possible values for x
//! - Operations propagate ranges: `[1,5] + [2,3] = [3,8]`
//! - Comparisons narrow ranges: `x < 10` ⇒ `x ∈ [−∞, 9]`
//!
//! ## Example
//!
//! ```text
//! x = 5              ← x ∈ [5, 5]
//! y = x + 10         ← y ∈ [15, 15]
//! if (y < 20):       ← y ∈ [15, 15] ∩ [−∞, 19] = [15, 15] ✓
//!     z = y * 2      ← z ∈ [30, 30]
//!     arr[z]         ← Check: z ∈ [30, 30], arr.len = 10 ⇒ OUT OF BOUNDS! ✗
//! ```
//!
//! ## Performance
//!
//! Range analysis is much faster than Simplex:
//! - Range: O(1) per operation (interval arithmetic)
//! - Simplex: O(n²) per solve (pivot operations)
//! - Typical: 0.1ms (range) vs 1-5ms (simplex)

use super::LatticeValue;
use crate::features::smt::domain::path_condition::{ComparisonOp, ConstValue};
use std::collections::HashMap;

/// Integer range: [min, max]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IntRange {
    pub min: i64,
    pub max: i64,
}

impl IntRange {
    /// Create a range
    pub fn new(min: i64, max: i64) -> Self {
        Self { min, max }
    }

    /// Create a singleton range (constant)
    pub fn constant(value: i64) -> Self {
        Self::new(value, value)
    }

    /// Create unbounded range (−∞, +∞)
    pub fn unbounded() -> Self {
        Self::new(i64::MIN, i64::MAX)
    }

    /// Check if range is empty (impossible)
    pub fn is_empty(&self) -> bool {
        self.min > self.max
    }

    /// Check if range is a constant
    pub fn is_constant(&self) -> bool {
        self.min == self.max
    }

    /// Get constant value if range is singleton
    pub fn as_constant(&self) -> Option<i64> {
        if self.is_constant() {
            Some(self.min)
        } else {
            None
        }
    }

    /// Intersect two ranges
    pub fn intersect(&self, other: &IntRange) -> IntRange {
        IntRange::new(self.min.max(other.min), self.max.min(other.max))
    }

    /// Union two ranges (conservative: smallest range containing both)
    pub fn union(&self, other: &IntRange) -> IntRange {
        IntRange::new(self.min.min(other.min), self.max.max(other.max))
    }

    /// Add two ranges
    pub fn add(&self, other: &IntRange) -> IntRange {
        IntRange::new(
            self.min.saturating_add(other.min),
            self.max.saturating_add(other.max),
        )
    }

    /// Subtract two ranges
    pub fn sub(&self, other: &IntRange) -> IntRange {
        IntRange::new(
            self.min.saturating_sub(other.max),
            self.max.saturating_sub(other.min),
        )
    }

    /// Multiply two ranges
    pub fn mul(&self, other: &IntRange) -> IntRange {
        let products = [
            self.min.saturating_mul(other.min),
            self.min.saturating_mul(other.max),
            self.max.saturating_mul(other.min),
            self.max.saturating_mul(other.max),
        ];
        IntRange::new(
            *products.iter().min().unwrap(),
            *products.iter().max().unwrap(),
        )
    }

    /// Divide two ranges (conservative, assumes divisor ≠ 0)
    pub fn div(&self, other: &IntRange) -> IntRange {
        if other.min <= 0 && other.max >= 0 {
            // Divisor can be zero - return unbounded
            return IntRange::unbounded();
        }

        let quotients = [
            self.min.checked_div(other.min).unwrap_or(i64::MIN),
            self.min.checked_div(other.max).unwrap_or(i64::MIN),
            self.max.checked_div(other.min).unwrap_or(i64::MAX),
            self.max.checked_div(other.max).unwrap_or(i64::MAX),
        ];
        IntRange::new(
            *quotients.iter().min().unwrap(),
            *quotients.iter().max().unwrap(),
        )
    }

    /// Apply comparison operator to narrow range
    pub fn apply_comparison(&self, op: ComparisonOp, value: i64) -> IntRange {
        match op {
            ComparisonOp::Lt => self.intersect(&IntRange::new(i64::MIN, value - 1)),
            ComparisonOp::Le => self.intersect(&IntRange::new(i64::MIN, value)),
            ComparisonOp::Gt => self.intersect(&IntRange::new(value + 1, i64::MAX)),
            ComparisonOp::Ge => self.intersect(&IntRange::new(value, i64::MAX)),
            ComparisonOp::Eq => self.intersect(&IntRange::constant(value)),
            ComparisonOp::Neq => {
                // x ≠ value: if range is [value, value], it becomes empty
                if self.min == value && self.max == value {
                    IntRange::new(1, 0) // Empty range
                } else {
                    *self // Cannot narrow further
                }
            }
            ComparisonOp::Null | ComparisonOp::NotNull => {
                // Null checks don't apply to integer ranges
                *self
            }
        }
    }

    /// Check if range satisfies comparison
    pub fn satisfies(&self, op: ComparisonOp, value: i64) -> Option<bool> {
        match op {
            ComparisonOp::Lt => {
                if self.max < value {
                    Some(true) // Always true
                } else if self.min >= value {
                    Some(false) // Always false
                } else {
                    None // Unknown
                }
            }
            ComparisonOp::Le => {
                if self.max <= value {
                    Some(true)
                } else if self.min > value {
                    Some(false)
                } else {
                    None
                }
            }
            ComparisonOp::Gt => {
                if self.min > value {
                    Some(true)
                } else if self.max <= value {
                    Some(false)
                } else {
                    None
                }
            }
            ComparisonOp::Ge => {
                if self.min >= value {
                    Some(true)
                } else if self.max < value {
                    Some(false)
                } else {
                    None
                }
            }
            ComparisonOp::Eq => {
                if self.min == value && self.max == value {
                    Some(true)
                } else if self.max < value || self.min > value {
                    Some(false)
                } else {
                    None
                }
            }
            ComparisonOp::Neq => {
                if self.max < value || self.min > value {
                    Some(true)
                } else if self.min == value && self.max == value {
                    Some(false)
                } else {
                    None
                }
            }
            ComparisonOp::Null | ComparisonOp::NotNull => {
                // Null checks don't apply to integer ranges
                None
            }
        }
    }
}

/// Range analyzer
pub struct RangeAnalyzer {
    /// Variable ranges
    ranges: HashMap<String, IntRange>,
}

impl Default for RangeAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

impl RangeAnalyzer {
    /// Create new range analyzer
    pub fn new() -> Self {
        Self {
            ranges: HashMap::new(),
        }
    }

    /// Set range for variable
    pub fn set_range(&mut self, var: String, range: IntRange) {
        self.ranges.insert(var, range);
    }

    /// Get range for variable
    pub fn get_range(&self, var: &str) -> IntRange {
        self.ranges
            .get(var)
            .copied()
            .unwrap_or_else(IntRange::unbounded)
    }

    /// Set constant value for variable
    pub fn set_constant(&mut self, var: String, value: i64) {
        self.ranges.insert(var, IntRange::constant(value));
    }

    /// Apply comparison constraint to variable
    pub fn apply_constraint(&mut self, var: &str, op: ComparisonOp, value: i64) -> bool {
        let current = self.get_range(var);
        let new_range = current.apply_comparison(op, value);

        if new_range.is_empty() {
            false // Infeasible
        } else {
            self.ranges.insert(var.to_string(), new_range);
            true // Feasible
        }
    }

    /// Check if constraint is satisfied
    pub fn check_constraint(&self, var: &str, op: ComparisonOp, value: i64) -> Option<bool> {
        let range = self.get_range(var);
        range.satisfies(op, value)
    }

    /// Compute range for binary operation
    pub fn compute_binary_op(
        &mut self,
        result: &str,
        left: &str,
        op: BinaryOp,
        right: &str,
    ) -> IntRange {
        let left_range = self.get_range(left);
        let right_range = self.get_range(right);

        let result_range = match op {
            BinaryOp::Add => left_range.add(&right_range),
            BinaryOp::Sub => left_range.sub(&right_range),
            BinaryOp::Mul => left_range.mul(&right_range),
            BinaryOp::Div => left_range.div(&right_range),
        };

        self.ranges.insert(result.to_string(), result_range);
        result_range
    }

    /// Merge ranges at join point (phi node)
    pub fn merge_ranges(&mut self, var: &str, ranges: &[IntRange]) -> IntRange {
        if ranges.is_empty() {
            return IntRange::unbounded();
        }

        let mut result = ranges[0];
        for range in &ranges[1..] {
            result = result.union(range);
        }

        self.ranges.insert(var.to_string(), result);
        result
    }

    /// Load SCCP values
    pub fn load_sccp_values(&mut self, values: &HashMap<String, LatticeValue>) {
        for (var, lattice) in values {
            if let Some(const_val) = lattice.as_const() {
                if let ConstValue::Int(i) = const_val {
                    self.set_constant(var.clone(), *i);
                }
            }
        }
    }

    /// Check array bounds: arr[index] with arr.len
    pub fn check_array_bounds(&self, index_var: &str, array_len: i64) -> ArrayBoundsCheck {
        let index_range = self.get_range(index_var);

        if index_range.min < 0 {
            ArrayBoundsCheck::NegativeIndex
        } else if index_range.max >= array_len {
            ArrayBoundsCheck::OutOfBounds
        } else {
            ArrayBoundsCheck::Safe
        }
    }
}

/// Binary operators for range analysis
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinaryOp {
    Add,
    Sub,
    Mul,
    Div,
}

/// Array bounds check result
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ArrayBoundsCheck {
    /// Index is always safe
    Safe,
    /// Index can be negative
    NegativeIndex,
    /// Index can exceed array length
    OutOfBounds,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_range_operations() {
        let r1 = IntRange::new(1, 5);
        let r2 = IntRange::new(2, 3);

        // Add: [1,5] + [2,3] = [3,8]
        assert_eq!(r1.add(&r2), IntRange::new(3, 8));

        // Sub: [1,5] - [2,3] = [-2,3]
        assert_eq!(r1.sub(&r2), IntRange::new(-2, 3));

        // Mul: [1,5] * [2,3] = [2,15]
        assert_eq!(r1.mul(&r2), IntRange::new(2, 15));
    }

    #[test]
    fn test_range_intersect() {
        let r1 = IntRange::new(1, 10);
        let r2 = IntRange::new(5, 15);

        // Intersect: [1,10] ∩ [5,15] = [5,10]
        assert_eq!(r1.intersect(&r2), IntRange::new(5, 10));
    }

    #[test]
    fn test_range_union() {
        let r1 = IntRange::new(1, 5);
        let r2 = IntRange::new(10, 15);

        // Union: [1,5] ∪ [10,15] = [1,15]
        assert_eq!(r1.union(&r2), IntRange::new(1, 15));
    }

    #[test]
    fn test_apply_comparison() {
        let r = IntRange::new(1, 10);

        // x < 5: [1,10] ∩ [−∞,4] = [1,4]
        assert_eq!(r.apply_comparison(ComparisonOp::Lt, 5), IntRange::new(1, 4));

        // x > 7: [1,10] ∩ [8,+∞] = [8,10]
        assert_eq!(
            r.apply_comparison(ComparisonOp::Gt, 7),
            IntRange::new(8, 10)
        );

        // x == 5: [1,10] ∩ [5,5] = [5,5]
        assert_eq!(
            r.apply_comparison(ComparisonOp::Eq, 5),
            IntRange::constant(5)
        );
    }

    #[test]
    fn test_satisfies_comparison() {
        let r = IntRange::new(5, 10);

        // x > 3: always true (min=5 > 3)
        assert_eq!(r.satisfies(ComparisonOp::Gt, 3), Some(true));

        // x < 20: always true (max=10 < 20)
        assert_eq!(r.satisfies(ComparisonOp::Lt, 20), Some(true));

        // x < 7: unknown (range overlaps)
        assert_eq!(r.satisfies(ComparisonOp::Lt, 7), None);

        // x > 15: always false (max=10 < 15)
        assert_eq!(r.satisfies(ComparisonOp::Gt, 15), Some(false));
    }

    #[test]
    fn test_array_bounds_check() {
        let mut analyzer = RangeAnalyzer::new();

        // index ∈ [0, 5], arr.len = 10
        analyzer.set_range("i".to_string(), IntRange::new(0, 5));
        assert_eq!(analyzer.check_array_bounds("i", 10), ArrayBoundsCheck::Safe);

        // index ∈ [8, 12], arr.len = 10
        analyzer.set_range("j".to_string(), IntRange::new(8, 12));
        assert_eq!(
            analyzer.check_array_bounds("j", 10),
            ArrayBoundsCheck::OutOfBounds
        );

        // index ∈ [-2, 3], arr.len = 10
        analyzer.set_range("k".to_string(), IntRange::new(-2, 3));
        assert_eq!(
            analyzer.check_array_bounds("k", 10),
            ArrayBoundsCheck::NegativeIndex
        );
    }

    #[test]
    fn test_range_propagation() {
        let mut analyzer = RangeAnalyzer::new();

        // x = 5
        analyzer.set_constant("x".to_string(), 5);

        // y = x + 10
        analyzer.compute_binary_op("y", "x", BinaryOp::Add, "x");
        analyzer.set_constant("ten".to_string(), 10);
        analyzer.compute_binary_op("y", "x", BinaryOp::Add, "ten");

        // y should be [15, 15]
        assert_eq!(analyzer.get_range("y"), IntRange::constant(15));
    }

    #[test]
    fn test_constraint_application() {
        let mut analyzer = RangeAnalyzer::new();

        // x ∈ [1, 100]
        analyzer.set_range("x".to_string(), IntRange::new(1, 100));

        // Apply: x < 50
        assert!(analyzer.apply_constraint("x", ComparisonOp::Lt, 50));
        assert_eq!(analyzer.get_range("x"), IntRange::new(1, 49));

        // Apply: x > 60 (infeasible with current range [1,49])
        assert!(!analyzer.apply_constraint("x", ComparisonOp::Gt, 60));
    }

    #[test]
    fn test_phi_merge() {
        let mut analyzer = RangeAnalyzer::new();

        // Merge [1,5] and [10,15]
        let ranges = vec![IntRange::new(1, 5), IntRange::new(10, 15)];
        let merged = analyzer.merge_ranges("x", &ranges);

        // Result should be [1,15] (conservative union)
        assert_eq!(merged, IntRange::new(1, 15));
    }
}
