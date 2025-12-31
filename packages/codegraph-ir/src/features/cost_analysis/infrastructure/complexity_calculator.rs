//! Complexity Calculator (RFC-028)
//!
//! Cost composition: Sequential (add), Nested (multiply).

use crate::features::cost_analysis::domain::{BoundResult, ComplexityClass};
use std::collections::HashMap;

/// Calculate overall complexity from loop bounds
///
/// Algorithm (RFC-028 Section 3.3):
/// - Sequential loops: add (max)
/// - Nested loops: multiply
/// - Function calls: lookup (cached)
///
/// Examples:
/// ```text
/// # Single loop
/// for i in range(n):  → O(n)
///
/// # Sequential loops
/// for i in range(n):
///     ...
/// for j in range(m):  → O(max(n, m)) ≈ O(n + m)
///
/// # Nested loops
/// for i in range(n):
///     for j in range(m):  → O(n * m) = O(n²) if n==m
/// ```
pub struct ComplexityCalculator;

impl ComplexityCalculator {
    pub fn new() -> Self {
        Self
    }

    /// Calculate overall complexity
    ///
    /// Args:
    ///     loop_bounds: List of loop bound results
    ///     nesting_levels: Map of loop_id → nesting level (0=top-level)
    ///
    /// Returns:
    ///     (ComplexityClass, confidence, cost_term)
    pub fn calculate(
        &self,
        loop_bounds: &[BoundResult],
        nesting_levels: &HashMap<String, usize>,
    ) -> (ComplexityClass, f64, String) {
        if loop_bounds.is_empty() {
            return (ComplexityClass::Constant, 1.0, "1".to_string());
        }

        // Group by nesting level
        let mut by_level: HashMap<usize, Vec<&BoundResult>> = HashMap::new();
        for bound in loop_bounds {
            let level = *nesting_levels.get(&bound.loop_id).unwrap_or(&0);
            by_level.entry(level).or_default().push(bound);
        }

        // Calculate nested complexity (multiply across levels)
        let mut terms = Vec::new();
        let mut total_confidence = 1.0;

        let mut levels: Vec<_> = by_level.keys().copied().collect();
        levels.sort_unstable();

        for level in levels {
            let level_bounds = &by_level[&level];

            // Within same level: sequential (take max, approximate as add)
            let level_term = self.combine_sequential(level_bounds);
            terms.push(level_term);

            // Confidence: product (worst case)
            let level_confidence = level_bounds
                .iter()
                .map(|b| b.confidence)
                .fold(f64::INFINITY, f64::min);
            total_confidence *= level_confidence;
        }

        // Compose cost term
        let cost_term = if terms.len() == 1 {
            terms[0].clone()
        } else {
            // Nested: multiply
            terms.join(" * ")
        };

        // Classify complexity
        let complexity = self.classify_complexity(&cost_term);

        tracing::debug!(
            "Calculated complexity: {} (term={}, confidence={:.2})",
            complexity.as_str(),
            cost_term,
            total_confidence
        );

        (complexity, total_confidence, cost_term)
    }

    /// Combine sequential loops (same nesting level)
    ///
    /// Algorithm: max(bounds) ≈ add(bounds)
    /// Simplification: 같은 변수면 하나만, 다르면 max
    ///
    /// Examples:
    ///     [n, m] → "max(n, m)"
    ///     [n, n] → "n"
    fn combine_sequential(&self, bounds: &[&BoundResult]) -> String {
        if bounds.len() == 1 {
            return bounds[0].bound.clone();
        }

        // Collect unique bounds
        let mut unique_bounds: Vec<String> = bounds.iter().map(|b| b.bound.clone()).collect();
        unique_bounds.sort();
        unique_bounds.dedup();

        if unique_bounds.len() == 1 {
            // All same: n, n, n → n
            unique_bounds[0].clone()
        } else {
            // Different: n, m → max(n, m)
            format!("max({})", unique_bounds.join(", "))
        }
    }

    /// Classify complexity from cost term
    ///
    /// Args:
    ///     cost_term: Symbolic expression ("n", "n * m", "2^n")
    ///
    /// Returns:
    ///     ComplexityClass
    ///
    /// Algorithm:
    /// - No variables → O(1)
    /// - Single variable, no ops → O(n)
    /// - Single variable with * → O(n²) or higher
    /// - Multiple variables with * → O(n * m) ≈ O(n²)
    /// - Exponential patterns → O(2^n)
    ///
    /// Production: Conservative (과대평가)
    fn classify_complexity(&self, cost_term: &str) -> ComplexityClass {
        // Constant
        if cost_term == "1" {
            return ComplexityClass::Constant;
        }
        if cost_term == "unknown" {
            return ComplexityClass::Unknown;
        }

        // Exponential patterns
        if cost_term.contains("2^") || cost_term.contains('^') {
            return ComplexityClass::Exponential;
        }

        // Factorial
        if cost_term.contains('!') {
            return ComplexityClass::Factorial;
        }

        // Count multiplication depth
        let mult_count = cost_term.matches('*').count();

        match mult_count {
            0 => {
                // Single variable: O(n)
                if cost_term.contains("log") {
                    ComplexityClass::Logarithmic
                } else {
                    ComplexityClass::Linear
                }
            }
            1 => {
                // n * m or n * log(m)
                if cost_term.contains("log") {
                    ComplexityClass::Linearithmic // O(n log n)
                } else {
                    ComplexityClass::Quadratic // O(n²) or O(n * m)
                }
            }
            2 => {
                // n * m * k
                ComplexityClass::Cubic
            }
            _ => {
                // n * m * k * ...
                ComplexityClass::Exponential // Conservative
            }
        }
    }
}

impl Default for ComplexityCalculator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::cost_analysis::domain::{InferenceMethod, Verdict};

    #[test]
    fn test_calculate_no_loops() {
        let calc = ComplexityCalculator::new();
        let (complexity, confidence, term) = calc.calculate(&[], &HashMap::new());

        assert_eq!(complexity, ComplexityClass::Constant);
        assert_eq!(confidence, 1.0);
        assert_eq!(term, "1");
    }

    #[test]
    fn test_calculate_single_loop() {
        let calc = ComplexityCalculator::new();
        let bound = BoundResult::new(
            "n".to_string(),
            Verdict::Proven,
            0.95,
            InferenceMethod::Pattern,
            "loop_1".to_string(),
        )
        .unwrap();

        let mut nesting = HashMap::new();
        nesting.insert("loop_1".to_string(), 0);

        let (complexity, confidence, term) = calc.calculate(&[bound], &nesting);

        assert_eq!(complexity, ComplexityClass::Linear);
        assert_eq!(confidence, 0.95);
        assert_eq!(term, "n");
    }

    #[test]
    fn test_calculate_nested_loops() {
        let calc = ComplexityCalculator::new();
        let bound1 = BoundResult::new(
            "n".to_string(),
            Verdict::Proven,
            0.95,
            InferenceMethod::Pattern,
            "loop_1".to_string(),
        )
        .unwrap();

        let bound2 = BoundResult::new(
            "m".to_string(),
            Verdict::Proven,
            0.9,
            InferenceMethod::Pattern,
            "loop_2".to_string(),
        )
        .unwrap();

        let mut nesting = HashMap::new();
        nesting.insert("loop_1".to_string(), 0);
        nesting.insert("loop_2".to_string(), 1);

        let (complexity, confidence, term) = calc.calculate(&[bound1, bound2], &nesting);

        assert_eq!(complexity, ComplexityClass::Quadratic);
        assert!((confidence - 0.855).abs() < 0.01); // 0.95 * 0.9
        assert_eq!(term, "n * m");
    }

    #[test]
    fn test_calculate_sequential_loops() {
        let calc = ComplexityCalculator::new();
        let bound1 = BoundResult::new(
            "n".to_string(),
            Verdict::Proven,
            0.95,
            InferenceMethod::Pattern,
            "loop_1".to_string(),
        )
        .unwrap();

        let bound2 = BoundResult::new(
            "m".to_string(),
            Verdict::Proven,
            0.9,
            InferenceMethod::Pattern,
            "loop_2".to_string(),
        )
        .unwrap();

        let mut nesting = HashMap::new();
        nesting.insert("loop_1".to_string(), 0);
        nesting.insert("loop_2".to_string(), 0); // Same level

        let (complexity, confidence, term) = calc.calculate(&[bound1, bound2], &nesting);

        assert_eq!(complexity, ComplexityClass::Linear); // max(n, m)
        assert_eq!(confidence, 0.9); // min(0.95, 0.9)
        assert_eq!(term, "max(m, n)"); // Sorted
    }

    #[test]
    fn test_classify_complexity() {
        let calc = ComplexityCalculator::new();

        assert_eq!(calc.classify_complexity("1"), ComplexityClass::Constant);
        assert_eq!(calc.classify_complexity("n"), ComplexityClass::Linear);
        assert_eq!(
            calc.classify_complexity("log(n)"),
            ComplexityClass::Logarithmic
        );
        assert_eq!(
            calc.classify_complexity("n * m"),
            ComplexityClass::Quadratic
        );
        assert_eq!(
            calc.classify_complexity("n * log(n)"),
            ComplexityClass::Linearithmic
        );
        assert_eq!(
            calc.classify_complexity("n * m * k"),
            ComplexityClass::Cubic
        );
        assert_eq!(
            calc.classify_complexity("2^n"),
            ComplexityClass::Exponential
        );
        assert_eq!(calc.classify_complexity("n!"), ComplexityClass::Factorial);
    }

    #[test]
    fn test_combine_sequential() {
        let calc = ComplexityCalculator::new();

        let bound1 = BoundResult::new(
            "n".to_string(),
            Verdict::Proven,
            0.95,
            InferenceMethod::Pattern,
            "loop_1".to_string(),
        )
        .unwrap();

        let bound2 = BoundResult::new(
            "n".to_string(),
            Verdict::Proven,
            0.9,
            InferenceMethod::Pattern,
            "loop_2".to_string(),
        )
        .unwrap();

        // Same bound: should return "n"
        let result = calc.combine_sequential(&[&bound1, &bound2]);
        assert_eq!(result, "n");

        let bound3 = BoundResult::new(
            "m".to_string(),
            Verdict::Proven,
            0.9,
            InferenceMethod::Pattern,
            "loop_3".to_string(),
        )
        .unwrap();

        // Different bounds: should return "max(m, n)"
        let result = calc.combine_sequential(&[&bound1, &bound3]);
        assert_eq!(result, "max(m, n)");
    }
}
