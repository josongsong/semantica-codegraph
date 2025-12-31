// TaintQueryBuilder - Specialized queries for taint analysis
//
// Provides fluent API for taint flow queries:
// - Filter by vulnerability type (CWE-89, CWE-79, etc.)
// - Filter by severity (Critical, High, Medium, Low)
// - Filter by confidence threshold
// - Get source/sink nodes

use crate::features::ir_generation::domain::ir_document::IRDocument;
use crate::features::query_engine::infrastructure::GraphIndex;

/// Taint flow severity
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Severity {
    Critical,
    High,
    Medium,
    Low,
    Info,
}

impl Severity {
    pub fn as_str(&self) -> &'static str {
        match self {
            Severity::Critical => "critical",
            Severity::High => "high",
            Severity::Medium => "medium",
            Severity::Low => "low",
            Severity::Info => "info",
        }
    }
}

/// Taint flow result
#[derive(Debug, Clone)]
pub struct TaintFlow {
    pub source_id: String,
    pub sink_id: String,
    pub vulnerability_type: String,  // e.g., "CWE-89", "CWE-79"
    pub severity: Severity,
    pub confidence: f64,
    pub path: Vec<String>,  // Node IDs in path
    pub sanitizers: Vec<String>,  // Sanitizer node IDs
}

/// TaintQueryBuilder - Fluent API for taint flow queries
///
/// Example:
/// ```no_run
/// let flows = engine.query()
///     .taint_flows()
///     .vulnerability_type("CWE-89")
///     .severity(Severity::Critical)
///     .min_confidence(0.8)
///     .execute()?;
///
/// for flow in flows {
///     println!("Found {} flow: {} -> {}",
///         flow.vulnerability_type,
///         flow.source_id,
///         flow.sink_id
///     );
/// }
/// ```
pub struct TaintQueryBuilder<'a> {
    index: &'a GraphIndex,
    ir_doc: &'a IRDocument,

    // Filters
    vuln_type_filter: Option<String>,
    severity_filter: Option<Severity>,
    min_confidence: Option<f64>,
    source_pattern: Option<String>,
    sink_pattern: Option<String>,

    // Pagination
    limit: Option<usize>,
}

impl<'a> TaintQueryBuilder<'a> {
    /// Create new TaintQueryBuilder
    pub fn new(index: &'a GraphIndex, ir_doc: &'a IRDocument) -> Self {
        Self {
            index,
            ir_doc,
            vuln_type_filter: None,
            severity_filter: None,
            min_confidence: None,
            source_pattern: None,
            sink_pattern: None,
            limit: None,
        }
    }

    /// Filter by vulnerability type (CWE ID)
    ///
    /// Example:
    /// ```no_run
    /// .vulnerability_type("CWE-89")  // SQL injection
    /// .vulnerability_type("CWE-79")  // XSS
    /// ```
    pub fn vulnerability_type(mut self, vuln_type: &str) -> Self {
        self.vuln_type_filter = Some(vuln_type.to_string());
        self
    }

    /// Filter by minimum severity
    ///
    /// Example:
    /// ```no_run
    /// .severity(Severity::Critical)  // Only critical
    /// .severity(Severity::High)      // High and above
    /// ```
    pub fn severity(mut self, severity: Severity) -> Self {
        self.severity_filter = Some(severity);
        self
    }

    /// Filter by minimum confidence threshold
    ///
    /// Example:
    /// ```no_run
    /// .min_confidence(0.8)  // Only flows with confidence >= 0.8
    /// ```
    pub fn min_confidence(mut self, confidence: f64) -> Self {
        self.min_confidence = Some(confidence);
        self
    }

    /// Filter by source pattern
    ///
    /// Example:
    /// ```no_run
    /// .from_source("user_input")
    /// .from_source("request.get")
    /// ```
    pub fn from_source(mut self, pattern: &str) -> Self {
        self.source_pattern = Some(pattern.to_string());
        self
    }

    /// Filter by sink pattern
    ///
    /// Example:
    /// ```no_run
    /// .to_sink("execute")
    /// .to_sink("eval")
    /// ```
    pub fn to_sink(mut self, pattern: &str) -> Self {
        self.sink_pattern = Some(pattern.to_string());
        self
    }

    /// Limit number of results
    pub fn limit(mut self, limit: usize) -> Self {
        self.limit = Some(limit);
        self
    }

    /// Execute query and return taint flows
    ///
    /// ## Integration Guide
    /// Use `AnalyzeTaintUseCase` from `taint_analysis::application`:
    /// ```ignore
    /// use crate::features::taint_analysis::application::AnalyzeTaintUseCase;
    /// let use_case = AnalyzeTaintUseCase::new(config);
    /// let result = use_case.execute(nodes, edges)?;
    /// ```
    ///
    /// See: `taint_analysis/application/mod.rs` (25,097 LOC)
    pub fn execute(self) -> Result<Vec<TaintFlow>, String> {
        // INTEGRATION PENDING: Connect to AnalyzeTaintUseCase
        // Impl exists at: taint_analysis::application::AnalyzeTaintUseCase
        Ok(Vec::new())
    }

    /// Get all sources for this query
    ///
    /// Example:
    /// ```no_run
    /// let sources = engine.query()
    ///     .taint_flows()
    ///     .vulnerability_type("CWE-89")
    ///     .get_sources()?;
    /// ```
    pub fn get_sources(self) -> Result<Vec<String>, String> {
        // INTEGRATION PENDING: Use taint_analysis::domain::TaintSource
        Ok(Vec::new())
    }

    /// Get all sinks for this query
    ///
    /// Example:
    /// ```no_run
    /// let sinks = engine.query()
    ///     .taint_flows()
    ///     .vulnerability_type("CWE-89")
    ///     .get_sinks()?;
    /// ```
    pub fn get_sinks(self) -> Result<Vec<String>, String> {
        // INTEGRATION PENDING: Use taint_analysis::domain::TaintSink
        Ok(Vec::new())
    }
}

/// Helper methods for common taint queries
impl<'a> TaintQueryBuilder<'a> {
    /// Get SQL injection flows
    ///
    /// Example:
    /// ```no_run
    /// let sql_injections = engine.query()
    ///     .taint_flows()
    ///     .sql_injection()
    ///     .execute()?;
    /// ```
    pub fn sql_injection(self) -> Self {
        self.vulnerability_type("CWE-89")
    }

    /// Get XSS flows
    ///
    /// Example:
    /// ```no_run
    /// let xss_flows = engine.query()
    ///     .taint_flows()
    ///     .xss()
    ///     .execute()?;
    /// ```
    pub fn xss(self) -> Self {
        self.vulnerability_type("CWE-79")
    }

    /// Get command injection flows
    ///
    /// Example:
    /// ```no_run
    /// let cmd_injections = engine.query()
    ///     .taint_flows()
    ///     .command_injection()
    ///     .execute()?;
    /// ```
    pub fn command_injection(self) -> Self {
        self.vulnerability_type("CWE-78")
    }

    /// Get path traversal flows
    ///
    /// Example:
    /// ```no_run
    /// let path_traversals = engine.query()
    ///     .taint_flows()
    ///     .path_traversal()
    ///     .execute()?;
    /// ```
    pub fn path_traversal(self) -> Self {
        self.vulnerability_type("CWE-22")
    }

    /// Get only critical severity flows
    ///
    /// Example:
    /// ```no_run
    /// let critical = engine.query()
    ///     .taint_flows()
    ///     .critical_only()
    ///     .execute()?;
    /// ```
    pub fn critical_only(self) -> Self {
        self.severity(Severity::Critical)
    }

    /// Get high severity and above
    pub fn high_severity_and_above(self) -> Self {
        self.severity(Severity::High)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::ir_generation::domain::ir_document::IRDocument;
    use crate::features::query_engine::infrastructure::GraphIndex;

    #[test]
    fn test_taint_query_builder_creation() {
        let doc = IRDocument::new("test.py".to_string());
        let index = GraphIndex::new(&doc);
        let _builder = TaintQueryBuilder::new(&index, &doc);
    }

    #[test]
    fn test_taint_query_filters() {
        let doc = IRDocument::new("test.py".to_string());
        let index = GraphIndex::new(&doc);
        let builder = TaintQueryBuilder::new(&index, &doc);

        let _query = builder
            .vulnerability_type("CWE-89")
            .severity(Severity::Critical)
            .min_confidence(0.8)
            .from_source("user_input")
            .to_sink("execute");

        // Should compile and chain correctly
    }

    #[test]
    fn test_sql_injection_helper() {
        let doc = IRDocument::new("test.py".to_string());
        let index = GraphIndex::new(&doc);
        let builder = TaintQueryBuilder::new(&index, &doc);

        let _query = builder
            .sql_injection()
            .critical_only()
            .min_confidence(0.9);

        // Should compile
    }

    #[test]
    fn test_severity_ordering() {
        assert!(Severity::Critical > Severity::High);
        assert!(Severity::High > Severity::Medium);
        assert!(Severity::Medium > Severity::Low);
        assert!(Severity::Low > Severity::Info);
    }

    #[test]
    fn test_severity_as_str() {
        assert_eq!(Severity::Critical.as_str(), "critical");
        assert_eq!(Severity::High.as_str(), "high");
        assert_eq!(Severity::Medium.as_str(), "medium");
        assert_eq!(Severity::Low.as_str(), "low");
        assert_eq!(Severity::Info.as_str(), "info");
    }
}
