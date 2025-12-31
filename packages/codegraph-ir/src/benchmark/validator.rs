//! Ground Truth validation
//!
//! Validates benchmark results against expected baselines with configurable tolerance.

use crate::benchmark::ground_truth::{GroundTruth, ValidationStatus};
use crate::benchmark::result::BenchmarkResult;
use crate::benchmark::Tolerance;
use serde::{Deserialize, Serialize};

/// Validation severity
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum Severity {
    Critical, // >20% regression
    High,     // 10-20% regression
    Medium,   // 5-10% regression
    Low,      // Within tolerance but worth noting
}

/// Single validation violation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Violation {
    pub metric: String,
    pub expected: f64,
    pub actual: f64,
    pub diff_pct: f64,
    pub tolerance_pct: f64,
    pub severity: Severity,
}

/// Validation result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationResult {
    pub status: ValidationStatus,
    pub violations: Vec<Violation>,
    pub summary: String,
}

/// Ground Truth validator
pub struct GroundTruthValidator {
    pub tolerance: Tolerance,
}

impl GroundTruthValidator {
    pub fn new(tolerance: Tolerance) -> Self {
        Self { tolerance }
    }

    /// Validate benchmark result against ground truth
    pub fn validate(
        &self,
        result: &BenchmarkResult,
        ground_truth: &GroundTruth,
    ) -> ValidationResult {
        let mut violations = Vec::new();

        // 1. Duration check
        let duration_diff_pct = Self::pct_diff(
            ground_truth.expected.duration_sec,
            result.duration.as_secs_f64(),
        );
        if duration_diff_pct.abs() > self.tolerance.duration_pct {
            violations.push(Violation {
                metric: "duration".to_string(),
                expected: ground_truth.expected.duration_sec,
                actual: result.duration.as_secs_f64(),
                diff_pct: duration_diff_pct,
                tolerance_pct: self.tolerance.duration_pct,
                severity: Self::classify_severity(duration_diff_pct.abs()),
            });
        }

        // 2. Throughput check
        let throughput_diff_pct = Self::pct_diff(
            ground_truth.expected.throughput_loc_per_sec,
            result.throughput_loc_per_sec,
        );
        if throughput_diff_pct.abs() > self.tolerance.throughput_pct {
            violations.push(Violation {
                metric: "throughput".to_string(),
                expected: ground_truth.expected.throughput_loc_per_sec,
                actual: result.throughput_loc_per_sec,
                diff_pct: throughput_diff_pct,
                tolerance_pct: self.tolerance.throughput_pct,
                severity: Self::classify_severity(throughput_diff_pct.abs()),
            });
        }

        // 3. Memory check
        let memory_diff_pct = Self::pct_diff(ground_truth.expected.memory_mb, result.memory_mb);
        if memory_diff_pct.abs() > self.tolerance.memory_pct {
            violations.push(Violation {
                metric: "memory".to_string(),
                expected: ground_truth.expected.memory_mb,
                actual: result.memory_mb,
                diff_pct: memory_diff_pct,
                tolerance_pct: self.tolerance.memory_pct,
                severity: Self::classify_severity(memory_diff_pct.abs()),
            });
        }

        // 4. Deterministic metrics (exact match within tolerance)
        if result
            .total_nodes
            .abs_diff(ground_truth.expected.total_nodes)
            > self.tolerance.count_tolerance
        {
            violations.push(Violation {
                metric: "total_nodes".to_string(),
                expected: ground_truth.expected.total_nodes as f64,
                actual: result.total_nodes as f64,
                diff_pct: Self::pct_diff(
                    ground_truth.expected.total_nodes as f64,
                    result.total_nodes as f64,
                ),
                tolerance_pct: 0.0,
                severity: Severity::Critical,
            });
        }

        if result
            .total_edges
            .abs_diff(ground_truth.expected.total_edges)
            > self.tolerance.count_tolerance
        {
            violations.push(Violation {
                metric: "total_edges".to_string(),
                expected: ground_truth.expected.total_edges as f64,
                actual: result.total_edges as f64,
                diff_pct: Self::pct_diff(
                    ground_truth.expected.total_edges as f64,
                    result.total_edges as f64,
                ),
                tolerance_pct: 0.0,
                severity: Severity::Critical,
            });
        }

        if result
            .total_chunks
            .abs_diff(ground_truth.expected.total_chunks)
            > self.tolerance.count_tolerance
        {
            violations.push(Violation {
                metric: "total_chunks".to_string(),
                expected: ground_truth.expected.total_chunks as f64,
                actual: result.total_chunks as f64,
                diff_pct: Self::pct_diff(
                    ground_truth.expected.total_chunks as f64,
                    result.total_chunks as f64,
                ),
                tolerance_pct: 0.0,
                severity: Severity::Critical,
            });
        }

        if result
            .total_symbols
            .abs_diff(ground_truth.expected.total_symbols)
            > self.tolerance.count_tolerance
        {
            violations.push(Violation {
                metric: "total_symbols".to_string(),
                expected: ground_truth.expected.total_symbols as f64,
                actual: result.total_symbols as f64,
                diff_pct: Self::pct_diff(
                    ground_truth.expected.total_symbols as f64,
                    result.total_symbols as f64,
                ),
                tolerance_pct: 0.0,
                severity: Severity::Critical,
            });
        }

        // Determine overall status
        let status = if violations.is_empty() {
            ValidationStatus::Pass
        } else {
            ValidationStatus::Fail
        };

        // Generate summary
        let summary = if violations.is_empty() {
            "✅ All metrics within tolerance".to_string()
        } else {
            format!(
                "❌ {} violation(s) detected:\n{}",
                violations.len(),
                violations
                    .iter()
                    .map(|v| {
                        let sign = if v.diff_pct > 0.0 { "+" } else { "" };
                        format!(
                            "  - {}: {}{:.1}% (expected: {:.2}, actual: {:.2}, tolerance: ±{:.1}%)",
                            v.metric, sign, v.diff_pct, v.expected, v.actual, v.tolerance_pct
                        )
                    })
                    .collect::<Vec<_>>()
                    .join("\n")
            )
        };

        ValidationResult {
            status,
            violations,
            summary,
        }
    }

    fn pct_diff(expected: f64, actual: f64) -> f64 {
        ((actual - expected) / expected) * 100.0
    }

    fn classify_severity(diff_pct: f64) -> Severity {
        match diff_pct {
            d if d > 20.0 => Severity::Critical,
            d if d > 10.0 => Severity::High,
            d if d > 5.0 => Severity::Medium,
            _ => Severity::Low,
        }
    }
}
