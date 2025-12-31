//! Domain models for cost analysis
//!
//! Pure business logic with no external dependencies.

use serde::{Deserialize, Serialize};
use std::cmp::Ordering;

/// Big-O complexity classes
///
/// Ordered by computational cost (ascending).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ComplexityClass {
    /// O(1) - Constant time
    Constant,
    /// O(log n) - Logarithmic time
    Logarithmic,
    /// O(n) - Linear time
    Linear,
    /// O(n log n) - Linearithmic time
    Linearithmic,
    /// O(n²) - Quadratic time
    Quadratic,
    /// O(n³) - Cubic time
    Cubic,
    /// O(2^n) - Exponential time
    Exponential,
    /// O(n!) - Factorial time
    Factorial,
    /// O(?) - Unknown complexity
    Unknown,
}

impl ComplexityClass {
    /// Get string representation (e.g., "O(n)")
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Constant => "O(1)",
            Self::Logarithmic => "O(log n)",
            Self::Linear => "O(n)",
            Self::Linearithmic => "O(n log n)",
            Self::Quadratic => "O(n²)",
            Self::Cubic => "O(n³)",
            Self::Exponential => "O(2^n)",
            Self::Factorial => "O(n!)",
            Self::Unknown => "O(?)",
        }
    }

    /// Is this considered slow? (>= O(n²))
    pub fn is_slow(&self) -> bool {
        matches!(
            self,
            Self::Quadratic | Self::Cubic | Self::Exponential | Self::Factorial
        )
    }

    /// Get ordering index for comparison
    fn order_index(&self) -> u8 {
        match self {
            Self::Constant => 0,
            Self::Logarithmic => 1,
            Self::Linear => 2,
            Self::Linearithmic => 3,
            Self::Quadratic => 4,
            Self::Cubic => 5,
            Self::Exponential => 6,
            Self::Factorial => 7,
            Self::Unknown => 8,
        }
    }
}

impl PartialOrd for ComplexityClass {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for ComplexityClass {
    fn cmp(&self, other: &Self) -> Ordering {
        self.order_index().cmp(&other.order_index())
    }
}

/// Loop bound inference result
///
/// Represents the inferred iteration count of a loop.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BoundResult {
    /// Symbolic bound expression (e.g., "n", "len(arr)", "n * m")
    pub bound: String,

    /// How was this bound obtained?
    /// - "proven": Pattern matching, SCCP constant
    /// - "likely": Widening, simple while
    /// - "heuristic": Unbounded, complex loop
    pub verdict: Verdict,

    /// Confidence: 0.0-1.0
    pub confidence: f64,

    /// Inference method
    pub method: InferenceMethod,

    /// Conservative upper bound (for heuristic)
    pub upper_bound_hint: Option<String>,

    /// Human-readable warning (for heuristic)
    pub warning: Option<String>,

    /// Loop ID
    pub loop_id: String,

    /// Location (file_path, line_number)
    pub location: Option<(String, usize)>,
}

impl BoundResult {
    /// Create new bound result with validation
    pub fn new(
        bound: String,
        verdict: Verdict,
        confidence: f64,
        method: InferenceMethod,
        loop_id: String,
    ) -> Result<Self, String> {
        // Validate confidence
        if !(0.0..=1.0).contains(&confidence) {
            return Err(format!("confidence must be 0.0-1.0, got {}", confidence));
        }

        // Verdict/Confidence consistency check
        match verdict {
            Verdict::Proven if confidence < 0.8 => {
                return Err(format!(
                    "proven verdict should have confidence >= 0.8, got {}",
                    confidence
                ))
            }
            Verdict::Heuristic if confidence > 0.5 => {
                return Err(format!(
                    "heuristic verdict should have confidence <= 0.5, got {}",
                    confidence
                ))
            }
            _ => {}
        }

        Ok(Self {
            bound,
            verdict,
            confidence,
            method,
            upper_bound_hint: None,
            warning: None,
            loop_id,
            location: None,
        })
    }

    /// Is bound unknown?
    pub fn is_unknown(&self) -> bool {
        matches!(self.bound.as_str(), "unknown" | "?" | "∞")
    }

    /// Set location
    pub fn with_location(mut self, file_path: String, line: usize) -> Self {
        self.location = Some((file_path, line));
        self
    }

    /// Set upper bound hint
    pub fn with_upper_bound_hint(mut self, hint: String) -> Self {
        self.upper_bound_hint = Some(hint);
        self
    }

    /// Set warning
    pub fn with_warning(mut self, warning: String) -> Self {
        self.warning = Some(warning);
        self
    }
}

/// Verdict level
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Verdict {
    /// Pattern matching, SCCP constant
    Proven,
    /// Widening, simple while
    Likely,
    /// Unbounded, complex loop
    Heuristic,
}

impl Verdict {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Proven => "proven",
            Self::Likely => "likely",
            Self::Heuristic => "heuristic",
        }
    }
}

/// Inference method
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum InferenceMethod {
    /// Pattern matching (range, for-in)
    Pattern,
    /// SCCP constant propagation
    Sccp,
    /// Widening (while loops)
    Widening,
    /// DFG analysis
    Dfg,
    /// Heuristic (unknown)
    Heuristic,
}

impl InferenceMethod {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Pattern => "pattern",
            Self::Sccp => "sccp",
            Self::Widening => "widening",
            Self::Dfg => "dfg",
            Self::Heuristic => "heuristic",
        }
    }
}

/// Cost analysis result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostResult {
    /// Function fully qualified name
    pub function_fqn: String,

    /// Complexity class (O(n), O(n²))
    pub complexity: ComplexityClass,

    /// Confidence level
    pub verdict: Verdict,

    /// Confidence: 0.0-1.0
    pub confidence: f64,

    /// Human-readable summary
    pub explanation: String,

    /// Loop bound results (for details)
    pub loop_bounds: Vec<BoundResult>,

    /// Performance hotspots
    pub hotspots: Vec<Hotspot>,

    /// Additional metadata
    #[serde(default)]
    pub metadata: serde_json::Value,
}

impl CostResult {
    /// Is this function slow? (>= O(n²))
    pub fn is_slow(&self) -> bool {
        self.complexity.is_slow()
    }

    /// Is this proven? (not heuristic)
    pub fn is_proven(&self) -> bool {
        self.verdict == Verdict::Proven
    }
}

/// Performance hotspot
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Hotspot {
    /// Line number
    pub line: usize,

    /// Reason (e.g., "Loop: n * m")
    pub reason: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_complexity_ordering() {
        assert!(ComplexityClass::Constant < ComplexityClass::Linear);
        assert!(ComplexityClass::Linear < ComplexityClass::Quadratic);
        assert!(ComplexityClass::Quadratic < ComplexityClass::Exponential);
    }

    #[test]
    fn test_complexity_is_slow() {
        assert!(!ComplexityClass::Constant.is_slow());
        assert!(!ComplexityClass::Linear.is_slow());
        assert!(ComplexityClass::Quadratic.is_slow());
        assert!(ComplexityClass::Exponential.is_slow());
    }

    #[test]
    fn test_bound_result_validation() {
        // Valid proven bound
        let result = BoundResult::new(
            "n".to_string(),
            Verdict::Proven,
            0.95,
            InferenceMethod::Pattern,
            "loop_1".to_string(),
        );
        assert!(result.is_ok());

        // Invalid: proven with low confidence
        let result = BoundResult::new(
            "n".to_string(),
            Verdict::Proven,
            0.5,
            InferenceMethod::Pattern,
            "loop_1".to_string(),
        );
        assert!(result.is_err());

        // Invalid: heuristic with high confidence
        let result = BoundResult::new(
            "unknown".to_string(),
            Verdict::Heuristic,
            0.9,
            InferenceMethod::Heuristic,
            "loop_1".to_string(),
        );
        assert!(result.is_err());
    }

    #[test]
    fn test_bound_result_is_unknown() {
        let bound = BoundResult::new(
            "unknown".to_string(),
            Verdict::Heuristic,
            0.2,
            InferenceMethod::Heuristic,
            "loop_1".to_string(),
        )
        .unwrap();
        assert!(bound.is_unknown());

        let bound = BoundResult::new(
            "n".to_string(),
            Verdict::Proven,
            0.95,
            InferenceMethod::Pattern,
            "loop_1".to_string(),
        )
        .unwrap();
        assert!(!bound.is_unknown());
    }
}
