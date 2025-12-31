//! Interval Tracker - Range-based constraint tracking
//!
//! Tracks variable value ranges to detect contradictions and improve precision.
//!
//! # Examples
//!
//! ```rust
//! use codegraph_ir::features::smt::infrastructure::IntervalTracker;
//! use codegraph_ir::features::smt::domain::{PathCondition, ConstValue};
//!
//! let mut tracker = IntervalTracker::new();
//!
//! // Add: x > 5
//! tracker.add_constraint(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));
//! // Add: x < 10
//! tracker.add_constraint(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));
//!
//! // Query: 5 < x < 10
//! assert!(tracker.is_feasible());
//! ```

use crate::features::smt::domain::{ComparisonOp, ConstValue, PathCondition, VarId};
use std::collections::HashMap;

/// Integer interval [lower, upper]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IntInterval {
    /// Lower bound (inclusive), None = -∞
    pub lower: Option<i64>,
    /// Upper bound (inclusive), None = +∞
    pub upper: Option<i64>,
    /// Is interval open on lower bound?
    pub lower_open: bool,
    /// Is interval open on upper bound?
    pub upper_open: bool,
}

impl IntInterval {
    /// Create unbounded interval (-∞, +∞)
    pub fn unbounded() -> Self {
        Self {
            lower: None,
            upper: None,
            lower_open: true,
            upper_open: true,
        }
    }

    /// Create bounded interval [lower, upper]
    pub fn bounded(lower: i64, upper: i64) -> Self {
        Self {
            lower: Some(lower),
            upper: Some(upper),
            lower_open: false,
            upper_open: false,
        }
    }

    /// Create lower-bounded interval [lower, +∞)
    pub fn lower_bounded(lower: i64, open: bool) -> Self {
        Self {
            lower: Some(lower),
            upper: None,
            lower_open: open,
            upper_open: true,
        }
    }

    /// Create upper-bounded interval (-∞, upper]
    pub fn upper_bounded(upper: i64, open: bool) -> Self {
        Self {
            lower: None,
            upper: Some(upper),
            lower_open: true,
            upper_open: open,
        }
    }

    /// Check if interval is empty (contradiction)
    pub fn is_empty(&self) -> bool {
        match (self.lower, self.upper) {
            (Some(l), Some(u)) => {
                if self.lower_open && self.upper_open {
                    l >= u
                } else if self.lower_open || self.upper_open {
                    l >= u
                } else {
                    l > u
                }
            }
            _ => false,
        }
    }

    /// Intersect with another interval
    pub fn intersect(&self, other: &IntInterval) -> IntInterval {
        let (new_lower, new_lower_open) = match (self.lower, other.lower) {
            (None, None) => (None, true),
            (None, Some(l)) => (Some(l), other.lower_open),
            (Some(l), None) => (Some(l), self.lower_open),
            (Some(l1), Some(l2)) => {
                if l1 > l2 {
                    (Some(l1), self.lower_open)
                } else if l1 < l2 {
                    (Some(l2), other.lower_open)
                } else {
                    // l1 == l2
                    (Some(l1), self.lower_open || other.lower_open)
                }
            }
        };

        let (new_upper, new_upper_open) = match (self.upper, other.upper) {
            (None, None) => (None, true),
            (None, Some(u)) => (Some(u), other.upper_open),
            (Some(u), None) => (Some(u), self.upper_open),
            (Some(u1), Some(u2)) => {
                if u1 < u2 {
                    (Some(u1), self.upper_open)
                } else if u1 > u2 {
                    (Some(u2), other.upper_open)
                } else {
                    // u1 == u2
                    (Some(u1), self.upper_open || other.upper_open)
                }
            }
        };

        IntInterval {
            lower: new_lower,
            upper: new_upper,
            lower_open: new_lower_open,
            upper_open: new_upper_open,
        }
    }

    /// Check if value is in interval
    pub fn contains(&self, value: i64) -> bool {
        let lower_ok = match self.lower {
            None => true,
            Some(l) => {
                if self.lower_open {
                    value > l
                } else {
                    value >= l
                }
            }
        };

        let upper_ok = match self.upper {
            None => true,
            Some(u) => {
                if self.upper_open {
                    value < u
                } else {
                    value <= u
                }
            }
        };

        lower_ok && upper_ok
    }

    /// Add constraint from PathCondition
    pub fn from_constraint(cond: &PathCondition) -> Option<Self> {
        let value = cond.value.as_ref()?;
        let int_val = match value {
            ConstValue::Int(i) => *i,
            _ => return None,
        };

        Some(match cond.op {
            ComparisonOp::Eq => Self::bounded(int_val, int_val),
            ComparisonOp::Neq => return None, // Cannot represent as interval
            ComparisonOp::Lt => Self::upper_bounded(int_val, true), // (-∞, val)
            ComparisonOp::Le => Self::upper_bounded(int_val, false), // (-∞, val]
            ComparisonOp::Gt => Self::lower_bounded(int_val, true), // (val, +∞)
            ComparisonOp::Ge => Self::lower_bounded(int_val, false), // [val, +∞)
            ComparisonOp::Null | ComparisonOp::NotNull => return None,
        })
    }
}

/// Interval-based constraint tracker
pub struct IntervalTracker {
    /// Variable intervals
    intervals: HashMap<VarId, IntInterval>,
    /// Maximum variables to track
    max_vars: usize,
}

impl Default for IntervalTracker {
    fn default() -> Self {
        Self::new()
    }
}

impl IntervalTracker {
    /// Create new interval tracker
    pub fn new() -> Self {
        Self {
            intervals: HashMap::new(),
            max_vars: 50, // Track up to 50 variables
        }
    }

    /// Add constraint to tracker
    ///
    /// Returns false if constraint causes contradiction
    pub fn add_constraint(&mut self, cond: &PathCondition) -> bool {
        // Check capacity
        if !self.intervals.contains_key(&cond.var) && self.intervals.len() >= self.max_vars {
            return true; // Conservative: assume feasible
        }

        // Create interval from constraint
        let new_interval = match IntInterval::from_constraint(cond) {
            Some(interval) => interval,
            None => return true, // Cannot represent as interval
        };

        // Get or create existing interval
        let existing = self
            .intervals
            .entry(cond.var.clone())
            .or_insert_with(IntInterval::unbounded);

        // Intersect intervals
        let result = existing.intersect(&new_interval);

        // Check for contradiction
        if result.is_empty() {
            return false;
        }

        // Update interval
        self.intervals.insert(cond.var.clone(), result);
        true
    }

    /// Check if all constraints are feasible
    pub fn is_feasible(&self) -> bool {
        !self.intervals.values().any(|interval| interval.is_empty())
    }

    /// Get interval for variable
    pub fn get_interval(&self, var: &VarId) -> Option<&IntInterval> {
        self.intervals.get(var)
    }

    /// Clear all intervals
    pub fn clear(&mut self) {
        self.intervals.clear();
    }

    /// Get number of tracked variables
    pub fn var_count(&self) -> usize {
        self.intervals.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_unbounded_interval() {
        let interval = IntInterval::unbounded();
        assert!(interval.contains(0));
        assert!(interval.contains(-1000));
        assert!(interval.contains(1000));
    }

    #[test]
    fn test_bounded_interval() {
        let interval = IntInterval::bounded(5, 10);
        assert!(interval.contains(5));
        assert!(interval.contains(7));
        assert!(interval.contains(10));
        assert!(!interval.contains(4));
        assert!(!interval.contains(11));
    }

    #[test]
    fn test_open_interval() {
        // (5, 10)
        let mut interval = IntInterval::bounded(5, 10);
        interval.lower_open = true;
        interval.upper_open = true;

        assert!(!interval.contains(5)); // Open lower
        assert!(interval.contains(7));
        assert!(!interval.contains(10)); // Open upper
    }

    #[test]
    fn test_interval_intersection_feasible() {
        // [5, 15] ∩ [10, 20] = [10, 15]
        let i1 = IntInterval::bounded(5, 15);
        let i2 = IntInterval::bounded(10, 20);
        let result = i1.intersect(&i2);

        assert_eq!(result.lower, Some(10));
        assert_eq!(result.upper, Some(15));
        assert!(!result.is_empty());
    }

    #[test]
    fn test_interval_intersection_empty() {
        // [5, 10] ∩ [15, 20] = ∅
        let i1 = IntInterval::bounded(5, 10);
        let i2 = IntInterval::bounded(15, 20);
        let result = i1.intersect(&i2);

        assert!(result.is_empty());
    }

    #[test]
    fn test_interval_from_constraint_lt() {
        // x < 10
        let cond = PathCondition::lt("x".to_string(), ConstValue::Int(10));
        let interval = IntInterval::from_constraint(&cond).unwrap();

        assert_eq!(interval.lower, None);
        assert_eq!(interval.upper, Some(10));
        assert!(interval.upper_open); // Open bound
        assert!(interval.contains(9));
        assert!(!interval.contains(10));
    }

    #[test]
    fn test_interval_from_constraint_ge() {
        // x >= 5
        let cond = PathCondition::new("x".to_string(), ComparisonOp::Ge, Some(ConstValue::Int(5)));
        let interval = IntInterval::from_constraint(&cond).unwrap();

        assert_eq!(interval.lower, Some(5));
        assert_eq!(interval.upper, None);
        assert!(!interval.lower_open); // Closed bound
        assert!(interval.contains(5));
        assert!(interval.contains(100));
        assert!(!interval.contains(4));
    }

    #[test]
    fn test_tracker_simple_feasible() {
        let mut tracker = IntervalTracker::new();

        // x > 5
        let result =
            tracker.add_constraint(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));
        assert!(result);

        // x < 10
        let result =
            tracker.add_constraint(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));
        assert!(result);

        assert!(tracker.is_feasible());
    }

    #[test]
    fn test_tracker_contradiction() {
        let mut tracker = IntervalTracker::new();

        // x < 10
        tracker.add_constraint(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));

        // x > 20 (contradiction)
        let result =
            tracker.add_constraint(&PathCondition::gt("x".to_string(), ConstValue::Int(20)));

        assert!(!result); // Should detect contradiction
    }

    #[test]
    fn test_tracker_tight_range() {
        let mut tracker = IntervalTracker::new();

        // x >= 5
        tracker.add_constraint(&PathCondition::new(
            "x".to_string(),
            ComparisonOp::Ge,
            Some(ConstValue::Int(5)),
        ));

        // x <= 5 (only x = 5 is valid)
        tracker.add_constraint(&PathCondition::new(
            "x".to_string(),
            ComparisonOp::Le,
            Some(ConstValue::Int(5)),
        ));

        assert!(tracker.is_feasible());

        let interval = tracker.get_interval(&"x".to_string()).unwrap();
        assert_eq!(interval.lower, Some(5));
        assert_eq!(interval.upper, Some(5));
    }

    #[test]
    fn test_tracker_multiple_vars() {
        let mut tracker = IntervalTracker::new();

        // x > 5
        tracker.add_constraint(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));

        // y < 10
        tracker.add_constraint(&PathCondition::lt("y".to_string(), ConstValue::Int(10)));

        // z == 7
        tracker.add_constraint(&PathCondition::eq("z".to_string(), ConstValue::Int(7)));

        assert_eq!(tracker.var_count(), 3);
        assert!(tracker.is_feasible());
    }

    #[test]
    fn test_tracker_clear() {
        let mut tracker = IntervalTracker::new();

        tracker.add_constraint(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));
        tracker.add_constraint(&PathCondition::lt("y".to_string(), ConstValue::Int(10)));

        assert_eq!(tracker.var_count(), 2);

        tracker.clear();
        assert_eq!(tracker.var_count(), 0);
    }

    #[test]
    fn test_edge_case_x_lt_10_and_x_ge_10() {
        let mut tracker = IntervalTracker::new();

        // x < 10
        tracker.add_constraint(&PathCondition::lt("x".to_string(), ConstValue::Int(10)));

        // x >= 10 (contradiction)
        let result = tracker.add_constraint(&PathCondition::new(
            "x".to_string(),
            ComparisonOp::Ge,
            Some(ConstValue::Int(10)),
        ));

        assert!(!result);
    }

    #[test]
    fn test_edge_case_x_gt_5_and_x_le_5() {
        let mut tracker = IntervalTracker::new();

        // x > 5 (open)
        tracker.add_constraint(&PathCondition::gt("x".to_string(), ConstValue::Int(5)));

        // x <= 5 (closed)
        let result = tracker.add_constraint(&PathCondition::new(
            "x".to_string(),
            ComparisonOp::Le,
            Some(ConstValue::Int(5)),
        ));

        assert!(!result); // Contradiction: (5, +∞) ∩ (-∞, 5] = ∅
    }
}
