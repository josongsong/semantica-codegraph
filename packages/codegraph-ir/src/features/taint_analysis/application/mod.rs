/*
 * Taint Analysis Application Layer
 *
 * Use cases and orchestration logic following Clean Architecture principles.
 *
 * Architecture:
 * ```
 * +------------------+     +-------------------+     +-------------------+
 * |   Input Ports    | --> |    Use Cases      | --> |   Output Ports    |
 * | (Service Traits) |     | (Business Logic)  |     | (Repo Traits)     |
 * +------------------+     +-------------------+     +-------------------+
 *        ^                         |                         |
 *        |                         v                         v
 *   Adapters               Domain Models              Infrastructure
 * (API, CLI, MCP)       (TaintPath, etc.)          (DB, Files, etc.)
 * ```
 *
 * Use Cases:
 * 1. AnalyzeTaintUseCase - Main taint analysis workflow
 * 2. DifferentialAnalysisUseCase - Compare versions for security changes
 * 3. BackwardAnalysisUseCase - Sink-to-source tracing
 * 4. IFDSTaintService - IFDS/IDE-based interprocedural analysis (RFC-001 Config)
 */

// ============================================================================
// IFDS/IDE Taint Service (RFC-001 Config Integration)
// ============================================================================
pub mod ifds_taint_service;
pub use ifds_taint_service::{
    IDEAnalysisResult, IDESolverConfig, IFDSAnalysisError, IFDSAnalysisResult, IFDSSolverConfig,
    IFDSTaintService, SolverType, SparseAnalysisStats, SparseIFDSConfig,
};

use async_trait::async_trait;
use rustc_hash::{FxHashMap, FxHashSet};
use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::time::Instant;

use super::infrastructure::{
    BackwardTaintAnalyzer, BackwardTaintConfig, BackwardTaintPath, ControlDependencyGraph,
    ImplicitFlowAnalyzer, ImplicitFlowConfig, ImplicitFlowVulnerability, TaintPath, TaintSeverity,
    IFDSCFG,
};
use super::ports::{
    default_sanitizer_patterns, default_sink_patterns, default_source_patterns, AnalysisMode,
    AnalysisStats, BackwardTaintPathDTO, CodeRepository, ImplicitFlowDTO, TaintAnalysisConfig,
    TaintAnalysisError, TaintAnalysisRequest, TaintAnalysisResponse, TaintAnalysisService,
    TaintPathDTO, TaintResultRepository,
};
use crate::shared::models::Node;

// ============================================================================
// Main Use Case: Analyze Taint
// ============================================================================

/// Main taint analysis use case
///
/// Orchestrates various analysis techniques based on configuration.
pub struct AnalyzeTaintUseCase {
    /// Code repository (output port)
    code_repo: Arc<dyn CodeRepository>,

    /// Result repository (output port)
    result_repo: Option<Arc<dyn TaintResultRepository>>,

    /// Default source patterns
    source_patterns: Vec<String>,

    /// Default sink patterns
    sink_patterns: Vec<String>,

    /// Default sanitizer patterns
    sanitizer_patterns: Vec<String>,
}

impl AnalyzeTaintUseCase {
    /// Create new use case with dependencies
    pub fn new(
        code_repo: Arc<dyn CodeRepository>,
        result_repo: Option<Arc<dyn TaintResultRepository>>,
    ) -> Self {
        Self {
            code_repo,
            result_repo,
            source_patterns: default_source_patterns(),
            sink_patterns: default_sink_patterns(),
            sanitizer_patterns: default_sanitizer_patterns(),
        }
    }

    /// Execute analysis
    pub async fn execute(
        &self,
        request: TaintAnalysisRequest,
    ) -> Result<TaintAnalysisResponse, TaintAnalysisError> {
        let start = Instant::now();

        // 1. Load IR nodes
        let nodes = self.code_repo.get_ir_nodes(&request.code_path).await?;

        if nodes.is_empty() {
            return Ok(TaintAnalysisResponse {
                success: true,
                forward_paths: vec![],
                backward_paths: vec![],
                implicit_flows: vec![],
                stats: AnalysisStats::default(),
                errors: vec!["No IR nodes found".to_string()],
            });
        }

        // 2. Build analysis context
        let sources = self.build_sources_map(&request.source_patterns, &nodes);
        let sinks = self.build_sinks_map(&request.sink_patterns, &nodes);

        // 3. Run forward analysis
        let forward_paths = self.run_forward_analysis(&request.config, &nodes, &sources, &sinks)?;

        // 4. Run backward analysis (if enabled)
        let backward_paths = if request.config.backward_analysis {
            self.run_backward_analysis(&request.config, &nodes, &sinks)?
        } else {
            vec![]
        };

        // 5. Run implicit flow analysis (if enabled)
        let implicit_flows = if request.config.implicit_flow {
            self.run_implicit_flow_analysis(&request.config, &nodes, &sources, &sinks)?
        } else {
            vec![]
        };

        // 6. Build response
        let elapsed = start.elapsed();

        // Calculate stats before moving paths
        let forward_count = forward_paths.len();
        let backward_count = backward_paths.len();
        let forward_sanitized = forward_paths.iter().filter(|p| p.is_sanitized).count();
        let backward_sanitized = backward_paths.iter().filter(|p| p.is_sanitized).count();
        let implicit_count = implicit_flows.len();

        // Calculate edges analyzed (sum of all path lengths)
        let edges_analyzed = forward_paths.iter().map(|p| p.path.len()).sum::<usize>()
            + backward_paths.iter().map(|p| p.path.len()).sum::<usize>()
            + implicit_count; // Implicit flows are single edges

        let response = TaintAnalysisResponse {
            success: true,
            forward_paths: forward_paths.into_iter().map(TaintPathDTO::from).collect(),
            backward_paths: backward_paths
                .into_iter()
                .map(BackwardTaintPathDTO::from)
                .collect(),
            implicit_flows: implicit_flows
                .into_iter()
                .map(ImplicitFlowDTO::from)
                .collect(),
            stats: AnalysisStats {
                nodes_analyzed: nodes.len(),
                edges_analyzed,
                paths_found: forward_count + backward_count,
                sanitized_paths: forward_sanitized + backward_sanitized,
                implicit_flows_found: implicit_count,
                analysis_time_ms: elapsed.as_millis() as u64,
                memory_used_bytes: 0, // Requires allocator hooks - out of scope
            },
            errors: vec![],
        };

        // 7. Optionally save results
        if let Some(repo) = &self.result_repo {
            let _ = repo.save_results(&response).await;
        }

        Ok(response)
    }

    /// Build source node map from patterns
    fn build_sources_map(
        &self,
        patterns: &[String],
        nodes: &[Node],
    ) -> HashMap<String, HashSet<String>> {
        let mut sources = HashMap::new();

        for node in nodes {
            let node_name = node
                .name
                .as_ref()
                .map(|n| n.to_lowercase())
                .unwrap_or_default();
            for pattern in patterns {
                if node_name.contains(&pattern.to_lowercase()) {
                    sources
                        .entry(node.id.clone())
                        .or_insert_with(HashSet::new)
                        .insert(pattern.clone());
                }
            }
        }

        sources
    }

    /// Build sink node map from patterns
    fn build_sinks_map(
        &self,
        patterns: &[String],
        nodes: &[Node],
    ) -> HashMap<String, HashSet<String>> {
        let mut sinks = HashMap::new();

        for node in nodes {
            let node_name = node
                .name
                .as_ref()
                .map(|n| n.to_lowercase())
                .unwrap_or_default();
            for pattern in patterns {
                if node_name.contains(&pattern.to_lowercase()) {
                    sinks
                        .entry(node.id.clone())
                        .or_insert_with(HashSet::new)
                        .insert(pattern.clone());
                }
            }
        }

        sinks
    }

    /// Run forward taint analysis
    ///
    /// Note: Full interprocedural analysis requires call graph construction.
    /// Currently returns empty results as placeholder.
    fn run_forward_analysis(
        &self,
        _config: &TaintAnalysisConfig,
        _nodes: &[Node],
        _sources: &HashMap<String, HashSet<String>>,
        _sinks: &HashMap<String, HashSet<String>>,
    ) -> Result<Vec<TaintPath>, TaintAnalysisError> {
        // DESIGN: Forward taint requires call graph construction
        // - Current: Returns empty (call graph not available at this layer)
        // - Alternative: Use IFDS-based analysis via IFDSTaintService
        // - Status: Intentional - use backward_analysis or IFDS for actual taint
        Ok(Vec::new())
    }

    /// Run backward taint analysis
    fn run_backward_analysis(
        &self,
        config: &TaintAnalysisConfig,
        nodes: &[Node],
        sinks: &HashMap<String, HashSet<String>>,
    ) -> Result<Vec<BackwardTaintPath>, TaintAnalysisError> {
        let backward_config = BackwardTaintConfig {
            max_depth: config.max_depth.unwrap_or(100),
            max_paths: 1000,
            source_patterns: FxHashSet::from_iter(self.source_patterns.iter().cloned()),
            sanitizer_patterns: FxHashSet::from_iter(self.sanitizer_patterns.iter().cloned()),
            include_sanitized: false,
        };

        let mut analyzer = BackwardTaintAnalyzer::new(backward_config);

        // Build CFG from nodes (simplified - real impl needs edge data)
        let cfg = self.build_cfg_from_nodes(nodes);

        // Convert sinks to format expected by backward analyzer
        let sink_vars: FxHashMap<String, Vec<String>> = sinks
            .iter()
            .map(|(k, v)| (k.clone(), v.iter().cloned().collect()))
            .collect();

        let paths = analyzer.analyze(&cfg, &sink_vars);

        Ok(paths)
    }

    /// Run implicit flow analysis
    fn run_implicit_flow_analysis(
        &self,
        config: &TaintAnalysisConfig,
        nodes: &[Node],
        sources: &HashMap<String, HashSet<String>>,
        _sinks: &HashMap<String, HashSet<String>>,
    ) -> Result<Vec<ImplicitFlowVulnerability>, TaintAnalysisError> {
        let implicit_config = ImplicitFlowConfig {
            max_depth: config.max_depth.unwrap_or(100),
            max_paths: 1000,
            track_nested: true,
            include_low_severity: false,
            taint_sources: FxHashSet::from_iter(self.source_patterns.iter().cloned()),
            taint_sinks: FxHashSet::from_iter(self.sink_patterns.iter().cloned()),
        };

        // Build CFGs
        let cfg = self.build_cfg_from_nodes(nodes);
        let cdg = ControlDependencyGraph::build_from_cfg(&cfg);

        // Convert sources to expected format
        let initial_taint: FxHashMap<String, FxHashSet<String>> = sources
            .iter()
            .map(|(k, v)| (k.clone(), FxHashSet::from_iter(v.iter().cloned())))
            .collect();

        let mut analyzer = ImplicitFlowAnalyzer::new(implicit_config);
        let vulns = analyzer.analyze(&cfg, &cdg, &initial_taint);

        Ok(vulns)
    }

    /// Build IFDS CFG from nodes (simplified)
    fn build_cfg_from_nodes(&self, nodes: &[Node]) -> IFDSCFG {
        let mut cfg = IFDSCFG::new();

        // Add nodes as entries/exits based on type
        for (i, node) in nodes.iter().enumerate() {
            if i == 0 {
                cfg.add_entry(&node.id);
            }
            if i == nodes.len() - 1 {
                cfg.add_exit(&node.id);
            }

            // Add edges between consecutive nodes (simplified)
            if i + 1 < nodes.len() {
                cfg.add_edge(super::infrastructure::CFGEdge::normal(
                    &node.id,
                    &nodes[i + 1].id,
                ));
            }
        }

        cfg
    }
}

// Note: build_worklist_cfg_from_nodes removed as WorklistCFG has different API

// ============================================================================
// Implement Input Port
// ============================================================================

/// Default implementation of TaintAnalysisService
pub struct DefaultTaintAnalysisService {
    use_case: AnalyzeTaintUseCase,
}

impl DefaultTaintAnalysisService {
    pub fn new(
        code_repo: Arc<dyn CodeRepository>,
        result_repo: Option<Arc<dyn TaintResultRepository>>,
    ) -> Self {
        Self {
            use_case: AnalyzeTaintUseCase::new(code_repo, result_repo),
        }
    }
}

#[async_trait]
impl TaintAnalysisService for DefaultTaintAnalysisService {
    async fn analyze(
        &self,
        request: TaintAnalysisRequest,
    ) -> Result<TaintAnalysisResponse, TaintAnalysisError> {
        self.use_case.execute(request).await
    }

    async fn analyze_file(
        &self,
        path: &str,
        config: TaintAnalysisConfig,
    ) -> Result<TaintAnalysisResponse, TaintAnalysisError> {
        let request = TaintAnalysisRequest {
            code_path: path.to_string(),
            config,
            source_patterns: default_source_patterns(),
            sink_patterns: default_sink_patterns(),
            sanitizer_patterns: Some(default_sanitizer_patterns()),
            mode: AnalysisMode::Balanced,
        };

        self.use_case.execute(request).await
    }

    async fn analyze_ir(
        &self,
        nodes: Vec<Node>,
        config: TaintAnalysisConfig,
    ) -> Result<TaintAnalysisResponse, TaintAnalysisError> {
        // Direct IR analysis without going through repository
        let start = Instant::now();

        if nodes.is_empty() {
            return Ok(TaintAnalysisResponse {
                success: true,
                forward_paths: vec![],
                backward_paths: vec![],
                implicit_flows: vec![],
                stats: AnalysisStats::default(),
                errors: vec!["No IR nodes provided".to_string()],
            });
        }

        let sources = self
            .use_case
            .build_sources_map(&default_source_patterns(), &nodes);
        let sinks = self
            .use_case
            .build_sinks_map(&default_sink_patterns(), &nodes);

        let forward_paths = self
            .use_case
            .run_forward_analysis(&config, &nodes, &sources, &sinks)?;
        let forward_count = forward_paths.len();

        let elapsed = start.elapsed();
        Ok(TaintAnalysisResponse {
            success: true,
            forward_paths: forward_paths.into_iter().map(TaintPathDTO::from).collect(),
            backward_paths: vec![],
            implicit_flows: vec![],
            stats: AnalysisStats {
                nodes_analyzed: nodes.len(),
                edges_analyzed: 0,
                paths_found: forward_count,
                sanitized_paths: 0,
                implicit_flows_found: 0,
                analysis_time_ms: elapsed.as_millis() as u64,
                memory_used_bytes: 0,
            },
            errors: vec![],
        })
    }

    fn supported_sources(&self) -> Vec<String> {
        default_source_patterns()
    }

    fn supported_sinks(&self) -> Vec<String> {
        default_sink_patterns()
    }

    fn supported_sanitizers(&self) -> Vec<String> {
        default_sanitizer_patterns()
    }
}

// ============================================================================
// In-Memory Repositories (for testing)
// ============================================================================

/// In-memory code repository for testing
pub struct InMemoryCodeRepository {
    nodes: HashMap<String, Vec<Node>>,
}

impl InMemoryCodeRepository {
    pub fn new() -> Self {
        Self {
            nodes: HashMap::new(),
        }
    }

    pub fn add_file(&mut self, path: &str, nodes: Vec<Node>) {
        self.nodes.insert(path.to_string(), nodes);
    }
}

impl Default for InMemoryCodeRepository {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl CodeRepository for InMemoryCodeRepository {
    async fn get_ir_nodes(&self, path: &str) -> Result<Vec<Node>, TaintAnalysisError> {
        self.nodes
            .get(path)
            .cloned()
            .ok_or_else(|| TaintAnalysisError::not_found(format!("File not found: {}", path)))
    }

    async fn get_function_ir(&self, function_id: &str) -> Result<Vec<Node>, TaintAnalysisError> {
        // Search all files for function
        for nodes in self.nodes.values() {
            for node in nodes {
                if node.id == function_id {
                    return Ok(vec![node.clone()]);
                }
            }
        }
        Err(TaintAnalysisError::not_found(format!(
            "Function not found: {}",
            function_id
        )))
    }

    async fn list_files(&self, _directory: &str) -> Result<Vec<String>, TaintAnalysisError> {
        Ok(self.nodes.keys().cloned().collect())
    }
}

/// In-memory result repository for testing
pub struct InMemoryResultRepository {
    results: std::sync::Mutex<HashMap<String, TaintAnalysisResponse>>,
    counter: std::sync::atomic::AtomicU64,
}

impl InMemoryResultRepository {
    pub fn new() -> Self {
        Self {
            results: std::sync::Mutex::new(HashMap::new()),
            counter: std::sync::atomic::AtomicU64::new(0),
        }
    }
}

impl Default for InMemoryResultRepository {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl TaintResultRepository for InMemoryResultRepository {
    async fn save_results(
        &self,
        results: &TaintAnalysisResponse,
    ) -> Result<String, TaintAnalysisError> {
        let id = self
            .counter
            .fetch_add(1, std::sync::atomic::Ordering::SeqCst)
            .to_string();
        self.results
            .lock()
            .unwrap()
            .insert(id.clone(), results.clone());
        Ok(id)
    }

    async fn load_results(&self, id: &str) -> Result<TaintAnalysisResponse, TaintAnalysisError> {
        self.results
            .lock()
            .unwrap()
            .get(id)
            .cloned()
            .ok_or_else(|| TaintAnalysisError::not_found(format!("Results not found: {}", id)))
    }

    async fn list_results(&self) -> Result<Vec<String>, TaintAnalysisError> {
        Ok(self.results.lock().unwrap().keys().cloned().collect())
    }

    async fn delete_results(&self, id: &str) -> Result<(), TaintAnalysisError> {
        self.results.lock().unwrap().remove(id);
        Ok(())
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::NodeKind;

    fn create_test_node(id: &str, name: &str) -> Node {
        use crate::shared::models::{NodeBuilder, Span};
        NodeBuilder::new()
            .id(id)
            .with_name(name)
            .kind(NodeKind::Function)
            .file_path("test.py")
            .span(Span::new(1, 0, 10, 0))
            .fqn(format!("test::{}", name))
            .language("python")
            .build()
            .expect("Failed to build test node")
    }

    #[tokio::test]
    async fn test_in_memory_code_repo() {
        let mut repo = InMemoryCodeRepository::new();
        repo.add_file("test.py", vec![create_test_node("1", "user_input")]);

        let nodes = repo.get_ir_nodes("test.py").await.unwrap();
        assert_eq!(nodes.len(), 1);
        assert_eq!(nodes[0].name.as_deref(), Some("user_input"));
    }

    #[tokio::test]
    async fn test_in_memory_result_repo() {
        let repo = InMemoryResultRepository::new();

        let response = TaintAnalysisResponse {
            success: true,
            forward_paths: vec![],
            backward_paths: vec![],
            implicit_flows: vec![],
            stats: AnalysisStats::default(),
            errors: vec![],
        };

        let id = repo.save_results(&response).await.unwrap();
        let loaded = repo.load_results(&id).await.unwrap();
        assert!(loaded.success);
    }

    #[tokio::test]
    async fn test_analyze_taint_use_case_empty() {
        let code_repo = Arc::new(InMemoryCodeRepository::new());
        let use_case = AnalyzeTaintUseCase::new(code_repo, None);

        let request = TaintAnalysisRequest {
            code_path: "nonexistent.py".to_string(),
            config: TaintAnalysisConfig::default(),
            source_patterns: default_source_patterns(),
            sink_patterns: default_sink_patterns(),
            sanitizer_patterns: None,
            mode: AnalysisMode::Balanced,
        };

        let result = use_case.execute(request).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_analyze_taint_use_case_with_nodes() {
        let mut code_repo = InMemoryCodeRepository::new();
        code_repo.add_file(
            "test.py",
            vec![
                create_test_node("1", "user_input"),
                create_test_node("2", "process"),
                create_test_node("3", "execute"),
            ],
        );

        let use_case = AnalyzeTaintUseCase::new(Arc::new(code_repo), None);

        let request = TaintAnalysisRequest {
            code_path: "test.py".to_string(),
            config: TaintAnalysisConfig::default(),
            source_patterns: vec!["user_input".to_string()],
            sink_patterns: vec!["execute".to_string()],
            sanitizer_patterns: None,
            mode: AnalysisMode::Balanced,
        };

        let result = use_case.execute(request).await.unwrap();
        assert!(result.success);
        assert_eq!(result.stats.nodes_analyzed, 3);
    }

    #[test]
    fn test_build_sources_map() {
        let code_repo = Arc::new(InMemoryCodeRepository::new());
        let use_case = AnalyzeTaintUseCase::new(code_repo, None);

        let nodes = vec![
            create_test_node("1", "user_input"),
            create_test_node("2", "request_param"),
            create_test_node("3", "process"),
        ];

        let sources =
            use_case.build_sources_map(&["user_input".to_string(), "request".to_string()], &nodes);

        assert!(sources.contains_key("1"));
        assert!(sources.contains_key("2"));
        assert!(!sources.contains_key("3"));
    }

    #[test]
    fn test_build_sinks_map() {
        let code_repo = Arc::new(InMemoryCodeRepository::new());
        let use_case = AnalyzeTaintUseCase::new(code_repo, None);

        let nodes = vec![
            create_test_node("1", "process"),
            create_test_node("2", "execute_command"),
            create_test_node("3", "sql_query"),
        ];

        let sinks = use_case.build_sinks_map(&["execute".to_string(), "query".to_string()], &nodes);

        assert!(!sinks.contains_key("1"));
        assert!(sinks.contains_key("2"));
        assert!(sinks.contains_key("3"));
    }
}
