/*
 * Type Narrowing Integration
 *
 * Combines typestate protocol analysis with type narrowing for enhanced null safety.
 *
 * # Use Case
 * ```python
 * if file is not None:  # Type narrowing: file is NOT None
 *     file.read()       # Typestate: file must be Open
 * ```
 *
 * # Integration Strategy
 * - Type narrowing provides null safety (is None, is not None)
 * - Typestate provides protocol safety (Open, Closed, etc.)
 * - Combined: Both null AND protocol state must be valid
 *
 * # Time Complexity
 * O(type_narrowing) + O(typestate) = O(CFG nodes × variables)
 *
 * # Architecture
 * Application layer integration (no domain/infra changes)
 */

use super::super::domain::{ProtocolViolation, State};
use super::analyzer::{TypestateAnalyzer, TypestateConfig, TypestateResult};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Combined type narrowing + typestate analysis result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CombinedAnalysisResult {
    /// Typestate violations
    pub typestate_violations: Vec<ProtocolViolation>,

    /// Type narrowing violations (placeholder for future integration)
    pub type_narrowing_violations: Vec<TypeNarrowingViolation>,

    /// Combined statistics
    pub stats: CombinedStats,
}

/// Type narrowing violation (placeholder)
///
/// Future: Integrate with existing type_narrowing.rs
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypeNarrowingViolation {
    pub line: usize,
    pub variable: String,
    pub expected_type: String,
    pub actual_type: String,
    pub message: String,
}

/// Combined analysis statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CombinedStats {
    pub typestate_analysis_time_ms: u64,
    pub type_narrowing_analysis_time_ms: u64,
    pub total_violations: usize,
}

/// Combined type analyzer
///
/// Integrates typestate protocol analysis with type narrowing.
///
/// # Example
/// ```rust
/// use codegraph_ir::features::typestate::application::CombinedTypeAnalyzer;
/// use codegraph_ir::features::typestate::infrastructure::FileProtocol;
///
/// let analyzer = CombinedTypeAnalyzer::new()
///     .with_typestate_protocol(FileProtocol::define());
///
/// // Future: Analyze with both typestate and type narrowing
/// ```
pub struct CombinedTypeAnalyzer {
    /// Typestate analyzer
    typestate: TypestateAnalyzer,

    /// Type narrowing integration (future)
    /// Currently: Placeholder for type_narrowing.rs integration
    type_info: HashMap<String, TypeInfo>,
}

/// Type information (simplified placeholder)
///
/// Future: Use actual TypeNarrowingAnalyzer from type_narrowing.rs
#[derive(Debug, Clone)]
struct TypeInfo {
    pub base_type: String,
    pub nullable: bool,
}

impl CombinedTypeAnalyzer {
    /// Create new combined analyzer
    pub fn new() -> Self {
        Self {
            typestate: TypestateAnalyzer::new(),
            type_info: HashMap::new(),
        }
    }

    /// Add typestate protocol
    pub fn with_typestate_protocol(
        mut self,
        protocol: crate::features::typestate::domain::Protocol,
    ) -> Self {
        self.typestate = self.typestate.with_protocol(protocol);
        self
    }

    /// Set typestate configuration
    pub fn with_typestate_config(mut self, config: TypestateConfig) -> Self {
        self.typestate = self.typestate.with_config(config);
        self
    }

    /// Analyze with both typestate and type narrowing
    ///
    /// # Current Implementation
    /// - ✅ Typestate analysis: Fully implemented
    /// - ⏳ Type narrowing: Placeholder (future integration)
    ///
    /// # Future Enhancement
    /// ```rust,ignore
    /// // Integrate with type_narrowing.rs
    /// let type_result = self.type_narrowing.analyze(code);
    /// let typestate_result = self.typestate.analyze(code);
    /// // Combine results
    /// ```
    pub fn analyze(
        &mut self,
        blocks: Vec<super::analyzer::SimpleBlock>,
        edges: Vec<(String, String)>,
    ) -> CombinedAnalysisResult {
        let start = std::time::Instant::now();

        // Step 1: Type narrowing (placeholder - future integration)
        let type_narrowing_time_ms = 0; // Placeholder
        let type_narrowing_violations = Vec::new(); // Placeholder

        // Step 2: Typestate analysis
        let typestate_start = std::time::Instant::now();
        let typestate_result = self.typestate.analyze_simple(blocks, edges);
        let typestate_time_ms = typestate_start.elapsed().as_millis() as u64;

        let violation_count = typestate_result.violations.len();
        CombinedAnalysisResult {
            typestate_violations: typestate_result.violations,
            type_narrowing_violations,
            stats: CombinedStats {
                typestate_analysis_time_ms: typestate_time_ms,
                type_narrowing_analysis_time_ms: type_narrowing_time_ms,
                total_violations: violation_count,
            },
        }
    }

    /// Check if variable is null-safe (future integration)
    ///
    /// # Future Enhancement
    /// Integrate with type_narrowing.rs to check:
    /// - is None / is not None guards
    /// - isinstance() checks
    /// - Truthiness checks
    fn is_null_safe(&self, _variable: &str, _at_line: usize) -> bool {
        // Placeholder: Always assume null-safe for now
        true
    }
}

impl Default for CombinedTypeAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::typestate::application::analyzer::{SimpleBlock, Statement};
    use crate::features::typestate::infrastructure::FileProtocol;

    #[test]
    fn test_combined_analyzer_creation() {
        let analyzer = CombinedTypeAnalyzer::new().with_typestate_protocol(FileProtocol::define());

        // Verify analyzer is created
        assert_eq!(analyzer.typestate.protocols.len(), 1);
    }

    #[test]
    fn test_combined_analysis_typestate_only() {
        let mut analyzer =
            CombinedTypeAnalyzer::new().with_typestate_protocol(FileProtocol::define());

        let blocks = vec![
            SimpleBlock {
                id: "entry".to_string(),
                line: 1,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "open".to_string(),
                }],
            },
            SimpleBlock {
                id: "b1".to_string(),
                line: 2,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "close".to_string(),
                }],
            },
            SimpleBlock {
                id: "b2".to_string(),
                line: 3,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "read".to_string(),
                }],
            },
        ];

        let edges = vec![
            ("entry".to_string(), "b1".to_string()),
            ("b1".to_string(), "b2".to_string()),
        ];

        let result = analyzer.analyze(blocks, edges);

        // Should detect use-after-close from typestate
        assert_eq!(result.typestate_violations.len(), 1);
        assert_eq!(result.stats.total_violations, 1);

        // Type narrowing placeholder (empty for now)
        assert_eq!(result.type_narrowing_violations.len(), 0);
    }

    #[test]
    fn test_combined_analysis_no_violations() {
        let mut analyzer =
            CombinedTypeAnalyzer::new().with_typestate_protocol(FileProtocol::define());

        let blocks = vec![
            SimpleBlock {
                id: "entry".to_string(),
                line: 1,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "open".to_string(),
                }],
            },
            SimpleBlock {
                id: "b1".to_string(),
                line: 2,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "read".to_string(),
                }],
            },
            SimpleBlock {
                id: "b2".to_string(),
                line: 3,
                statements: vec![Statement::MethodCall {
                    object: "file".to_string(),
                    method: "close".to_string(),
                }],
            },
        ];

        let edges = vec![
            ("entry".to_string(), "b1".to_string()),
            ("b1".to_string(), "b2".to_string()),
        ];

        let result = analyzer.analyze(blocks, edges);

        // No violations on happy path
        assert_eq!(result.typestate_violations.len(), 0);
        assert_eq!(result.stats.total_violations, 0);
    }
}
