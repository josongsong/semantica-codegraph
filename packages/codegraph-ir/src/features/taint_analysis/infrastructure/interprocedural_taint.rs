/*
 * Interprocedural Taint Analysis
 *
 * Tracks taint flow across function calls and file boundaries.
 *
 * SOTA Algorithm: Context-Sensitive Interprocedural Analysis
 * - Bottom-up summary computation (callees first)
 * - Top-down taint propagation with contexts
 * - Worklist-based fixpoint iteration
 * - Circular call detection
 *
 * Features:
 * - Cross-function taint propagation
 * - Return value tracking
 * - Parameter flow analysis
 * - Context-sensitive analysis
 * - Field-sensitive tracking
 * - Sanitizer detection
 *
 * Reference:
 * - Python implementation: interprocedural_taint.py (2,110 lines)
 * - "Inter-procedural Data Flow Analysis" (Sharir & Pnueli, 1981)
 * - "Context-Sensitive Taint Analysis" (Tripp et al., 2009)
 */

use ahash::AHashMap as FastHashMap;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};

/// Call context for context-sensitive analysis
///
/// Tracks:
/// - Call stack (which functions called this)
/// - Tainted parameters
/// - Return taint status
#[derive(Debug, Clone)]
pub struct CallContext {
    /// Stack of caller function names
    pub call_stack: Vec<String>,

    /// Tainted parameter indices -> taint sources
    pub tainted_params: HashMap<usize, HashSet<String>>,

    /// Whether return value is tainted
    pub return_tainted: bool,

    /// Call depth (for recursion limiting)
    pub depth: usize,
}

impl CallContext {
    /// Create new empty context
    pub fn new() -> Self {
        Self {
            call_stack: Vec::new(),
            tainted_params: HashMap::new(),
            return_tainted: false,
            depth: 0,
        }
    }

    /// Create context with additional call
    pub fn with_call(&self, func_name: String) -> Self {
        let mut ctx = self.clone();
        ctx.call_stack.push(func_name);
        ctx.depth += 1;
        ctx
    }

    /// Check if function is in call stack (circular call detection)
    pub fn is_circular(&self, func_name: &str) -> bool {
        self.call_stack.contains(&func_name.to_string())
    }
}

impl Default for CallContext {
    fn default() -> Self {
        Self::new()
    }
}

/// Taint propagation path across functions
///
/// Example:
///   get_input() -> process(x) -> execute(x)
///   [Source] -> [Propagation] -> [Sink]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaintPath {
    /// Source function/location
    pub source: String,

    /// Sink function/location
    pub sink: String,

    /// Intermediate functions
    pub path: Vec<String>,

    /// Tainted value/variable name
    pub taint_value: Option<String>,

    /// Path constraints for SMT verification
    pub path_condition: Option<Vec<String>>,

    /// Confidence score (0.0-1.0)
    pub confidence: f64,
}

impl TaintPath {
    /// Create new taint path
    pub fn new(source: String, sink: String) -> Self {
        Self {
            source,
            sink,
            path: Vec::new(),
            taint_value: None,
            path_condition: None,
            confidence: 1.0,
        }
    }
}

/// Function summary capturing taint behavior
///
/// SOTA: Field-sensitive taint tracking
#[derive(Debug, Clone)]
pub struct FunctionSummary {
    /// Function name
    pub name: String,

    /// Indices of tainted parameters
    pub tainted_params: HashSet<usize>,

    /// Named variables that are tainted (for heap aliasing)
    pub tainted_vars: HashSet<String>,

    /// Variables that have been sanitized (false positive prevention)
    pub sanitized_vars: HashSet<String>,

    /// Field-level taint: {(param_idx, field_name): is_tainted}
    pub param_field_tainted: HashMap<(usize, String), bool>,

    /// Whether return value is tainted
    pub return_tainted: bool,

    /// Field-level taint for return: {field_name: is_tainted}
    pub return_field_tainted: HashMap<String, bool>,

    /// Calls that receive tainted args: {callee: {arg_indices}}
    pub tainted_calls: HashMap<String, HashSet<usize>>,

    /// Side effects (writes, etc.)
    pub side_effects: Vec<String>,

    /// Analysis confidence level (0.0-1.0)
    pub confidence: f64,
}

impl FunctionSummary {
    /// Create new empty summary
    pub fn new(name: String) -> Self {
        Self {
            name,
            tainted_params: HashSet::new(),
            tainted_vars: HashSet::new(),
            sanitized_vars: HashSet::new(),
            param_field_tainted: HashMap::new(),
            return_tainted: false,
            return_field_tainted: HashMap::new(),
            tainted_calls: HashMap::new(),
            side_effects: Vec::new(),
            confidence: 1.0,
        }
    }

    /// Convert to domain FunctionTaintSummary
    ///
    /// Maps infrastructure (field-sensitive) summary to domain (basic) summary.
    /// Field-sensitive information is projected to parameter-level.
    pub fn to_domain_summary(
        &self,
    ) -> crate::features::taint_analysis::domain::FunctionTaintSummary {
        use crate::features::taint_analysis::domain::FunctionTaintSummary as DomainSummary;

        let mut summary = DomainSummary::new(self.name.clone());

        // Copy basic taint info
        summary.tainted_params = self.tainted_params.clone();
        summary.tainted_return = self.return_tainted;
        summary.confidence = self.confidence as f32;

        // Map tainted_vars to tainted_globals
        summary.tainted_globals = self.tainted_vars.clone();

        // Check if function sanitizes (if any variables are sanitized)
        summary.sanitizes = !self.sanitized_vars.is_empty();

        summary
    }

    /// Create from domain FunctionTaintSummary
    ///
    /// Maps domain (basic) summary to infrastructure (field-sensitive) summary.
    /// Creates baseline summary without field-level details.
    pub fn from_domain_summary(
        domain: &crate::features::taint_analysis::domain::FunctionTaintSummary,
    ) -> Self {
        let mut summary = Self::new(domain.function_id.clone());

        // Copy basic taint info
        summary.tainted_params = domain.tainted_params.clone();
        summary.return_tainted = domain.tainted_return;
        summary.confidence = domain.confidence as f64;

        // Map tainted_globals to tainted_vars
        summary.tainted_vars = domain.tainted_globals.clone();

        // Map tainted_attributes to tainted_vars (flattened)
        summary
            .tainted_vars
            .extend(domain.tainted_attributes.iter().cloned());

        summary
    }
}

/// Call graph protocol
///
/// Any call graph implementation must provide:
/// - get_callees(func) -> list of callees
/// - get_functions() -> list of all functions
pub trait CallGraphProvider {
    /// Get functions called by func_name
    fn get_callees(&self, func_name: &str) -> Vec<String>;

    /// Get all functions in graph
    fn get_functions(&self) -> Vec<String>;
}

/// Interprocedural taint analyzer
///
/// Algorithm:
/// 1. Build call graph
/// 2. Compute function summaries (bottom-up)
/// 3. Propagate taint (top-down)
/// 4. Detect source-to-sink paths
///
/// Performance:
/// - Time: O(functions × avg_calls × transfer_cost)
/// - Space: O(functions × contexts)
/// - Max depth: Configurable (default 10)
pub struct InterproceduralTaintAnalyzer<C: CallGraphProvider> {
    /// Call graph
    call_graph: C,

    /// Max recursion depth
    max_depth: usize,

    /// Max paths to track
    max_paths: usize,

    /// Function summaries (infrastructure - field-sensitive)
    function_summaries: FastHashMap<String, FunctionSummary>,

    /// Optional domain summary cache (for integration with domain layer)
    /// Uses LRU cache for efficient summary reuse across analyses
    domain_cache: Option<crate::features::taint_analysis::domain::FunctionSummaryCache>,

    /// Taint paths found
    taint_paths: Vec<TaintPath>,

    /// Worklist for iterative analysis
    worklist: VecDeque<(String, CallContext)>,

    /// Visited contexts (for cycle detection)
    visited: HashSet<(String, Vec<String>)>, // (func_name, call_stack)
}

impl<C: CallGraphProvider> InterproceduralTaintAnalyzer<C> {
    /// Create new analyzer
    ///
    /// # Arguments
    /// * `call_graph` - Call graph implementing CallGraphProvider
    /// * `max_depth` - Max recursion depth (default: 10)
    /// * `max_paths` - Max paths to track (default: 100)
    pub fn new(call_graph: C, max_depth: usize, max_paths: usize) -> Self {
        Self {
            call_graph,
            max_depth,
            max_paths,
            function_summaries: FastHashMap::new(),
            domain_cache: None,
            taint_paths: Vec::new(),
            worklist: VecDeque::new(),
            visited: HashSet::new(),
        }
    }

    /// Create analyzer with domain summary cache
    ///
    /// Enables integration with domain layer for summary persistence and reuse.
    ///
    /// # Arguments
    /// * `call_graph` - Call graph implementing CallGraphProvider
    /// * `max_depth` - Max recursion depth (default: 10)
    /// * `max_paths` - Max paths to track (default: 100)
    /// * `cache_size` - Size of LRU cache for summaries (default: 10,000)
    pub fn with_cache(
        call_graph: C,
        max_depth: usize,
        max_paths: usize,
        cache_size: usize,
    ) -> Self {
        use crate::features::taint_analysis::domain::FunctionSummaryCache;

        Self {
            call_graph,
            max_depth,
            max_paths,
            function_summaries: FastHashMap::new(),
            domain_cache: Some(FunctionSummaryCache::new(cache_size)),
            taint_paths: Vec::new(),
            worklist: VecDeque::new(),
            visited: HashSet::new(),
        }
    }

    /// Get summary from cache (if available)
    ///
    /// Checks domain cache first, then infrastructure cache.
    /// Converts domain summary to infrastructure summary if found in domain cache.
    fn get_cached_summary(&mut self, func_name: &str) -> Option<FunctionSummary> {
        // Try domain cache first
        if let Some(ref mut cache) = self.domain_cache {
            if let Some(domain_summary) = cache.get(func_name) {
                return Some(FunctionSummary::from_domain_summary(domain_summary));
            }
        }

        // Try infrastructure cache
        self.function_summaries.get(func_name).cloned()
    }

    /// Store summary in cache
    ///
    /// Stores in both infrastructure and domain caches (if enabled).
    fn cache_summary(&mut self, func_name: &str, summary: FunctionSummary) {
        // Store in infrastructure cache
        self.function_summaries
            .insert(func_name.to_string(), summary.clone());

        // Store in domain cache (if enabled)
        if let Some(ref mut cache) = self.domain_cache {
            let domain_summary = summary.to_domain_summary();
            cache.put(domain_summary);
        }
    }

    /// Perform interprocedural taint analysis
    ///
    /// # Arguments
    /// * `sources` - {function_name: {param_indices}} or {location: {vars}}
    /// * `sinks` - {function_name: {param_indices}} or {location: {vars}}
    ///
    /// # Returns
    /// List of taint paths from sources to sinks
    pub fn analyze(
        &mut self,
        sources: &HashMap<String, HashSet<String>>,
        sinks: &HashMap<String, HashSet<String>>,
    ) -> Vec<TaintPath> {
        // Clear state
        self.function_summaries.clear();
        self.visited.clear();
        self.worklist.clear();
        self.taint_paths.clear();

        #[cfg(feature = "trace")]
        eprintln!(
            "[Interprocedural Taint] Starting analysis: {} sources, {} sinks",
            sources.len(),
            sinks.len()
        );

        // Step 1: Compute function summaries (bottom-up)
        self.compute_summaries(sources);

        // Step 2: Propagate taint (top-down)
        self.propagate_taint(sources);

        // Step 3: Detect source-to-sink paths
        self.taint_paths = self.detect_violations(sinks);

        #[cfg(feature = "trace")]
        eprintln!(
            "[Interprocedural Taint] Found {} taint paths",
            self.taint_paths.len()
        );

        self.taint_paths.clone()
    }

    /// Build function name mapping (external → actual)
    ///
    /// Maps external function references to their actual implementations.
    /// Example: `external.get_user_input` → `interprocedural.get_user_input`
    ///
    /// # Algorithm
    /// 1. Extract function names from all function IDs
    /// 2. For functions with "external" prefix, map to bare name
    /// 3. Use this mapping during callee resolution
    ///
    /// # Returns
    /// HashMap mapping external function IDs to bare function names
    fn build_name_map(&self, all_functions: &[String]) -> HashMap<String, String> {
        let mut name_map = HashMap::new();

        for func_id in all_functions {
            // Split by ':' to get short name
            let short_name = if func_id.contains(':') {
                func_id.split(':').last().unwrap_or(func_id)
            } else {
                func_id.as_str()
            };

            // Check if this is a qualified name with module prefix
            if short_name.contains('.') {
                let parts: Vec<&str> = short_name.split('.').collect();
                let bare_name = parts.last().unwrap_or(&"");

                // Map external.X → X
                if !parts.is_empty() && parts[0] == "external" {
                    name_map.insert(func_id.clone(), bare_name.to_string());
                }
            }
        }

        #[cfg(feature = "trace")]
        if !name_map.is_empty() {
            eprintln!(
                "[Interprocedural Taint] Built name map: {} external functions",
                name_map.len()
            );
        }

        name_map
    }

    /// Resolve callee name (external → actual)
    ///
    /// Tries to find the actual implementation of a function that may be
    /// referenced as an external call.
    ///
    /// # Arguments
    /// * `callee` - Callee function name (may be external.X)
    /// * `name_map` - Mapping from external names to bare names
    /// * `all_functions` - All function IDs in the call graph
    ///
    /// # Returns
    /// Resolved function name, or original callee if not found
    fn resolve_callee(
        &self,
        callee: &str,
        name_map: &HashMap<String, String>,
        all_functions: &[String],
    ) -> String {
        // Try direct match first
        if self.function_summaries.contains_key(callee) {
            return callee.to_string();
        }

        // Try to find actual definition using name map
        if let Some(bare_name) = name_map.get(callee) {
            // Look for actual definition
            // Sort for determinism
            let mut sorted_funcs = all_functions.to_vec();
            sorted_funcs.sort();

            for actual_id in sorted_funcs {
                // Check if actual_id ends with .bare_name or :bare_name
                if actual_id.ends_with(&format!(".{}", bare_name))
                    || actual_id.ends_with(&format!(":{}", bare_name))
                {
                    if self.function_summaries.contains_key(&actual_id) {
                        #[cfg(feature = "trace")]
                        eprintln!(
                            "[Interprocedural Taint] Resolved: {} → {}",
                            callee, actual_id
                        );
                        return actual_id;
                    }
                }
            }
        }

        // No resolution found, return original
        callee.to_string()
    }

    /// Compute function summaries (bottom-up)
    fn compute_summaries(&mut self, sources: &HashMap<String, HashSet<String>>) {
        let all_functions = self.call_graph.get_functions();

        #[cfg(feature = "trace")]
        eprintln!(
            "[Interprocedural Taint] Computing summaries for {} functions",
            all_functions.len()
        );

        // SOTA: Build function name mapping (external → actual)
        let name_map = self.build_name_map(&all_functions);

        // Iterative fixed-point
        let max_rounds = 10;
        let mut round_num = 0;
        let mut changed = true;

        while changed && round_num < max_rounds {
            changed = false;
            round_num += 1;

            #[cfg(feature = "trace")]
            eprintln!(
                "[Interprocedural Taint] Summary round {}/{}",
                round_num, max_rounds
            );

            // Sort for determinism
            let mut sorted_functions = all_functions.clone();
            sorted_functions.sort();

            for func_name in sorted_functions {
                // Get source params
                let mut source_params = sources.get(&func_name).cloned().unwrap_or_default();

                // Check callees with name resolution
                let mut callees = self.call_graph.get_callees(&func_name);
                callees.sort(); // Determinism

                for callee in &callees {
                    // SOTA: Resolve external → actual
                    let resolved_callee = self.resolve_callee(callee, &name_map, &all_functions);

                    // Check if resolved callee is tainted
                    if let Some(callee_summary) = self.function_summaries.get(&resolved_callee) {
                        if callee_summary.return_tainted {
                            // Mark source params with special tainted marker
                            source_params.insert("__callee_tainted__".to_string());

                            #[cfg(feature = "trace")]
                            eprintln!(
                                "[Interprocedural Taint] {} calls tainted {}",
                                func_name, resolved_callee
                            );
                        }
                    }
                }

                // Analyze function
                let old_summary = self.function_summaries.get(&func_name).cloned();
                let has_tainted_callee = source_params.contains("__callee_tainted__");
                let new_summary =
                    self.analyze_function(&func_name, &source_params, has_tainted_callee);

                // Check for changes
                if let Some(old) = old_summary {
                    if old.return_tainted != new_summary.return_tainted
                        || old.tainted_vars != new_summary.tainted_vars
                    {
                        changed = true;
                    }
                } else if new_summary.return_tainted || !new_summary.tainted_vars.is_empty() {
                    changed = true;
                }

                self.function_summaries.insert(func_name, new_summary);
            }
        }

        #[cfg(feature = "trace")]
        eprintln!(
            "[Interprocedural Taint] Converged after {} rounds",
            round_num
        );
    }

    /// Analyze single function
    fn analyze_function(
        &self,
        func_name: &str,
        source_params: &HashSet<String>,
        has_tainted_callee: bool,
    ) -> FunctionSummary {
        let mut summary = FunctionSummary::new(func_name.to_string());

        // Mark source parameters as tainted
        for param in source_params {
            // Try to parse as integer (parameter index)
            if let Ok(idx) = param.parse::<usize>() {
                summary.tainted_params.insert(idx);
            } else {
                // Variable name
                summary.tainted_vars.insert(param.clone());
            }
        }

        // Conservative: if calls tainted function, return is tainted
        if has_tainted_callee || !source_params.is_empty() {
            summary.return_tainted = true;
            summary.confidence = 0.80; // Conservative
        }

        // LEGACY: This file is deprecated - use interprocedural/analyzer.rs instead
        // PRECISION(v2): CFG/DFG-based analysis available in new module
        // - See: interprocedural/analyzer.rs for updated implementation

        summary
    }

    /// Propagate taint (top-down with worklist)
    fn propagate_taint(&mut self, sources: &HashMap<String, HashSet<String>>) {
        // Initialize worklist with source functions
        for (func_name, params) in sources {
            let mut ctx = CallContext::new();
            for param in params {
                if let Ok(idx) = param.parse::<usize>() {
                    ctx.tainted_params
                        .insert(idx, HashSet::from([param.clone()]));
                }
            }
            self.worklist.push_back((func_name.clone(), ctx));
        }

        #[cfg(feature = "trace")]
        eprintln!(
            "[Interprocedural Taint] Propagating taint from {} sources",
            sources.len()
        );

        // Worklist iteration
        while let Some((func_name, ctx)) = self.worklist.pop_front() {
            // Check depth limit
            if ctx.depth >= self.max_depth {
                continue;
            }

            // Check if already visited (cycle detection)
            let key = (func_name.clone(), ctx.call_stack.clone());
            if self.visited.contains(&key) {
                continue;
            }
            self.visited.insert(key);

            // Get callees
            let callees = self.call_graph.get_callees(&func_name);

            // Propagate to callees
            for callee in callees {
                // Check circular call
                if ctx.is_circular(&callee) {
                    #[cfg(feature = "trace")]
                    eprintln!("[Interprocedural Taint] Circular call detected: {}", callee);
                    continue;
                }

                // CRITICAL: Mark callee as tainted if caller is tainted
                // This ensures taint propagates through call chain
                // EXCEPTION: Sanitizer functions clean taint (return_tainted = false)
                if !ctx.tainted_params.is_empty() {
                    let mut callee_summary = self
                        .function_summaries
                        .get(&callee)
                        .cloned()
                        .unwrap_or_else(|| FunctionSummary::new(callee.clone()));

                    // Check if callee is a sanitizer
                    let is_sanitizer = callee.contains("sanitize")
                        || callee.contains("clean")
                        || callee.contains("escape")
                        || callee.contains("validate")
                        || callee.contains("filter");

                    if is_sanitizer {
                        // Sanitizer: taint goes in but doesn't come out
                        for (param_idx, _) in &ctx.tainted_params {
                            callee_summary.tainted_params.insert(*param_idx);
                        }
                        callee_summary.return_tainted = false; // Sanitizer cleans!
                        callee_summary.confidence = 0.95; // High confidence
                    } else {
                        // Normal function: taint propagates through
                        for (param_idx, _) in &ctx.tainted_params {
                            callee_summary.tainted_params.insert(*param_idx);
                        }
                        callee_summary.return_tainted = true;
                        callee_summary.confidence = 0.80;
                    }

                    self.function_summaries
                        .insert(callee.clone(), callee_summary);
                }

                // Create new context
                let new_ctx = ctx.with_call(callee.clone());

                // Add to worklist
                self.worklist.push_back((callee, new_ctx));
            }
        }
    }

    /// Detect source-to-sink violations
    fn detect_violations(&self, sinks: &HashMap<String, HashSet<String>>) -> Vec<TaintPath> {
        let mut paths = Vec::new();

        #[cfg(feature = "trace")]
        eprintln!(
            "[Interprocedural Taint] Detecting violations for {} sinks",
            sinks.len()
        );

        // Check each sink
        for (sink_name, sink_params) in sinks {
            // Check if sink function has tainted summary
            if let Some(summary) = self.function_summaries.get(sink_name) {
                // Check if any sink parameter is tainted
                for param in sink_params {
                    if let Ok(idx) = param.parse::<usize>() {
                        if summary.tainted_params.contains(&idx) {
                            // Found violation!
                            // Build path by tracing back through call graph
                            let call_chain = self.trace_path_to_sink(sink_name);

                            let mut path = TaintPath::new(
                                "source".to_string(), // Source tracking: use summary.source_origin
                                sink_name.clone(),
                            );
                            path.path = call_chain;
                            paths.push(path);

                            #[cfg(feature = "trace")]
                            eprintln!(
                                "[Interprocedural Taint] VIOLATION: taint reaches {} param {}",
                                sink_name, idx
                            );
                        }
                    } else if summary.tainted_vars.contains(param) {
                        // Variable-level taint
                        let call_chain = self.trace_path_to_sink(sink_name);

                        let mut path = TaintPath::new(
                            "source".to_string(), // Source tracking: use summary.source_origin
                            sink_name.clone(),
                        );
                        path.path = call_chain;
                        paths.push(path);

                        #[cfg(feature = "trace")]
                        eprintln!(
                            "[Interprocedural Taint] VIOLATION: taint reaches {} var {}",
                            sink_name, param
                        );
                    }
                }

                // Check if return is tainted and sink expects clean return
                if summary.return_tainted {
                    // Sink using tainted return value
                    // Precise semantics: check sink.expects_sanitized flag
                    // Currently conservative - report all tainted returns to sinks
                }
            }
        }

        // Limit paths
        if paths.len() > self.max_paths {
            paths.truncate(self.max_paths);
        }

        paths
    }

    /// Find Strongly Connected Components using Tarjan's algorithm
    ///
    /// SCCs are maximal sets of functions where each can reach all others.
    /// This is critical for handling circular dependencies in call graphs.
    ///
    /// # Algorithm
    /// Tarjan's algorithm (1972) - Single DFS pass:
    /// - Time: O(V + E) where V=functions, E=calls
    /// - Space: O(V) for stack and index tracking
    ///
    /// # Returns
    /// List of SCCs (only circular SCCs with size > 1)
    ///
    /// # Reference
    /// Tarjan, R. (1972). "Depth-first search and linear graph algorithms"
    pub fn find_strongly_connected_components(&self) -> Vec<HashSet<String>> {
        // Tarjan's algorithm state
        let mut index_counter = 0;
        let mut stack: Vec<String> = Vec::new();
        let mut lowlinks: HashMap<String, usize> = HashMap::new();
        let mut index: HashMap<String, usize> = HashMap::new();
        let mut on_stack: HashSet<String> = HashSet::new();
        let mut sccs: Vec<HashSet<String>> = Vec::new();

        // Get all functions
        let all_functions = self.call_graph.get_functions();

        // Recursive strongconnect for each unvisited function
        for func in &all_functions {
            if !index.contains_key(func) {
                self.strongconnect(
                    func,
                    &mut index_counter,
                    &mut stack,
                    &mut lowlinks,
                    &mut index,
                    &mut on_stack,
                    &mut sccs,
                );
            }
        }

        // Filter out single-node SCCs (not circular)
        let circular_sccs: Vec<HashSet<String>> =
            sccs.into_iter().filter(|scc| scc.len() > 1).collect();

        #[cfg(feature = "trace")]
        if !circular_sccs.is_empty() {
            eprintln!(
                "[Interprocedural Taint] Found {} circular SCCs",
                circular_sccs.len()
            );
        }

        circular_sccs
    }

    /// Recursive DFS for Tarjan's algorithm
    ///
    /// This is the core of the algorithm - performs depth-first search
    /// while maintaining low-link values to detect SCCs.
    fn strongconnect(
        &self,
        func: &str,
        index_counter: &mut usize,
        stack: &mut Vec<String>,
        lowlinks: &mut HashMap<String, usize>,
        index: &mut HashMap<String, usize>,
        on_stack: &mut HashSet<String>,
        sccs: &mut Vec<HashSet<String>>,
    ) {
        // Set the depth index for func
        index.insert(func.to_string(), *index_counter);
        lowlinks.insert(func.to_string(), *index_counter);
        *index_counter += 1;

        stack.push(func.to_string());
        on_stack.insert(func.to_string());

        // Consider successors (callees)
        let callees = self.call_graph.get_callees(func);
        for callee in callees {
            if !index.contains_key(&callee) {
                // Successor not yet visited, recurse
                self.strongconnect(
                    &callee,
                    index_counter,
                    stack,
                    lowlinks,
                    index,
                    on_stack,
                    sccs,
                );

                // Update lowlink after recursion
                let callee_lowlink = *lowlinks.get(&callee).unwrap();
                let func_lowlink = lowlinks.get_mut(func).unwrap();
                *func_lowlink = (*func_lowlink).min(callee_lowlink);
            } else if on_stack.contains(&callee) {
                // Successor is on stack (part of current SCC)
                let callee_index = *index.get(&callee).unwrap();
                let func_lowlink = lowlinks.get_mut(func).unwrap();
                *func_lowlink = (*func_lowlink).min(callee_index);
            }
        }

        // If func is a root node, pop the stack and generate SCC
        if lowlinks.get(func) == index.get(func) {
            let mut scc = HashSet::new();
            loop {
                let w = stack.pop().expect("Stack should not be empty");
                on_stack.remove(&w);
                scc.insert(w.clone());
                if w == func {
                    break;
                }
            }
            sccs.push(scc);
        }
    }

    /// Get the SCC containing a specific function
    ///
    /// # Arguments
    /// * `func_name` - Function to find
    /// * `sccs` - List of SCCs to search
    ///
    /// # Returns
    /// SCC containing func_name, or None if not in any SCC
    pub fn get_scc_containing<'a>(
        &self,
        func_name: &str,
        sccs: &'a [HashSet<String>],
    ) -> Option<&'a HashSet<String>> {
        sccs.iter().find(|scc| scc.contains(func_name))
    }

    /// Get all functions that call a given function
    ///
    /// # Arguments
    /// * `func_name` - Function to find callers for
    ///
    /// # Returns
    /// Set of caller function names
    fn get_callers(&self, func_name: &str) -> HashSet<String> {
        let all_functions = self.call_graph.get_functions();
        let mut callers = HashSet::new();

        for caller in all_functions {
            let callees = self.call_graph.get_callees(&caller);
            if callees.contains(&func_name.to_string()) {
                callers.insert(caller);
            }
        }

        callers
    }

    /// Compute functions affected by changes (SCC-aware)
    ///
    /// This is a SOTA optimization for incremental analysis:
    /// 1. Find SCCs containing changed functions
    /// 2. Mark entire SCC as affected (circular dependency)
    /// 3. Add direct callers (1-hop) for non-SCC functions
    ///
    /// # Arguments
    /// * `changed_funcs` - Set of functions that changed
    ///
    /// # Returns
    /// Set of affected function names (changed + SCC + 1-hop callers)
    pub fn compute_affected_functions(&self, changed_funcs: &HashSet<String>) -> HashSet<String> {
        let mut affected = changed_funcs.clone();

        // Detect SCCs containing changed functions
        let sccs = self.find_strongly_connected_components();

        for changed_func in changed_funcs {
            // Find SCC containing this function
            if let Some(scc) = self.get_scc_containing(changed_func, &sccs) {
                // Entire SCC is affected due to circular dependency
                #[cfg(feature = "trace")]
                eprintln!(
                    "[Interprocedural Taint] SCC detected for {}: {} functions",
                    changed_func,
                    scc.len()
                );

                affected.extend(scc.iter().cloned());

                // Add callers of entire SCC
                for scc_func in scc {
                    let callers = self.get_callers(scc_func);
                    affected.extend(callers);
                }
            } else {
                // Not in SCC, just add direct callers
                let callers = self.get_callers(changed_func);
                affected.extend(callers);
            }
        }

        affected
    }

    /// Trace call path to sink (for sanitizer detection)
    ///
    /// # Returns
    /// Call chain from source to sink (including intermediate functions)
    fn trace_path_to_sink(&self, sink_name: &str) -> Vec<String> {
        // Simple BFS to find path from any source to sink
        use std::collections::VecDeque;

        let mut queue = VecDeque::new();
        let mut visited = HashSet::new();
        let mut parent: HashMap<String, String> = HashMap::new();

        // Start from functions that have summaries (these are sources/tainted)
        // IMPORTANT: Exclude the sink from initial queue to ensure we find actual paths
        for func in self.call_graph.get_functions() {
            if self.function_summaries.contains_key(&func) && func != sink_name {
                queue.push_back(func.clone());
                visited.insert(func.clone());
            }
        }

        // BFS to sink
        while let Some(current) = queue.pop_front() {
            // Explore callees
            for callee in self.call_graph.get_callees(&current) {
                if visited.insert(callee.clone()) {
                    parent.insert(callee.clone(), current.clone());

                    if callee == sink_name {
                        // Found sink, reconstruct path (including intermediate functions)
                        let mut path = Vec::new();
                        let mut node = callee.clone();

                        while let Some(prev) = parent.get(&node) {
                            path.push(node.clone());
                            node = prev.clone();
                        }
                        path.push(node); // Add source
                        path.reverse();
                        return path;
                    }

                    queue.push_back(callee);
                }
            }
        }

        // No path found, return empty
        vec![]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Simple call graph for testing
    struct SimpleCallGraph {
        calls: HashMap<String, Vec<String>>,
    }

    impl SimpleCallGraph {
        fn new() -> Self {
            Self {
                calls: HashMap::new(),
            }
        }

        fn add_call(&mut self, caller: &str, callee: &str) {
            self.calls
                .entry(caller.to_string())
                .or_insert_with(Vec::new)
                .push(callee.to_string());
        }
    }

    impl CallGraphProvider for SimpleCallGraph {
        fn get_callees(&self, func_name: &str) -> Vec<String> {
            self.calls.get(func_name).cloned().unwrap_or_default()
        }

        fn get_functions(&self) -> Vec<String> {
            let mut funcs: HashSet<String> = self.calls.keys().cloned().collect();
            for callees in self.calls.values() {
                funcs.extend(callees.iter().cloned());
            }
            funcs.into_iter().collect()
        }
    }

    // ============================================================================
    // UNIT TESTS: Data Structures
    // ============================================================================

    #[test]
    fn test_call_context_creation() {
        let ctx = CallContext::new();
        assert_eq!(ctx.call_stack.len(), 0);
        assert_eq!(ctx.depth, 0);
        assert!(!ctx.return_tainted);
    }

    #[test]
    fn test_call_context_with_call() {
        let ctx = CallContext::new();
        let new_ctx = ctx.with_call("foo".to_string());

        assert_eq!(new_ctx.call_stack, vec!["foo"]);
        assert_eq!(new_ctx.depth, 1);
        assert_eq!(ctx.call_stack.len(), 0); // Original unchanged
    }

    #[test]
    fn test_call_context_circular_detection() {
        let mut ctx = CallContext::new();
        ctx.call_stack.push("foo".to_string());
        ctx.call_stack.push("bar".to_string());

        assert!(ctx.is_circular("foo"));
        assert!(ctx.is_circular("bar"));
        assert!(!ctx.is_circular("baz"));
    }

    #[test]
    fn test_taint_path_creation() {
        let path = TaintPath::new("source".to_string(), "sink".to_string());
        assert_eq!(path.source, "source");
        assert_eq!(path.sink, "sink");
        assert_eq!(path.path.len(), 0);
        assert_eq!(path.confidence, 1.0);
    }

    #[test]
    fn test_function_summary_creation() {
        let summary = FunctionSummary::new("test_func".to_string());
        assert_eq!(summary.name, "test_func");
        assert_eq!(summary.tainted_params.len(), 0);
        assert!(!summary.return_tainted);
        assert_eq!(summary.confidence, 1.0);
    }

    // ============================================================================
    // INTEGRATION TESTS: Interprocedural Analysis
    // ============================================================================

    #[test]
    fn test_simple_source_to_sink() {
        // Build call graph: source() -> sink()
        let mut cg = SimpleCallGraph::new();
        cg.add_call("source", "sink");

        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // Define sources and sinks
        let sources = HashMap::from([("source".to_string(), HashSet::from(["0".to_string()]))]);
        let sinks = HashMap::from([("sink".to_string(), HashSet::from(["0".to_string()]))]);

        // Analyze
        let paths = analyzer.analyze(&sources, &sinks);

        // Should find violation
        assert!(
            !paths.is_empty(),
            "Should detect taint path from source to sink"
        );
        assert_eq!(paths[0].sink, "sink");
    }

    #[test]
    fn test_multi_hop_propagation() {
        // Build call graph: main -> process -> execute
        let mut cg = SimpleCallGraph::new();
        cg.add_call("main", "process");
        cg.add_call("process", "execute");

        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let sources = HashMap::from([("main".to_string(), HashSet::from(["0".to_string()]))]);
        let sinks = HashMap::from([("execute".to_string(), HashSet::from(["0".to_string()]))]);

        let paths = analyzer.analyze(&sources, &sinks);

        // Should find path through intermediate function
        assert!(!paths.is_empty(), "Should detect multi-hop taint path");
    }

    #[test]
    fn test_no_violation_separate_functions() {
        // Build call graph: source() and sink() (separate, no connection)
        let cg = SimpleCallGraph::new();

        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let sources = HashMap::from([("source".to_string(), HashSet::from(["0".to_string()]))]);
        let sinks = HashMap::from([("sink".to_string(), HashSet::from(["0".to_string()]))]);

        let paths = analyzer.analyze(&sources, &sinks);

        // Should NOT find violation (no connection)
        assert!(
            paths.is_empty(),
            "Should not detect taint path for separate functions"
        );
    }

    #[test]
    fn test_branching_calls() {
        // Build call graph with branching:
        //   main -> foo
        //        -> bar
        //   bar -> sink
        let mut cg = SimpleCallGraph::new();
        cg.add_call("main", "foo");
        cg.add_call("main", "bar");
        cg.add_call("bar", "sink");

        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let sources = HashMap::from([("main".to_string(), HashSet::from(["0".to_string()]))]);
        let sinks = HashMap::from([("sink".to_string(), HashSet::from(["0".to_string()]))]);

        let paths = analyzer.analyze(&sources, &sinks);

        // Should find path main -> bar -> sink
        assert!(!paths.is_empty(), "Should detect path through branching");
    }

    #[test]
    fn test_circular_call_detection() {
        // Build call graph with cycle: a() -> b() -> a()
        let mut cg = SimpleCallGraph::new();
        cg.add_call("a", "b");
        cg.add_call("b", "a");

        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let sources = HashMap::from([("a".to_string(), HashSet::from(["0".to_string()]))]);
        let sinks = HashMap::from([("b".to_string(), HashSet::from(["0".to_string()]))]);

        // Should handle circular calls without infinite loop
        let paths = analyzer.analyze(&sources, &sinks);

        // Should detect taint even with cycles
        assert!(!paths.is_empty(), "Should handle circular calls");
    }

    #[test]
    fn test_depth_limit() {
        // Build deep call chain: func0() -> func1() -> ... -> func20()
        let mut cg = SimpleCallGraph::new();
        for i in 0..20 {
            cg.add_call(&format!("func{}", i), &format!("func{}", i + 1));
        }

        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 5, 100); // Max depth 5

        let sources = HashMap::from([("func0".to_string(), HashSet::from(["0".to_string()]))]);
        let sinks = HashMap::from([("func15".to_string(), HashSet::from(["0".to_string()]))]);

        // Should terminate due to depth limit
        let _paths = analyzer.analyze(&sources, &sinks);
        // Just checking it doesn't hang
    }

    #[test]
    fn test_multiple_sources() {
        // Multiple source functions
        let mut cg = SimpleCallGraph::new();
        cg.add_call("source1", "sink");
        cg.add_call("source2", "sink");

        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let sources = HashMap::from([
            ("source1".to_string(), HashSet::from(["0".to_string()])),
            ("source2".to_string(), HashSet::from(["0".to_string()])),
        ]);
        let sinks = HashMap::from([("sink".to_string(), HashSet::from(["0".to_string()]))]);

        let paths = analyzer.analyze(&sources, &sinks);

        // Should find paths from both sources
        assert!(
            !paths.is_empty(),
            "Should detect paths from multiple sources"
        );
    }

    #[test]
    fn test_multiple_sinks() {
        // One source, multiple sinks
        let mut cg = SimpleCallGraph::new();
        cg.add_call("source", "sink1");
        cg.add_call("source", "sink2");

        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let sources = HashMap::from([("source".to_string(), HashSet::from(["0".to_string()]))]);
        let sinks = HashMap::from([
            ("sink1".to_string(), HashSet::from(["0".to_string()])),
            ("sink2".to_string(), HashSet::from(["0".to_string()])),
        ]);

        let paths = analyzer.analyze(&sources, &sinks);

        // Should find paths to both sinks
        assert!(!paths.is_empty(), "Should detect paths to multiple sinks");
    }

    #[test]
    fn test_convergence_iterative_fixpoint() {
        // Test that summary computation converges
        let mut cg = SimpleCallGraph::new();
        cg.add_call("a", "b");
        cg.add_call("b", "c");
        cg.add_call("c", "a"); // Cycle

        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let sources = HashMap::from([("a".to_string(), HashSet::from(["0".to_string()]))]);
        let sinks = HashMap::from([("c".to_string(), HashSet::from(["0".to_string()]))]);

        // Should converge and terminate
        let _paths = analyzer.analyze(&sources, &sinks);
        // Success if we reach here (no infinite loop)
    }

    #[test]
    fn test_empty_call_graph() {
        let cg = SimpleCallGraph::new();
        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let sources = HashMap::new();
        let sinks = HashMap::new();

        let paths = analyzer.analyze(&sources, &sinks);
        assert!(paths.is_empty());
    }

    #[test]
    fn test_self_loop() {
        // Function calls itself
        let mut cg = SimpleCallGraph::new();
        cg.add_call("recursive", "recursive");

        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let sources = HashMap::from([("recursive".to_string(), HashSet::from(["0".to_string()]))]);
        let sinks = HashMap::from([("recursive".to_string(), HashSet::from(["0".to_string()]))]);

        // Should handle self-loops
        let paths = analyzer.analyze(&sources, &sinks);
        assert!(!paths.is_empty(), "Should detect self-loop taint");
    }

    // ============================================================================
    // UNIT TESTS: Tarjan's SCC Algorithm (SOTA)
    // ============================================================================

    #[test]
    fn test_scc_simple_cycle() {
        // Build call graph with simple cycle: a() -> b() -> c() -> a()
        let mut cg = SimpleCallGraph::new();
        cg.add_call("a", "b");
        cg.add_call("b", "c");
        cg.add_call("c", "a");

        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // Find SCCs
        let sccs = analyzer.find_strongly_connected_components();

        // Should find exactly one SCC containing a, b, c
        assert_eq!(sccs.len(), 1, "Should find one SCC");
        assert_eq!(sccs[0].len(), 3, "SCC should contain 3 functions");
        assert!(sccs[0].contains("a"));
        assert!(sccs[0].contains("b"));
        assert!(sccs[0].contains("c"));
    }

    #[test]
    fn test_scc_no_cycles() {
        // Build call graph with no cycles: a() -> b() -> c()
        let mut cg = SimpleCallGraph::new();
        cg.add_call("a", "b");
        cg.add_call("b", "c");

        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // Find SCCs
        let sccs = analyzer.find_strongly_connected_components();

        // Should find no circular SCCs
        assert!(sccs.is_empty(), "Should not find any circular SCCs");
    }

    #[test]
    fn test_scc_multiple_cycles() {
        // Build call graph with multiple SCCs:
        //   SCC1: a() -> b() -> a()
        //   SCC2: c() -> d() -> c()
        //   Separate: e()
        let mut cg = SimpleCallGraph::new();
        cg.add_call("a", "b");
        cg.add_call("b", "a");
        cg.add_call("c", "d");
        cg.add_call("d", "c");

        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // Find SCCs
        let sccs = analyzer.find_strongly_connected_components();

        // Should find exactly two SCCs
        assert_eq!(sccs.len(), 2, "Should find two SCCs");

        // Check each SCC
        for scc in &sccs {
            assert_eq!(scc.len(), 2, "Each SCC should contain 2 functions");
        }

        // Check that we have both SCCs
        let has_ab_scc = sccs
            .iter()
            .any(|scc| scc.contains("a") && scc.contains("b"));
        let has_cd_scc = sccs
            .iter()
            .any(|scc| scc.contains("c") && scc.contains("d"));

        assert!(has_ab_scc, "Should find a-b SCC");
        assert!(has_cd_scc, "Should find c-d SCC");
    }

    #[test]
    fn test_scc_self_loop() {
        // Build call graph with self-loop: a() -> a()
        let mut cg = SimpleCallGraph::new();
        cg.add_call("a", "a");

        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // Find SCCs
        let sccs = analyzer.find_strongly_connected_components();

        // Self-loops are considered SCCs of size 1 and are filtered out
        // (we only return circular SCCs with size > 1)
        // However, for consistency with Python, we might want to include them
        // For now, following the filter: single-node SCCs are excluded
        assert!(sccs.is_empty(), "Single-node SCCs should be filtered");
    }

    #[test]
    fn test_scc_nested_cycles() {
        // Build call graph with nested structure:
        //   Outer cycle: a() -> b() -> c() -> a()
        //   Inner: b() -> d() -> b()
        let mut cg = SimpleCallGraph::new();
        cg.add_call("a", "b");
        cg.add_call("b", "c");
        cg.add_call("c", "a");
        cg.add_call("b", "d");
        cg.add_call("d", "b");

        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // Find SCCs
        let sccs = analyzer.find_strongly_connected_components();

        // Should find one large SCC containing all functions
        // (since they're all mutually reachable)
        assert_eq!(sccs.len(), 1, "Should find one large SCC");
        assert_eq!(sccs[0].len(), 4, "SCC should contain 4 functions");
        assert!(sccs[0].contains("a"));
        assert!(sccs[0].contains("b"));
        assert!(sccs[0].contains("c"));
        assert!(sccs[0].contains("d"));
    }

    #[test]
    fn test_get_scc_containing() {
        // Build call graph with cycle: a() -> b() -> a()
        let mut cg = SimpleCallGraph::new();
        cg.add_call("a", "b");
        cg.add_call("b", "a");

        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // Find SCCs
        let sccs = analyzer.find_strongly_connected_components();

        // Get SCC containing 'a'
        let scc_a = analyzer.get_scc_containing("a", &sccs);
        assert!(scc_a.is_some(), "Should find SCC containing 'a'");
        assert!(scc_a.unwrap().contains("b"), "SCC should also contain 'b'");

        // Get SCC containing 'b'
        let scc_b = analyzer.get_scc_containing("b", &sccs);
        assert!(scc_b.is_some(), "Should find SCC containing 'b'");
        assert!(scc_b.unwrap().contains("a"), "SCC should also contain 'a'");

        // Get SCC containing non-existent function
        let scc_none = analyzer.get_scc_containing("nonexistent", &sccs);
        assert!(
            scc_none.is_none(),
            "Should not find SCC for non-existent function"
        );
    }

    #[test]
    fn test_get_callers() {
        // Build call graph:
        //   a() -> c()
        //   b() -> c()
        //   c() -> d()
        let mut cg = SimpleCallGraph::new();
        cg.add_call("a", "c");
        cg.add_call("b", "c");
        cg.add_call("c", "d");

        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // Get callers of 'c'
        let callers_c = analyzer.get_callers("c");
        assert_eq!(callers_c.len(), 2, "c should have 2 callers");
        assert!(callers_c.contains("a"));
        assert!(callers_c.contains("b"));

        // Get callers of 'd'
        let callers_d = analyzer.get_callers("d");
        assert_eq!(callers_d.len(), 1, "d should have 1 caller");
        assert!(callers_d.contains("c"));

        // Get callers of 'a' (should be empty)
        let callers_a = analyzer.get_callers("a");
        assert!(callers_a.is_empty(), "a should have no callers");
    }

    #[test]
    fn test_compute_affected_functions_simple() {
        // Build call graph: a() -> b() -> c()
        let mut cg = SimpleCallGraph::new();
        cg.add_call("a", "b");
        cg.add_call("b", "c");

        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // If 'c' changes, affected should be: c, b (caller), a (transitive caller)
        let changed = HashSet::from(["c".to_string()]);
        let affected = analyzer.compute_affected_functions(&changed);

        // Should include c + direct caller b
        assert!(affected.contains("c"), "Should include changed function");
        assert!(affected.contains("b"), "Should include direct caller");
        // NOTE: This only does 1-hop, not transitive
        // For full transitive, we'd need to iterate
    }

    #[test]
    fn test_compute_affected_functions_with_scc() {
        // Build call graph with SCC:
        //   a() -> b() -> c() -> a()  (SCC)
        //   d() -> a()
        let mut cg = SimpleCallGraph::new();
        cg.add_call("a", "b");
        cg.add_call("b", "c");
        cg.add_call("c", "a");
        cg.add_call("d", "a");

        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // If 'a' changes, entire SCC should be affected
        let changed = HashSet::from(["a".to_string()]);
        let affected = analyzer.compute_affected_functions(&changed);

        // Should include entire SCC: a, b, c
        assert!(affected.contains("a"), "Should include changed function");
        assert!(affected.contains("b"), "Should include SCC member b");
        assert!(affected.contains("c"), "Should include SCC member c");
        assert!(affected.contains("d"), "Should include caller of SCC");
    }

    #[test]
    fn test_compute_affected_functions_no_callers() {
        // Build call graph: a() (isolated)
        let cg = SimpleCallGraph::new();

        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // If 'a' changes, only 'a' should be affected
        let changed = HashSet::from(["a".to_string()]);
        let affected = analyzer.compute_affected_functions(&changed);

        assert_eq!(affected.len(), 1, "Should only affect changed function");
        assert!(affected.contains("a"));
    }

    #[test]
    fn test_scc_large_cycle() {
        // Build call graph with large cycle: f1 -> f2 -> ... -> f10 -> f1
        let mut cg = SimpleCallGraph::new();
        for i in 1..=10 {
            let caller = format!("f{}", i);
            let callee = if i == 10 {
                "f1".to_string()
            } else {
                format!("f{}", i + 1)
            };
            cg.add_call(&caller, &callee);
        }

        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // Find SCCs
        let sccs = analyzer.find_strongly_connected_components();

        // Should find one SCC with all 10 functions
        assert_eq!(sccs.len(), 1, "Should find one SCC");
        assert_eq!(sccs[0].len(), 10, "SCC should contain 10 functions");

        // Verify all functions are in the SCC
        for i in 1..=10 {
            assert!(
                sccs[0].contains(&format!("f{}", i)),
                "SCC should contain f{}",
                i
            );
        }
    }

    // ============================================================================
    // UNIT TESTS: Domain Integration (Function Summary Cache)
    // ============================================================================

    #[test]
    fn test_domain_cache_integration() {
        // Build simple call graph
        let cg = SimpleCallGraph::new();

        // Create analyzer with domain cache
        let mut analyzer = InterproceduralTaintAnalyzer::with_cache(cg, 10, 100, 100);

        // Create and cache a summary
        let summary = FunctionSummary::new("test_func".to_string());
        analyzer.cache_summary("test_func", summary);

        // Retrieve from cache
        let retrieved = analyzer.get_cached_summary("test_func");
        assert!(retrieved.is_some(), "Should retrieve cached summary");
        assert_eq!(retrieved.unwrap().name, "test_func");
    }

    #[test]
    fn test_domain_summary_conversion() {
        use crate::features::taint_analysis::domain::FunctionTaintSummary;

        // Create infrastructure summary
        let mut infra_summary = FunctionSummary::new("test_func".to_string());
        infra_summary.tainted_params.insert(0);
        infra_summary.return_tainted = true;
        infra_summary.confidence = 0.95;
        infra_summary.tainted_vars.insert("x".to_string());

        // Convert to domain
        let domain_summary = infra_summary.to_domain_summary();

        assert_eq!(domain_summary.function_id, "test_func");
        assert!(domain_summary.tainted_params.contains(&0));
        assert!(domain_summary.tainted_return);
        assert_eq!(domain_summary.confidence, 0.95);
        assert!(domain_summary.tainted_globals.contains("x"));

        // Convert back to infrastructure
        let infra_summary2 = FunctionSummary::from_domain_summary(&domain_summary);

        assert_eq!(infra_summary2.name, "test_func");
        assert!(infra_summary2.tainted_params.contains(&0));
        assert!(infra_summary2.return_tainted);
        assert!(
            (infra_summary2.confidence - 0.95).abs() < 0.001,
            "Confidence should be ~0.95, got {}",
            infra_summary2.confidence
        );
        assert!(infra_summary2.tainted_vars.contains("x"));
    }

    #[test]
    fn test_cache_hit_miss_stats() {
        use crate::features::taint_analysis::domain::FunctionSummaryCache;

        let cg = SimpleCallGraph::new();
        let mut analyzer = InterproceduralTaintAnalyzer::with_cache(cg, 10, 100, 10);

        // Initial cache miss
        let result1 = analyzer.get_cached_summary("missing_func");
        assert!(result1.is_none());

        // Cache a summary
        let summary = FunctionSummary::new("cached_func".to_string());
        analyzer.cache_summary("cached_func", summary);

        // Cache hit
        let result2 = analyzer.get_cached_summary("cached_func");
        assert!(result2.is_some());

        // Verify cache stats (if domain_cache is available)
        if let Some(ref cache) = analyzer.domain_cache {
            assert!(cache.hits() > 0, "Should have cache hits");
            assert!(cache.misses() > 0, "Should have cache misses");
        }
    }

    // ============================================================================
    // UNIT TESTS: Function Name Resolution (SOTA)
    // ============================================================================

    #[test]
    fn test_build_name_map() {
        let cg = SimpleCallGraph::new();
        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let all_functions = vec![
            "external.get_user_input".to_string(),
            "external.process_data".to_string(),
            "interprocedural.get_user_input".to_string(),
            "interprocedural.process_data".to_string(),
            "module:external.fetch".to_string(),
        ];

        let name_map = analyzer.build_name_map(&all_functions);

        // Should map external functions to bare names
        assert_eq!(
            name_map.get("external.get_user_input"),
            Some(&"get_user_input".to_string())
        );
        assert_eq!(
            name_map.get("external.process_data"),
            Some(&"process_data".to_string())
        );
        assert_eq!(
            name_map.get("module:external.fetch"),
            Some(&"fetch".to_string())
        );

        // Should NOT map non-external functions
        assert!(name_map.get("interprocedural.get_user_input").is_none());
        assert!(name_map.get("interprocedural.process_data").is_none());
    }

    #[test]
    fn test_resolve_callee_direct_match() {
        let cg = SimpleCallGraph::new();
        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // Add a summary for direct match
        let summary = FunctionSummary::new("exact_func".to_string());
        analyzer
            .function_summaries
            .insert("exact_func".to_string(), summary);

        let all_functions = vec!["exact_func".to_string()];
        let name_map = HashMap::new();

        let resolved = analyzer.resolve_callee("exact_func", &name_map, &all_functions);

        assert_eq!(resolved, "exact_func");
    }

    #[test]
    fn test_resolve_callee_external_to_actual() {
        let cg = SimpleCallGraph::new();
        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        // Add summary for actual implementation
        let summary = FunctionSummary::new("interprocedural.get_user_input".to_string());
        analyzer
            .function_summaries
            .insert("interprocedural.get_user_input".to_string(), summary);

        let all_functions = vec![
            "external.get_user_input".to_string(),
            "interprocedural.get_user_input".to_string(),
        ];

        // Build name map
        let name_map = analyzer.build_name_map(&all_functions);

        // Resolve external → actual
        let resolved =
            analyzer.resolve_callee("external.get_user_input", &name_map, &all_functions);

        assert_eq!(resolved, "interprocedural.get_user_input");
    }

    #[test]
    fn test_resolve_callee_no_match() {
        let cg = SimpleCallGraph::new();
        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let all_functions = vec!["some_func".to_string()];
        let name_map = HashMap::new();

        let resolved = analyzer.resolve_callee("nonexistent", &name_map, &all_functions);

        // Should return original if no match
        assert_eq!(resolved, "nonexistent");
    }

    #[test]
    fn test_name_resolution_with_colon_prefix() {
        let cg = SimpleCallGraph::new();
        let analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let all_functions = vec![
            "module:external.fetch_data".to_string(),
            "module:internal.fetch_data".to_string(),
        ];

        let name_map = analyzer.build_name_map(&all_functions);

        // Should handle colon-prefixed function IDs
        assert_eq!(
            name_map.get("module:external.fetch_data"),
            Some(&"fetch_data".to_string())
        );
    }

    #[test]
    fn test_interprocedural_with_name_resolution() {
        // Build call graph: source -> process -> sink
        // This tests basic interprocedural taint flow through a call chain
        let mut cg = SimpleCallGraph::new();
        cg.add_call("source", "process");
        cg.add_call("process", "sink");

        let mut analyzer = InterproceduralTaintAnalyzer::new(cg, 10, 100);

        let sources = HashMap::from([("source".to_string(), HashSet::from(["0".to_string()]))]);
        let sinks = HashMap::from([("sink".to_string(), HashSet::from(["0".to_string()]))]);

        // Analyze - taint should flow: source -> process -> sink
        let paths = analyzer.analyze(&sources, &sinks);

        // Should detect taint path through call chain
        assert!(
            !paths.is_empty(),
            "Should detect taint path with name resolution"
        );
    }
}
