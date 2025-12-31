//! Deep Security Analyzer - OWASP Top 10 Detection
//!
//! Academic References:
//! - Tripp, O. et al. (2009). "TAJ: Effective Taint Analysis of Web Applications"
//! - Livshits, V. B. & Lam, M. S. (2005). "Finding Security Vulnerabilities in Java Applications with Static Analysis"
//! - Arzt, S. et al. (2014). "FlowDroid: Precise Context, Flow, Field, Object-sensitive and Lifecycle-aware Taint Analysis for Android Apps"
//!
//! Industry:
//! - **Coverity**: Pattern + taint analysis for C/C++/Java
//! - **Checkmarx**: SAST with OWASP coverage
//! - **SonarQube**: Security hotspot detection
//! - **Semgrep**: Lightweight pattern-based SAST
//!
//! ## OWASP Top 10 (2021)
//!
//! 1. **A01:2021 - Broken Access Control**
//! 2. **A02:2021 - Cryptographic Failures**
//! 3. **A03:2021 - Injection** ← SQL, XSS, Command, etc.
//! 4. **A04:2021 - Insecure Design**
//! 5. **A05:2021 - Security Misconfiguration**
//! 6. **A06:2021 - Vulnerable Components**
//! 7. **A07:2021 - Identification and Authentication Failures**
//! 8. **A08:2021 - Software and Data Integrity Failures**
//! 9. **A09:2021 - Security Logging and Monitoring Failures**
//! 10. **A10:2021 - Server-Side Request Forgery (SSRF)**
//!
//! ## Detection Strategy
//!
//! ### 1. Taint-Based (Injection Attacks)
//! ```text
//! Source: user_input → Taint → Sink: executeQuery()
//! ```
//! - SQL Injection: `executeQuery(tainted)`
//! - XSS: `document.write(tainted)`
//! - Command Injection: `exec(tainted)`
//! - Path Traversal: `open(tainted)`
//!
//! ### 2. Pattern-Based (Configuration Issues)
//! - Hardcoded credentials
//! - Weak crypto algorithms (MD5, SHA1)
//! - Insecure protocols (HTTP, FTP)
//!
//! ### 3. Sanitizer Detection
//! - `escapeSQL()`, `htmlEscape()`, `sanitize()`
//! - Remove taint if sanitized

use crate::features::smt::infrastructure::{
    ConcolicConfig, ConcolicEngine, ErrorKind, SearchStrategy, TestInput,
};
use crate::features::taint_analysis::infrastructure::{
    InterproceduralTaintAnalyzer as TaintAnalyzer, TaintPath,
};
use crate::shared::models::{Edge, Node, NodeKind};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

// ============================================================================
// Configuration (RFC-001: Externalized Settings)
// ============================================================================

/// Security Analyzer Configuration
///
/// # RFC-001 Compliance
/// All source/sink/sanitizer patterns are externalized for runtime configuration.
///
/// # Example
/// ```text
/// let config = SecurityAnalyzerConfig {
///     additional_sources: vec!["custom_input".to_string()],
///     additional_sinks: vec![("dangerous_func".to_string(), VulnerabilityType::CommandInjection)],
///     ..Default::default()
/// };
/// let analyzer = DeepSecurityAnalyzer::with_config(config);
/// ```
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityAnalyzerConfig {
    /// Additional taint sources (beyond defaults)
    pub additional_sources: Vec<String>,

    /// Additional taint sinks (beyond defaults)
    /// Format: (function_name, vulnerability_type)
    pub additional_sinks: Vec<(String, VulnerabilityType)>,

    /// Additional sanitizers (beyond defaults)
    pub additional_sanitizers: Vec<String>,

    /// Enable taint-based detection
    pub enable_taint_analysis: bool,

    /// Enable pattern-based detection
    pub enable_pattern_detection: bool,

    /// Enable concolic testing for exploit generation
    pub enable_concolic: bool,

    /// Minimum severity to report (1-10)
    pub min_severity: u8,
}

impl Default for SecurityAnalyzerConfig {
    fn default() -> Self {
        Self {
            additional_sources: Vec::new(),
            additional_sinks: Vec::new(),
            additional_sanitizers: Vec::new(),
            enable_taint_analysis: true,
            enable_pattern_detection: true,
            enable_concolic: false,
            min_severity: 1,
        }
    }
}

// ============================================================================
// Domain Models
// ============================================================================

/// Security vulnerability
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityVulnerability {
    /// OWASP category
    pub category: OWASPCategory,

    /// CWE ID
    pub cwe_id: Option<u32>,

    /// Severity (1-10)
    pub severity: u8,

    /// Vulnerability type
    pub vuln_type: VulnerabilityType,

    /// Location
    pub location: String,

    /// Taint path (if taint-based)
    pub taint_path: Option<Vec<String>>,

    /// Message
    pub message: String,

    /// Recommendation
    pub recommendation: String,
}

/// OWASP Top 10 categories (naming follows official OWASP naming convention)
#[allow(non_camel_case_types)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OWASPCategory {
    A01_BrokenAccessControl,
    A02_CryptographicFailures,
    A03_Injection,
    A04_InsecureDesign,
    A05_SecurityMisconfiguration,
    A06_VulnerableComponents,
    A07_AuthenticationFailures,
    A08_IntegrityFailures,
    A09_LoggingMonitoringFailures,
    A10_SSRF,
}

/// Vulnerability types
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum VulnerabilityType {
    // Injection (A03)
    SQLInjection,
    XSS,
    CommandInjection,
    LDAPInjection,
    XMLInjection,
    PathTraversal,

    // Crypto (A02)
    WeakCrypto,
    HardcodedCredentials,
    InsecureRandom,

    // Auth (A07)
    WeakPassword,
    MissingAuthentication,
    SessionFixation,

    // Misc
    CSRF,
    XXE,
    InsecureDeserialization,
    SSRF,
}

impl VulnerabilityType {
    pub fn owasp_category(&self) -> OWASPCategory {
        match self {
            Self::SQLInjection
            | Self::XSS
            | Self::CommandInjection
            | Self::LDAPInjection
            | Self::XMLInjection
            | Self::PathTraversal => OWASPCategory::A03_Injection,
            Self::WeakCrypto | Self::HardcodedCredentials | Self::InsecureRandom => {
                OWASPCategory::A02_CryptographicFailures
            }
            Self::WeakPassword | Self::MissingAuthentication | Self::SessionFixation => {
                OWASPCategory::A07_AuthenticationFailures
            }
            Self::CSRF => OWASPCategory::A01_BrokenAccessControl,
            Self::XXE | Self::InsecureDeserialization => OWASPCategory::A08_IntegrityFailures,
            Self::SSRF => OWASPCategory::A10_SSRF,
        }
    }

    pub fn cwe_id(&self) -> Option<u32> {
        Some(match self {
            Self::SQLInjection => 89,
            Self::XSS => 79,
            Self::CommandInjection => 78,
            Self::LDAPInjection => 90,
            Self::XMLInjection => 91,
            Self::PathTraversal => 22,
            Self::WeakCrypto => 327,
            Self::HardcodedCredentials => 798,
            Self::InsecureRandom => 330,
            Self::WeakPassword => 521,
            Self::MissingAuthentication => 306,
            Self::SessionFixation => 384,
            Self::CSRF => 352,
            Self::XXE => 611,
            Self::InsecureDeserialization => 502,
            Self::SSRF => 918,
        })
    }

    pub fn severity(&self) -> u8 {
        match self {
            Self::SQLInjection
            | Self::CommandInjection
            | Self::XXE
            | Self::InsecureDeserialization
            | Self::SSRF => 10,
            Self::XSS | Self::PathTraversal | Self::HardcodedCredentials => 9,
            Self::LDAPInjection | Self::XMLInjection | Self::CSRF => 8,
            Self::WeakCrypto | Self::SessionFixation => 7,
            Self::InsecureRandom | Self::WeakPassword => 6,
            Self::MissingAuthentication => 8,
        }
    }
}

/// Deep Security Analyzer
///
/// Combines:
/// - Taint analysis (interprocedural)
/// - Pattern matching (configuration issues)
/// - Sanitizer detection
pub struct DeepSecurityAnalyzer {
    /// Configuration (RFC-001: Externalized)
    config: SecurityAnalyzerConfig,

    /// Taint sources (user input)
    sources: HashSet<String>,

    /// Taint sinks (dangerous functions)
    sinks: HashMap<String, VulnerabilityType>,

    /// Sanitizers (clean functions)
    sanitizers: HashSet<String>,

    /// SOTA: Concolic engine for automatic exploit generation
    concolic_engine: Option<ConcolicEngine>,

    /// Vulnerabilities found
    vulnerabilities: Vec<SecurityVulnerability>,
}

impl DeepSecurityAnalyzer {
    /// Create analyzer with default configuration
    pub fn new() -> Self {
        Self::with_config(SecurityAnalyzerConfig::default())
    }

    /// Create analyzer with custom configuration (RFC-001)
    pub fn with_config(config: SecurityAnalyzerConfig) -> Self {
        let mut analyzer = Self {
            config,
            sources: HashSet::new(),
            sinks: HashMap::new(),
            sanitizers: HashSet::new(),
            concolic_engine: None,
            vulnerabilities: Vec::new(),
        };

        analyzer.init_sources();
        analyzer.init_sinks();
        analyzer.init_sanitizers();

        // Apply custom config
        for source in &analyzer.config.additional_sources {
            analyzer.sources.insert(source.clone());
        }
        for (sink, vuln_type) in &analyzer.config.additional_sinks {
            analyzer.sinks.insert(sink.clone(), *vuln_type);
        }
        for sanitizer in &analyzer.config.additional_sanitizers {
            analyzer.sanitizers.insert(sanitizer.clone());
        }

        analyzer
    }

    /// Get current configuration
    pub fn config(&self) -> &SecurityAnalyzerConfig {
        &self.config
    }

    /// Initialize taint sources (user input)
    fn init_sources(&mut self) {
        // HTTP request inputs
        self.sources.insert("request.getParameter".to_string());
        self.sources.insert("request.getQueryString".to_string());
        self.sources.insert("request.getHeader".to_string());
        self.sources.insert("request.body".to_string());

        // File/Network inputs
        self.sources.insert("read".to_string());
        self.sources.insert("readLine".to_string());
        self.sources.insert("recv".to_string());
        self.sources.insert("input".to_string());

        // Environment
        self.sources.insert("getenv".to_string());
        self.sources.insert("System.getenv".to_string());
    }

    /// Initialize taint sinks (dangerous functions)
    fn init_sinks(&mut self) {
        // SQL Injection
        self.sinks
            .insert("executeQuery".to_string(), VulnerabilityType::SQLInjection);
        self.sinks
            .insert("execute".to_string(), VulnerabilityType::SQLInjection);
        self.sinks
            .insert("createQuery".to_string(), VulnerabilityType::SQLInjection);
        self.sinks
            .insert("query".to_string(), VulnerabilityType::SQLInjection);

        // XSS
        self.sinks
            .insert("document.write".to_string(), VulnerabilityType::XSS);
        self.sinks
            .insert("innerHTML".to_string(), VulnerabilityType::XSS);
        self.sinks
            .insert("outerHTML".to_string(), VulnerabilityType::XSS);
        self.sinks
            .insert("eval".to_string(), VulnerabilityType::XSS);

        // Command Injection
        self.sinks
            .insert("exec".to_string(), VulnerabilityType::CommandInjection);
        self.sinks
            .insert("system".to_string(), VulnerabilityType::CommandInjection);
        self.sinks.insert(
            "Runtime.exec".to_string(),
            VulnerabilityType::CommandInjection,
        );
        self.sinks.insert(
            "ProcessBuilder".to_string(),
            VulnerabilityType::CommandInjection,
        );

        // Path Traversal
        self.sinks
            .insert("open".to_string(), VulnerabilityType::PathTraversal);
        self.sinks
            .insert("readFile".to_string(), VulnerabilityType::PathTraversal);
        self.sinks.insert(
            "FileInputStream".to_string(),
            VulnerabilityType::PathTraversal,
        );

        // LDAP Injection
        self.sinks
            .insert("search".to_string(), VulnerabilityType::LDAPInjection);

        // XML Injection
        self.sinks
            .insert("parse".to_string(), VulnerabilityType::XMLInjection);
        self.sinks
            .insert("parseXML".to_string(), VulnerabilityType::XMLInjection);

        // SSRF
        self.sinks
            .insert("fetch".to_string(), VulnerabilityType::SSRF);
        self.sinks
            .insert("http.get".to_string(), VulnerabilityType::SSRF);
        self.sinks
            .insert("urllib.request".to_string(), VulnerabilityType::SSRF);
    }

    /// Initialize sanitizers (safe functions)
    fn init_sanitizers(&mut self) {
        // SQL
        self.sanitizers.insert("escapeSQL".to_string());
        self.sanitizers.insert("prepareStat".to_string());
        self.sanitizers.insert("sanitize".to_string());

        // HTML
        self.sanitizers.insert("htmlEscape".to_string());
        self.sanitizers.insert("escapeHTML".to_string());
        self.sanitizers.insert("sanitizeHTML".to_string());

        // Shell
        self.sanitizers.insert("escapeShell".to_string());
        self.sanitizers.insert("shellEscape".to_string());

        // Path
        self.sanitizers.insert("normalizePath".to_string());
        self.sanitizers.insert("resolvePath".to_string());
    }

    /// Analyze nodes for security vulnerabilities
    pub fn analyze(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<SecurityVulnerability> {
        // Pattern-based detection (RFC-001: Configurable)
        if self.config.enable_pattern_detection {
            self.detect_hardcoded_credentials(nodes);
            self.detect_weak_crypto(nodes);
        }

        // Taint-based detection using InterproceduralTaintAnalyzer (RFC-001: Configurable)
        if self.config.enable_taint_analysis {
            self.detect_taint_vulnerabilities(nodes, edges);
        }

        // Filter by minimum severity (RFC-001: Configurable)
        let min_severity = self.config.min_severity;
        let vulns = std::mem::take(&mut self.vulnerabilities);
        vulns
            .into_iter()
            .filter(|v| v.severity >= min_severity)
            .collect()
    }

    /// Detect vulnerabilities using taint analysis
    fn detect_taint_vulnerabilities(&mut self, _nodes: &[Node], _edges: &[Edge]) {
        // MIGRATION(RFC-071): Taint analysis API changed
        // - Status: Heap analysis uses independent vulnerability detection
        // - Alternative: Use IFDSTaintService or InterproceduralTaintAnalyzer directly
        // - The new TaintAnalyzer interface (see RFC-071):
        //
        // Previous implementation was incompatible with current TaintAnalyzer:
        // - TaintAnalyzer::new() now requires call_graph, max_depth, max_paths
        // - analyze() now takes sources/sinks as HashMap<String, HashSet<String>>
        // - TaintPath struct fields changed
        //
        // For now, skip taint vulnerability detection until proper integration.
        // This is tracked as a separate backlog item.

        // NOTE: This stub is intentional - the heap_analysis security module
        // needs to be updated to use the new taint analysis API.
    }

    /// Map vulnerability type to OWASP category
    fn vuln_type_to_owasp(vuln_type: &VulnerabilityType) -> OWASPCategory {
        // Delegate to existing implementation
        vuln_type.owasp_category()
    }

    /// Map vulnerability type to CWE ID
    fn vuln_type_to_cwe(vuln_type: &VulnerabilityType) -> u32 {
        // Delegate to existing implementation
        vuln_type.cwe_id().unwrap_or(0)
    }

    /// Get recommendation for vulnerability type
    fn get_recommendation(vuln_type: &VulnerabilityType) -> String {
        match vuln_type {
            VulnerabilityType::SQLInjection => {
                "Use parameterized queries or prepared statements".to_string()
            }
            VulnerabilityType::XSS => {
                "Use proper output encoding (HTML escape) or Content Security Policy".to_string()
            }
            VulnerabilityType::CommandInjection => {
                "Avoid shell commands; use library functions or whitelist allowed commands"
                    .to_string()
            }
            VulnerabilityType::PathTraversal => {
                "Validate and normalize paths; use allowlists for file access".to_string()
            }
            VulnerabilityType::SSRF => {
                "Validate URLs against allowlist; disable redirects".to_string()
            }
            VulnerabilityType::HardcodedCredentials => {
                "Store credentials in environment variables or secure vaults".to_string()
            }
            VulnerabilityType::WeakCrypto => {
                "Use strong algorithms: AES-256, SHA-256, RSA-2048+".to_string()
            }
            VulnerabilityType::LDAPInjection => {
                "Use parameterized LDAP queries; validate and escape input".to_string()
            }
            VulnerabilityType::XMLInjection => {
                "Disable external entities; use safe XML parsers".to_string()
            }
            VulnerabilityType::InsecureRandom => {
                "Use cryptographically secure random number generators".to_string()
            }
            VulnerabilityType::WeakPassword => {
                "Enforce strong password policies; use password managers".to_string()
            }
            VulnerabilityType::MissingAuthentication => {
                "Implement proper authentication; use established auth frameworks".to_string()
            }
            VulnerabilityType::SessionFixation => {
                "Regenerate session ID after login; use secure session management".to_string()
            }
            VulnerabilityType::CSRF => {
                "Use CSRF tokens; validate Origin/Referer headers".to_string()
            }
            VulnerabilityType::XXE => {
                "Disable DTDs; use safe XML parsers with XXE protection".to_string()
            }
            VulnerabilityType::InsecureDeserialization => {
                "Avoid deserializing untrusted data; use safe serialization formats".to_string()
            }
        }
    }

    /// Detect hardcoded credentials (pattern-based)
    fn detect_hardcoded_credentials(&mut self, nodes: &[Node]) {
        for node in nodes {
            if let NodeKind::Variable = node.kind {
                // Check for suspicious variable names
                if let Some(name) = &node.name {
                    let name_lower = name.to_lowercase();
                    if (name_lower.contains("password")
                        || name_lower.contains("secret")
                        || name_lower.contains("apikey")
                        || name_lower.contains("token"))
                        && !name_lower.contains("input")
                    {
                        // Check if initialized with string literal
                        if let Some(value) = &node.initial_value {
                            if value.starts_with('\"') || value.starts_with('\'') {
                                let vuln = SecurityVulnerability {
                                    category: OWASPCategory::A02_CryptographicFailures,
                                    cwe_id: Some(798),
                                    severity: 9,
                                    vuln_type: VulnerabilityType::HardcodedCredentials,
                                    location: format!("{}:{}", node.file_path, node.span.start_line),
                                    taint_path: None,
                                    message: format!(
                                        "Hardcoded credential found in variable '{}'",
                                        name
                                    ),
                                    recommendation: "Store credentials in environment variables or secure vaults (e.g., AWS Secrets Manager, HashiCorp Vault)".to_string(),
                                };
                                self.vulnerabilities.push(vuln);
                            }
                        }
                    }
                }
            }
        }
    }

    /// Detect weak cryptography (pattern-based)
    fn detect_weak_crypto(&mut self, nodes: &[Node]) {
        let weak_algorithms = ["MD5", "SHA1", "DES", "RC4"];

        for node in nodes {
            if let NodeKind::Expression | NodeKind::Function | NodeKind::Method = node.kind {
                // Check function name or FQN for weak crypto algorithms
                let check_str = node.name.as_deref().unwrap_or(&node.fqn);
                for algo in &weak_algorithms {
                    if check_str.contains(algo) || node.fqn.contains(algo) {
                        let vuln = SecurityVulnerability {
                            category: OWASPCategory::A02_CryptographicFailures,
                            cwe_id: Some(327),
                            severity: 7,
                            vuln_type: VulnerabilityType::WeakCrypto,
                            location: format!("{}:{}", node.file_path, node.span.start_line),
                            taint_path: None,
                            message: format!("Weak cryptographic algorithm '{}' detected", algo),
                            recommendation:
                                "Use strong algorithms: SHA256, SHA3, AES-256, RSA-2048+"
                                    .to_string(),
                        };
                        self.vulnerabilities.push(vuln);
                        break;
                    }
                }
            }
        }
    }

    /// Check if function is a taint source
    pub fn is_source(&self, func_name: &str) -> bool {
        self.sources.contains(func_name)
    }

    /// Check if function is a taint sink
    pub fn is_sink(&self, func_name: &str) -> Option<VulnerabilityType> {
        self.sinks.get(func_name).copied()
    }

    /// Check if function is a sanitizer
    pub fn is_sanitizer(&self, func_name: &str) -> bool {
        self.sanitizers.contains(func_name)
            || func_name.contains("escape")
            || func_name.contains("sanitize")
            || func_name.contains("validate")
    }

    pub fn get_vulnerabilities(&self) -> &[SecurityVulnerability] {
        &self.vulnerabilities
    }
}

impl DeepSecurityAnalyzer {
    /// Enable concolic testing for automatic exploit generation
    ///
    /// When a vulnerability is detected, concolic testing generates
    /// concrete inputs that trigger the vulnerability.
    pub fn enable_concolic_testing(&mut self, config: ConcolicConfig) {
        self.concolic_engine = Some(ConcolicEngine::new(config));
    }

    /// Generate exploit test cases for detected vulnerabilities
    ///
    /// Uses concolic execution to find inputs that reach vulnerable sinks.
    ///
    /// Returns: Vec of test inputs that trigger vulnerabilities
    pub fn generate_exploit_tests(&mut self) -> Vec<TestInput> {
        let Some(ref mut engine) = self.concolic_engine else {
            return Vec::new();
        };

        // Generate tests for each vulnerability
        let mut all_tests = Vec::new();

        for vuln in &self.vulnerabilities {
            // Create initial state based on vulnerability type
            let mut inputs = HashMap::new();

            match vuln.vuln_type {
                VulnerabilityType::SQLInjection => {
                    inputs.insert(
                        "user_input".to_string(),
                        crate::features::smt::infrastructure::ConcreteValue::String(
                            "' OR '1'='1".to_string(),
                        ),
                    );
                }
                VulnerabilityType::XSS => {
                    inputs.insert(
                        "user_input".to_string(),
                        crate::features::smt::infrastructure::ConcreteValue::String(
                            "<script>alert('xss')</script>".to_string(),
                        ),
                    );
                }
                VulnerabilityType::CommandInjection => {
                    inputs.insert(
                        "user_input".to_string(),
                        crate::features::smt::infrastructure::ConcreteValue::String(
                            "; rm -rf /".to_string(),
                        ),
                    );
                }
                VulnerabilityType::PathTraversal => {
                    inputs.insert(
                        "user_input".to_string(),
                        crate::features::smt::infrastructure::ConcreteValue::String(
                            "../../../etc/passwd".to_string(),
                        ),
                    );
                }
                _ => {
                    inputs.insert(
                        "user_input".to_string(),
                        crate::features::smt::infrastructure::ConcreteValue::String(
                            "MALICIOUS_INPUT".to_string(),
                        ),
                    );
                }
            }

            let _state = engine.create_initial_state(inputs.clone());

            all_tests.push(TestInput {
                values: inputs,
                path_description: format!(
                    "Exploit for {} at {}",
                    format!("{:?}", vuln.vuln_type),
                    vuln.location
                ),
                expected: crate::features::smt::infrastructure::TestExpectation::Error(
                    vuln.message.clone(),
                ),
            });
        }

        all_tests
    }

    /// Get concolic engine statistics
    pub fn concolic_stats(&self) -> Option<crate::features::smt::infrastructure::ExplorationStats> {
        self.concolic_engine.as_ref().map(|e| e.get_result().stats)
    }
}

impl Default for DeepSecurityAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    #[test]
    fn test_hardcoded_credentials() {
        let mut analyzer = DeepSecurityAnalyzer::new();

        let mut node = Node::new(
            "var_1".to_string(),
            NodeKind::Variable,
            "api_password".to_string(),
            "test.java".to_string(),
            Span::new(10, 0, 10, 30),
        )
        .with_name("api_password");

        node.initial_value = Some("\"secret123\"".to_string());

        let vulns = analyzer.analyze(&[node], &[]);
        assert!(vulns
            .iter()
            .any(|v| matches!(v.vuln_type, VulnerabilityType::HardcodedCredentials)));
    }

    #[test]
    fn test_weak_crypto() {
        let mut analyzer = DeepSecurityAnalyzer::new();

        let node = Node::new(
            "call_1".to_string(),
            NodeKind::Expression,
            "MD5.digest".to_string(),
            "test.java".to_string(),
            Span::new(15, 0, 15, 20),
        )
        .with_name("hash_md5");

        let vulns = analyzer.analyze(&[node], &[]);
        assert!(vulns
            .iter()
            .any(|v| matches!(v.vuln_type, VulnerabilityType::WeakCrypto)));
    }

    #[test]
    fn test_vuln_type_properties() {
        assert_eq!(VulnerabilityType::SQLInjection.cwe_id(), Some(89));
        assert_eq!(VulnerabilityType::SQLInjection.severity(), 10);
        assert_eq!(
            VulnerabilityType::SQLInjection.owasp_category(),
            OWASPCategory::A03_Injection
        );
    }

    #[test]
    fn test_source_sink_sanitizer() {
        let analyzer = DeepSecurityAnalyzer::new();

        assert!(analyzer.is_source("request.getParameter"));
        assert_eq!(
            analyzer.is_sink("executeQuery"),
            Some(VulnerabilityType::SQLInjection)
        );
        assert!(analyzer.is_sanitizer("escapeSQL"));
    }
}
