//! Concurrency Analysis Use Case
//!
//! **SOTA Implementation**: RacerD-inspired async race detection for Python.
//!
//! ## Algorithm
//! 1. Find async functions via `Node.is_async == true`
//! 2. Detect shared variable accesses via `Edge(Reads/Writes)`
//! 3. Identify await points (interleaving opportunities)
//! 4. Report races without lock protection
//!
//! ## Performance
//! - Time: O(N + E) where N = nodes, E = edges
//! - Space: O(A) where A = number of accesses per function
//!
//! ## References
//! - RacerD: Blackshear et al. (Facebook Infer, 2018)

use crate::features::concurrency_analysis::{
    AsyncRaceDetector, ConcurrencyError, RaceCondition, Result,
};
use crate::features::cross_file::IRDocument;
use crate::shared::models::{Node, NodeKind};

/// Analyze concurrency issues in IR document
///
/// High-level use case for detecting race conditions and deadlocks.
pub struct ConcurrencyAnalysisUseCase {
    race_detector: AsyncRaceDetector,
}

impl ConcurrencyAnalysisUseCase {
    /// Create new concurrency analysis use case
    pub fn new() -> Self {
        Self {
            race_detector: AsyncRaceDetector::new(),
        }
    }

    /// Analyze all async functions for race conditions
    ///
    /// # Algorithm
    /// 1. Enumerate all async functions in IR document
    /// 2. For each async function, run race detector
    /// 3. Collect and return all detected races
    ///
    /// # Performance
    /// O(F × (N + E)) where F = async functions
    pub fn analyze_all(&self, ir_doc: &IRDocument) -> Result<Vec<RaceCondition>> {
        let mut all_races = Vec::new();

        // Find all async functions (REAL implementation)
        let async_functions = ir_doc.find_async_functions();

        for func_node in async_functions {
            match self
                .race_detector
                .analyze_async_function(ir_doc, &func_node.id)
            {
                Ok(races) => all_races.extend(races),
                Err(ConcurrencyError::NotAsyncFunction(_)) => {
                    // Skip non-async functions (shouldn't happen with proper filtering)
                    continue;
                }
                Err(e) => {
                    // Log error but continue with other functions
                    eprintln!("Error analyzing {}: {}", func_node.id, e);
                }
            }
        }

        Ok(all_races)
    }

    /// Analyze specific async function
    pub fn analyze_function(
        &self,
        ir_doc: &IRDocument,
        func_fqn: &str,
    ) -> Result<Vec<RaceCondition>> {
        self.race_detector.analyze_async_function(ir_doc, func_fqn)
    }

    /// Get summary statistics
    pub fn get_summary(&self, races: &[RaceCondition]) -> ConcurrencySummary {
        let mut critical = 0;
        let mut high = 0;
        let mut medium = 0;
        let mut low = 0;

        for race in races {
            match race.severity {
                crate::features::concurrency_analysis::RaceSeverity::Critical => critical += 1,
                crate::features::concurrency_analysis::RaceSeverity::High => high += 1,
                crate::features::concurrency_analysis::RaceSeverity::Medium => medium += 1,
                crate::features::concurrency_analysis::RaceSeverity::Low => low += 1,
            }
        }

        ConcurrencySummary {
            total_races: races.len(),
            critical,
            high,
            medium,
            low,
        }
    }
}

impl Default for ConcurrencyAnalysisUseCase {
    fn default() -> Self {
        Self::new()
    }
}

/// Concurrency analysis summary
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ConcurrencySummary {
    pub total_races: usize,
    pub critical: usize,
    pub high: usize,
    pub medium: usize,
    pub low: usize,
}

// ═══════════════════════════════════════════════════════════════════════════════
// IRDocument Extension Trait - PRODUCTION IMPLEMENTATION
// ═══════════════════════════════════════════════════════════════════════════════

/// Extension trait for IRDocument to support concurrency analysis
pub trait IRDocumentConcurrencyExt {
    /// Find all async functions in the IR document
    ///
    /// # Algorithm
    /// Filters nodes where:
    /// - `kind == Function || kind == Method`
    /// - `is_async == Some(true)`
    ///
    /// # Performance
    /// O(N) where N = total nodes
    fn find_async_functions(&self) -> Vec<&Node>;
}

impl IRDocumentConcurrencyExt for IRDocument {
    fn find_async_functions(&self) -> Vec<&Node> {
        self.nodes
            .iter()
            .filter(|node| {
                // Check if it's a function or method
                let is_callable = matches!(
                    node.kind,
                    NodeKind::Function | NodeKind::Method | NodeKind::Lambda
                );

                // Check if it's marked as async
                let is_async = node.is_async.unwrap_or(false);

                is_callable && is_async
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{Edge, EdgeKind, Span};

    // ═══════════════════════════════════════════════════════════════════════════
    // Test Helpers
    // ═══════════════════════════════════════════════════════════════════════════

    fn make_async_function(id: &str, file: &str, start_line: u32, end_line: u32) -> Node {
        Node::new(
            id.to_string(),
            NodeKind::Function,
            id.to_string(),
            file.to_string(),
            Span::new(start_line, 0, end_line, 0),
        )
        .with_is_async(true)
    }

    fn make_sync_function(id: &str, file: &str) -> Node {
        Node::new(
            id.to_string(),
            NodeKind::Function,
            id.to_string(),
            file.to_string(),
            Span::new(1, 0, 10, 0),
        )
    }

    fn make_await_node(id: &str, parent: &str, file: &str, line: u32) -> Node {
        Node::new(
            id.to_string(),
            NodeKind::Expression,
            format!("await_{}", id),
            file.to_string(),
            Span::new(line, 4, line, 30),
        )
        .with_parent_id(parent.to_string())
        .with_name(format!("await asyncio.sleep({})", line))
    }

    fn make_read_edge(source: &str, target: &str, line: u32) -> Edge {
        Edge::new(source.to_string(), target.to_string(), EdgeKind::Reads)
            .with_span(Span::new(line, 4, line, 20))
    }

    fn make_write_edge(source: &str, target: &str, line: u32) -> Edge {
        Edge::new(source.to_string(), target.to_string(), EdgeKind::Writes)
            .with_span(Span::new(line, 4, line, 25))
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Basic Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_use_case_creation() {
        let _use_case = ConcurrencyAnalysisUseCase::new();
    }

    #[test]
    fn test_summary_empty() {
        let use_case = ConcurrencyAnalysisUseCase::new();
        let summary = use_case.get_summary(&[]);

        assert_eq!(summary.total_races, 0);
        assert_eq!(summary.critical, 0);
        assert_eq!(summary.high, 0);
        assert_eq!(summary.medium, 0);
        assert_eq!(summary.low, 0);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // find_async_functions Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_find_async_functions_empty() {
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![],
            edges: vec![],
            repo_id: None,
        };

        let async_fns = ir_doc.find_async_functions();
        assert!(async_fns.is_empty());
    }

    #[test]
    fn test_find_async_functions_only_sync() {
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                make_sync_function("sync_fn1", "test.py"),
                make_sync_function("sync_fn2", "test.py"),
            ],
            edges: vec![],
            repo_id: None,
        };

        let async_fns = ir_doc.find_async_functions();
        assert!(async_fns.is_empty(), "Should not find sync functions");
    }

    #[test]
    fn test_find_async_functions_mixed() {
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                make_async_function("async_fn", "test.py", 1, 10),
                make_sync_function("sync_fn", "test.py"),
            ],
            edges: vec![],
            repo_id: None,
        };

        let async_fns = ir_doc.find_async_functions();
        assert_eq!(async_fns.len(), 1);
        assert_eq!(async_fns[0].id, "async_fn");
    }

    #[test]
    fn test_find_async_functions_methods() {
        let method = Node::new(
            "MyClass.async_method".to_string(),
            NodeKind::Method,
            "MyClass.async_method".to_string(),
            "test.py".to_string(),
            Span::new(5, 4, 15, 4),
        )
        .with_is_async(true);

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![method],
            edges: vec![],
            repo_id: None,
        };

        let async_fns = ir_doc.find_async_functions();
        assert_eq!(async_fns.len(), 1);
        assert_eq!(async_fns[0].kind, NodeKind::Method);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Integration Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_analyze_all_empty() {
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![],
            edges: vec![],
            repo_id: None,
        };

        let use_case = ConcurrencyAnalysisUseCase::new();
        let races = use_case.analyze_all(&ir_doc).unwrap();

        assert!(races.is_empty());
    }

    #[test]
    fn test_analyze_all_no_async() {
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![make_sync_function("fn", "test.py")],
            edges: vec![],
            repo_id: None,
        };

        let use_case = ConcurrencyAnalysisUseCase::new();
        let races = use_case.analyze_all(&ir_doc).unwrap();

        assert!(races.is_empty());
    }

    #[test]
    fn test_analyze_detects_race() {
        // Create IR with race condition:
        // async def increment():
        //     x = self.count    # read at line 5
        //     await sleep(0)    # await at line 10
        //     self.count = x+1  # write at line 15
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                make_async_function("increment", "test.py", 1, 20),
                make_await_node("await_1", "increment", "test.py", 10),
            ],
            edges: vec![
                make_read_edge("increment", "self.count", 5),
                make_write_edge("increment", "self.count", 15),
            ],
            repo_id: None,
        };

        let use_case = ConcurrencyAnalysisUseCase::new();
        let races = use_case.analyze_all(&ir_doc).unwrap();

        assert!(!races.is_empty(), "Should detect race condition");

        let race = &races[0];
        assert_eq!(race.shared_var, "self.count");
        assert!(race.severity >= crate::features::concurrency_analysis::RaceSeverity::High);
    }

    #[test]
    fn test_analyze_no_race_without_await() {
        // No await → no interleaving → no race
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![
                make_async_function("fn", "test.py", 1, 20),
                // No await node
            ],
            edges: vec![
                make_read_edge("fn", "self.count", 5),
                make_write_edge("fn", "self.count", 15),
            ],
            repo_id: None,
        };

        let use_case = ConcurrencyAnalysisUseCase::new();
        let races = use_case.analyze_all(&ir_doc).unwrap();

        assert!(races.is_empty(), "No await means no race");
    }

    #[test]
    fn test_summary_counts() {
        use crate::features::concurrency_analysis::domain::{
            race_condition::AccessLocation, AccessType, AwaitPoint, LockRegion, RaceCondition,
        };

        // Create fake races for summary test
        let races = vec![
            RaceCondition::new(
                "var1".to_string(),
                AccessLocation {
                    file_path: "test.py".to_string(),
                    line: 1,
                    access_type: AccessType::Write,
                },
                AccessLocation {
                    file_path: "test.py".to_string(),
                    line: 2,
                    access_type: AccessType::Write,
                },
                vec![AwaitPoint {
                    file_path: "test.py".to_string(),
                    line: 1,
                    await_expr: "await".to_string(),
                    function_name: "fn".to_string(),
                }],
                vec![],
                "test.py".to_string(),
                "fn".to_string(),
            ), // Critical (write-write)
            RaceCondition::new(
                "var2".to_string(),
                AccessLocation {
                    file_path: "test.py".to_string(),
                    line: 3,
                    access_type: AccessType::Write,
                },
                AccessLocation {
                    file_path: "test.py".to_string(),
                    line: 4,
                    access_type: AccessType::Read,
                },
                vec![AwaitPoint {
                    file_path: "test.py".to_string(),
                    line: 3,
                    await_expr: "await".to_string(),
                    function_name: "fn".to_string(),
                }],
                vec![],
                "test.py".to_string(),
                "fn".to_string(),
            ), // High (write-read)
        ];

        let use_case = ConcurrencyAnalysisUseCase::new();
        let summary = use_case.get_summary(&races);

        assert_eq!(summary.total_races, 2);
        assert_eq!(summary.critical, 1);
        assert_eq!(summary.high, 1);
    }
}
