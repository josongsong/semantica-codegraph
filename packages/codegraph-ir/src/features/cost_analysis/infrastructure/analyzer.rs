//! Cost Analyzer (RFC-028 Phase 1)
//!
//! Main entry point for cost analysis.
//!
//! Architecture: Infrastructure Layer (Hexagonal)
//! Dependencies: CFG (Control Flow Graph)
//!
//! Algorithm:
//! 1. Find loops (LOOP_HEADER blocks or back edges in CFG)
//! 2. Infer bounds from loop patterns
//! 3. Calculate complexity
//! 4. Generate CostResult
//!
//! Production:
//! - NO Fake/Stub
//! - CFG-based loop detection

use crate::features::cost_analysis::domain::{
    BoundResult, ComplexityClass, CostResult, Hotspot, InferenceMethod, Verdict,
};
use crate::features::cost_analysis::infrastructure::complexity_calculator::ComplexityCalculator;
use crate::features::flow_graph::domain::{CFGBlock, CFGEdge, CFGEdgeKind};
use crate::shared::models::{Node, NodeKind};
use std::collections::{HashMap, HashSet, VecDeque};

/// Cost Analyzer (RFC-028 Main Entry)
///
/// Responsibilities:
/// - Find loops in CFG
/// - Infer bounds using pattern matching
/// - Generate CostResult
///
/// NOT Responsible For:
/// - CFG generation (FlowGraphBuilder)
/// - Complexity classification (ComplexityCalculator)
///
/// Performance:
/// - Target: <10ms per function
/// - O(CFG blocks + edges)
pub struct CostAnalyzer {
    complexity_calc: ComplexityCalculator,
    cache: Option<HashMap<String, CostResult>>,
}

impl CostAnalyzer {
    /// Create new cost analyzer
    pub fn new(enable_cache: bool) -> Self {
        tracing::info!("cost_analyzer_initialized (cache={})", enable_cache);

        Self {
            complexity_calc: ComplexityCalculator::new(),
            cache: if enable_cache {
                Some(HashMap::new())
            } else {
                None
            },
        }
    }

    /// Analyze function cost
    ///
    /// Args:
    ///     nodes: IR nodes (must include function node)
    ///     cfg_blocks: CFG blocks for the function
    ///     cfg_edges: CFG edges
    ///     function_fqn: Function fully qualified name
    ///
    /// Returns:
    ///     CostResult
    pub fn analyze_function(
        &mut self,
        nodes: &[Node],
        cfg_blocks: &[CFGBlock],
        cfg_edges: &[CFGEdge],
        function_fqn: &str,
    ) -> Result<CostResult, String> {
        // Cache check
        if let Some(cache) = &self.cache {
            if let Some(result) = cache.get(function_fqn) {
                tracing::debug!("Cost cache hit: {}", function_fqn);
                return Ok(result.clone());
            }
        }

        tracing::info!("Analyzing cost: {}", function_fqn);

        // Find function node
        let func_node = self.find_function_node(nodes, function_fqn)?;

        // Find function's CFG blocks
        // Note: function_node_id can be either the node ID or function name depending on pipeline
        let func_blocks: Vec<&CFGBlock> = cfg_blocks
            .iter()
            .filter(|b| {
                b.function_node_id.as_ref().map_or(false, |id| {
                    // Match by node ID (hash) or function name
                    id == &func_node.id || func_node.name.as_ref().map_or(false, |name| id == name)
                })
            })
            .collect();

        if func_blocks.is_empty() {
            let result = self.create_constant_result(func_node);
            self.cache_result(function_fqn, &result);
            return Ok(result);
        }

        // Find loop blocks (back edges in CFG)
        let loop_blocks = self.find_loop_blocks(&func_blocks, cfg_edges);

        if loop_blocks.is_empty() {
            let result = self.create_constant_result(func_node);
            self.cache_result(function_fqn, &result);
            return Ok(result);
        }

        // Infer loop bounds
        let loop_bounds = self.infer_loop_bounds(&loop_blocks, nodes);

        // Determine nesting levels
        let nesting_levels = self.determine_nesting_levels(&func_blocks, cfg_edges);

        // Calculate complexity
        let (complexity, confidence, cost_term) = self
            .complexity_calc
            .calculate(&loop_bounds, &nesting_levels);

        // Overall verdict
        let verdict = self.determine_verdict(&loop_bounds);

        // Explanation
        let explanation = self.generate_explanation(complexity, verdict, loop_bounds.len());

        // Hotspots
        let hotspots = self.find_hotspots(&loop_blocks);

        // Create result
        let result = CostResult {
            function_fqn: function_fqn.to_string(),
            complexity,
            verdict,
            confidence,
            explanation,
            loop_bounds,
            hotspots,
            metadata: serde_json::json!({
                "cost_term": cost_term,
            }),
        };

        self.cache_result(function_fqn, &result);

        tracing::info!(
            "Cost analysis complete: {} → {} ({})",
            function_fqn,
            complexity.as_str(),
            verdict.as_str()
        );

        Ok(result)
    }

    /// Find function node by FQN
    fn find_function_node<'a>(
        &self,
        nodes: &'a [Node],
        function_fqn: &str,
    ) -> Result<&'a Node, String> {
        nodes
            .iter()
            .find(|n| {
                matches!(n.kind, NodeKind::Function | NodeKind::Method) && n.fqn == function_fqn
            })
            .ok_or_else(|| format!("Function not found: {}", function_fqn))
    }

    /// Find loop blocks using back edges in CFG
    ///
    /// A back edge (target → source where source dominates target) indicates a loop.
    /// Simplified: LoopBack edge kind
    fn find_loop_blocks<'a>(
        &self,
        cfg_blocks: &[&'a CFGBlock],
        cfg_edges: &[CFGEdge],
    ) -> Vec<&'a CFGBlock> {
        let mut loop_headers = HashSet::new();

        // Find LoopBack edges
        for edge in cfg_edges {
            if edge.kind == CFGEdgeKind::LoopBack {
                loop_headers.insert(&edge.target_block_id);
            }
        }

        // Also check block kind (if available)
        cfg_blocks
            .iter()
            .filter(|b| {
                loop_headers.contains(&b.id)
                    || b.kind
                        .as_ref()
                        .map_or(false, |k| k == "LOOP_HEADER" || k == "LoopHeader")
            })
            .copied()
            .collect()
    }

    /// Infer loop bounds from loop blocks
    ///
    /// Supported patterns:
    /// 1. for-in range → infer from range (Phase 2 with Expression IR)
    /// 2. for-in collection → len(collection)
    /// 3. while → heuristic
    ///
    /// Current (Phase 1): Simple pattern matching on statements
    fn infer_loop_bounds(&self, loop_blocks: &[&CFGBlock], _nodes: &[Node]) -> Vec<BoundResult> {
        loop_blocks
            .iter()
            .map(|block| {
                // Phase 1: Simple heuristic based on statements
                // ROADMAP(Phase 2): Parse statements for range() extraction
                // - Current: Heuristic-based bound detection
                // - Improvement: AST parsing for `for i in range(n)` patterns
                // - Status: Working, precision improvement planned

                let bound = if block.statements.is_empty() {
                    "unknown".to_string()
                } else {
                    // Try to infer from first statement
                    let stmt = &block.statements[0];

                    if stmt.contains("range") {
                        // range(n) or range(start, end)
                        self.extract_range_bound(stmt)
                    } else if stmt.contains("in ") {
                        // for item in collection
                        "len(collection)".to_string()
                    } else {
                        "unknown".to_string()
                    }
                };

                let (verdict, confidence, method) = if bound == "unknown" {
                    (Verdict::Heuristic, 0.3, InferenceMethod::Heuristic)
                } else if bound.starts_with("len(") {
                    (Verdict::Likely, 0.75, InferenceMethod::Pattern)
                } else {
                    (Verdict::Likely, 0.85, InferenceMethod::Pattern)
                };

                BoundResult::new(bound, verdict, confidence, method, block.id.clone())
                    .unwrap_or_else(|_| {
                        // SAFETY: confidence=0.3 is within valid range [0.0, 1.0]
                        // and verdict/method are consistent, so this unwrap is safe
                        BoundResult::new(
                            "unknown".to_string(),
                            Verdict::Heuristic,
                            0.3,
                            InferenceMethod::Heuristic,
                            block.id.clone(),
                        )
                        .unwrap()
                    })
                    .with_location(
                        // METADATA(v2): CFGBlock.file_path propagation
                        // - Current: "unknown" placeholder (cost analysis works, location limited)
                        // - Fix: Add file_path field to CFGBlock struct
                        "unknown".to_string(),
                        block
                            .span
                            .as_ref()
                            .map(|s| s.start_line as usize)
                            .unwrap_or(0),
                    )
            })
            .collect()
    }

    /// Extract bound from range() call (simple pattern matching)
    ///
    /// Examples:
    /// - "range(n)" → "n"
    /// - "range(0, 10)" → "10"
    /// - "range(start, end)" → "end"
    fn extract_range_bound(&self, stmt: &str) -> String {
        // Simple regex-free extraction
        if let Some(start) = stmt.find("range(") {
            let args_start = start + 6;
            if let Some(end) = stmt[args_start..].find(')') {
                let args = &stmt[args_start..args_start + end];
                let parts: Vec<&str> = args.split(',').map(|s| s.trim()).collect();

                // range(end) or range(start, end)
                if parts.len() == 1 {
                    parts[0].to_string()
                } else if parts.len() >= 2 {
                    parts[1].to_string()
                } else {
                    "n".to_string()
                }
            } else {
                "n".to_string()
            }
        } else {
            "n".to_string()
        }
    }

    /// Determine nesting levels using CFG topology
    ///
    /// Algorithm: BFS from entry block, count loops in path
    fn determine_nesting_levels(
        &self,
        cfg_blocks: &[&CFGBlock],
        cfg_edges: &[CFGEdge],
    ) -> HashMap<String, usize> {
        let mut levels = HashMap::new();

        if cfg_blocks.is_empty() {
            return levels;
        }

        // Build successors map
        let mut successors: HashMap<&str, Vec<&str>> = HashMap::new();
        for edge in cfg_edges {
            successors
                .entry(edge.source_block_id.as_str())
                .or_default()
                .push(edge.target_block_id.as_str());
        }

        // Find entry block
        let entry_block = cfg_blocks.iter().find(|b| {
            b.kind
                .as_ref()
                .map_or(false, |k| k == "Entry" || k == "ENTRY")
        });

        let entry_id = if let Some(entry) = entry_block {
            &entry.id
        } else {
            // No entry: assume first block
            if cfg_blocks.is_empty() {
                return levels;
            }
            &cfg_blocks[0].id
        };

        // Find loop block IDs
        let loop_ids: HashSet<_> = cfg_blocks
            .iter()
            .filter(|b| {
                b.kind
                    .as_ref()
                    .map_or(false, |k| k == "LOOP_HEADER" || k == "LoopHeader")
            })
            .map(|b| b.id.as_str())
            .collect();

        // BFS from entry
        let mut visited = HashSet::new();
        let mut queue = VecDeque::new();
        queue.push_back((entry_id.as_str(), 0_usize)); // (block_id, loops_in_path)

        const MAX_BFS_ITERATIONS: usize = 10000;
        let mut iterations = 0;

        while let Some((block_id, loops_in_path)) = queue.pop_front() {
            iterations += 1;
            if iterations >= MAX_BFS_ITERATIONS {
                tracing::error!(
                    "BFS timeout at {} iterations, CFG may have cycle",
                    iterations
                );
                break;
            }

            if visited.contains(block_id) {
                continue;
            }
            visited.insert(block_id);

            // If this is a loop, record its nesting level
            let next_loops = if loop_ids.contains(block_id) {
                levels.insert(block_id.to_string(), loops_in_path);
                loops_in_path + 1
            } else {
                loops_in_path
            };

            // Add successors
            if let Some(succs) = successors.get(block_id) {
                for succ_id in succs {
                    if !visited.contains(succ_id) {
                        queue.push_back((succ_id, next_loops));
                    }
                }
            }
        }

        levels
    }

    /// Determine overall verdict (worst case)
    fn determine_verdict(&self, loop_bounds: &[BoundResult]) -> Verdict {
        let verdicts: Vec<_> = loop_bounds.iter().map(|b| b.verdict).collect();

        if verdicts.contains(&Verdict::Heuristic) {
            Verdict::Heuristic
        } else if verdicts.contains(&Verdict::Likely) {
            Verdict::Likely
        } else {
            Verdict::Proven
        }
    }

    /// Generate explanation
    fn generate_explanation(
        &self,
        complexity: ComplexityClass,
        verdict: Verdict,
        loop_count: usize,
    ) -> String {
        if complexity == ComplexityClass::Constant {
            return "No loops: O(1)".to_string();
        }

        match verdict {
            Verdict::Proven => format!("{}: {} loop(s) proven", complexity.as_str(), loop_count),
            Verdict::Likely => format!("{}: {} loop(s) likely", complexity.as_str(), loop_count),
            Verdict::Heuristic => {
                format!("{} (conservative): unbounded loop(s)", complexity.as_str())
            }
        }
    }

    /// Find hotspots
    fn find_hotspots(&self, loop_blocks: &[&CFGBlock]) -> Vec<Hotspot> {
        loop_blocks
            .iter()
            .map(|block| Hotspot {
                line: block
                    .span
                    .as_ref()
                    .map(|s| s.start_line as usize)
                    .unwrap_or(0),
                reason: "Loop".to_string(),
            })
            .collect()
    }

    /// Create O(1) result
    fn create_constant_result(&self, func_node: &Node) -> CostResult {
        CostResult {
            function_fqn: func_node.fqn.clone(),
            complexity: ComplexityClass::Constant,
            verdict: Verdict::Proven,
            confidence: 1.0,
            explanation: "No loops: O(1)".to_string(),
            loop_bounds: Vec::new(),
            hotspots: Vec::new(),
            metadata: serde_json::json!({"cost_term": "1"}),
        }
    }

    /// Cache result
    fn cache_result(&mut self, function_fqn: &str, result: &CostResult) {
        if let Some(cache) = &mut self.cache {
            cache.insert(function_fqn.to_string(), result.clone());
        }
    }

    /// Invalidate cache
    pub fn invalidate_cache(&mut self, function_fqn: Option<&str>) -> usize {
        if let Some(cache) = &mut self.cache {
            if let Some(fqn) = function_fqn {
                if cache.remove(fqn).is_some() {
                    1
                } else {
                    0
                }
            } else {
                let count = cache.len();
                cache.clear();
                count
            }
        } else {
            0
        }
    }
}

impl Default for CostAnalyzer {
    fn default() -> Self {
        Self::new(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    #[test]
    fn test_analyze_no_loops() {
        let mut analyzer = CostAnalyzer::new(false);

        let func_node = Node {
            id: "func_1".to_string(),
            kind: NodeKind::Method,
            fqn: "test.foo".to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(1, 0, 5, 0),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("foo".to_string()),
            module_path: Some("test".to_string()),
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        };

        let result = analyzer
            .analyze_function(&[func_node], &[], &[], "test.foo")
            .unwrap();

        assert_eq!(result.complexity, ComplexityClass::Constant);
        assert_eq!(result.verdict, Verdict::Proven);
        assert_eq!(result.confidence, 1.0);
    }

    #[test]
    fn test_extract_range_bound() {
        let analyzer = CostAnalyzer::new(false);

        assert_eq!(analyzer.extract_range_bound("range(10)"), "10");
        assert_eq!(analyzer.extract_range_bound("range(0, n)"), "n");
        assert_eq!(analyzer.extract_range_bound("range(1, 100, 2)"), "100");
    }
}
