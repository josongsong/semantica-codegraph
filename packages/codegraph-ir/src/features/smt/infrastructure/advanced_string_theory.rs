//! Advanced String Theory (SOTA v2.3 - Phase 3)
//!
//! Advanced string operations beyond basic pattern matching.
//!
//! # Capabilities
//!
//! - **indexOf**: Track position of substring occurrences
//! - **substring**: Reasoning about extracted substrings
//! - **Composition**: Combine multiple string operations
//!
//! # Limitations
//!
//! - ⚠️ **Approximate**: Not as precise as Z3 string theory
//! - ⚠️ **Simple patterns only**: Complex regex NOT supported
//! - ⚠️ **Conservative**: Returns Unknown when uncertain
//!
//! # Examples
//!
//! ```text
//! use codegraph_ir::features::smt::infrastructure::AdvancedStringTheory;
//!
//! let mut theory = AdvancedStringTheory::new();
//!
//! // s.startsWith("http://")
//! theory.add_starts_with("url".to_string(), "http://".to_string());
//!
//! // indexOf(s, ".") > 7
//! theory.add_index_of_constraint(
//!     "url".to_string(),
//!     ".".to_string(),
//!     ComparisonOp::Gt,
//!     7
//! );
//!
//! assert!(theory.is_feasible());
//! ```

use crate::features::smt::domain::{ComparisonOp, VarId};
use std::collections::HashMap;

/// String operation type
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StringOperation {
    /// indexOf(str, pattern) - position of first occurrence
    IndexOf { pattern: String },
    /// substring(str, start, end) - extract substring
    Substring { start: usize, end: Option<usize> },
    /// length(str) - string length
    Length,
}

/// Index constraint: indexOf(str, pattern) <op> value
#[derive(Debug, Clone)]
pub struct IndexOfConstraint {
    /// Variable name
    pub var: VarId,
    /// Pattern to search for
    pub pattern: String,
    /// Comparison operator
    pub op: ComparisonOp,
    /// Position value
    pub position: i64,
}

/// Substring constraint: substring(str, start, end) == value
#[derive(Debug, Clone)]
pub struct SubstringConstraint {
    /// Variable name
    pub var: VarId,
    /// Start position
    pub start: usize,
    /// End position (None = to end of string)
    pub end: Option<usize>,
    /// Expected value
    pub value: String,
}

/// Prefix/suffix tracking
#[derive(Debug, Clone)]
pub struct PrefixSuffix {
    /// Known prefixes
    pub prefixes: Vec<String>,
    /// Known suffixes
    pub suffixes: Vec<String>,
}

impl Default for PrefixSuffix {
    fn default() -> Self {
        Self::new()
    }
}

impl PrefixSuffix {
    pub fn new() -> Self {
        Self {
            prefixes: Vec::new(),
            suffixes: Vec::new(),
        }
    }
}

/// Advanced string theory tracker
pub struct AdvancedStringTheory {
    /// indexOf constraints
    index_of_constraints: Vec<IndexOfConstraint>,

    /// substring constraints
    substring_constraints: Vec<SubstringConstraint>,

    /// Prefix/suffix tracking
    prefix_suffix: HashMap<VarId, PrefixSuffix>,

    /// String length bounds (min, max)
    length_bounds: HashMap<VarId, (usize, Option<usize>)>,

    /// Contradiction flag
    has_contradiction: bool,

    /// Max constraints
    max_constraints: usize,
}

impl Default for AdvancedStringTheory {
    fn default() -> Self {
        Self::new()
    }
}

impl AdvancedStringTheory {
    /// Create new advanced string theory tracker
    pub fn new() -> Self {
        Self {
            index_of_constraints: Vec::new(),
            substring_constraints: Vec::new(),
            prefix_suffix: HashMap::new(),
            length_bounds: HashMap::new(),
            has_contradiction: false,
            max_constraints: 50,
        }
    }

    /// Add startsWith constraint
    pub fn add_starts_with(&mut self, var: VarId, prefix: String) -> bool {
        if self.has_contradiction {
            return false;
        }

        // Add prefix
        self.prefix_suffix
            .entry(var.clone())
            .or_default()
            .prefixes
            .push(prefix.clone());

        // Infer minimum length
        let min_len = prefix.len();
        self.update_length_bound(&var, Some(min_len), None);

        // Check if compatible with existing substring constraints
        self.check_prefix_suffix_compatibility(&var, &prefix, true);

        !self.has_contradiction
    }

    /// Add endsWith constraint
    pub fn add_ends_with(&mut self, var: VarId, suffix: String) -> bool {
        if self.has_contradiction {
            return false;
        }

        // Add suffix
        self.prefix_suffix
            .entry(var.clone())
            .or_default()
            .suffixes
            .push(suffix.clone());

        // Infer minimum length
        let min_len = suffix.len();
        self.update_length_bound(&var, Some(min_len), None);

        // Check compatibility
        self.check_prefix_suffix_compatibility(&var, &suffix, false);

        !self.has_contradiction
    }

    /// Add indexOf constraint: indexOf(var, pattern) <op> position
    pub fn add_index_of_constraint(
        &mut self,
        var: VarId,
        pattern: String,
        op: ComparisonOp,
        position: i64,
    ) -> bool {
        if self.has_contradiction {
            return false;
        }

        if self.index_of_constraints.len() >= self.max_constraints {
            return true; // Conservative
        }

        let constraint = IndexOfConstraint {
            var: var.clone(),
            pattern: pattern.clone(),
            op,
            position,
        };

        // Validate constraint
        if !self.validate_index_of_constraint(&constraint) {
            self.has_contradiction = true;
            return false;
        }

        // Infer length bounds from indexOf
        match op {
            ComparisonOp::Gt => {
                // indexOf > position
                // String must be at least position + 1 + pattern.len()
                let min_len = (position as usize)
                    .saturating_add(pattern.len())
                    .saturating_add(1);
                self.update_length_bound(&var, Some(min_len), None);
            }
            ComparisonOp::Ge => {
                // indexOf >= position
                let min_len = (position as usize).saturating_add(pattern.len());
                self.update_length_bound(&var, Some(min_len), None);
            }
            ComparisonOp::Eq => {
                // indexOf == position
                if position >= 0 {
                    let min_len = (position as usize).saturating_add(pattern.len());
                    self.update_length_bound(&var, Some(min_len), None);
                }
            }
            _ => {}
        }

        self.index_of_constraints.push(constraint);
        true
    }

    /// Add substring constraint: substring(var, start, end) == value
    pub fn add_substring_constraint(
        &mut self,
        var: VarId,
        start: usize,
        end: Option<usize>,
        value: String,
    ) -> bool {
        if self.has_contradiction {
            return false;
        }

        if self.substring_constraints.len() >= self.max_constraints {
            return true; // Conservative
        }

        // Validate constraint
        let constraint_len = value.len();
        let expected_end = end.unwrap_or(start + constraint_len);

        if expected_end < start {
            self.has_contradiction = true;
            return false;
        }

        // Check if substring length matches
        if let Some(e) = end {
            if e.saturating_sub(start) != constraint_len {
                self.has_contradiction = true;
                return false;
            }
        }

        // Infer length bounds
        let min_len = if end.is_some() {
            expected_end
        } else {
            start + constraint_len
        };
        self.update_length_bound(&var, Some(min_len), None);

        // If start == 0, this is a prefix
        if start == 0 {
            self.add_starts_with(var.clone(), value.clone());
        }

        let constraint = SubstringConstraint {
            var,
            start,
            end,
            value,
        };

        self.substring_constraints.push(constraint);
        !self.has_contradiction
    }

    /// Update length bound for variable
    fn update_length_bound(&mut self, var: &VarId, new_min: Option<usize>, new_max: Option<usize>) {
        let (current_min, current_max) = self.length_bounds.get(var).cloned().unwrap_or((0, None));

        let final_min = match (Some(current_min), new_min) {
            (Some(a), Some(b)) => a.max(b),
            (Some(a), None) => a,
            (None, Some(b)) => b,
            (None, None) => 0,
        };

        let final_max = match (current_max, new_max) {
            (Some(a), Some(b)) => Some(a.min(b)),
            (Some(a), None) => Some(a),
            (None, Some(b)) => Some(b),
            (None, None) => None,
        };

        // Check contradiction
        if let Some(max) = final_max {
            if final_min > max {
                self.has_contradiction = true;
                return;
            }
        }

        self.length_bounds
            .insert(var.clone(), (final_min, final_max));
    }

    /// Validate indexOf constraint
    fn validate_index_of_constraint(&self, constraint: &IndexOfConstraint) -> bool {
        // Check if position is compatible with length bounds
        if let Some((min_len, max_len)) = self.length_bounds.get(&constraint.var) {
            match constraint.op {
                ComparisonOp::Gt => {
                    // indexOf > position
                    // If max_len <= position + pattern.len(), impossible
                    if let Some(max) = max_len {
                        if *max <= (constraint.position as usize) + constraint.pattern.len() {
                            return false;
                        }
                    }
                }
                ComparisonOp::Eq => {
                    // indexOf == position
                    // If min_len < position + pattern.len(), impossible
                    let required_len = (constraint.position as usize) + constraint.pattern.len();
                    if *min_len < required_len {
                        return false;
                    }
                }
                _ => {}
            }
        }

        // Check compatibility with prefixes/suffixes
        if constraint.position == 0 {
            if let Some(ps) = self.prefix_suffix.get(&constraint.var) {
                // indexOf at position 0 means string starts with pattern
                for prefix in &ps.prefixes {
                    if !prefix.starts_with(&constraint.pattern)
                        && !constraint.pattern.starts_with(prefix)
                    {
                        return false;
                    }
                }
            }
        }

        true
    }

    /// Check prefix/suffix compatibility
    fn check_prefix_suffix_compatibility(&mut self, var: &VarId, pattern: &str, is_prefix: bool) {
        // Check against substring constraints
        for substring in &self.substring_constraints {
            if substring.var != *var {
                continue;
            }

            if is_prefix && substring.start == 0 {
                // Both are prefixes - must be compatible
                if !pattern.starts_with(&substring.value) && !substring.value.starts_with(pattern) {
                    self.has_contradiction = true;
                    return;
                }
            }
        }

        // Check against existing prefixes/suffixes
        if let Some(ps) = self.prefix_suffix.get(var) {
            if is_prefix {
                // Check against all existing prefixes
                for existing_prefix in &ps.prefixes {
                    if existing_prefix != pattern {
                        // Prefixes must be compatible (one is prefix of other)
                        if !pattern.starts_with(existing_prefix)
                            && !existing_prefix.starts_with(pattern)
                        {
                            self.has_contradiction = true;
                            return;
                        }
                    }
                }
            } else {
                // Check against all existing suffixes
                for existing_suffix in &ps.suffixes {
                    if existing_suffix != pattern {
                        // Suffixes must be compatible (one is suffix of other)
                        if !pattern.ends_with(existing_suffix)
                            && !existing_suffix.ends_with(pattern)
                        {
                            self.has_contradiction = true;
                            return;
                        }
                    }
                }
            }
        }
    }

    /// Check if all constraints are feasible
    pub fn is_feasible(&self) -> bool {
        !self.has_contradiction
    }

    /// Get minimum length for variable
    pub fn get_min_length(&self, var: &VarId) -> Option<usize> {
        self.length_bounds.get(var).map(|(min, _)| *min)
    }

    /// Get maximum length for variable
    pub fn get_max_length(&self, var: &VarId) -> Option<usize> {
        self.length_bounds.get(var).and_then(|(_, max)| *max)
    }

    /// Clear all state
    pub fn clear(&mut self) {
        self.index_of_constraints.clear();
        self.substring_constraints.clear();
        self.prefix_suffix.clear();
        self.length_bounds.clear();
        self.has_contradiction = false;
    }

    /// Get constraint count
    pub fn constraint_count(&self) -> usize {
        self.index_of_constraints.len() + self.substring_constraints.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_starts_with_basic() {
        let mut theory = AdvancedStringTheory::new();

        assert!(theory.add_starts_with("url".to_string(), "http://".to_string()));
        assert!(theory.is_feasible());

        // Should infer minimum length
        assert_eq!(theory.get_min_length(&"url".to_string()), Some(7));
    }

    #[test]
    fn test_index_of_basic() {
        let mut theory = AdvancedStringTheory::new();

        // indexOf(url, ".") > 7
        assert!(theory.add_index_of_constraint(
            "url".to_string(),
            ".".to_string(),
            ComparisonOp::Gt,
            7
        ));

        assert!(theory.is_feasible());

        // Should infer minimum length > 7 + 1 (pattern len)
        assert!(theory.get_min_length(&"url".to_string()).unwrap() >= 8);
    }

    #[test]
    fn test_index_of_with_prefix() {
        let mut theory = AdvancedStringTheory::new();

        // url starts with "http://"
        theory.add_starts_with("url".to_string(), "http://".to_string());

        // indexOf(url, ".") > 7
        theory.add_index_of_constraint("url".to_string(), ".".to_string(), ComparisonOp::Gt, 7);

        assert!(theory.is_feasible());
    }

    #[test]
    fn test_substring_basic() {
        let mut theory = AdvancedStringTheory::new();

        // substring(url, 0, 7) == "http://"
        assert!(theory.add_substring_constraint(
            "url".to_string(),
            0,
            Some(7),
            "http://".to_string()
        ));

        assert!(theory.is_feasible());
        assert_eq!(theory.get_min_length(&"url".to_string()), Some(7));
    }

    #[test]
    fn test_substring_contradiction() {
        let mut theory = AdvancedStringTheory::new();

        // substring(url, 5, 3) - end < start!
        // Note: This is caught in add_substring_constraint validation
        let result =
            theory.add_substring_constraint("url".to_string(), 5, Some(3), "xx".to_string());

        assert!(!result);
        assert!(!theory.is_feasible());
    }

    #[test]
    fn test_combined_constraints() {
        let mut theory = AdvancedStringTheory::new();

        // url starts with "http://"
        theory.add_starts_with("url".to_string(), "http://".to_string());

        // substring(url, 0, 7) == "http://" (compatible)
        assert!(theory.add_substring_constraint(
            "url".to_string(),
            0,
            Some(7),
            "http://".to_string()
        ));

        // indexOf(url, ".") > 10
        assert!(theory.add_index_of_constraint(
            "url".to_string(),
            ".".to_string(),
            ComparisonOp::Gt,
            10
        ));

        assert!(theory.is_feasible());
        assert!(theory.get_min_length(&"url".to_string()).unwrap() >= 11);
    }

    #[test]
    fn test_prefix_contradiction() {
        let mut theory = AdvancedStringTheory::new();

        // url starts with "http://"
        theory.add_starts_with("url".to_string(), "http://".to_string());

        // substring(url, 0, 5) == "ftp://" (contradiction!)
        let result =
            theory.add_substring_constraint("url".to_string(), 0, Some(6), "ftp://".to_string());

        assert!(!result);
        assert!(!theory.is_feasible());
    }
}
