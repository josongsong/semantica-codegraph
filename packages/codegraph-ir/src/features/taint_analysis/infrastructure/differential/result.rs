/*
 * Differential Taint Analysis Result Types
 *
 * Data structures for representing differential analysis results.
 */

use serde::{Deserialize, Serialize};
use std::collections::HashSet;

/// Severity levels for vulnerabilities
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Severity {
    /// Critical: Immediate security risk
    Critical,
    /// High: Significant security risk
    High,
    /// Medium: Moderate security risk
    Medium,
    /// Low: Minor security risk
    Low,
    /// Info: Informational finding
    Info,
}

impl Severity {
    /// Convert to string
    pub fn as_str(&self) -> &'static str {
        match self {
            Severity::Critical => "CRITICAL",
            Severity::High => "HIGH",
            Severity::Medium => "MEDIUM",
            Severity::Low => "LOW",
            Severity::Info => "INFO",
        }
    }

    /// Convert to uppercase string
    pub fn to_uppercase(&self) -> String {
        self.as_str().to_string()
    }
}

/// Vulnerability category
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum VulnerabilityCategory {
    /// New taint flow introduced
    TaintFlowIntroduced,
    /// Existing taint flow removed
    TaintFlowRemoved,
    /// Bypass path added
    BypassPathAdded,
    /// Sanitizer removed
    SanitizerRemoved,
    /// Sanitizer added
    SanitizerAdded,
    /// Other category
    Other(String),
}

impl VulnerabilityCategory {
    /// Convert to string representation
    pub fn as_str(&self) -> &str {
        match self {
            VulnerabilityCategory::TaintFlowIntroduced => "TaintFlowIntroduced",
            VulnerabilityCategory::TaintFlowRemoved => "TaintFlowRemoved",
            VulnerabilityCategory::BypassPathAdded => "BypassPathAdded",
            VulnerabilityCategory::SanitizerRemoved => "SanitizerRemoved",
            VulnerabilityCategory::SanitizerAdded => "SanitizerAdded",
            VulnerabilityCategory::Other(s) => s,
        }
    }
}

/// Taint source location
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TaintSource {
    /// Variable or expression name
    pub name: String,
    /// Source line number
    pub line: u32,
    /// Optional: Column number
    pub column: Option<u32>,
    /// Optional: File path
    pub file_path: Option<String>,
}

/// Taint sink location
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TaintSink {
    /// Sink function/method name
    pub name: String,
    /// Sink line number
    pub line: u32,
    /// Optional: Column number
    pub column: Option<u32>,
    /// Optional: File path
    pub file_path: Option<String>,
}

/// Vulnerability detected by differential analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Vulnerability {
    /// Unique identifier for tracking
    pub id: String,

    /// Severity level
    pub severity: Severity,

    /// Category of vulnerability
    pub category: VulnerabilityCategory,

    /// Taint source
    pub source: TaintSource,

    /// Taint sink
    pub sink: TaintSink,

    /// File path where vulnerability occurs
    pub file_path: String,

    /// Human-readable description
    pub description: String,

    /// Was this safe in the base version?
    pub safe_in_base: bool,

    /// Optional: Path condition (for path-sensitive analysis)
    pub path_condition: Option<String>,

    /// Confidence score (0.0-1.0)
    pub confidence: f64,
}

impl Vulnerability {
    /// Create new vulnerability with auto-generated ID
    pub fn new(
        severity: Severity,
        category: VulnerabilityCategory,
        source: TaintSource,
        sink: TaintSink,
        file_path: String,
        description: String,
    ) -> Self {
        // Generate ID from source, sink, and file
        let id = format!(
            "vuln-{}-{}-{}",
            file_path.replace(['/', '.', ' '], "-"),
            source.name,
            sink.name
        );
        Self {
            id,
            severity,
            category,
            source,
            sink,
            file_path,
            description,
            safe_in_base: false,
            path_condition: None,
            confidence: 1.0,
        }
    }

    /// Create vulnerability with explicit ID
    pub fn with_id(mut self, id: impl Into<String>) -> Self {
        self.id = id.into();
        self
    }

    /// Set safe_in_base flag
    pub fn with_safe_in_base(mut self, safe: bool) -> Self {
        self.safe_in_base = safe;
        self
    }

    /// Set path condition
    pub fn with_path_condition(mut self, condition: String) -> Self {
        self.path_condition = Some(condition);
        self
    }

    /// Set confidence
    pub fn with_confidence(mut self, confidence: f64) -> Self {
        self.confidence = confidence;
        self
    }
}

/// Information about a sanitizer (security control)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SanitizerInfo {
    /// Function name
    pub function_name: String,
    /// Line number
    pub line: usize,
    /// File path
    pub file_path: String,
}

/// Partially fixed vulnerability (some paths fixed, some remain)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PartialFix {
    /// Original vulnerability ID reference
    pub vulnerability_id: String,
    /// Original vulnerability (optional, for details)
    pub vulnerability: Option<Vulnerability>,
    /// Total number of attack paths
    pub total_paths: usize,
    /// Fixed paths count
    pub fixed_paths: usize,
    /// Remaining vulnerable paths count
    pub remaining_paths: usize,
    /// Description of partial fix
    pub description: String,
}

impl PartialFix {
    /// Create new partial fix
    pub fn new(vulnerability_id: String, total_paths: usize, fixed_paths: usize) -> Self {
        Self {
            vulnerability_id,
            vulnerability: None,
            total_paths,
            fixed_paths,
            remaining_paths: total_paths.saturating_sub(fixed_paths),
            description: String::new(),
        }
    }

    /// Add description
    pub fn with_description(mut self, desc: impl Into<String>) -> Self {
        self.description = desc.into();
        self
    }

    /// Add original vulnerability details
    pub fn with_vulnerability(mut self, vuln: Vulnerability) -> Self {
        self.vulnerability = Some(vuln);
        self
    }

    /// Calculate fix percentage
    pub fn fix_percentage(&self) -> f64 {
        if self.total_paths == 0 {
            100.0
        } else {
            (self.fixed_paths as f64 / self.total_paths as f64) * 100.0
        }
    }
}

/// Statistics about differential analysis
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DiffStats {
    /// Total files changed (from git diff)
    pub files_changed: usize,
    /// Total files analyzed (after filtering)
    pub files_analyzed: usize,
    /// Total lines of code analyzed
    pub lines_analyzed: usize,
    /// Base version vulnerabilities
    pub base_vulnerabilities: usize,
    /// Modified version vulnerabilities
    pub modified_vulnerabilities: usize,
    /// Analysis time (milliseconds)
    pub analysis_time_ms: u64,
}

/// Result of differential taint analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DifferentialTaintResult {
    /// Newly introduced vulnerabilities (not in base, present in modified)
    pub new_vulnerabilities: Vec<Vulnerability>,

    /// Fixed vulnerabilities (in base, not in modified)
    pub fixed_vulnerabilities: Vec<Vulnerability>,

    /// Removed sanitizers (security controls deleted)
    pub removed_sanitizers: Vec<SanitizerInfo>,

    /// Added sanitizers (security controls added)
    pub added_sanitizers: Vec<SanitizerInfo>,

    /// Partially fixed vulnerabilities (some paths fixed, some remain)
    pub partially_fixed: Vec<PartialFix>,

    /// Files affected by changes
    pub affected_files: Vec<String>,

    /// Statistics
    pub stats: DiffStats,
}

impl Default for DifferentialTaintResult {
    fn default() -> Self {
        Self {
            new_vulnerabilities: Vec::new(),
            fixed_vulnerabilities: Vec::new(),
            removed_sanitizers: Vec::new(),
            added_sanitizers: Vec::new(),
            partially_fixed: Vec::new(),
            affected_files: Vec::new(),
            stats: DiffStats::default(),
        }
    }
}

impl DifferentialTaintResult {
    /// Create new empty result
    pub fn new() -> Self {
        Self::default()
    }

    /// Calculate net regression count (new vulns - fixed vulns)
    pub fn regression_count(&self) -> i32 {
        self.new_vulnerabilities.len() as i32 - self.fixed_vulnerabilities.len() as i32
    }

    /// Check if any high-severity regressions exist
    pub fn has_high_severity_regression(&self) -> bool {
        self.new_vulnerabilities
            .iter()
            .any(|v| matches!(v.severity, Severity::High | Severity::Critical))
    }

    /// Generate summary report string
    pub fn summary(&self) -> String {
        format!(
            "New: {}, Fixed: {}, Net: {:+}",
            self.new_vulnerabilities.len(),
            self.fixed_vulnerabilities.len(),
            self.regression_count()
        )
    }

    /// Get all unique file paths affected
    pub fn affected_file_set(&self) -> HashSet<String> {
        self.affected_files.iter().cloned().collect()
    }

    /// Check if result indicates improvement (more fixes than regressions)
    pub fn is_improvement(&self) -> bool {
        self.regression_count() < 0
    }

    /// Check if result indicates regression
    pub fn is_regression(&self) -> bool {
        self.regression_count() > 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_severity_string() {
        assert_eq!(Severity::Critical.as_str(), "CRITICAL");
        assert_eq!(Severity::High.as_str(), "HIGH");
        assert_eq!(Severity::Medium.as_str(), "MEDIUM");
    }

    #[test]
    fn test_vulnerability_builder() {
        let vuln = Vulnerability::new(
            Severity::High,
            VulnerabilityCategory::TaintFlowIntroduced,
            TaintSource {
                name: "user_input".to_string(),
                line: 10,
                column: None,
                file_path: None,
            },
            TaintSink {
                name: "execute_sql".to_string(),
                line: 20,
                column: None,
                file_path: None,
            },
            "test.py".to_string(),
            "SQL injection".to_string(),
        )
        .with_safe_in_base(true)
        .with_confidence(0.95);

        assert_eq!(vuln.severity, Severity::High);
        assert!(vuln.safe_in_base);
        assert_eq!(vuln.confidence, 0.95);
    }

    #[test]
    fn test_regression_count() {
        let mut result = DifferentialTaintResult::new();
        assert_eq!(result.regression_count(), 0);

        result.new_vulnerabilities.push(Vulnerability::new(
            Severity::High,
            VulnerabilityCategory::TaintFlowIntroduced,
            TaintSource {
                name: "test".to_string(),
                line: 1,
                column: None,
                file_path: None,
            },
            TaintSink {
                name: "sink".to_string(),
                line: 2,
                column: None,
                file_path: None,
            },
            "test.py".to_string(),
            "Test".to_string(),
        ));

        assert_eq!(result.regression_count(), 1);
        assert!(result.is_regression());
        assert!(!result.is_improvement());
    }

    #[test]
    fn test_has_high_severity_regression() {
        let mut result = DifferentialTaintResult::new();
        assert!(!result.has_high_severity_regression());

        result.new_vulnerabilities.push(Vulnerability::new(
            Severity::High,
            VulnerabilityCategory::TaintFlowIntroduced,
            TaintSource {
                name: "test".to_string(),
                line: 1,
                column: None,
                file_path: None,
            },
            TaintSink {
                name: "sink".to_string(),
                line: 2,
                column: None,
                file_path: None,
            },
            "test.py".to_string(),
            "Test".to_string(),
        ));

        assert!(result.has_high_severity_regression());
    }

    #[test]
    fn test_summary() {
        let mut result = DifferentialTaintResult::new();
        result.new_vulnerabilities.push(Vulnerability::new(
            Severity::High,
            VulnerabilityCategory::TaintFlowIntroduced,
            TaintSource {
                name: "test".to_string(),
                line: 1,
                column: None,
                file_path: None,
            },
            TaintSink {
                name: "sink".to_string(),
                line: 2,
                column: None,
                file_path: None,
            },
            "test.py".to_string(),
            "Test".to_string(),
        ));

        let summary = result.summary();
        assert!(summary.contains("New: 1"));
        assert!(summary.contains("Fixed: 0"));
        assert!(summary.contains("Net: +1"));
    }
}
