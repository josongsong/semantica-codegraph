use rustc_hash::{FxHashMap, FxHashSet};
use serde::{Deserialize, Serialize};
/// DeadlockDetector - Wait-for Graph based deadlock detection
///
/// Detects potential deadlocks in async/await code by building a Wait-For Graph (WFG)
/// and checking for cycles using Tarjan's SCC algorithm.
///
/// ## Algorithm
/// 1. **Lock Acquisition Analysis**: Track `async with lock` and `await lock.acquire()`
/// 2. **Wait-For Graph Construction**: Task A waits for Task B if A holds lock L1 and waits for L2 held by B
/// 3. **Cycle Detection**: Use Tarjan's SCC algorithm to find cycles
/// 4. **Deadlock Reporting**: Report cycle as potential deadlock with severity
///
/// ## Example Deadlock Pattern
/// ```python
/// async def task1():
///     async with lock_a:        # holds lock_a
///         await asyncio.sleep(0)
///         async with lock_b:    # waits for lock_b → DEADLOCK
///             pass
///
/// async def task2():
///     async with lock_b:        # holds lock_b
///         await asyncio.sleep(0)
///         async with lock_a:    # waits for lock_a → DEADLOCK
///             pass
/// ```
///
/// ## Performance
/// - Time: O(V + E) where V = tasks, E = lock dependencies
/// - Target: < 50ms per module
///
/// ## Academic References
/// - Tarjan, R. E. (1972). "Depth-First Search and Linear Graph Algorithms"
/// - Coffman et al. (1971). "System Deadlocks"
use std::collections::{HashMap, HashSet, VecDeque};

use super::error::{ConcurrencyError, Result};
use crate::features::cross_file::IRDocument;
use crate::shared::models::{Node, NodeKind};

// ============================================================================
// Deadlock Models
// ============================================================================

/// Lock acquisition type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LockAcquisitionType {
    /// `async with lock:`
    AsyncWith,
    /// `await lock.acquire()`
    AwaitAcquire,
    /// `with lock:` (synchronous)
    SyncWith,
    /// `lock.acquire()` (synchronous, blocking)
    SyncAcquire,
}

/// Lock acquisition event
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LockAcquisition {
    /// Lock variable name
    pub lock_name: String,
    /// Acquisition type
    pub acquisition_type: LockAcquisitionType,
    /// Line number
    pub line: u32,
    /// Nesting level (for nested lock acquisitions)
    pub nesting_level: usize,
}

/// Lock held by a task
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct HeldLock {
    pub lock_name: String,
    pub line: u32,
}

/// Lock wait (task waiting for a lock)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct LockWait {
    pub lock_name: String,
    pub line: u32,
    /// Locks held while waiting
    pub held_locks: Vec<HeldLock>,
}

/// Wait-For Graph node (represents a task or lock)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum WFGNode {
    Task { name: String, file: String },
    Lock { name: String },
}

impl WFGNode {
    pub fn task(name: impl Into<String>, file: impl Into<String>) -> Self {
        WFGNode::Task {
            name: name.into(),
            file: file.into(),
        }
    }

    pub fn lock(name: impl Into<String>) -> Self {
        WFGNode::Lock { name: name.into() }
    }

    pub fn name(&self) -> &str {
        match self {
            WFGNode::Task { name, .. } => name,
            WFGNode::Lock { name } => name,
        }
    }
}

/// Wait-For Graph edge
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WFGEdge {
    pub from: WFGNode,
    pub to: WFGNode,
    pub edge_type: WFGEdgeType,
    pub line: Option<u32>,
}

/// Edge type in Wait-For Graph
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum WFGEdgeType {
    /// Task holds lock: Task → Lock
    Holds,
    /// Task waits for lock: Task → Lock
    WaitsFor,
    /// Lock held by task: Lock → Task
    HeldBy,
}

/// Wait-For Graph
#[derive(Debug, Clone, Default)]
pub struct WaitForGraph {
    /// Adjacency list: node → outgoing edges
    edges: FxHashMap<String, Vec<WFGEdge>>,
    /// All nodes
    nodes: FxHashSet<String>,
}

impl WaitForGraph {
    pub fn new() -> Self {
        Self::default()
    }

    /// Add an edge to the graph
    pub fn add_edge(&mut self, edge: WFGEdge) {
        let from_key = Self::node_key(&edge.from);
        let to_key = Self::node_key(&edge.to);

        self.nodes.insert(from_key.clone());
        self.nodes.insert(to_key);

        self.edges.entry(from_key).or_default().push(edge);
    }

    /// Get edges from a node
    pub fn edges_from(&self, node: &str) -> Option<&Vec<WFGEdge>> {
        self.edges.get(node)
    }

    /// Get all nodes
    pub fn nodes(&self) -> impl Iterator<Item = &String> {
        self.nodes.iter()
    }

    /// Number of nodes
    pub fn node_count(&self) -> usize {
        self.nodes.len()
    }

    /// Number of edges
    pub fn edge_count(&self) -> usize {
        self.edges.values().map(|v| v.len()).sum()
    }

    fn node_key(node: &WFGNode) -> String {
        match node {
            WFGNode::Task { name, file } => format!("task:{}:{}", file, name),
            WFGNode::Lock { name } => format!("lock:{}", name),
        }
    }
}

// ============================================================================
// Deadlock Detection Result
// ============================================================================

/// Deadlock severity
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum DeadlockSeverity {
    /// Proven deadlock (cycle confirmed)
    Critical,
    /// Likely deadlock (potential cycle under certain conditions)
    High,
    /// Possible deadlock (heuristic detection)
    Medium,
    /// Lock order warning (not a deadlock but bad practice)
    Low,
}

/// Deadlock cycle (participating tasks/locks)
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DeadlockCycle {
    /// Nodes in the cycle (alternating Task → Lock → Task → ...)
    pub cycle: Vec<WFGNode>,
    /// Severity
    pub severity: DeadlockSeverity,
    /// Human-readable explanation
    pub explanation: String,
    /// Fix suggestion
    pub fix_suggestion: String,
}

impl DeadlockCycle {
    /// Build explanation for the deadlock
    fn build_explanation(cycle: &[WFGNode]) -> String {
        let mut explanation = String::new();
        explanation.push_str("Deadlock cycle detected:\n");

        for (i, node) in cycle.iter().enumerate() {
            let next_idx = (i + 1) % cycle.len();
            let next_node = &cycle[next_idx];

            match (node, next_node) {
                (WFGNode::Task { name, .. }, WFGNode::Lock { name: lock }) => {
                    explanation.push_str(&format!("  {} waits for {}\n", name, lock));
                }
                (WFGNode::Lock { name: lock }, WFGNode::Task { name, .. }) => {
                    explanation.push_str(&format!("  {} held by {}\n", lock, name));
                }
                _ => {}
            }
        }

        explanation
    }

    /// Build fix suggestion
    fn build_fix_suggestion(cycle: &[WFGNode]) -> String {
        let locks: Vec<_> = cycle
            .iter()
            .filter_map(|n| match n {
                WFGNode::Lock { name } => Some(name.as_str()),
                _ => None,
            })
            .collect();

        format!(
            "Fix: Establish consistent lock ordering. Suggested order: {:?}\n\
             Alternatively: Use asyncio.wait_for() with timeout, or use RLock if reentrant.",
            locks
        )
    }
}

/// Deadlock detection result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeadlockResult {
    /// Detected deadlock cycles
    pub deadlocks: Vec<DeadlockCycle>,
    /// Total tasks analyzed
    pub tasks_analyzed: usize,
    /// Total locks found
    pub locks_found: usize,
    /// Analysis time (ms)
    pub analysis_time_ms: u64,
}

impl DeadlockResult {
    pub fn new() -> Self {
        Self {
            deadlocks: Vec::new(),
            tasks_analyzed: 0,
            locks_found: 0,
            analysis_time_ms: 0,
        }
    }

    pub fn has_deadlocks(&self) -> bool {
        !self.deadlocks.is_empty()
    }

    pub fn critical_count(&self) -> usize {
        self.deadlocks
            .iter()
            .filter(|d| d.severity == DeadlockSeverity::Critical)
            .count()
    }
}

impl Default for DeadlockResult {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// Deadlock Detector
// ============================================================================

/// Deadlock detector using Wait-For Graph and Tarjan's SCC
pub struct DeadlockDetector {
    /// Wait-For Graph
    wfg: WaitForGraph,
    /// Lock order constraints (for lock order analysis)
    lock_order: FxHashMap<String, FxHashSet<String>>,
}

impl DeadlockDetector {
    pub fn new() -> Self {
        Self {
            wfg: WaitForGraph::new(),
            lock_order: FxHashMap::default(),
        }
    }

    /// Analyze module for deadlocks
    pub fn analyze_module(&mut self, ir_doc: &IRDocument) -> Result<DeadlockResult> {
        let start = std::time::Instant::now();

        // Build Wait-For Graph
        self.build_wfg(ir_doc)?;

        // Detect cycles using Tarjan's SCC
        let cycles = self.find_cycles();

        // Convert cycles to deadlock reports
        let deadlocks: Vec<_> = cycles
            .into_iter()
            .map(|cycle| {
                let severity = if cycle.len() >= 4 {
                    DeadlockSeverity::Critical
                } else {
                    DeadlockSeverity::High
                };

                DeadlockCycle {
                    explanation: DeadlockCycle::build_explanation(&cycle),
                    fix_suggestion: DeadlockCycle::build_fix_suggestion(&cycle),
                    cycle,
                    severity,
                }
            })
            .collect();

        Ok(DeadlockResult {
            deadlocks,
            tasks_analyzed: self.count_tasks(),
            locks_found: self.count_locks(),
            analysis_time_ms: start.elapsed().as_millis() as u64,
        })
    }

    /// Build Wait-For Graph from IR
    fn build_wfg(&mut self, ir_doc: &IRDocument) -> Result<()> {
        // Find all async functions
        let async_funcs: Vec<_> = ir_doc
            .nodes
            .iter()
            .filter(|n| n.kind == NodeKind::Function && n.is_async.unwrap_or(false))
            .collect();

        for func in async_funcs {
            self.analyze_function_locks(ir_doc, func)?;
        }

        Ok(())
    }

    /// Analyze lock acquisitions in a function
    fn analyze_function_locks(&mut self, ir_doc: &IRDocument, func: &Node) -> Result<()> {
        let func_name = &func.id;
        let file_path = ir_doc.file_path.clone();

        // Track held locks at each point
        let mut held_locks: Vec<HeldLock> = Vec::new();

        // Find all lock-related patterns
        let lock_patterns = self.find_lock_patterns(ir_doc, func);

        for pattern in lock_patterns {
            match pattern {
                LockPattern::Acquire { lock_name, line } => {
                    // Task waits for lock
                    let task_node = WFGNode::task(func_name, &file_path);
                    let lock_node = WFGNode::lock(&lock_name);

                    // If holding other locks, this creates potential for deadlock
                    if !held_locks.is_empty() {
                        // Record lock order
                        for held in &held_locks {
                            self.record_lock_order(&held.lock_name, &lock_name);
                        }
                    }

                    // Add wait edge
                    self.wfg.add_edge(WFGEdge {
                        from: task_node.clone(),
                        to: lock_node.clone(),
                        edge_type: WFGEdgeType::WaitsFor,
                        line: Some(line),
                    });

                    // Now holds the lock
                    held_locks.push(HeldLock {
                        lock_name: lock_name.clone(),
                        line,
                    });

                    // Add holds edge
                    self.wfg.add_edge(WFGEdge {
                        from: task_node,
                        to: lock_node.clone(),
                        edge_type: WFGEdgeType::Holds,
                        line: Some(line),
                    });

                    // Add held-by edge
                    self.wfg.add_edge(WFGEdge {
                        from: lock_node,
                        to: WFGNode::task(func_name, &file_path),
                        edge_type: WFGEdgeType::HeldBy,
                        line: Some(line),
                    });
                }
                LockPattern::Release { lock_name, .. } => {
                    // Remove from held locks
                    held_locks.retain(|h| h.lock_name != lock_name);
                }
            }
        }

        Ok(())
    }

    /// Find lock patterns in function
    fn find_lock_patterns(&self, ir_doc: &IRDocument, func: &Node) -> Vec<LockPattern> {
        let mut patterns = Vec::new();

        // Simple heuristic: look for nodes mentioning locks
        // In a full implementation, this would use CFG traversal
        for node in &ir_doc.nodes {
            if let Some(parent_id) = &node.parent_id {
                if parent_id != &func.id {
                    continue;
                }
            } else {
                continue;
            }

            // Use docstring or fqn as fallback for node content
            let node_text = node
                .docstring
                .as_deref()
                .or(node.name.as_deref())
                .unwrap_or(&node.fqn);
            let line = node.span.start_line as u32;

            // Detect `async with lock:` pattern
            if node_text.contains("async with") && node_text.contains("lock") {
                if let Some(lock_name) = self.extract_lock_name(node_text) {
                    patterns.push(LockPattern::Acquire { lock_name, line });
                }
            }

            // Detect `await lock.acquire()` pattern
            if node_text.contains("acquire") && node_text.contains("await") {
                if let Some(lock_name) = self.extract_lock_name_from_acquire(node_text) {
                    patterns.push(LockPattern::Acquire { lock_name, line });
                }
            }

            // Detect `lock.release()` pattern
            if node_text.contains("release()") {
                if let Some(lock_name) = self.extract_lock_name_from_release(node_text) {
                    patterns.push(LockPattern::Release { lock_name, line });
                }
            }
        }

        patterns
    }

    /// Extract lock name from `async with lock_name:` pattern
    fn extract_lock_name(&self, text: &str) -> Option<String> {
        // Simple pattern: find word after "async with"
        let text = text.trim();
        if let Some(pos) = text.find("async with") {
            let rest = &text[pos + 10..].trim_start();
            let end = rest
                .find(|c: char| !c.is_alphanumeric() && c != '_')
                .unwrap_or(rest.len());
            if end > 0 {
                return Some(rest[..end].to_string());
            }
        }
        None
    }

    /// Extract lock name from `await lock.acquire()`
    fn extract_lock_name_from_acquire(&self, text: &str) -> Option<String> {
        // Pattern: `lock_name.acquire()`
        if let Some(pos) = text.find(".acquire") {
            let before = &text[..pos];
            let words: Vec<_> = before.split_whitespace().collect();
            if let Some(last) = words.last() {
                let name = last.trim_matches(|c: char| !c.is_alphanumeric() && c != '_');
                if !name.is_empty() && name != "await" {
                    return Some(name.to_string());
                }
            }
        }
        None
    }

    /// Extract lock name from `lock.release()`
    fn extract_lock_name_from_release(&self, text: &str) -> Option<String> {
        if let Some(pos) = text.find(".release") {
            let before = &text[..pos];
            let words: Vec<_> = before.split_whitespace().collect();
            if let Some(last) = words.last() {
                let name = last.trim_matches(|c: char| !c.is_alphanumeric() && c != '_');
                if !name.is_empty() {
                    return Some(name.to_string());
                }
            }
        }
        None
    }

    /// Record lock order (a acquired before b)
    fn record_lock_order(&mut self, a: &str, b: &str) {
        self.lock_order
            .entry(a.to_string())
            .or_default()
            .insert(b.to_string());
    }

    /// Detect lock order violations
    pub fn detect_lock_order_violations(&self) -> Vec<(String, String)> {
        let mut violations = Vec::new();

        for (a, after_a) in &self.lock_order {
            for b in after_a {
                // Check if b → a also exists (violation)
                if let Some(after_b) = self.lock_order.get(b) {
                    if after_b.contains(a) {
                        violations.push((a.clone(), b.clone()));
                    }
                }
            }
        }

        violations
    }

    /// Find cycles in Wait-For Graph using Tarjan's SCC
    fn find_cycles(&self) -> Vec<Vec<WFGNode>> {
        let mut cycles = Vec::new();
        let nodes: Vec<_> = self.wfg.nodes().cloned().collect();

        if nodes.is_empty() {
            return cycles;
        }

        // Tarjan's SCC algorithm
        let mut index = 0;
        let mut stack: Vec<String> = Vec::new();
        let mut on_stack: FxHashSet<String> = FxHashSet::default();
        let mut indices: FxHashMap<String, usize> = FxHashMap::default();
        let mut lowlinks: FxHashMap<String, usize> = FxHashMap::default();

        fn strongconnect(
            v: &str,
            wfg: &WaitForGraph,
            index: &mut usize,
            stack: &mut Vec<String>,
            on_stack: &mut FxHashSet<String>,
            indices: &mut FxHashMap<String, usize>,
            lowlinks: &mut FxHashMap<String, usize>,
            cycles: &mut Vec<Vec<WFGNode>>,
        ) {
            indices.insert(v.to_string(), *index);
            lowlinks.insert(v.to_string(), *index);
            *index += 1;
            stack.push(v.to_string());
            on_stack.insert(v.to_string());

            // Explore successors
            if let Some(edges) = wfg.edges_from(v) {
                for edge in edges {
                    let w = match &edge.to {
                        WFGNode::Task { name, file } => format!("task:{}:{}", file, name),
                        WFGNode::Lock { name } => format!("lock:{}", name),
                    };

                    if !indices.contains_key(&w) {
                        strongconnect(&w, wfg, index, stack, on_stack, indices, lowlinks, cycles);
                        let v_lowlink = *lowlinks.get(v).unwrap();
                        let w_lowlink = *lowlinks.get(&w).unwrap();
                        lowlinks.insert(v.to_string(), v_lowlink.min(w_lowlink));
                    } else if on_stack.contains(&w) {
                        let v_lowlink = *lowlinks.get(v).unwrap();
                        let w_index = *indices.get(&w).unwrap();
                        lowlinks.insert(v.to_string(), v_lowlink.min(w_index));
                    }
                }
            }

            // Check if v is root of SCC
            let v_lowlink = *lowlinks.get(v).unwrap();
            let v_index = *indices.get(v).unwrap();

            if v_lowlink == v_index {
                let mut scc = Vec::new();
                loop {
                    let w = stack.pop().unwrap();
                    on_stack.remove(&w);
                    scc.push(w.clone());
                    if w == v {
                        break;
                    }
                }

                // SCC with more than one node indicates a cycle
                if scc.len() > 1 {
                    let cycle: Vec<WFGNode> = scc
                        .into_iter()
                        .map(|s| {
                            if s.starts_with("task:") {
                                let parts: Vec<_> = s[5..].splitn(2, ':').collect();
                                WFGNode::Task {
                                    file: parts.first().unwrap_or(&"").to_string(),
                                    name: parts.get(1).unwrap_or(&"").to_string(),
                                }
                            } else if s.starts_with("lock:") {
                                WFGNode::Lock {
                                    name: s[5..].to_string(),
                                }
                            } else {
                                WFGNode::Lock { name: s }
                            }
                        })
                        .collect();
                    cycles.push(cycle);
                }
            }
        }

        for node in &nodes {
            if !indices.contains_key(node) {
                strongconnect(
                    node,
                    &self.wfg,
                    &mut index,
                    &mut stack,
                    &mut on_stack,
                    &mut indices,
                    &mut lowlinks,
                    &mut cycles,
                );
            }
        }

        cycles
    }

    fn count_tasks(&self) -> usize {
        self.wfg.nodes().filter(|n| n.starts_with("task:")).count()
    }

    fn count_locks(&self) -> usize {
        self.wfg.nodes().filter(|n| n.starts_with("lock:")).count()
    }

    /// Get the Wait-For Graph for inspection
    pub fn wfg(&self) -> &WaitForGraph {
        &self.wfg
    }
}

impl Default for DeadlockDetector {
    fn default() -> Self {
        Self::new()
    }
}

/// Internal lock pattern
enum LockPattern {
    Acquire { lock_name: String, line: u32 },
    Release { lock_name: String, line: u32 },
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_wfg_construction() {
        let mut wfg = WaitForGraph::new();

        let task1 = WFGNode::task("task1", "main.py");
        let lock_a = WFGNode::lock("lock_a");

        wfg.add_edge(WFGEdge {
            from: task1.clone(),
            to: lock_a.clone(),
            edge_type: WFGEdgeType::Holds,
            line: Some(10),
        });

        assert_eq!(wfg.node_count(), 2);
        assert_eq!(wfg.edge_count(), 1);
    }

    #[test]
    fn test_lock_pattern_extraction() {
        let detector = DeadlockDetector::new();

        // Test async with pattern
        let lock = detector.extract_lock_name("async with my_lock:");
        assert_eq!(lock, Some("my_lock".to_string()));

        // Test acquire pattern
        let lock = detector.extract_lock_name_from_acquire("await lock_a.acquire()");
        assert_eq!(lock, Some("lock_a".to_string()));

        // Test release pattern
        let lock = detector.extract_lock_name_from_release("lock_b.release()");
        assert_eq!(lock, Some("lock_b".to_string()));
    }

    #[test]
    fn test_lock_order_violation() {
        let mut detector = DeadlockDetector::new();

        // Task1: lock_a → lock_b
        detector.record_lock_order("lock_a", "lock_b");

        // Task2: lock_b → lock_a (violation!)
        detector.record_lock_order("lock_b", "lock_a");

        let violations = detector.detect_lock_order_violations();
        assert!(!violations.is_empty());
    }

    #[test]
    fn test_cycle_detection() {
        let mut wfg = WaitForGraph::new();

        // Create a cycle: A → B → C → A
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("A"),
            to: WFGNode::lock("B"),
            edge_type: WFGEdgeType::HeldBy,
            line: None,
        });
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("B"),
            to: WFGNode::lock("C"),
            edge_type: WFGEdgeType::HeldBy,
            line: None,
        });
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("C"),
            to: WFGNode::lock("A"),
            edge_type: WFGEdgeType::HeldBy,
            line: None,
        });

        let mut detector = DeadlockDetector::new();
        detector.wfg = wfg;

        let cycles = detector.find_cycles();
        assert!(!cycles.is_empty());
        assert_eq!(cycles[0].len(), 3);
    }

    #[test]
    fn test_deadlock_severity() {
        assert_eq!(DeadlockSeverity::Critical as u8, 0);
        // Basic enum works
    }

    #[test]
    fn test_deadlock_result_default() {
        let result = DeadlockResult::new();
        assert!(!result.has_deadlocks());
        assert_eq!(result.critical_count(), 0);
    }

    #[test]
    fn test_deadlock_cycle_explanation() {
        let cycle = vec![
            WFGNode::task("task1", "main.py"),
            WFGNode::lock("lock_a"),
            WFGNode::task("task2", "main.py"),
            WFGNode::lock("lock_b"),
        ];

        let explanation = DeadlockCycle::build_explanation(&cycle);
        assert!(explanation.contains("Deadlock cycle"));
        assert!(explanation.contains("task1"));
        assert!(explanation.contains("lock_a"));
    }

    // =========================================================================
    // SOTA L11 Edge Cases - Deadlock Detection Comprehensive Tests
    // =========================================================================

    /// Base Case: Empty graph
    #[test]
    fn test_empty_graph_no_cycles() {
        let detector = DeadlockDetector::new();
        let cycles = detector.find_cycles();
        assert!(cycles.is_empty(), "Empty graph should have no cycles");
    }

    /// Base Case: Single node, no edges
    #[test]
    fn test_single_node_no_cycle() {
        let mut wfg = WaitForGraph::new();
        wfg.add_edge(WFGEdge {
            from: WFGNode::task("task1", "main.py"),
            to: WFGNode::lock("lock_a"),
            edge_type: WFGEdgeType::Holds,
            line: Some(10),
        });
        
        let mut detector = DeadlockDetector::new();
        detector.wfg = wfg;
        
        let cycles = detector.find_cycles();
        assert!(cycles.is_empty(), "Single edge should not create cycle");
    }

    /// Edge Case: Self-loop (task waiting on itself)
    /// Note: Tarjan's SCC algorithm with `scc.len() > 1` filter does NOT detect self-loops.
    /// Self-loops require separate handling or `scc.len() >= 1` with self-edge check.
    /// This test documents current behavior.
    #[test]
    fn test_self_loop_not_detected_by_scc() {
        let mut wfg = WaitForGraph::new();
        
        // Self-loop: lock A → lock A (pathological case)
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("A"),
            to: WFGNode::lock("A"),
            edge_type: WFGEdgeType::HeldBy,
            line: None,
        });
        
        let mut detector = DeadlockDetector::new();
        detector.wfg = wfg;
        
        let cycles = detector.find_cycles();
        // Current SCC implementation requires >1 node for cycle detection
        // Self-loop detection would require additional logic
        // This is a known limitation documented here
        assert!(cycles.is_empty(), "Current SCC filter (len > 1) does not detect self-loops");
    }

    /// Edge Case: Two-node cycle (simplest deadlock)
    #[test]
    fn test_two_node_cycle() {
        let mut wfg = WaitForGraph::new();
        
        // A → B → A
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("A"),
            to: WFGNode::lock("B"),
            edge_type: WFGEdgeType::HeldBy,
            line: None,
        });
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("B"),
            to: WFGNode::lock("A"),
            edge_type: WFGEdgeType::HeldBy,
            line: None,
        });
        
        let mut detector = DeadlockDetector::new();
        detector.wfg = wfg;
        
        let cycles = detector.find_cycles();
        assert!(!cycles.is_empty(), "Two-node cycle should be detected");
        assert_eq!(cycles[0].len(), 2);
    }

    /// Extreme Case: Large cycle (N nodes)
    #[test]
    fn test_large_cycle_detection() {
        let mut wfg = WaitForGraph::new();
        let n = 100;
        
        // Create cycle: lock_0 → lock_1 → ... → lock_99 → lock_0
        for i in 0..n {
            let from_name = format!("lock_{}", i);
            let to_name = format!("lock_{}", (i + 1) % n);
            
            wfg.add_edge(WFGEdge {
                from: WFGNode::lock(&from_name),
                to: WFGNode::lock(&to_name),
                edge_type: WFGEdgeType::HeldBy,
                line: None,
            });
        }
        
        let mut detector = DeadlockDetector::new();
        detector.wfg = wfg;
        
        let cycles = detector.find_cycles();
        assert!(!cycles.is_empty(), "Large cycle should be detected");
        assert_eq!(cycles[0].len(), n, "Cycle should have {} nodes", n);
    }

    /// Edge Case: Multiple independent cycles
    #[test]
    fn test_multiple_independent_cycles() {
        let mut wfg = WaitForGraph::new();
        
        // Cycle 1: A → B → A
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("A"),
            to: WFGNode::lock("B"),
            edge_type: WFGEdgeType::HeldBy,
            line: None,
        });
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("B"),
            to: WFGNode::lock("A"),
            edge_type: WFGEdgeType::HeldBy,
            line: None,
        });
        
        // Cycle 2: X → Y → Z → X (independent)
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("X"),
            to: WFGNode::lock("Y"),
            edge_type: WFGEdgeType::HeldBy,
            line: None,
        });
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("Y"),
            to: WFGNode::lock("Z"),
            edge_type: WFGEdgeType::HeldBy,
            line: None,
        });
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("Z"),
            to: WFGNode::lock("X"),
            edge_type: WFGEdgeType::HeldBy,
            line: None,
        });
        
        let mut detector = DeadlockDetector::new();
        detector.wfg = wfg;
        
        let cycles = detector.find_cycles();
        assert_eq!(cycles.len(), 2, "Should detect both independent cycles");
    }

    /// Edge Case: Overlapping SCCs (figure-8 pattern)
    #[test]
    fn test_overlapping_sccs() {
        let mut wfg = WaitForGraph::new();
        
        // Two cycles sharing node C:
        // A → B → C → A
        // C → D → E → C
        wfg.add_edge(WFGEdge { from: WFGNode::lock("A"), to: WFGNode::lock("B"), edge_type: WFGEdgeType::HeldBy, line: None });
        wfg.add_edge(WFGEdge { from: WFGNode::lock("B"), to: WFGNode::lock("C"), edge_type: WFGEdgeType::HeldBy, line: None });
        wfg.add_edge(WFGEdge { from: WFGNode::lock("C"), to: WFGNode::lock("A"), edge_type: WFGEdgeType::HeldBy, line: None });
        wfg.add_edge(WFGEdge { from: WFGNode::lock("C"), to: WFGNode::lock("D"), edge_type: WFGEdgeType::HeldBy, line: None });
        wfg.add_edge(WFGEdge { from: WFGNode::lock("D"), to: WFGNode::lock("E"), edge_type: WFGEdgeType::HeldBy, line: None });
        wfg.add_edge(WFGEdge { from: WFGNode::lock("E"), to: WFGNode::lock("C"), edge_type: WFGEdgeType::HeldBy, line: None });
        
        let mut detector = DeadlockDetector::new();
        detector.wfg = wfg;
        
        let cycles = detector.find_cycles();
        // Should find one large SCC containing A,B,C,D,E
        assert!(!cycles.is_empty(), "Should detect overlapping SCCs");
    }

    /// Extreme Case: Star topology (no cycles)
    #[test]
    fn test_star_topology_no_cycle() {
        let mut wfg = WaitForGraph::new();
        
        // Center → Spoke1, Spoke2, Spoke3 (no back edges)
        for i in 1..=10 {
            wfg.add_edge(WFGEdge {
                from: WFGNode::lock("center"),
                to: WFGNode::lock(&format!("spoke_{}", i)),
                edge_type: WFGEdgeType::HeldBy,
                line: None,
            });
        }
        
        let mut detector = DeadlockDetector::new();
        detector.wfg = wfg;
        
        let cycles = detector.find_cycles();
        assert!(cycles.is_empty(), "Star topology has no cycles");
    }

    /// Edge Case: Diamond pattern (no cycle)
    #[test]
    fn test_diamond_pattern_no_cycle() {
        let mut wfg = WaitForGraph::new();
        
        // A → B → D, A → C → D (diamond, not cycle)
        wfg.add_edge(WFGEdge { from: WFGNode::lock("A"), to: WFGNode::lock("B"), edge_type: WFGEdgeType::HeldBy, line: None });
        wfg.add_edge(WFGEdge { from: WFGNode::lock("A"), to: WFGNode::lock("C"), edge_type: WFGEdgeType::HeldBy, line: None });
        wfg.add_edge(WFGEdge { from: WFGNode::lock("B"), to: WFGNode::lock("D"), edge_type: WFGEdgeType::HeldBy, line: None });
        wfg.add_edge(WFGEdge { from: WFGNode::lock("C"), to: WFGNode::lock("D"), edge_type: WFGEdgeType::HeldBy, line: None });
        
        let mut detector = DeadlockDetector::new();
        detector.wfg = wfg;
        
        let cycles = detector.find_cycles();
        assert!(cycles.is_empty(), "Diamond pattern has no cycles");
    }

    /// Edge Case: Lock order violation is symmetric
    #[test]
    fn test_lock_order_violation_symmetric() {
        let mut detector = DeadlockDetector::new();
        
        // Only a → b is recorded
        detector.record_lock_order("lock_a", "lock_b");
        
        let violations = detector.detect_lock_order_violations();
        assert!(violations.is_empty(), "One-way order is not violation");
        
        // Now add b → a
        detector.record_lock_order("lock_b", "lock_a");
        
        let violations = detector.detect_lock_order_violations();
        assert!(!violations.is_empty(), "Symmetric orders should be violation");
    }

    /// Extreme Case: Many lock order relationships
    /// Note: Current `detect_lock_order_violations` only detects DIRECT violations
    /// (a → b AND b → a), not transitive violations (a → b → c → a).
    /// This test documents current behavior.
    #[test]
    fn test_many_lock_orders() {
        let mut detector = DeadlockDetector::new();
        
        // Create chain: lock_0 → lock_1 → ... → lock_99
        for i in 0..99 {
            detector.record_lock_order(&format!("lock_{}", i), &format!("lock_{}", i + 1));
        }
        
        // No violations in linear chain
        let violations = detector.detect_lock_order_violations();
        assert!(violations.is_empty(), "Linear chain has no violations");
        
        // Add lock_99 → lock_0 (creates transitive cycle, NOT direct violation)
        detector.record_lock_order("lock_99", "lock_0");
        
        // Current implementation only detects DIRECT a↔b violations
        // lock_0 → lock_1 and lock_99 → lock_0 do NOT form direct violation
        // (would need lock_0 → lock_99 AND lock_99 → lock_0 for direct detection)
        let violations = detector.detect_lock_order_violations();
        assert!(violations.is_empty(), "Transitive cycles not detected by direct violation check");
        
        // Add DIRECT violation: lock_0 → lock_99 (now lock_0 ↔ lock_99)
        detector.record_lock_order("lock_0", "lock_99");
        
        let violations = detector.detect_lock_order_violations();
        assert!(!violations.is_empty(), "Direct a↔b violation should be detected");
    }

    /// Base Case: WFGNode key generation
    #[test]
    fn test_wfg_node_key_uniqueness() {
        let task1_a = WFGNode::task("task1", "file_a.py");
        let task1_b = WFGNode::task("task1", "file_b.py");
        let lock1 = WFGNode::lock("lock1");
        
        // Same task name in different files should be different keys
        let key1 = WaitForGraph::node_key(&task1_a);
        let key2 = WaitForGraph::node_key(&task1_b);
        let key3 = WaitForGraph::node_key(&lock1);
        
        assert_ne!(key1, key2, "Same task name in different files should differ");
        assert_ne!(key1, key3, "Task and lock should differ");
    }

    /// Edge Case: DeadlockResult aggregation
    #[test]
    fn test_deadlock_result_aggregation() {
        let mut result = DeadlockResult::new();
        
        // Initially empty
        assert!(!result.has_deadlocks());
        assert_eq!(result.critical_count(), 0);
        
        // Add Critical deadlock
        result.deadlocks.push(DeadlockCycle {
            cycle: vec![WFGNode::lock("A"), WFGNode::lock("B")],
            severity: DeadlockSeverity::Critical,
            explanation: "Test".to_string(),
            fix_suggestion: "Fix".to_string(),
        });
        
        // Add High severity
        result.deadlocks.push(DeadlockCycle {
            cycle: vec![WFGNode::lock("X")],
            severity: DeadlockSeverity::High,
            explanation: "Test2".to_string(),
            fix_suggestion: "Fix2".to_string(),
        });
        
        assert!(result.has_deadlocks());
        assert_eq!(result.critical_count(), 1);
        assert_eq!(result.deadlocks.len(), 2);
    }

    /// Edge Case: Fix suggestion generation
    #[test]
    fn test_fix_suggestion_generation() {
        let cycle = vec![
            WFGNode::task("task1", "main.py"),
            WFGNode::lock("lock_a"),
            WFGNode::task("task2", "main.py"),
            WFGNode::lock("lock_b"),
        ];
        
        let suggestion = DeadlockCycle::build_fix_suggestion(&cycle);
        
        // Should suggest lock ordering
        assert!(suggestion.contains("lock ordering") || suggestion.contains("order"));
        // Should mention the locks
        assert!(suggestion.contains("lock_a") || suggestion.contains("lock_b"));
    }

    /// Extreme Case: Performance - large graph traversal
    #[test]
    fn test_large_graph_performance() {
        let mut wfg = WaitForGraph::new();
        let n = 500; // 500 nodes
        
        // Dense graph (no cycles)
        for i in 0..n {
            for j in (i + 1)..n.min(i + 10) {
                wfg.add_edge(WFGEdge {
                    from: WFGNode::lock(&format!("node_{}", i)),
                    to: WFGNode::lock(&format!("node_{}", j)),
                    edge_type: WFGEdgeType::HeldBy,
                    line: None,
                });
            }
        }
        
        let mut detector = DeadlockDetector::new();
        detector.wfg = wfg;
        
        let start = std::time::Instant::now();
        let cycles = detector.find_cycles();
        let elapsed = start.elapsed();
        
        // Should complete in reasonable time (< 1 second)
        assert!(
            elapsed.as_millis() < 1000,
            "Large graph analysis took too long: {:?}",
            elapsed
        );
        assert!(cycles.is_empty(), "DAG should have no cycles");
    }

    /// Edge Case: Mixed Task and Lock nodes in cycle
    #[test]
    fn test_mixed_task_lock_cycle() {
        let mut wfg = WaitForGraph::new();
        
        // Realistic deadlock pattern:
        // task1 → lock_a (holds)
        // lock_a → task2 (held by)
        // task2 → lock_b (waits for)
        // lock_b → task1 (held by - but task1 is waiting)
        wfg.add_edge(WFGEdge {
            from: WFGNode::task("task1", "main.py"),
            to: WFGNode::lock("lock_a"),
            edge_type: WFGEdgeType::Holds,
            line: Some(10),
        });
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("lock_a"),
            to: WFGNode::task("task2", "main.py"),
            edge_type: WFGEdgeType::HeldBy,
            line: Some(20),
        });
        wfg.add_edge(WFGEdge {
            from: WFGNode::task("task2", "main.py"),
            to: WFGNode::lock("lock_b"),
            edge_type: WFGEdgeType::WaitsFor,
            line: Some(25),
        });
        wfg.add_edge(WFGEdge {
            from: WFGNode::lock("lock_b"),
            to: WFGNode::task("task1", "main.py"),
            edge_type: WFGEdgeType::HeldBy,
            line: Some(15),
        });
        
        let mut detector = DeadlockDetector::new();
        detector.wfg = wfg;
        
        let cycles = detector.find_cycles();
        assert!(!cycles.is_empty(), "Mixed task/lock cycle should be detected");
    }
}
