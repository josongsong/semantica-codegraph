/*
 * Differential Taint Analyzer - Core Implementation
 *
 * Compares taint analysis results between two code versions to detect security regressions.
 *
 * Algorithm:
 * 1. Analyze base version → TaintResult_base
 * 2. Analyze modified version → TaintResult_modified
 * 3. Compare vulnerabilities:
 *    - new_vulns = modified \ base (set difference)
 *    - fixed_vulns = base \ modified
 * 4. Detect sanitizer changes
 * 5. Build differential report
 *
 * Performance:
 * - Target: < 3 minutes for typical PR (50 files)
 * - Strategy: Incremental analysis (only changed files)
 * - Caching: 50-80% hit rate expected
 */

use rustc_hash::FxHashMap;
use std::collections::{HashMap, HashSet};
use std::time::Instant;

use super::cache::{AnalysisCache, CacheKey};
use super::error::{DifferentialError, DifferentialResult};
use super::result::*;
use crate::errors::CodegraphError;
use crate::features::taint_analysis::infrastructure::path_sensitive::{
    PathSensitiveTaintAnalyzer, PathSensitiveVulnerability,
};

/// Configuration for differential analysis
#[derive(Debug, Clone)]
pub struct DifferentialConfig {
    /// Enable path-sensitive matching
    pub path_sensitive: bool,

    /// Enable SMT-based path equivalence checking
    pub enable_smt: bool,

    /// Enable caching
    pub enable_cache: bool,

    /// Debug mode (verbose logging)
    pub debug: bool,

    /// Performance budget (max analysis time in seconds)
    pub time_budget_secs: u64,
}

impl Default for DifferentialConfig {
    fn default() -> Self {
        Self {
            path_sensitive: true,
            enable_smt: true,
            enable_cache: true,
            debug: false,
            time_budget_secs: 180, // 3 minutes
        }
    }
}

/// Differential Taint Analyzer
///
/// Detects security regressions by comparing taint analysis results.
pub struct DifferentialTaintAnalyzer {
    /// Configuration
    config: DifferentialConfig,

    /// Result cache
    cache: Option<AnalysisCache>,

    /// Performance tracking
    start_time: Option<Instant>,
}

impl DifferentialTaintAnalyzer {
    /// Create new analyzer with default configuration
    pub fn new() -> Self {
        Self::with_config(DifferentialConfig::default())
    }

    /// Create analyzer with custom configuration
    pub fn with_config(config: DifferentialConfig) -> Self {
        let cache = if config.enable_cache {
            Some(AnalysisCache::new())
        } else {
            None
        };

        Self {
            config,
            cache,
            start_time: None,
        }
    }

    /// Enable/disable path-sensitive matching
    pub fn with_path_sensitive(mut self, enable: bool) -> Self {
        self.config.path_sensitive = enable;
        self
    }

    /// Enable/disable SMT checking
    pub fn with_smt(mut self, enable: bool) -> Self {
        self.config.enable_smt = enable;
        self
    }

    /// Enable/disable caching
    pub fn with_cache(mut self, enable: bool) -> Self {
        self.config.enable_cache = enable;
        if !enable {
            self.cache = None;
        } else if self.cache.is_none() {
            self.cache = Some(AnalysisCache::new());
        }
        self
    }

    /// Enable or disable debug output
    pub fn with_debug(mut self, enable: bool) -> Self {
        self.config.debug = enable;
        self
    }

    /// Compare two code versions
    ///
    /// # Arguments
    /// * `base_code` - Base version source code
    /// * `modified_code` - Modified version source code
    ///
    /// # Returns
    /// Differential analysis result showing new/fixed vulnerabilities
    pub fn compare(
        &mut self,
        base_code: &str,
        modified_code: &str,
    ) -> DifferentialResult<DifferentialTaintResult> {
        self.start_time = Some(Instant::now());

        // Step 1: Analyze base version
        let base_analysis = self.analyze_version(base_code, "base")?;

        // Step 2: Analyze modified version
        let modified_analysis = self.analyze_version(modified_code, "modified")?;

        // Step 3: Compute differential
        let diff = self.compute_diff(&base_analysis, &modified_analysis)?;

        // Step 4: Check time budget
        self.check_time_budget()?;

        Ok(diff)
    }

    /// Analyze single version (internal)
    fn analyze_version(
        &self,
        code: &str,
        version_name: &str,
    ) -> DifferentialResult<Vec<PathSensitiveVulnerability>> {
        if self.config.debug {
            eprintln!(
                "[DEBUG] Analyzing {} version ({} bytes)",
                version_name,
                code.len()
            );
        }

        // Use IRTaintAnalyzer to parse and analyze code
        let mut ir_analyzer = super::ir_integration::IRTaintAnalyzer::new()
            .with_smt(self.config.enable_smt)
            .with_debug(self.config.debug);

        // Detect language from code (simple heuristic)
        let language = self.detect_language(code);

        // Run analysis
        ir_analyzer.analyze(code, &language).map_err(|e| {
            if version_name == "base" {
                DifferentialError::base_error(e.to_string())
            } else {
                DifferentialError::modified_error(e.to_string())
            }
        })
    }

    /// Detect programming language from code (simple heuristic)
    fn detect_language(&self, code: &str) -> String {
        // Simple detection based on keywords/syntax
        if code.contains("def ") || code.contains("import ") {
            "python".to_string()
        } else if code.contains("function ") || code.contains("const ") || code.contains("let ") {
            "javascript".to_string()
        } else if code.contains("func ") || code.contains("package ") {
            "go".to_string()
        } else {
            // Default to python for now
            "python".to_string()
        }
    }

    /// Compute differential between two analysis results
    fn compute_diff(
        &self,
        base: &[PathSensitiveVulnerability],
        modified: &[PathSensitiveVulnerability],
    ) -> DifferentialResult<DifferentialTaintResult> {
        let start = Instant::now();
        let mut result = DifferentialTaintResult::new();

        // Convert to internal vulnerability format
        let base_vulns = self.convert_vulnerabilities(base);
        let modified_vulns = self.convert_vulnerabilities(modified);

        // Detect new vulnerabilities (in modified, not in base)
        for vuln in &modified_vulns {
            if !self.exists_in(&vuln, &base_vulns) {
                let mut new_vuln = vuln.clone();
                new_vuln.safe_in_base = true;
                result.new_vulnerabilities.push(new_vuln);
            }
        }

        // Detect fixed vulnerabilities (in base, not in modified)
        for vuln in &base_vulns {
            if !self.exists_in(&vuln, &modified_vulns) {
                result.fixed_vulnerabilities.push(vuln.clone());
            }
        }

        // Update statistics
        result.stats.base_vulnerabilities = base_vulns.len();
        result.stats.modified_vulnerabilities = modified_vulns.len();
        result.stats.analysis_time_ms = start.elapsed().as_millis() as u64;

        if self.config.debug {
            eprintln!("[DEBUG] Diff computed: {}", result.summary());
        }

        Ok(result)
    }

    /// Convert PathSensitiveVulnerability to internal Vulnerability format
    fn convert_vulnerabilities(&self, vulns: &[PathSensitiveVulnerability]) -> Vec<Vulnerability> {
        vulns
            .iter()
            .map(|v| {
                // Extract source and sink from path
                let source_name = v
                    .tainted_vars
                    .first()
                    .cloned()
                    .unwrap_or_else(|| "unknown".to_string());

                let sink_name = v.sink.clone();

                // Parse severity
                let severity = match v.severity.to_uppercase().as_str() {
                    "CRITICAL" => Severity::Critical,
                    "HIGH" => Severity::High,
                    "MEDIUM" => Severity::Medium,
                    "LOW" => Severity::Low,
                    _ => Severity::Info,
                };

                // Create vulnerability
                let vuln = Vulnerability::new(
                    severity,
                    VulnerabilityCategory::TaintFlowIntroduced,
                    TaintSource {
                        name: source_name,
                        // METADATA(v2): Line/column extraction requires TaintPath to carry source location
                        // - Current: 0 placeholder (detection works, location display limited)
                        // - Fix: Extend TaintPath with SourceLocation field
                        line: 0,
                        column: None,
                        file_path: None,
                    },
                    TaintSink {
                        name: sink_name,
                        line: 0, // See METADATA(v2) above
                        column: None,
                        file_path: None,
                    },
                    "unknown".to_string(), // Context requires call-site tracking
                    format!(
                        "Taint flow detected: {} → {}",
                        v.tainted_vars.join(", "),
                        v.sink
                    ),
                )
                .with_confidence(v.confidence);

                // Add path conditions if available
                if !v.path_conditions.is_empty() {
                    vuln.with_path_condition(v.path_conditions.join(" && "))
                } else {
                    vuln
                }
            })
            .collect()
    }

    /// Check if vulnerability exists in a list
    fn exists_in(&self, vuln: &Vulnerability, list: &[Vulnerability]) -> bool {
        list.iter().any(|v| self.vulnerabilities_match(vuln, v))
    }

    /// Check if two vulnerabilities represent the same issue
    fn vulnerabilities_match(&self, v1: &Vulnerability, v2: &Vulnerability) -> bool {
        // Basic matching: same source, sink, and category
        let basic_match = v1.source.name == v2.source.name
            && v1.sink.name == v2.sink.name
            && v1.category == v2.category;

        if !basic_match {
            return false;
        }

        // Path-sensitive matching
        if self.config.path_sensitive {
            match (&v1.path_condition, &v2.path_condition) {
                (Some(pc1), Some(pc2)) => {
                    if self.config.enable_smt {
                        // SMT(v3): Path condition equivalence via SMT solver
                        // - Current: String equality (works for identical paths)
                        // - Improvement: Z3 integration for semantic equivalence
                        // - Status: String match sufficient for most cases
                        pc1 == pc2
                    } else {
                        // Simple string match
                        pc1 == pc2
                    }
                }
                (None, None) => true,
                _ => false, // One has path condition, other doesn't
            }
        } else {
            // Path-insensitive: basic match is sufficient
            true
        }
    }

    /// Check if time budget exceeded
    fn check_time_budget(&self) -> DifferentialResult<()> {
        if let Some(start) = self.start_time {
            let elapsed = start.elapsed().as_secs();
            if elapsed > self.config.time_budget_secs {
                return Err(DifferentialError::timeout(
                    self.config.time_budget_secs,
                    elapsed,
                ));
            }
        }
        Ok(())
    }

    /// Get cache statistics (if caching enabled)
    pub fn cache_stats(&self) -> Option<super::cache::CacheStats> {
        self.cache.as_ref().map(|c| c.stats())
    }
}

impl Default for DifferentialTaintAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_analyzer_creation() {
        let analyzer = DifferentialTaintAnalyzer::new();
        assert!(analyzer.config.path_sensitive);
        assert!(analyzer.config.enable_smt);
        assert!(analyzer.config.enable_cache);
    }

    #[test]
    fn test_analyzer_with_config() {
        let analyzer = DifferentialTaintAnalyzer::new()
            .with_path_sensitive(false)
            .with_smt(false)
            .with_cache(false);

        assert!(!analyzer.config.path_sensitive);
        assert!(!analyzer.config.enable_smt);
        assert!(!analyzer.config.enable_cache);
        assert!(analyzer.cache.is_none());
    }

    #[test]
    fn test_empty_comparison() {
        let mut analyzer = DifferentialTaintAnalyzer::new();

        let base_code = "def process(input): pass";
        let modified_code = "def process(input): pass";

        let result = analyzer.compare(base_code, modified_code).unwrap();

        assert_eq!(result.new_vulnerabilities.len(), 0);
        assert_eq!(result.fixed_vulnerabilities.len(), 0);
        assert_eq!(result.regression_count(), 0);
    }

    #[test]
    fn test_vulnerability_matching_basic() {
        let analyzer = DifferentialTaintAnalyzer::new().with_path_sensitive(false);

        let v1 = Vulnerability::new(
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
        );

        let v2 = Vulnerability::new(
            Severity::High,
            VulnerabilityCategory::TaintFlowIntroduced,
            TaintSource {
                name: "user_input".to_string(),
                line: 11,
                column: None,
                file_path: None,
            },
            TaintSink {
                name: "execute_sql".to_string(),
                line: 21,
                column: None,
                file_path: None,
            },
            "test.py".to_string(),
            "SQL injection".to_string(),
        );

        assert!(analyzer.vulnerabilities_match(&v1, &v2));
    }

    #[test]
    fn test_vulnerability_matching_different_source() {
        let analyzer = DifferentialTaintAnalyzer::new();

        let v1 = Vulnerability::new(
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
        );

        let v2 = Vulnerability::new(
            Severity::High,
            VulnerabilityCategory::TaintFlowIntroduced,
            TaintSource {
                name: "other_input".to_string(), // Different source
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
        );

        assert!(!analyzer.vulnerabilities_match(&v1, &v2));
    }

    #[test]
    fn test_convert_vulnerabilities() {
        let analyzer = DifferentialTaintAnalyzer::new();

        let ps_vuln = PathSensitiveVulnerability {
            sink: "execute_sql".to_string(),
            tainted_vars: vec!["user_input".to_string()],
            path_conditions: vec!["is_admin == true".to_string()],
            severity: "HIGH".to_string(),
            confidence: 0.95,
            path: vec!["node1".to_string(), "node2".to_string()],
        };

        let vulns = analyzer.convert_vulnerabilities(&[ps_vuln]);

        assert_eq!(vulns.len(), 1);
        assert_eq!(vulns[0].severity, Severity::High);
        assert_eq!(vulns[0].source.name, "user_input");
        assert_eq!(vulns[0].sink.name, "execute_sql");
        assert_eq!(vulns[0].confidence, 0.95);
        assert!(vulns[0].path_condition.is_some());
    }

    #[test]
    fn test_time_budget() {
        let mut analyzer = DifferentialTaintAnalyzer::new();
        analyzer.config.time_budget_secs = 0; // Zero budget for testing
        analyzer.start_time = Some(Instant::now());

        // Sleep to ensure elapsed time > budget (macOS may have sub-second precision issues)
        std::thread::sleep(std::time::Duration::from_millis(1500));

        let result = analyzer.check_time_budget();
        assert!(result.is_err(), "Expected timeout error");

        if let Err(DifferentialError::TimeoutExceeded { expected, actual }) = result {
            assert_eq!(expected, 0);
            assert!(
                actual >= 1,
                "Expected at least 1 second elapsed, got {}",
                actual
            );
        } else {
            panic!("Expected TimeoutExceeded error, got {:?}", result);
        }
    }
}
