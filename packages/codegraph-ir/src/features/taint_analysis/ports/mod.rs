/*
 * Taint Analysis Ports (Hexagonal Architecture)
 *
 * Ports define the boundaries between the domain/infrastructure and external world.
 *
 * Architecture:
 * ```
 *                    +-------------------------+
 *                    |     External World      |
 *                    |  (API, CLI, MCP, Tests) |
 *                    +------------+------------+
 *                                 |
 *                    +------------v------------+
 *                    |      Input Ports        | ← Driving adapters call these
 *                    | (TaintAnalysisService)  |
 *                    +------------+------------+
 *                                 |
 *                    +------------v------------+
 *                    |    Application Layer    |
 *                    |      (Use Cases)        |
 *                    +------------+------------+
 *                                 |
 *                    +------------v------------+
 *                    |     Domain Layer        |
 *                    |   (Business Logic)      |
 *                    +------------+------------+
 *                                 |
 *                    +------------v------------+
 *                    |     Output Ports        | ← Application calls these
 *                    | (Repositories, Clients) |
 *                    +------------+------------+
 *                                 |
 *                    +------------v------------+
 *                    |     Infrastructure      |
 *                    | (DB, Files, Networks)   |
 *                    +-------------------------+
 * ```
 */

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

use super::infrastructure::{BackwardTaintPath, ImplicitFlowVulnerability, TaintPath};
use crate::config::TaintConfig;
use crate::shared::models::Node;

// ============================================================================
// DTOs (Data Transfer Objects)
// ============================================================================

/// Request for taint analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaintAnalysisRequest {
    /// Source code or IR nodes to analyze
    pub code_path: String,

    /// Analysis configuration
    pub config: TaintAnalysisConfig,

    /// Source patterns to detect
    pub source_patterns: Vec<String>,

    /// Sink patterns to detect
    pub sink_patterns: Vec<String>,

    /// Sanitizer patterns (optional)
    pub sanitizer_patterns: Option<Vec<String>>,

    /// Analysis mode
    pub mode: AnalysisMode,
}

/// Analysis configuration
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TaintAnalysisConfig {
    /// Maximum analysis depth
    pub max_depth: Option<usize>,

    /// Enable interprocedural analysis
    pub interprocedural: bool,

    /// Enable context-sensitive analysis
    pub context_sensitive: bool,

    /// Enable field-sensitive analysis
    pub field_sensitive: bool,

    /// Enable path-sensitive analysis
    pub path_sensitive: bool,

    /// Enable implicit flow detection
    pub implicit_flow: bool,

    /// Enable backward analysis (sink → source)
    pub backward_analysis: bool,

    /// Timeout in seconds
    pub timeout_seconds: Option<u64>,
}

impl TaintAnalysisConfig {
    /// Convert to RFC-001 TaintConfig
    ///
    /// Maps ports layer config to the canonical RFC-001 configuration.
    /// This enables integration with the preset system (Fast/Balanced/Thorough).
    pub fn to_rfc001_config(&self) -> TaintConfig {
        // Start from default (Balanced preset)
        let mut config = TaintConfig::default();

        // Apply overrides from ports config
        if let Some(depth) = self.max_depth {
            config.max_depth = depth;
        }

        config.enable_interprocedural = self.interprocedural;
        config.context_sensitive = self.context_sensitive;
        config.field_sensitive = self.field_sensitive;
        config.path_sensitive = self.path_sensitive;
        config.implicit_flow_enabled = self.implicit_flow;
        config.backward_analysis_enabled = self.backward_analysis;

        if let Some(timeout) = self.timeout_seconds {
            config.timeout_seconds = timeout;
        }

        config
    }

    /// Create from RFC-001 TaintConfig
    ///
    /// Maps RFC-001 configuration to ports layer DTO.
    pub fn from_rfc001_config(config: &TaintConfig) -> Self {
        Self {
            max_depth: Some(config.max_depth),
            interprocedural: config.enable_interprocedural,
            context_sensitive: config.context_sensitive,
            field_sensitive: config.field_sensitive,
            path_sensitive: config.path_sensitive,
            implicit_flow: config.implicit_flow_enabled,
            backward_analysis: config.backward_analysis_enabled,
            timeout_seconds: Some(config.timeout_seconds),
        }
    }

    /// Create from preset
    pub fn from_preset(mode: AnalysisMode) -> Self {
        use crate::config::preset::Preset;

        let preset = match mode {
            AnalysisMode::Fast => Preset::Fast,
            AnalysisMode::Balanced => Preset::Balanced,
            AnalysisMode::Thorough => Preset::Thorough,
            AnalysisMode::Custom => return Self::default(),
        };

        Self::from_rfc001_config(&TaintConfig::from_preset(preset))
    }
}

/// Analysis mode
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum AnalysisMode {
    /// Fast analysis (less precise, quick results)
    Fast,

    /// Balanced analysis (default)
    #[default]
    Balanced,

    /// Thorough analysis (most precise, slower)
    Thorough,

    /// Custom configuration
    Custom,
}

/// Response from taint analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaintAnalysisResponse {
    /// Analysis successful
    pub success: bool,

    /// Forward taint paths (source → sink)
    pub forward_paths: Vec<TaintPathDTO>,

    /// Backward taint paths (sink → source)
    pub backward_paths: Vec<BackwardTaintPathDTO>,

    /// Implicit flow vulnerabilities
    pub implicit_flows: Vec<ImplicitFlowDTO>,

    /// Analysis statistics
    pub stats: AnalysisStats,

    /// Errors encountered (if any)
    pub errors: Vec<String>,
}

/// Simplified taint path for external communication
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaintPathDTO {
    pub source: String,
    pub sink: String,
    pub source_type: String,
    pub sink_type: String,
    pub path: Vec<String>,
    pub path_length: usize,
    pub is_sanitized: bool,
    pub sanitizers: Vec<String>,
    pub severity: String,
    pub vulnerability_type: String,
}

impl From<TaintPath> for TaintPathDTO {
    fn from(path: TaintPath) -> Self {
        Self {
            source: path.source.clone(),
            sink: path.sink.clone(),
            source_type: "external".to_string(),
            sink_type: "dangerous".to_string(),
            path: path.path.clone(),
            path_length: path.path.len(),
            is_sanitized: path.is_sanitized,
            sanitizers: vec![], // TaintPath doesn't have sanitizers field
            severity: format!("{:?}", path.severity),
            vulnerability_type: "taint_flow".to_string(),
        }
    }
}

/// Simplified backward taint path
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackwardTaintPathDTO {
    pub sink: String,
    pub source: String,
    pub sink_type: String,
    pub source_type: String,
    pub path: Vec<String>,
    pub path_length: usize,
    pub is_sanitized: bool,
    pub variable: String,
}

impl From<BackwardTaintPath> for BackwardTaintPathDTO {
    fn from(path: BackwardTaintPath) -> Self {
        Self {
            sink: path.sink,
            source: path.source,
            sink_type: path.sink_type,
            source_type: path.source_type,
            path: path.path,
            path_length: path.path_length,
            is_sanitized: path.is_sanitized,
            variable: path.variable,
        }
    }
}

/// Simplified implicit flow vulnerability
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImplicitFlowDTO {
    pub source_variable: String,
    pub sink_variable: String,
    pub control_dependency: String,
    pub severity: String,
    pub description: String,
}

impl From<ImplicitFlowVulnerability> for ImplicitFlowDTO {
    fn from(vuln: ImplicitFlowVulnerability) -> Self {
        Self {
            source_variable: vuln.source_variable.clone(),
            sink_variable: vuln.tainted_variable.clone(),
            control_dependency: vuln.condition_node.clone(),
            severity: format!("{:?}", vuln.severity),
            description: format!(
                "Implicit flow: {} -> {} via {}",
                vuln.source_variable, vuln.tainted_variable, vuln.sink_type
            ),
        }
    }
}

/// Analysis statistics
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AnalysisStats {
    pub nodes_analyzed: usize,
    pub edges_analyzed: usize,
    pub paths_found: usize,
    pub sanitized_paths: usize,
    pub implicit_flows_found: usize,
    pub analysis_time_ms: u64,
    pub memory_used_bytes: usize,
}

// ============================================================================
// Input Ports (Driving Ports)
// ============================================================================

/// Main input port for taint analysis
///
/// External adapters (API, CLI, MCP) implement this to drive the analysis.
#[async_trait]
pub trait TaintAnalysisService: Send + Sync {
    /// Analyze code for taint vulnerabilities
    async fn analyze(
        &self,
        request: TaintAnalysisRequest,
    ) -> Result<TaintAnalysisResponse, TaintAnalysisError>;

    /// Analyze specific file
    async fn analyze_file(
        &self,
        path: &str,
        config: TaintAnalysisConfig,
    ) -> Result<TaintAnalysisResponse, TaintAnalysisError>;

    /// Analyze IR nodes directly
    async fn analyze_ir(
        &self,
        nodes: Vec<Node>,
        config: TaintAnalysisConfig,
    ) -> Result<TaintAnalysisResponse, TaintAnalysisError>;

    /// Get supported source patterns
    fn supported_sources(&self) -> Vec<String>;

    /// Get supported sink patterns
    fn supported_sinks(&self) -> Vec<String>;

    /// Get supported sanitizer patterns
    fn supported_sanitizers(&self) -> Vec<String>;
}

/// Input port for differential taint analysis
#[async_trait]
pub trait DifferentialTaintService: Send + Sync {
    /// Compare two versions for taint changes
    async fn compare_versions(
        &self,
        old_version: &str,
        new_version: &str,
        config: TaintAnalysisConfig,
    ) -> Result<DifferentialResult, TaintAnalysisError>;

    /// Analyze git diff for security regressions
    async fn analyze_git_diff(
        &self,
        base_commit: &str,
        head_commit: &str,
    ) -> Result<DifferentialResult, TaintAnalysisError>;
}

/// Differential analysis result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DifferentialResult {
    pub new_vulnerabilities: Vec<TaintPathDTO>,
    pub fixed_vulnerabilities: Vec<TaintPathDTO>,
    pub modified_vulnerabilities: Vec<TaintPathDTO>,
    pub stats: DifferentialStats,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DifferentialStats {
    pub files_changed: usize,
    pub functions_changed: usize,
    pub new_count: usize,
    pub fixed_count: usize,
    pub modified_count: usize,
}

// ============================================================================
// Output Ports (Driven Ports)
// ============================================================================

/// Output port for persisting analysis results
#[async_trait]
pub trait TaintResultRepository: Send + Sync {
    /// Save analysis results
    async fn save_results(
        &self,
        results: &TaintAnalysisResponse,
    ) -> Result<String, TaintAnalysisError>;

    /// Load previous analysis results
    async fn load_results(&self, id: &str) -> Result<TaintAnalysisResponse, TaintAnalysisError>;

    /// List all saved results
    async fn list_results(&self) -> Result<Vec<String>, TaintAnalysisError>;

    /// Delete analysis results
    async fn delete_results(&self, id: &str) -> Result<(), TaintAnalysisError>;
}

/// Output port for accessing code/IR
#[async_trait]
pub trait CodeRepository: Send + Sync {
    /// Get IR nodes for a file
    async fn get_ir_nodes(&self, path: &str) -> Result<Vec<Node>, TaintAnalysisError>;

    /// Get IR nodes for a function
    async fn get_function_ir(&self, function_id: &str) -> Result<Vec<Node>, TaintAnalysisError>;

    /// List available files
    async fn list_files(&self, directory: &str) -> Result<Vec<String>, TaintAnalysisError>;
}

/// Output port for external notifications
#[async_trait]
pub trait TaintNotificationService: Send + Sync {
    /// Notify about new vulnerability
    async fn notify_vulnerability(&self, vuln: &TaintPathDTO) -> Result<(), TaintAnalysisError>;

    /// Send analysis report
    async fn send_report(&self, report: &TaintAnalysisResponse) -> Result<(), TaintAnalysisError>;
}

// ============================================================================
// Error Types
// ============================================================================

/// Error type for taint analysis operations
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaintAnalysisError {
    pub kind: TaintErrorKind,
    pub message: String,
    pub context: Option<String>,
}

impl TaintAnalysisError {
    pub fn new(kind: TaintErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
            context: None,
        }
    }

    pub fn with_context(mut self, context: impl Into<String>) -> Self {
        self.context = Some(context.into());
        self
    }

    pub fn not_found(message: impl Into<String>) -> Self {
        Self::new(TaintErrorKind::NotFound, message)
    }

    pub fn invalid_input(message: impl Into<String>) -> Self {
        Self::new(TaintErrorKind::InvalidInput, message)
    }

    pub fn analysis_failed(message: impl Into<String>) -> Self {
        Self::new(TaintErrorKind::AnalysisFailed, message)
    }

    pub fn timeout(message: impl Into<String>) -> Self {
        Self::new(TaintErrorKind::Timeout, message)
    }
}

impl std::fmt::Display for TaintAnalysisError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[{:?}] {}", self.kind, self.message)?;
        if let Some(ctx) = &self.context {
            write!(f, " (context: {})", ctx)?;
        }
        Ok(())
    }
}

impl std::error::Error for TaintAnalysisError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TaintErrorKind {
    NotFound,
    InvalidInput,
    AnalysisFailed,
    Timeout,
    StorageError,
    NetworkError,
    ConfigurationError,
    InternalError,
}

// ============================================================================
// Factory Functions
// ============================================================================

/// Create default analysis configuration
pub fn default_config() -> TaintAnalysisConfig {
    TaintAnalysisConfig {
        max_depth: Some(100),
        interprocedural: true,
        context_sensitive: true,
        field_sensitive: true,
        path_sensitive: false, // Off by default (expensive)
        implicit_flow: true,
        backward_analysis: false,   // Off by default
        timeout_seconds: Some(300), // 5 minutes
    }
}

/// Create fast analysis configuration
pub fn fast_config() -> TaintAnalysisConfig {
    TaintAnalysisConfig {
        max_depth: Some(50),
        interprocedural: true,
        context_sensitive: false,
        field_sensitive: false,
        path_sensitive: false,
        implicit_flow: false,
        backward_analysis: false,
        timeout_seconds: Some(60),
    }
}

/// Create thorough analysis configuration
pub fn thorough_config() -> TaintAnalysisConfig {
    TaintAnalysisConfig {
        max_depth: Some(200),
        interprocedural: true,
        context_sensitive: true,
        field_sensitive: true,
        path_sensitive: true,
        implicit_flow: true,
        backward_analysis: true,
        timeout_seconds: Some(1800), // 30 minutes
    }
}

/// Default source patterns
pub fn default_source_patterns() -> Vec<String> {
    vec![
        "user_input".to_string(),
        "request".to_string(),
        "get_param".to_string(),
        "read_file".to_string(),
        "network".to_string(),
        "environ".to_string(),
        "stdin".to_string(),
        "args".to_string(),
        "query".to_string(),
        "cookie".to_string(),
    ]
}

/// Default sink patterns
pub fn default_sink_patterns() -> Vec<String> {
    vec![
        "execute".to_string(),
        "exec".to_string(),
        "eval".to_string(),
        "query".to_string(),
        "sql".to_string(),
        "send".to_string(),
        "response".to_string(),
        "write".to_string(),
        "log".to_string(),
        "system".to_string(),
    ]
}

/// Default sanitizer patterns
pub fn default_sanitizer_patterns() -> Vec<String> {
    vec![
        "sanitize".to_string(),
        "escape".to_string(),
        "validate".to_string(),
        "clean".to_string(),
        "filter".to_string(),
        "encode".to_string(),
        "quote".to_string(),
    ]
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_taint_analysis_config_default() {
        let config = TaintAnalysisConfig::default();
        assert!(!config.interprocedural);
        assert!(!config.context_sensitive);
    }

    #[test]
    fn test_fast_config() {
        let config = fast_config();
        assert_eq!(config.max_depth, Some(50));
        assert!(!config.context_sensitive);
        assert!(!config.path_sensitive);
    }

    #[test]
    fn test_thorough_config() {
        let config = thorough_config();
        assert_eq!(config.max_depth, Some(200));
        assert!(config.context_sensitive);
        assert!(config.path_sensitive);
        assert!(config.implicit_flow);
    }

    #[test]
    fn test_default_patterns() {
        let sources = default_source_patterns();
        assert!(sources.contains(&"user_input".to_string()));

        let sinks = default_sink_patterns();
        assert!(sinks.contains(&"execute".to_string()));

        let sanitizers = default_sanitizer_patterns();
        assert!(sanitizers.contains(&"sanitize".to_string()));
    }

    #[test]
    fn test_analysis_mode_default() {
        let mode = AnalysisMode::default();
        assert_eq!(mode, AnalysisMode::Balanced);
    }

    #[test]
    fn test_taint_error_creation() {
        let error =
            TaintAnalysisError::not_found("File not found").with_context("path: /test/file.rs");

        assert_eq!(error.kind, TaintErrorKind::NotFound);
        assert!(error.message.contains("File not found"));
        assert!(error.context.unwrap().contains("path:"));
    }

    #[test]
    fn test_taint_error_display() {
        let error = TaintAnalysisError::analysis_failed("Failed to parse IR");
        let display = format!("{}", error);
        assert!(display.contains("AnalysisFailed"));
        assert!(display.contains("Failed to parse"));
    }

    #[test]
    fn test_analysis_stats_default() {
        let stats = AnalysisStats::default();
        assert_eq!(stats.nodes_analyzed, 0);
        assert_eq!(stats.paths_found, 0);
    }

    #[test]
    fn test_taint_analysis_request() {
        let request = TaintAnalysisRequest {
            code_path: "/test/path".to_string(),
            config: default_config(),
            source_patterns: default_source_patterns(),
            sink_patterns: default_sink_patterns(),
            sanitizer_patterns: Some(default_sanitizer_patterns()),
            mode: AnalysisMode::Balanced,
        };

        assert_eq!(request.code_path, "/test/path");
        assert!(request.config.interprocedural);
    }

    #[test]
    fn test_taint_analysis_response() {
        let response = TaintAnalysisResponse {
            success: true,
            forward_paths: vec![],
            backward_paths: vec![],
            implicit_flows: vec![],
            stats: AnalysisStats::default(),
            errors: vec![],
        };

        assert!(response.success);
        assert!(response.forward_paths.is_empty());
    }

    // ========================================================================
    // Edge Cases
    // ========================================================================

    #[test]
    fn test_error_kinds_exhaustive() {
        // Ensure all error kinds are distinct
        let kinds = vec![
            TaintErrorKind::NotFound,
            TaintErrorKind::InvalidInput,
            TaintErrorKind::AnalysisFailed,
            TaintErrorKind::Timeout,
            TaintErrorKind::StorageError,
            TaintErrorKind::NetworkError,
            TaintErrorKind::ConfigurationError,
            TaintErrorKind::InternalError,
        ];

        // All kinds should be distinct
        for (i, k1) in kinds.iter().enumerate() {
            for (j, k2) in kinds.iter().enumerate() {
                if i != j {
                    assert_ne!(k1, k2);
                }
            }
        }
    }

    #[test]
    fn test_taint_path_dto_fields() {
        let dto = TaintPathDTO {
            source: "src".to_string(),
            sink: "snk".to_string(),
            source_type: "user".to_string(),
            sink_type: "exec".to_string(),
            path: vec!["a".to_string(), "b".to_string()],
            path_length: 2,
            is_sanitized: false,
            sanitizers: vec![],
            severity: "high".to_string(),
            vulnerability_type: "injection".to_string(),
        };

        assert_eq!(dto.source, "src");
        assert_eq!(dto.sink, "snk");
        assert_eq!(dto.path_length, 2);
        assert!(!dto.is_sanitized);
    }

    #[test]
    fn test_backward_taint_path_dto() {
        let dto = BackwardTaintPathDTO {
            sink: "execute".to_string(),
            source: "input".to_string(),
            sink_type: "cmd".to_string(),
            source_type: "user".to_string(),
            path: vec!["a".to_string()],
            path_length: 1,
            is_sanitized: true,
            variable: "x".to_string(),
        };

        assert!(dto.is_sanitized);
        assert_eq!(dto.variable, "x");
    }

    #[test]
    fn test_implicit_flow_dto() {
        let dto = ImplicitFlowDTO {
            source_variable: "secret".to_string(),
            sink_variable: "public".to_string(),
            control_dependency: "if_secret".to_string(),
            severity: "High".to_string(),
            description: "Implicit leak".to_string(),
        };

        assert_eq!(dto.source_variable, "secret");
        assert_eq!(dto.control_dependency, "if_secret");
    }

    #[test]
    fn test_differential_result() {
        let result = DifferentialResult {
            new_vulnerabilities: vec![],
            fixed_vulnerabilities: vec![],
            modified_vulnerabilities: vec![],
            stats: DifferentialStats::default(),
        };

        assert!(result.new_vulnerabilities.is_empty());
        assert_eq!(result.stats.new_count, 0);
    }

    #[test]
    fn test_analysis_modes() {
        assert_eq!(AnalysisMode::Fast, AnalysisMode::Fast);
        assert_ne!(AnalysisMode::Fast, AnalysisMode::Thorough);
        assert_eq!(AnalysisMode::default(), AnalysisMode::Balanced);
    }

    #[test]
    fn test_config_preset_consistency() {
        let fast = fast_config();
        let default = default_config();
        let thorough = thorough_config();

        // Fast should be less thorough than default
        assert!(fast.max_depth < default.max_depth);

        // Thorough should be more thorough than default
        assert!(thorough.max_depth > default.max_depth);

        // Thorough enables all options
        assert!(thorough.path_sensitive);
        assert!(thorough.implicit_flow);
        assert!(thorough.backward_analysis);
    }

    #[test]
    fn test_error_context_chaining() {
        let error = TaintAnalysisError::not_found("File missing").with_context("path=/test");

        assert_eq!(error.kind, TaintErrorKind::NotFound);
        assert!(error.context.is_some());

        let display = format!("{}", error);
        assert!(display.contains("File missing"));
        assert!(display.contains("path=/test"));
    }

    // ========================================================================
    // Extreme Cases
    // ========================================================================

    #[test]
    fn test_large_source_pattern_list() {
        let patterns: Vec<String> = (0..1000).map(|i| format!("pattern_{}", i)).collect();

        assert_eq!(patterns.len(), 1000);
        assert!(patterns.contains(&"pattern_500".to_string()));
    }

    #[test]
    fn test_long_path_in_dto() {
        let long_path: Vec<String> = (0..10000).map(|i| format!("node_{}", i)).collect();

        let dto = TaintPathDTO {
            source: "src".to_string(),
            sink: "snk".to_string(),
            source_type: "t".to_string(),
            sink_type: "t".to_string(),
            path: long_path.clone(),
            path_length: long_path.len(),
            is_sanitized: false,
            sanitizers: vec![],
            severity: "high".to_string(),
            vulnerability_type: "test".to_string(),
        };

        assert_eq!(dto.path_length, 10000);
    }

    #[test]
    fn test_many_errors_in_response() {
        let errors: Vec<String> = (0..100).map(|i| format!("Error {}", i)).collect();

        let response = TaintAnalysisResponse {
            success: false,
            forward_paths: vec![],
            backward_paths: vec![],
            implicit_flows: vec![],
            stats: AnalysisStats::default(),
            errors,
        };

        assert!(!response.success);
        assert_eq!(response.errors.len(), 100);
    }

    #[test]
    fn test_unicode_in_patterns() {
        let sources = vec![
            "사용자입력".to_string(),
            "ユーザー入力".to_string(),
            "пользователь".to_string(),
        ];

        assert_eq!(sources.len(), 3);
        assert!(sources[0].contains("사용자"));
    }

    #[test]
    fn test_stats_overflow_safety() {
        let stats = AnalysisStats {
            nodes_analyzed: usize::MAX,
            edges_analyzed: usize::MAX,
            paths_found: usize::MAX,
            sanitized_paths: usize::MAX,
            implicit_flows_found: usize::MAX,
            analysis_time_ms: u64::MAX,
            memory_used_bytes: usize::MAX,
        };

        // Should not panic on max values
        assert_eq!(stats.nodes_analyzed, usize::MAX);
    }

    #[test]
    fn test_serialization_round_trip() {
        let config = default_config();
        let json = serde_json::to_string(&config).unwrap();
        let restored: TaintAnalysisConfig = serde_json::from_str(&json).unwrap();

        assert_eq!(config.max_depth, restored.max_depth);
        assert_eq!(config.interprocedural, restored.interprocedural);
    }
}
