//! Heap Analysis Application Layer - Use Cases & Services
//!
//! This module contains the application services that orchestrate domain objects
//! and port interfaces to implement use cases.
//!
//! ## Hexagonal Architecture
//! - **Application**: Orchestrates domain and ports (this module)
//! - **Domain**: Business logic and models
//! - **Ports**: Interface definitions
//! - **Infrastructure**: Port implementations
//!
//! ## SOLID Compliance
//! - **S**: Each service has single responsibility
//! - **D**: Depends on port traits, not concrete implementations

use super::domain::{EscapeState, HeapIssue, HeapObject, IssueCategory, IssueSeverity, OwnershipState};
use super::ports::{
    EscapeAnalyzerPort, HeapAnalysisResult, HeapAnalyzerPort, MemoryCheckerPort,
    OwnershipAnalyzerPort, SecurityAnalyzerPort,
};
use crate::config::HeapConfig;
use crate::shared::models::{Edge, Node};
use std::collections::HashMap;

/// Heap Analysis Service - Main Application Service
///
/// Orchestrates all heap analysis components based on configuration.
///
/// ## SOLID Compliance
/// - **S**: Orchestration only, delegates to specialized analyzers
/// - **O**: Extensible via new port implementations
/// - **D**: Depends on port traits, not concrete types
///
/// ## Example
/// ```rust,ignore
/// use heap_analysis::application::HeapAnalysisService;
/// use heap_analysis::infrastructure::*;
///
/// let service = HeapAnalysisService::new(config)
///     .with_memory_checker(Box::new(NullDereferenceChecker::new()))
///     .with_memory_checker(Box::new(UseAfterFreeChecker::new()))
///     .with_escape_analyzer(Box::new(EscapeAnalyzer::new()))
///     .with_ownership_analyzer(Box::new(OwnershipTracker::new(&config)));
///
/// let result = service.analyze(&nodes, &edges);
/// ```
pub struct HeapAnalysisService {
    /// Configuration
    config: HeapConfig,

    /// Memory safety checkers
    memory_checkers: Vec<Box<dyn MemoryCheckerPort>>,

    /// Escape analyzer
    escape_analyzer: Option<Box<dyn EscapeAnalyzerPort>>,

    /// Ownership analyzer
    ownership_analyzer: Option<Box<dyn OwnershipAnalyzerPort>>,

    /// Security analyzer
    security_analyzer: Option<Box<dyn SecurityAnalyzerPort>>,
}

impl HeapAnalysisService {
    /// Create new service with configuration
    pub fn new(config: HeapConfig) -> Self {
        Self {
            config,
            memory_checkers: Vec::new(),
            escape_analyzer: None,
            ownership_analyzer: None,
            security_analyzer: None,
        }
    }

    /// Add a memory checker (builder pattern)
    pub fn with_memory_checker(mut self, checker: Box<dyn MemoryCheckerPort>) -> Self {
        self.memory_checkers.push(checker);
        self
    }

    /// Set escape analyzer (builder pattern)
    pub fn with_escape_analyzer(mut self, analyzer: Box<dyn EscapeAnalyzerPort>) -> Self {
        self.escape_analyzer = Some(analyzer);
        self
    }

    /// Set ownership analyzer (builder pattern)
    pub fn with_ownership_analyzer(mut self, analyzer: Box<dyn OwnershipAnalyzerPort>) -> Self {
        self.ownership_analyzer = Some(analyzer);
        self
    }

    /// Set security analyzer (builder pattern)
    pub fn with_security_analyzer(mut self, analyzer: Box<dyn SecurityAnalyzerPort>) -> Self {
        self.security_analyzer = Some(analyzer);
        self
    }

    /// Run analysis based on configuration
    pub fn analyze(&mut self, nodes: &[Node], edges: &[Edge]) -> HeapAnalysisResult {
        let mut result = HeapAnalysisResult::new();

        // Run memory safety analysis if enabled
        if self.config.enable_memory_safety {
            result.memory_issues = self.analyze_memory_safety(nodes, edges);
        }

        // Run escape analysis if enabled
        if self.config.enable_escape {
            result.escape_states = self.analyze_escapes(nodes);
        }

        // Run ownership analysis if enabled
        if self.config.enable_ownership {
            result.ownership_issues = self.analyze_ownership(nodes, edges);
        }

        // Run security analysis if enabled
        if self.config.enable_security {
            result.security_issues = self.analyze_security(nodes, edges);
        }

        result
    }

    /// Run memory safety analysis
    fn analyze_memory_safety(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue> {
        let mut issues = Vec::new();

        for checker in &mut self.memory_checkers {
            issues.extend(checker.analyze_with_edges(nodes, edges));
        }

        issues
    }

    /// Run escape analysis
    fn analyze_escapes(&mut self, nodes: &[Node]) -> HashMap<String, EscapeState> {
        if let Some(ref mut analyzer) = self.escape_analyzer {
            analyzer.analyze_escapes(nodes)
        } else {
            HashMap::new()
        }
    }

    /// Run ownership analysis
    fn analyze_ownership(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue> {
        if let Some(ref mut analyzer) = self.ownership_analyzer {
            analyzer.track_ownership(nodes, edges)
        } else {
            Vec::new()
        }
    }

    /// Run security analysis
    fn analyze_security(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue> {
        if let Some(ref mut analyzer) = self.security_analyzer {
            analyzer.analyze_security(nodes, edges)
        } else {
            Vec::new()
        }
    }

    /// Reset all analyzers
    pub fn reset(&mut self) {
        for checker in &mut self.memory_checkers {
            checker.reset();
        }
        if let Some(ref mut analyzer) = self.escape_analyzer {
            analyzer.reset();
        }
        if let Some(ref mut analyzer) = self.ownership_analyzer {
            analyzer.reset();
        }
        if let Some(ref mut analyzer) = self.security_analyzer {
            analyzer.reset();
        }
    }

    /// Get configuration reference
    pub fn config(&self) -> &HeapConfig {
        &self.config
    }
}

impl HeapAnalyzerPort for HeapAnalysisService {
    fn analyze_memory_safety(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue> {
        self.analyze_memory_safety(nodes, edges)
    }

    fn analyze_escapes(&mut self, nodes: &[Node]) -> HashMap<String, EscapeState> {
        self.analyze_escapes(nodes)
    }

    fn analyze_ownership(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue> {
        self.analyze_ownership(nodes, edges)
    }

    fn analyze_security(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue> {
        self.analyze_security(nodes, edges)
    }

    fn analyze_all(&mut self, nodes: &[Node], edges: &[Edge]) -> HeapAnalysisResult {
        self.analyze(nodes, edges)
    }

    fn reset(&mut self) {
        HeapAnalysisService::reset(self)
    }
}

/// Context-Sensitive Heap Analysis Service
///
/// Enhanced service that performs context-sensitive analysis.
/// Wraps base service with call-site sensitivity.
pub struct ContextSensitiveHeapService {
    /// Base service
    base_service: HeapAnalysisService,

    /// Context sensitivity level (0 = insensitive, 1..=3 = call-string length)
    context_depth: usize,

    /// Per-context results cache
    context_cache: HashMap<String, HeapAnalysisResult>,
}

impl ContextSensitiveHeapService {
    /// Create context-sensitive service
    pub fn new(config: HeapConfig) -> Self {
        let context_depth = config.context_sensitivity;
        Self {
            base_service: HeapAnalysisService::new(config),
            context_depth,
            context_cache: HashMap::new(),
        }
    }

    /// Analyze with context
    pub fn analyze_with_context(
        &mut self,
        nodes: &[Node],
        edges: &[Edge],
        context: &str,
    ) -> HeapAnalysisResult {
        // Check cache first
        if let Some(cached) = self.context_cache.get(context) {
            return cached.clone();
        }

        // Run analysis
        let result = self.base_service.analyze(nodes, edges);

        // Cache result (limited cache size)
        if self.context_cache.len() < 10000 {
            self.context_cache.insert(context.to_string(), result.clone());
        }

        result
    }

    /// Get context depth
    pub fn context_depth(&self) -> usize {
        self.context_depth
    }

    /// Clear context cache
    pub fn clear_cache(&mut self) {
        self.context_cache.clear();
    }

    /// Get base service (for configuration)
    pub fn base_service_mut(&mut self) -> &mut HeapAnalysisService {
        &mut self.base_service
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::preset::Preset;

    #[test]
    fn test_heap_analysis_service_creation() {
        let config = HeapConfig::from_preset(Preset::Balanced);
        let service = HeapAnalysisService::new(config);
        assert!(service.memory_checkers.is_empty());
    }

    #[test]
    fn test_heap_analysis_service_config() {
        let config = HeapConfig::from_preset(Preset::Thorough);
        let service = HeapAnalysisService::new(config.clone());
        assert!(service.config().enable_memory_safety);
        assert!(service.config().enable_ownership);
    }

    #[test]
    fn test_context_sensitive_service() {
        let config = HeapConfig::from_preset(Preset::Thorough)
            .context_sensitivity(2);
        let service = ContextSensitiveHeapService::new(config);
        assert_eq!(service.context_depth(), 2);
    }

    #[test]
    fn test_empty_analysis() {
        let config = HeapConfig::from_preset(Preset::Fast);
        let mut service = HeapAnalysisService::new(config);

        let result = service.analyze(&[], &[]);
        assert!(!result.has_issues());
    }
}
