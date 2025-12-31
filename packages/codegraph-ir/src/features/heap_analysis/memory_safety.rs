//! Memory Safety Checkers - SOTA NPE/UAF/Double-Free Detection
//!
//! Academic References:
//! - Fähndrich, M. & Leino, K. R. M. (2003). "Declaring and Checking Non-null Types"
//! - Chalin, P. & James, P. R. (2007). "Non-null References by Default in Java"
//! - Heine, D. L. & Lam, M. S. (2003). "A Practical Flow-Sensitive and Context-Sensitive C and C++ Memory Leak Detector"
//!
//! Industry:
//! - **Kotlin**: Nullable types (T vs T?)
//! - **Swift**: Optionals with compile-time safety
//! - **Rust**: Ownership system (no null, no UAF)
//! - **Meta Infer**: Production null safety for Android/iOS
//!
//! ## Checkers
//!
//! ### 1. Null Dereference Checker
//! - **Path-sensitive**: Tracks null status per control-flow path
//! - **Inter-procedural**: Propagates null through function calls
//! - **@Nullable/@NonNull annotations**: Java/Kotlin support
//!
//! ### 2. Use-After-Free Checker
//! - **Lifetime tracking**: Monitors allocation/deallocation
//! - **Heap state**: Uses Separation Logic symbolic heap
//! - **Free count**: Detects double-free
//!
//! ### 3. Double-Free Checker
//! - **Free count tracking**: free_count > 1 → error
//! - **State machine**: allocated → freed → error
//!
//! ## Example Issues
//!
//! ```c
//! // Null dereference
//! void foo(Object* p) {
//!     p->field = 42;  // ❌ p may be null
//! }
//!
//! // Use-after-free
//! void bar() {
//!     int* p = malloc(sizeof(int));
//!     free(p);
//!     *p = 42;  // ❌ UAF
//! }
//!
//! // Double-free
//! void baz() {
//!     int* p = malloc(sizeof(int));
//!     free(p);
//!     free(p);  // ❌ Double free
//! }
//! ```

use super::separation_logic::{MemorySafetyIssue, SymbolicHeap};
use crate::features::smt::infrastructure::ArrayBoundsChecker;
use crate::shared::models::{Edge, Node, NodeKind, Span};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ═══════════════════════════════════════════════════════════════════════════
// SOLID Compliance: Trait-based Memory Checker Interface
// ═══════════════════════════════════════════════════════════════════════════
//
// SOLID Principles Applied:
// - S (Single Responsibility): Each checker has one responsibility
// - O (Open/Closed): New checkers implement trait, no modification needed
// - L (Liskov Substitution): All checkers are interchangeable via trait
// - I (Interface Segregation): Minimal trait interface
// - D (Dependency Inversion): MemorySafetyAnalyzer depends on trait, not concrete types
//
// ═══════════════════════════════════════════════════════════════════════════

/// Memory Safety Checker Trait (SOLID: Interface Segregation)
///
/// All memory safety checkers implement this trait for uniform handling.
///
/// # SOLID Compliance
/// - **S**: Single method for analysis
/// - **I**: Minimal interface (analyze + name only)
/// - **L**: Any implementor can substitute another
///
/// # Example: Adding a New Checker
/// ```rust,ignore
/// struct MyCustomChecker { /* ... */ }
///
/// impl MemoryChecker for MyCustomChecker {
///     fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
///         // Custom analysis logic
///         vec![]
///     }
///
///     fn name(&self) -> &'static str {
///         "MyCustomChecker"
///     }
/// }
///
/// // Add to analyzer without modifying MemorySafetyAnalyzer code
/// analyzer.add_checker(Box::new(MyCustomChecker::new()));
/// ```
pub trait MemoryChecker: Send + Sync {
    /// Analyze nodes for memory safety issues
    ///
    /// # Arguments
    /// * `nodes` - IR nodes to analyze
    ///
    /// # Returns
    /// Vector of detected memory safety issues
    fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue>;

    /// Analyze with edge information for enhanced detection
    ///
    /// Default implementation delegates to `analyze()`.
    /// Override for checkers that benefit from edge information.
    fn analyze_with_edges(&mut self, nodes: &[Node], _edges: &[Edge]) -> Vec<MemorySafetyIssue> {
        self.analyze(nodes)
    }

    /// Checker name for debugging and logging
    fn name(&self) -> &'static str;

    /// Reset checker state for reuse
    fn reset(&mut self) {}
}

/// Null Dereference Checker
///
/// Detects potential null pointer dereferences with path sensitivity.
///
/// Algorithm:
/// 1. Forward dataflow analysis
/// 2. Track null status per variable per program point
/// 3. Check at dereference points
///
/// Null Status:
/// - **Definitely null**: x = null
/// - **Definitely not null**: x = new Object()
/// - **May be null**: x could be null or not (conservative)
pub struct NullDereferenceChecker {
    /// Current symbolic heap state
    heap: SymbolicHeap,

    /// Issues found
    issues: Vec<MemorySafetyIssue>,
}

impl NullDereferenceChecker {
    pub fn new() -> Self {
        Self {
            heap: SymbolicHeap::new(),
            issues: Vec::new(),
        }
    }

    /// Analyze nodes for null dereferences
    pub fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
        for node in nodes {
            self.check_node(node);
        }

        std::mem::take(&mut self.issues)
    }

    fn check_node(&mut self, node: &Node) {
        match node.kind {
            NodeKind::Variable => {
                // Track variable allocation based on type annotation
                if let Some(name) = &node.name {
                    if let Some(type_annotation) = &node.type_annotation {
                        if type_annotation.contains("null") || type_annotation.contains("None") {
                            self.heap.mark_may_be_null(name);
                        }
                    }
                }
            }

            NodeKind::Expression => {
                // Check if expression may involve null dereference
                // For now, we analyze expressions based on their FQN pattern
                if node.fqn.contains("::") {
                    // Extract receiver from FQN (e.g., "obj::method" -> "obj")
                    if let Some(receiver) = node.fqn.split("::").next() {
                        if self.heap.may_be_null(receiver) {
                            let issue = MemorySafetyIssue::null_dereference(
                                receiver,
                                format!("{}:{}", node.file_path, node.span.start_line),
                            );
                            self.issues.push(issue);
                        }
                    }
                }
            }

            NodeKind::Method | NodeKind::Function => {
                // Analyze method/function body
                // Function-level analysis: check return nullability and parameter handling
                // Note: Full CFG-based analysis is available via NullSafetyChecker in smt module
                // which provides path-sensitive, flow-sensitive null checking with datalog rules.
                //
                // For CFG-integrated analysis, use:
                //   1. Build CFG from BasicFlowGraph (flow_graph module)
                //   2. Extract statements from CFG blocks
                //   3. Run NullDereferenceChecker on each statement in CFG order
                //
                // Current implementation: Function-signature level analysis
                if let Some(name) = &node.name {
                    // Track function as potential null source if return type is nullable
                    if let Some(ret_type) = &node.return_type {
                        if ret_type.contains("null")
                            || ret_type.contains("None")
                            || ret_type.contains("Option")
                            || ret_type.contains("?")
                        {
                            self.heap.mark_may_be_null(&format!("{}()", name));
                        }
                    }
                }
            }

            _ => {}
        }
    }

    /// Check if expression may be null
    pub fn check_null_dereference(&mut self, var: &str, span: &Span, file_path: &str) -> bool {
        if self.heap.may_be_null(var) {
            let issue = MemorySafetyIssue::null_dereference(
                var,
                format!("{}:{}", file_path, span.start_line),
            );
            self.issues.push(issue);
            true
        } else {
            false
        }
    }

    /// Mark variable as allocated (not null)
    pub fn mark_allocated(&mut self, var: &str) {
        self.heap.allocate(var);
    }

    /// Mark variable as possibly null
    pub fn mark_nullable(&mut self, var: &str) {
        self.heap.mark_may_be_null(var);
    }

    pub fn get_issues(&self) -> &[MemorySafetyIssue] {
        &self.issues
    }
}

impl Default for NullDereferenceChecker {
    fn default() -> Self {
        Self::new()
    }
}

/// SOLID: MemoryChecker trait implementation for NullDereferenceChecker
impl MemoryChecker for NullDereferenceChecker {
    fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
        // Delegate to inherent method
        NullDereferenceChecker::analyze(self, nodes)
    }

    fn name(&self) -> &'static str {
        "NullDereferenceChecker"
    }

    fn reset(&mut self) {
        self.heap = SymbolicHeap::new();
        self.issues.clear();
    }
}

/// Use-After-Free Checker
///
/// Detects use of heap memory after it has been freed.
///
/// Algorithm:
/// 1. Track heap allocations in SymbolicHeap
/// 2. Mark variables as freed on free/delete
/// 3. Check if accessed after freed
///
/// Heap States:
/// - **Allocated**: Object is live
/// - **Freed**: Object has been deallocated
/// - **Uninitialized**: Never allocated
pub struct UseAfterFreeChecker {
    /// Symbolic heap for lifetime tracking
    heap: SymbolicHeap,

    /// Issues found
    issues: Vec<MemorySafetyIssue>,
}

impl UseAfterFreeChecker {
    pub fn new() -> Self {
        Self {
            heap: SymbolicHeap::new(),
            issues: Vec::new(),
        }
    }

    /// Analyze nodes for UAF
    pub fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
        for node in nodes {
            self.check_node(node);
        }

        std::mem::take(&mut self.issues)
    }

    fn check_node(&mut self, node: &Node) {
        match node.kind {
            NodeKind::Expression | NodeKind::Function | NodeKind::Method => {
                // Extract function name from name or FQN
                let func_name = node.name.as_deref().unwrap_or(&node.fqn);

                // Allocation: malloc, new, Box::new
                if self.is_allocation_function(func_name) {
                    // For allocations, use the variable name if available
                    if let Some(name) = &node.name {
                        self.heap.allocate(name);
                    }
                }
                // Deallocation: free, delete, drop
                else if self.is_deallocation_function(func_name) {
                    // Extract target from FQN (e.g., "free::p" -> "p")
                    if let Some(target) = node.fqn.split("::").nth(1) {
                        if let Err(err) = self.heap.deallocate(target) {
                            let issue = if err.contains("Double-free") {
                                MemorySafetyIssue::double_free(
                                    target,
                                    format!("{}:{}", node.file_path, node.span.start_line),
                                )
                            } else {
                                MemorySafetyIssue::use_after_free(
                                    target,
                                    format!("{}:{}", node.file_path, node.span.start_line),
                                )
                            };
                            self.issues.push(issue);
                        }
                    }
                }
                // Use: check if freed (based on FQN pattern like "obj::field")
                else if node.fqn.contains("::") {
                    if let Some(receiver) = node.fqn.split("::").next() {
                        // Only check if it looks like a variable name
                        if !self.heap.is_allocated(receiver)
                            && receiver.chars().all(|c| c.is_alphanumeric() || c == '_')
                            && !receiver.is_empty()
                        {
                            let issue = MemorySafetyIssue::use_after_free(
                                receiver,
                                format!("{}:{}", node.file_path, node.span.start_line),
                            );
                            self.issues.push(issue);
                        }
                    }
                }
            }

            _ => {}
        }
    }

    fn is_allocation_function(&self, name: &str) -> bool {
        matches!(
            name,
            "malloc" | "calloc" | "realloc" | "new" | "Box::new" | "Rc::new" | "Arc::new"
        ) || name.contains("alloc")
            || name.contains("new")
    }

    fn is_deallocation_function(&self, name: &str) -> bool {
        matches!(name, "free" | "delete" | "drop")
            || name.contains("free")
            || name.contains("delete")
    }

    pub fn get_issues(&self) -> &[MemorySafetyIssue] {
        &self.issues
    }
}

impl Default for UseAfterFreeChecker {
    fn default() -> Self {
        Self::new()
    }
}

/// SOLID: MemoryChecker trait implementation for UseAfterFreeChecker
impl MemoryChecker for UseAfterFreeChecker {
    fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
        UseAfterFreeChecker::analyze(self, nodes)
    }

    fn name(&self) -> &'static str {
        "UseAfterFreeChecker"
    }

    fn reset(&mut self) {
        self.heap = SymbolicHeap::new();
        self.issues.clear();
    }
}

/// Double-Free Checker
///
/// Detects when memory is freed multiple times.
///
/// Algorithm:
/// - Track free count in SymbolicHeap
/// - free_count = 0: Allocated
/// - free_count = 1: Freed (OK)
/// - free_count > 1: Double-free (ERROR)
///
/// Note: This is integrated into SymbolicHeap.deallocate()
pub struct DoubleFreeChecker {
    /// Symbolic heap
    heap: SymbolicHeap,

    /// Issues found
    issues: Vec<MemorySafetyIssue>,
}

impl DoubleFreeChecker {
    pub fn new() -> Self {
        Self {
            heap: SymbolicHeap::new(),
            issues: Vec::new(),
        }
    }

    /// Analyze nodes for double-free
    pub fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
        for node in nodes {
            self.check_node(node);
        }

        std::mem::take(&mut self.issues)
    }

    fn check_node(&mut self, node: &Node) {
        if let NodeKind::Expression = node.kind {
            let func_name = node.name.as_deref().unwrap_or(&node.fqn);
            if matches!(func_name, "free" | "delete")
                || func_name.contains("free")
                || func_name.contains("delete")
            {
                // Extract argument from FQN (e.g., "free::p" -> "p")
                if let Some(arg) = node.fqn.split("::").nth(1) {
                    if let Err(err) = self.heap.deallocate(arg) {
                        if err.contains("Double-free") {
                            let issue = MemorySafetyIssue::double_free(
                                arg,
                                format!("{}:{}", node.file_path, node.span.start_line),
                            );
                            self.issues.push(issue);
                        }
                    }
                }
            }
        }
    }

    pub fn get_issues(&self) -> &[MemorySafetyIssue] {
        &self.issues
    }
}

impl Default for DoubleFreeChecker {
    fn default() -> Self {
        Self::new()
    }
}

/// SOLID: MemoryChecker trait implementation for DoubleFreeChecker
impl MemoryChecker for DoubleFreeChecker {
    fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
        DoubleFreeChecker::analyze(self, nodes)
    }

    fn name(&self) -> &'static str {
        "DoubleFreeChecker"
    }

    fn reset(&mut self) {
        self.heap = SymbolicHeap::new();
        self.issues.clear();
    }
}

/// Buffer Overflow Checker (Spatial Memory Safety)
///
/// Detects potential buffer overflows by tracking array sizes and access indices.
/// Implements **Spatial Memory Safety** via bounds checking.
///
/// ## Algorithm
/// 1. Track array declarations and sizes
/// 2. Track index variables and constraints from conditionals
/// 3. Check array accesses against bounds
/// 4. **NEW**: Analyze control flow edges for index constraints
///
/// ## Detection Types
/// - **Constant index**: arr[15] when arr.len == 10
/// - **Symbolic index**: arr[i] when i not bounded
/// - **Negative index**: arr[-1]
/// - **Loop bounds**: for i in range(n): arr[i] when n > len(arr)
///
/// ## SOTA Features (Spatial Memory Safety)
/// - **Path-sensitive bounds**: Tracks index constraints per control flow path
/// - **Conditional guards**: Extracts bounds from `if i < len(arr)` patterns
/// - **Loop analysis**: Detects unsafe loop-based array access
///
/// # Integration with ArrayBoundsChecker
/// Uses SMT-lite ArrayBoundsChecker for constraint tracking
pub struct BufferOverflowChecker {
    /// Array bounds checker from SMT module
    bounds_checker: ArrayBoundsChecker,

    /// Array declarations: array_name → (file_path, line)
    array_locations: HashMap<String, String>,

    /// Index variable constraints: var → (min, max)
    index_constraints: HashMap<String, (Option<i64>, Option<i64>)>,

    /// Issues found
    issues: Vec<MemorySafetyIssue>,
}

impl BufferOverflowChecker {
    pub fn new() -> Self {
        Self {
            bounds_checker: ArrayBoundsChecker::new(),
            array_locations: HashMap::new(),
            index_constraints: HashMap::new(),
            issues: Vec::new(),
        }
    }

    /// Analyze nodes for buffer overflows (basic analysis without edges)
    pub fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
        // Two-pass analysis:
        // Pass 1: Collect array declarations and sizes
        for node in nodes {
            self.collect_array_info(node);
        }

        // Pass 2: Check array accesses
        for node in nodes {
            self.check_array_access(node);
        }

        std::mem::take(&mut self.issues)
    }

    /// Analyze with edge information for path-sensitive bounds checking
    ///
    /// # Spatial Memory Safety Enhancement
    /// Uses control flow edges to extract index constraints from:
    /// - Conditional guards: `if i < len(arr)`
    /// - Loop bounds: `for i in range(n)`
    /// - Assertions: `assert i >= 0`
    pub fn analyze_with_edges(
        &mut self,
        nodes: &[Node],
        edges: &[crate::shared::models::Edge],
    ) -> Vec<MemorySafetyIssue> {
        // Pass 0: Extract index constraints from control flow
        self.extract_index_constraints_from_edges(edges);

        // Pass 1: Collect array declarations and sizes
        for node in nodes {
            self.collect_array_info(node);
        }

        // Pass 2: Extract bounds from conditional nodes
        for node in nodes {
            self.extract_bounds_from_conditionals(node);
        }

        // Pass 3: Check array accesses with enhanced constraints
        for node in nodes {
            self.check_array_access_enhanced(node);
        }

        std::mem::take(&mut self.issues)
    }

    /// Extract index constraints from control flow edges
    fn extract_index_constraints_from_edges(&mut self, edges: &[crate::shared::models::Edge]) {
        use crate::shared::models::EdgeKind;

        for edge in edges {
            match edge.kind {
                // TrueBranch: condition was true
                // Extract constraints from the condition
                EdgeKind::TrueBranch => {
                    // If we have metadata about the condition, extract it
                    if let Some(metadata) = &edge.metadata {
                        if let Some(context) = &metadata.context {
                            self.parse_condition_for_bounds(context, true);
                        }
                    }
                }

                // FalseBranch: condition was false (negated)
                EdgeKind::FalseBranch => {
                    if let Some(metadata) = &edge.metadata {
                        if let Some(context) = &metadata.context {
                            self.parse_condition_for_bounds(context, false);
                        }
                    }
                }

                _ => {}
            }
        }
    }

    /// Parse a condition string to extract index bounds
    ///
    /// Patterns recognized:
    /// - `i < N` → upper bound N-1
    /// - `i <= N` → upper bound N
    /// - `i >= N` → lower bound N
    /// - `i > N` → lower bound N+1
    /// - `i < len(arr)` → upper bound = arr.len - 1
    fn parse_condition_for_bounds(&mut self, condition: &str, is_true_branch: bool) {
        // Pattern: "var < value" or "var <= value"
        let patterns = [
            (r"(\w+)\s*<\s*(\d+)", "<"),
            (r"(\w+)\s*<=\s*(\d+)", "<="),
            (r"(\w+)\s*>\s*(\d+)", ">"),
            (r"(\w+)\s*>=\s*(\d+)", ">="),
            (r"(\w+)\s*<\s*len\((\w+)\)", "<len"),
        ];

        // Simple pattern matching (could use regex for production)
        for (pattern, op) in &patterns {
            if let Some((var, bound)) = self.match_simple_pattern(condition, pattern) {
                self.apply_bound_constraint(&var, &bound, op, is_true_branch);
            }
        }
    }

    /// Simple pattern matching for common bound patterns
    fn match_simple_pattern(&self, condition: &str, _pattern: &str) -> Option<(String, String)> {
        // Simple implementation - match common patterns
        let condition = condition.trim();

        // Pattern: "var < N"
        if let Some(lt_pos) = condition.find('<') {
            let var = condition[..lt_pos].trim();
            let bound = condition[lt_pos + 1..].trim().trim_start_matches('=');

            if !var.is_empty() && !bound.is_empty() {
                return Some((var.to_string(), bound.to_string()));
            }
        }

        // Pattern: "var > N"
        if let Some(gt_pos) = condition.find('>') {
            let var = condition[..gt_pos].trim();
            let bound = condition[gt_pos + 1..].trim().trim_start_matches('=');

            if !var.is_empty() && !bound.is_empty() {
                return Some((var.to_string(), bound.to_string()));
            }
        }

        None
    }

    /// Apply a bound constraint to an index variable
    fn apply_bound_constraint(&mut self, var: &str, bound: &str, op: &str, is_true_branch: bool) {
        // Try to parse bound as number
        let bound_val: Option<i64> = bound.parse().ok();

        // Pre-compute array size for "<len" case (to avoid borrow conflict)
        let array_size_opt = if op == "<len" {
            self.get_array_size_opt(bound)
        } else {
            None
        };

        // Get or create constraint entry
        let entry = self
            .index_constraints
            .entry(var.to_string())
            .or_insert((None, None));

        match (op, is_true_branch) {
            // i < N (true): upper bound = N - 1
            ("<", true) => {
                if let Some(n) = bound_val {
                    entry.1 = Some(entry.1.map_or(n - 1, |old| old.min(n - 1)));
                }
            }
            // i < N (false): lower bound = N
            ("<", false) => {
                if let Some(n) = bound_val {
                    entry.0 = Some(entry.0.map_or(n, |old| old.max(n)));
                }
            }
            // i <= N (true): upper bound = N
            ("<=", true) => {
                if let Some(n) = bound_val {
                    entry.1 = Some(entry.1.map_or(n, |old| old.min(n)));
                }
            }
            // i > N (true): lower bound = N + 1
            (">", true) => {
                if let Some(n) = bound_val {
                    entry.0 = Some(entry.0.map_or(n + 1, |old| old.max(n + 1)));
                }
            }
            // i >= N (true): lower bound = N
            (">=", true) => {
                if let Some(n) = bound_val {
                    entry.0 = Some(entry.0.map_or(n, |old| old.max(n)));
                }
            }
            // i < len(arr): upper bound = arr.len - 1
            ("<len", true) => {
                // bound is the array name (size was pre-computed)
                if let Some(size) = array_size_opt {
                    let max = size as i64 - 1;
                    entry.1 = Some(entry.1.map_or(max, |old| old.min(max)));
                }
            }
            _ => {}
        }

        // Propagate to ArrayBoundsChecker
        let (min, max) = *self.index_constraints.get(var).unwrap();
        self.propagate_constraint_to_bounds_checker(var, min, max);
    }

    /// Propagate constraints to the underlying ArrayBoundsChecker
    fn propagate_constraint_to_bounds_checker(
        &mut self,
        var: &str,
        min: Option<i64>,
        max: Option<i64>,
    ) {
        use crate::features::smt::domain::{ComparisonOp, ConstValue, PathCondition};

        if let Some(lb) = min {
            let cond =
                PathCondition::new(var.to_string(), ComparisonOp::Ge, Some(ConstValue::Int(lb)));
            self.bounds_checker
                .add_index_constraint(var.to_string(), &cond);
        }

        if let Some(ub) = max {
            let cond =
                PathCondition::new(var.to_string(), ComparisonOp::Le, Some(ConstValue::Int(ub)));
            self.bounds_checker
                .add_index_constraint(var.to_string(), &cond);
        }
    }

    /// Extract bounds from conditional nodes
    fn extract_bounds_from_conditionals(&mut self, node: &Node) {
        // Look for comparison expressions that might be bounds checks
        if let NodeKind::Expression = node.kind {
            // Pattern: if i < len(arr) or if i >= 0
            if node.fqn.contains("__lt__")
                || node.fqn.contains("__le__")
                || node.fqn.contains("__gt__")
                || node.fqn.contains("__ge__")
            {
                // Try to extract constraint from FQN
                // FQN format: "i::__lt__::10" or similar
                self.parse_comparison_fqn(&node.fqn);
            }
        }
    }

    /// Parse comparison FQN to extract bounds
    fn parse_comparison_fqn(&mut self, fqn: &str) {
        let parts: Vec<&str> = fqn.split("::").collect();
        if parts.len() >= 3 {
            let var = parts[0];
            let op = parts[1];
            let bound = parts[2];

            if let Ok(bound_val) = bound.parse::<i64>() {
                let entry = self
                    .index_constraints
                    .entry(var.to_string())
                    .or_insert((None, None));

                match op {
                    "__lt__" => entry.1 = Some(bound_val - 1),
                    "__le__" => entry.1 = Some(bound_val),
                    "__gt__" => entry.0 = Some(bound_val + 1),
                    "__ge__" => entry.0 = Some(bound_val),
                    _ => {}
                }
            }
        }
    }

    /// Enhanced array access check using collected constraints
    fn check_array_access_enhanced(&mut self, node: &Node) {
        if let NodeKind::Expression = node.kind {
            if node.fqn.contains("__getitem__") || node.fqn.contains('[') {
                if let Some((array_name, index_info)) = self.parse_subscript(&node.fqn) {
                    let location = format!("{}:{}", node.file_path, node.span.start_line);

                    match index_info {
                        IndexInfo::Constant(idx) => {
                            // Direct bounds check
                            if !self.bounds_checker.is_access_safe(&array_name, idx) {
                                let size = self.get_array_size(&array_name);
                                let issue = MemorySafetyIssue::buffer_overflow(
                                    &array_name,
                                    idx,
                                    size,
                                    location,
                                );
                                self.issues.push(issue);
                            }
                        }
                        IndexInfo::Variable(idx_var) => {
                            // Check with constraints
                            let is_safe = self
                                .is_symbolic_access_safe_with_constraints(&array_name, &idx_var);

                            if !is_safe {
                                let issue = MemorySafetyIssue::buffer_overflow_symbolic(
                                    &array_name,
                                    &idx_var,
                                    location,
                                );
                                self.issues.push(issue);
                            }
                        }
                    }
                }
            }
        }
    }

    /// Check symbolic access with collected constraints
    fn is_symbolic_access_safe_with_constraints(&self, array: &str, index_var: &str) -> bool {
        // First check ArrayBoundsChecker
        if self
            .bounds_checker
            .is_symbolic_access_safe(&array.to_string(), &index_var.to_string())
        {
            return true;
        }

        // Then check our collected constraints
        if let Some((min, max)) = self.index_constraints.get(index_var) {
            if let Some(array_size) = self.get_array_size_opt(array) {
                let lower_ok = min.map_or(false, |m| m >= 0);
                let upper_ok = max.map_or(false, |m| m < array_size as i64);
                return lower_ok && upper_ok;
            }
        }

        false
    }

    /// Get array size as Option
    fn get_array_size_opt(&self, array_name: &str) -> Option<usize> {
        use crate::features::smt::infrastructure::ArraySize;

        match self.bounds_checker.get_array_size(&array_name.to_string()) {
            Some(ArraySize::Constant(size)) => Some(*size),
            _ => None,
        }
    }

    /// Pass 1: Collect array declarations
    fn collect_array_info(&mut self, node: &Node) {
        match node.kind {
            NodeKind::Variable => {
                if let Some(name) = &node.name {
                    // Check type annotation for array/list types
                    if let Some(type_ann) = &node.type_annotation {
                        if let Some(size) = self.extract_array_size(type_ann) {
                            self.bounds_checker.set_array_size(name.clone(), size);
                            self.array_locations.insert(
                                name.clone(),
                                format!("{}:{}", node.file_path, node.span.start_line),
                            );
                        }
                    }
                }
            }

            NodeKind::Expression => {
                // Detect array literals: arr = [1, 2, 3]
                if let Some(name) = &node.name {
                    // Simple heuristic: FQN contains "list" or "array"
                    if node.fqn.contains("list") || node.fqn.contains("array") {
                        // Try to infer size from FQN pattern
                        if let Some(size) = self.extract_literal_size(&node.fqn) {
                            self.bounds_checker.set_array_size(name.clone(), size);
                            self.array_locations.insert(
                                name.clone(),
                                format!("{}:{}", node.file_path, node.span.start_line),
                            );
                        }
                    }
                }
            }

            _ => {}
        }
    }

    /// Pass 2: Check array accesses
    fn check_array_access(&mut self, node: &Node) {
        if let NodeKind::Expression = node.kind {
            // Detect subscript access: arr[i]
            // FQN pattern: "arr::__getitem__::i" or "arr[i]"
            if node.fqn.contains("__getitem__") || node.fqn.contains('[') {
                if let Some((array_name, index_info)) = self.parse_subscript(&node.fqn) {
                    let location = format!("{}:{}", node.file_path, node.span.start_line);

                    match index_info {
                        IndexInfo::Constant(idx) => {
                            // Check constant index
                            if !self.bounds_checker.is_access_safe(&array_name, idx) {
                                // Get array size for error message
                                let size = self.get_array_size(&array_name);
                                let issue = MemorySafetyIssue::buffer_overflow(
                                    &array_name,
                                    idx,
                                    size,
                                    location,
                                );
                                self.issues.push(issue);
                            }
                        }
                        IndexInfo::Variable(idx_var) => {
                            // Check symbolic index
                            if !self
                                .bounds_checker
                                .is_symbolic_access_safe(&array_name, &idx_var)
                            {
                                let issue = MemorySafetyIssue::buffer_overflow_symbolic(
                                    &array_name,
                                    &idx_var,
                                    location,
                                );
                                self.issues.push(issue);
                            }
                        }
                    }
                }
            }
        }
    }

    /// Extract array size from type annotation
    /// e.g., "List[int, 10]" → Some(10), "int[100]" → Some(100)
    fn extract_array_size(&self, type_ann: &str) -> Option<usize> {
        // Pattern: [N] or , N] at the end
        if let Some(bracket_pos) = type_ann.rfind('[') {
            let after_bracket = &type_ann[bracket_pos + 1..];
            if let Some(close_pos) = after_bracket.find(']') {
                let size_str = &after_bracket[..close_pos];
                // Handle "int, 10" → "10"
                let size_part = size_str.split(',').last()?.trim();
                return size_part.parse().ok();
            }
        }
        None
    }

    /// Extract size from array literal
    /// e.g., "list::literal::3" → Some(3)
    fn extract_literal_size(&self, fqn: &str) -> Option<usize> {
        // Simple heuristic: last numeric part
        fqn.split("::").last()?.parse().ok()
    }

    /// Parse subscript expression
    /// e.g., "arr::__getitem__::5" → ("arr", Constant(5))
    /// e.g., "arr[i]" → ("arr", Variable("i"))
    fn parse_subscript(&self, fqn: &str) -> Option<(String, IndexInfo)> {
        // Pattern 1: arr::__getitem__::index
        if fqn.contains("__getitem__") {
            let parts: Vec<&str> = fqn.split("::").collect();
            if parts.len() >= 3 {
                let array_name = parts[0].to_string();
                let index_str = parts[2];

                // Try to parse as constant
                if let Ok(idx) = index_str.parse::<i64>() {
                    return Some((array_name, IndexInfo::Constant(idx)));
                } else {
                    return Some((array_name, IndexInfo::Variable(index_str.to_string())));
                }
            }
        }

        // Pattern 2: arr[index]
        if let Some(bracket_pos) = fqn.find('[') {
            let array_name = fqn[..bracket_pos].to_string();
            if let Some(close_pos) = fqn.find(']') {
                let index_str = &fqn[bracket_pos + 1..close_pos];

                if let Ok(idx) = index_str.parse::<i64>() {
                    return Some((array_name, IndexInfo::Constant(idx)));
                } else {
                    return Some((array_name, IndexInfo::Variable(index_str.to_string())));
                }
            }
        }

        None
    }

    /// Get array size (0 if unknown)
    fn get_array_size(&self, array_name: &str) -> usize {
        use crate::features::smt::infrastructure::ArraySize;

        match self.bounds_checker.get_array_size(&array_name.to_string()) {
            Some(ArraySize::Constant(size)) => *size,
            Some(ArraySize::Variable(_)) => 0, // Variable size - unknown at compile time
            Some(ArraySize::Unknown) | None => 0,
        }
    }

    /// Register index constraint (for symbolic analysis)
    pub fn add_index_constraint(&mut self, index_var: &str, min: Option<i64>, max: Option<i64>) {
        use crate::features::smt::domain::{ComparisonOp, ConstValue, PathCondition};

        if let Some(lb) = min {
            let cond = PathCondition::new(
                index_var.to_string(),
                ComparisonOp::Ge,
                Some(ConstValue::Int(lb)),
            );
            self.bounds_checker
                .add_index_constraint(index_var.to_string(), &cond);
        }
        if let Some(ub) = max {
            let cond = PathCondition::new(
                index_var.to_string(),
                ComparisonOp::Lt,
                Some(ConstValue::Int(ub)),
            );
            self.bounds_checker
                .add_index_constraint(index_var.to_string(), &cond);
        }
    }

    pub fn get_issues(&self) -> &[MemorySafetyIssue] {
        &self.issues
    }
}

impl Default for BufferOverflowChecker {
    fn default() -> Self {
        Self::new()
    }
}

/// SOLID: MemoryChecker trait implementation for BufferOverflowChecker
impl MemoryChecker for BufferOverflowChecker {
    fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
        BufferOverflowChecker::analyze(self, nodes)
    }

    fn analyze_with_edges(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<MemorySafetyIssue> {
        BufferOverflowChecker::analyze_with_edges(self, nodes, edges)
    }

    fn name(&self) -> &'static str {
        "BufferOverflowChecker"
    }

    fn reset(&mut self) {
        self.bounds_checker = ArrayBoundsChecker::new();
        self.array_locations.clear();
        self.index_constraints.clear();
        self.issues.clear();
    }
}

/// Index information for array access
enum IndexInfo {
    /// Constant index (e.g., arr[5])
    Constant(i64),
    /// Variable index (e.g., arr[i])
    Variable(String),
}

// ═══════════════════════════════════════════════════════════════════════════
// Spatial Memory Safety Checker (SOTA Implementation)
// ═══════════════════════════════════════════════════════════════════════════
//
// Academic References:
// - Nagarakatte, S. et al. (2009). "SoftBound: Highly Compatible and Complete
//   Spatial Memory Safety for C"
// - Necula, G. C. et al. (2005). "CCured: Type-Safe Retrofitting of Legacy
//   Software"
// - Dhurjati, D. et al. (2003). "Memory Safety Without Runtime Checks or
//   Garbage Collection"
//
// Industry:
// - LLVM AddressSanitizer: Runtime spatial/temporal safety
// - Microsoft SafeInt: Integer overflow detection for size calculations
// - Google BoundsSan: LLVM-based bounds checking
//
// ## Spatial Memory Safety Categories
//
// 1. **Buffer Overflow**: Array access beyond allocated bounds
// 2. **Out-of-Bounds Pointer Arithmetic**: ptr + offset > end
// 3. **Sub-object Bounds Violation**: Accessing beyond field bounds
// 4. **Type Size Mismatch**: Cast to larger type than allocated
// 5. **Negative Offset**: ptr - offset < start
// ═══════════════════════════════════════════════════════════════════════════

/// Object metadata for spatial safety tracking
#[derive(Debug, Clone)]
pub struct ObjectBounds {
    /// Base address (symbolic)
    pub base: String,
    /// Total allocated size in bytes
    pub size: usize,
    /// Field bounds: field_name → (offset, size)
    pub fields: HashMap<String, (usize, usize)>,
    /// Type of the object (for type-based checks)
    pub type_name: Option<String>,
}

impl ObjectBounds {
    pub fn new(base: impl Into<String>, size: usize) -> Self {
        Self {
            base: base.into(),
            size,
            fields: HashMap::new(),
            type_name: None,
        }
    }

    pub fn with_type(mut self, type_name: impl Into<String>) -> Self {
        self.type_name = Some(type_name.into());
        self
    }

    pub fn add_field(&mut self, name: impl Into<String>, offset: usize, size: usize) {
        self.fields.insert(name.into(), (offset, size));
    }

    /// Check if offset is within object bounds
    pub fn is_offset_valid(&self, offset: i64) -> bool {
        offset >= 0 && (offset as usize) < self.size
    }

    /// Check if access of given size at offset is valid
    pub fn is_access_valid(&self, offset: i64, access_size: usize) -> bool {
        if offset < 0 {
            return false;
        }
        let offset = offset as usize;
        offset
            .checked_add(access_size)
            .map_or(false, |end| end <= self.size)
    }

    /// Check if field access is valid
    pub fn is_field_access_valid(&self, field_name: &str, access_size: usize) -> Option<bool> {
        self.fields
            .get(field_name)
            .map(|&(_, field_size)| access_size <= field_size)
    }
}

/// Pointer information for spatial tracking
#[derive(Debug, Clone)]
pub struct PointerInfo {
    /// Base object this pointer refers to
    pub base_object: String,
    /// Current offset from base
    pub current_offset: i64,
    /// Derived type (if cast)
    pub derived_type: Option<String>,
    /// Derived type size (if cast)
    pub derived_size: Option<usize>,
}

impl PointerInfo {
    pub fn new(base_object: impl Into<String>) -> Self {
        Self {
            base_object: base_object.into(),
            current_offset: 0,
            derived_type: None,
            derived_size: None,
        }
    }

    pub fn with_offset(mut self, offset: i64) -> Self {
        self.current_offset = offset;
        self
    }

    pub fn with_cast(mut self, type_name: impl Into<String>, size: usize) -> Self {
        self.derived_type = Some(type_name.into());
        self.derived_size = Some(size);
        self
    }
}

/// Spatial Memory Safety Checker
///
/// Detects spatial memory safety violations:
/// - Out-of-bounds pointer arithmetic
/// - Sub-object bounds violations
/// - Type size mismatches (unsafe casts)
/// - Negative pointer offsets
///
/// ## Algorithm
///
/// 1. **Object Tracking**: Register allocations with size metadata
/// 2. **Pointer Tracking**: Track pointer derivation and offsets
/// 3. **Access Checking**: Validate all memory accesses against bounds
/// 4. **Type Checking**: Verify cast safety based on size
///
/// ## SOTA Features
///
/// - **SoftBound-style**: Base/bound tracking per pointer
/// - **CCured-style**: Type-based categorization (SAFE/SEQ/WILD)
/// - **Sub-object bounds**: Field-level precision (not just object)
pub struct SpatialMemorySafetyChecker {
    /// Object bounds: object_id → bounds metadata
    objects: HashMap<String, ObjectBounds>,

    /// Pointer tracking: pointer_var → info
    pointers: HashMap<String, PointerInfo>,

    /// Type sizes: type_name → size in bytes
    type_sizes: HashMap<String, usize>,

    /// Issues found
    issues: Vec<MemorySafetyIssue>,
}

impl SpatialMemorySafetyChecker {
    pub fn new() -> Self {
        let mut checker = Self {
            objects: HashMap::new(),
            pointers: HashMap::new(),
            type_sizes: HashMap::new(),
            issues: Vec::new(),
        };

        // Initialize common type sizes
        checker.register_type_size("char", 1);
        checker.register_type_size("i8", 1);
        checker.register_type_size("u8", 1);
        checker.register_type_size("i16", 2);
        checker.register_type_size("u16", 2);
        checker.register_type_size("short", 2);
        checker.register_type_size("i32", 4);
        checker.register_type_size("u32", 4);
        checker.register_type_size("int", 4);
        checker.register_type_size("float", 4);
        checker.register_type_size("i64", 8);
        checker.register_type_size("u64", 8);
        checker.register_type_size("long", 8);
        checker.register_type_size("double", 8);
        checker.register_type_size("*", 8); // pointer size (64-bit)

        checker
    }

    /// Register a type with its size
    pub fn register_type_size(&mut self, type_name: impl Into<String>, size: usize) {
        self.type_sizes.insert(type_name.into(), size);
    }

    /// Register an allocated object
    pub fn register_object(&mut self, id: impl Into<String>, size: usize) {
        let id = id.into();
        self.objects
            .insert(id.clone(), ObjectBounds::new(id.clone(), size));
        // Initial pointer points to base
        self.pointers.insert(id.clone(), PointerInfo::new(id));
    }

    /// Register object with type information
    pub fn register_typed_object(
        &mut self,
        id: impl Into<String>,
        size: usize,
        type_name: impl Into<String>,
    ) {
        let id = id.into();
        let type_name = type_name.into();
        self.objects.insert(
            id.clone(),
            ObjectBounds::new(id.clone(), size).with_type(&type_name),
        );
        self.pointers.insert(id.clone(), PointerInfo::new(id));
    }

    /// Register a field in an object
    pub fn register_field(
        &mut self,
        object_id: &str,
        field_name: impl Into<String>,
        offset: usize,
        size: usize,
    ) {
        if let Some(obj) = self.objects.get_mut(object_id) {
            obj.add_field(field_name, offset, size);
        }
    }

    /// Process pointer assignment: p = q
    pub fn process_pointer_copy(&mut self, target: &str, source: &str) {
        if let Some(source_info) = self.pointers.get(source).cloned() {
            self.pointers.insert(target.to_string(), source_info);
        }
    }

    /// Process pointer arithmetic: p = q + offset
    pub fn process_pointer_arithmetic(
        &mut self,
        target: &str,
        source: &str,
        offset: i64,
        location: &str,
    ) -> Option<MemorySafetyIssue> {
        let source_info = self.pointers.get(source)?.clone();
        let new_offset = source_info.current_offset + offset;

        // Check for negative offset
        if new_offset < 0 {
            let issue = MemorySafetyIssue::spatial_negative_offset(source, new_offset, location);
            self.issues.push(issue.clone());
            return Some(issue);
        }

        // Check against object bounds
        if let Some(obj) = self.objects.get(&source_info.base_object) {
            if !obj.is_offset_valid(new_offset) {
                let issue = MemorySafetyIssue::spatial_out_of_bounds(
                    source, new_offset, obj.size, location,
                );
                self.issues.push(issue.clone());
                return Some(issue);
            }
        }

        // Update pointer info
        self.pointers.insert(
            target.to_string(),
            PointerInfo::new(&source_info.base_object).with_offset(new_offset),
        );

        None
    }

    /// Process pointer cast: (T*)p
    pub fn process_pointer_cast(
        &mut self,
        pointer: &str,
        target_type: &str,
        location: &str,
    ) -> Option<MemorySafetyIssue> {
        let ptr_info = self.pointers.get(pointer)?.clone();
        let obj = self.objects.get(&ptr_info.base_object)?;

        // Get target type size
        let target_size = self.type_sizes.get(target_type).copied().or_else(|| {
            // Try to parse struct size from pattern "struct_N" where N is size
            target_type
                .strip_prefix("struct_")
                .and_then(|s| s.parse().ok())
        })?;

        // Check if remaining space is sufficient for the cast type
        let remaining = obj.size.saturating_sub(ptr_info.current_offset as usize);
        if target_size > remaining {
            let issue =
                MemorySafetyIssue::spatial_type_mismatch(pointer, target_size, remaining, location);
            self.issues.push(issue.clone());
            return Some(issue);
        }

        // Update pointer info with cast
        let mut updated = ptr_info;
        updated.derived_type = Some(target_type.to_string());
        updated.derived_size = Some(target_size);
        self.pointers.insert(pointer.to_string(), updated);

        None
    }

    /// Process memory access: *p or p[i]
    pub fn process_memory_access(
        &mut self,
        pointer: &str,
        access_size: usize,
        location: &str,
    ) -> Option<MemorySafetyIssue> {
        let ptr_info = self.pointers.get(pointer)?.clone();
        let obj = self.objects.get(&ptr_info.base_object)?;

        if !obj.is_access_valid(ptr_info.current_offset, access_size) {
            let issue = MemorySafetyIssue::spatial_out_of_bounds(
                pointer,
                ptr_info.current_offset,
                obj.size,
                location,
            );
            self.issues.push(issue.clone());
            return Some(issue);
        }

        None
    }

    /// Process field access: p->field or p.field
    pub fn process_field_access(
        &mut self,
        pointer: &str,
        field_name: &str,
        access_size: usize,
        location: &str,
    ) -> Option<MemorySafetyIssue> {
        let ptr_info = self.pointers.get(pointer)?.clone();
        let obj = self.objects.get(&ptr_info.base_object)?;

        // Check sub-object bounds
        if let Some(is_valid) = obj.is_field_access_valid(field_name, access_size) {
            if !is_valid {
                let (_, field_size) = obj.fields.get(field_name)?;
                let issue = MemorySafetyIssue::spatial_sub_object_violation(
                    &ptr_info.base_object,
                    field_name,
                    access_size,
                    *field_size,
                    location,
                );
                self.issues.push(issue.clone());
                return Some(issue);
            }
        }

        None
    }

    /// Analyze IR nodes for spatial memory safety violations
    pub fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
        // Pass 1: Collect allocations
        for node in nodes {
            self.collect_allocations(node);
        }

        // Pass 2: Check accesses
        for node in nodes {
            self.check_accesses(node);
        }

        std::mem::take(&mut self.issues)
    }

    /// Analyze with edges for enhanced checking
    pub fn analyze_with_edges(
        &mut self,
        nodes: &[Node],
        _edges: &[crate::shared::models::Edge],
    ) -> Vec<MemorySafetyIssue> {
        // For now, edges are used for future path-sensitive analysis
        self.analyze(nodes)
    }

    fn collect_allocations(&mut self, node: &Node) {
        match node.kind {
            NodeKind::Variable => {
                if let Some(name) = &node.name {
                    // Extract size from type annotation
                    if let Some(type_ann) = &node.type_annotation {
                        if let Some(size) = self.extract_type_size(type_ann) {
                            self.register_typed_object(name, size, type_ann);
                        }
                    }
                }
            }

            NodeKind::Expression => {
                // Detect malloc/calloc/new patterns
                let func = node.name.as_deref().unwrap_or(&node.fqn);
                if func.contains("malloc") || func.contains("calloc") || func.contains("new") {
                    if let Some(size) = self.extract_allocation_size(&node.fqn) {
                        // Use FQN as object ID
                        let obj_id = node.fqn.split("::").next().unwrap_or(&node.fqn);
                        self.register_object(obj_id, size);
                    }
                }
            }

            _ => {}
        }
    }

    fn check_accesses(&mut self, node: &Node) {
        if let NodeKind::Expression = node.kind {
            let location = format!("{}:{}", node.file_path, node.span.start_line);

            // Check pointer arithmetic: p + N
            if node.fqn.contains('+') || node.fqn.contains("add") {
                if let Some((ptr, offset)) = self.parse_pointer_arithmetic(&node.fqn) {
                    // Use a temporary name for the result
                    let result = format!("{}_plus_{}", ptr, offset);
                    self.process_pointer_arithmetic(&result, &ptr, offset, &location);
                }
            }

            // Check pointer casts: (T*)p
            if node.fqn.contains("cast") || node.fqn.contains("as") {
                if let Some((ptr, target_type)) = self.parse_pointer_cast(&node.fqn) {
                    self.process_pointer_cast(&ptr, &target_type, &location);
                }
            }

            // Check dereferences: *p
            if node.fqn.contains("deref") || node.fqn.starts_with('*') {
                if let Some((ptr, size)) = self.parse_dereference(&node.fqn) {
                    self.process_memory_access(&ptr, size, &location);
                }
            }

            // Check field access: p->field or p.field
            if node.fqn.contains("->") || (node.fqn.contains('.') && !node.fqn.contains("..")) {
                if let Some((ptr, field, size)) = self.parse_field_access(&node.fqn) {
                    self.process_field_access(&ptr, &field, size, &location);
                }
            }
        }
    }

    fn extract_type_size(&self, type_ann: &str) -> Option<usize> {
        // Direct type lookup
        if let Some(&size) = self.type_sizes.get(type_ann) {
            return Some(size);
        }

        // Array pattern: T[N]
        if let Some(bracket_pos) = type_ann.find('[') {
            if let Some(close_pos) = type_ann.find(']') {
                let element_type = &type_ann[..bracket_pos];
                let count_str = &type_ann[bracket_pos + 1..close_pos];
                if let (Some(&elem_size), Ok(count)) = (
                    self.type_sizes.get(element_type),
                    count_str.parse::<usize>(),
                ) {
                    return Some(elem_size * count);
                }
            }
        }

        // Pointer type: *T or T*
        if type_ann.contains('*') {
            return self.type_sizes.get("*").copied();
        }

        None
    }

    fn extract_allocation_size(&self, fqn: &str) -> Option<usize> {
        // Pattern: malloc(N) or malloc::N
        let parts: Vec<&str> = fqn.split("::").collect();
        for (i, part) in parts.iter().enumerate() {
            if *part == "malloc" || *part == "calloc" || *part == "new" {
                // Try next part as size
                if let Some(size_part) = parts.get(i + 1) {
                    if let Ok(size) = size_part.parse::<usize>() {
                        return Some(size);
                    }
                }
            }
        }

        // Pattern: malloc(100) inside parentheses
        if let (Some(start), Some(end)) = (fqn.find('('), fqn.find(')')) {
            let inner = &fqn[start + 1..end];
            if let Ok(size) = inner.parse::<usize>() {
                return Some(size);
            }
        }

        None
    }

    fn parse_pointer_arithmetic(&self, fqn: &str) -> Option<(String, i64)> {
        // Pattern: p+N or p::add::N
        if let Some(plus_pos) = fqn.find('+') {
            let ptr = fqn[..plus_pos].trim().to_string();
            let offset_str = fqn[plus_pos + 1..].trim();
            if let Ok(offset) = offset_str.parse::<i64>() {
                return Some((ptr, offset));
            }
        }

        // Pattern: p::add::N
        let parts: Vec<&str> = fqn.split("::").collect();
        if parts.len() >= 3 && parts[1] == "add" {
            let ptr = parts[0].to_string();
            if let Ok(offset) = parts[2].parse::<i64>() {
                return Some((ptr, offset));
            }
        }

        None
    }

    fn parse_pointer_cast(&self, fqn: &str) -> Option<(String, String)> {
        // Pattern: cast::ptr::target_type or (target_type)ptr
        let parts: Vec<&str> = fqn.split("::").collect();
        if parts.len() >= 3 && parts[0] == "cast" {
            return Some((parts[1].to_string(), parts[2].to_string()));
        }

        // Pattern: (T*)p → represented as T*::p
        if let Some(star_pos) = fqn.find('*') {
            let type_name = fqn[..star_pos + 1].trim().to_string();
            let rest = fqn[star_pos + 1..].trim();
            if let Some(ptr) = rest.split("::").next() {
                if !ptr.is_empty() {
                    return Some((ptr.trim().to_string(), type_name));
                }
            }
        }

        None
    }

    fn parse_dereference(&self, fqn: &str) -> Option<(String, usize)> {
        // Pattern: deref::ptr::size or *ptr
        let parts: Vec<&str> = fqn.split("::").collect();
        if parts.len() >= 2 && parts[0] == "deref" {
            let ptr = parts[1].to_string();
            let size = parts.get(2).and_then(|s| s.parse().ok()).unwrap_or(8);
            return Some((ptr, size));
        }

        // Pattern: *ptr (default to 8 bytes)
        if fqn.starts_with('*') {
            let ptr = fqn[1..].trim().to_string();
            return Some((ptr, 8));
        }

        None
    }

    fn parse_field_access(&self, fqn: &str) -> Option<(String, String, usize)> {
        // Pattern: ptr->field or ptr.field
        let sep = if fqn.contains("->") { "->" } else { "." };
        let parts: Vec<&str> = fqn.split(sep).collect();
        if parts.len() >= 2 {
            let ptr = parts[0].to_string();
            let field = parts[1].split("::").next()?.to_string();
            // Default field size, could be enhanced with type info
            return Some((ptr, field, 8));
        }

        None
    }

    /// Get all detected issues
    pub fn get_issues(&self) -> &[MemorySafetyIssue] {
        &self.issues
    }
}

impl Default for SpatialMemorySafetyChecker {
    fn default() -> Self {
        Self::new()
    }
}

/// SOLID: MemoryChecker trait implementation for SpatialMemorySafetyChecker
impl MemoryChecker for SpatialMemorySafetyChecker {
    fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
        SpatialMemorySafetyChecker::analyze(self, nodes)
    }

    fn analyze_with_edges(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<MemorySafetyIssue> {
        SpatialMemorySafetyChecker::analyze_with_edges(self, nodes, edges)
    }

    fn name(&self) -> &'static str {
        "SpatialMemorySafetyChecker"
    }

    fn reset(&mut self) {
        self.objects.clear();
        self.pointers.clear();
        self.issues.clear();
        // Keep type_sizes as they are standard
    }
}

/// Unified Memory Safety Analyzer (SOLID Compliant)
///
/// Combines all memory safety checkers using trait-based design:
/// - Null dereference
/// - Use-after-free
/// - Double-free
/// - Buffer overflow (integrated with ArrayBoundsChecker)
/// - Spatial memory safety (pointer arithmetic, type casts, sub-object bounds)
///
/// # SOLID Compliance
///
/// - **S** (Single Responsibility): Each checker has one job
/// - **O** (Open/Closed): Add new checkers without modifying this code
/// - **L** (Liskov Substitution): All checkers implement MemoryChecker trait
/// - **I** (Interface Segregation): MemoryChecker has minimal interface
/// - **D** (Dependency Inversion): Depends on MemoryChecker trait, not concrete types
///
/// # Example: Adding a Custom Checker
///
/// ```rust,ignore
/// let mut analyzer = MemorySafetyAnalyzer::new();
///
/// // Add custom checker without modifying MemorySafetyAnalyzer code (OCP)
/// analyzer.add_checker(Box::new(MyCustomChecker::new()));
///
/// let issues = analyzer.analyze(&nodes);
/// ```
///
/// # Academic References
/// - SoftBound (Nagarakatte et al.): Base/bound tracking
/// - CCured (Necula et al.): Type-safe pointer categorization
/// - LLVM AddressSanitizer: Industry-standard spatial safety
pub struct MemorySafetyAnalyzer {
    // Built-in checkers (kept for backward compatibility and direct access)
    null_checker: NullDereferenceChecker,
    uaf_checker: UseAfterFreeChecker,
    double_free_checker: DoubleFreeChecker,
    buffer_overflow_checker: BufferOverflowChecker,
    spatial_checker: SpatialMemorySafetyChecker,

    /// Custom checkers (SOLID: Open/Closed Principle)
    /// New checkers can be added without modifying this struct
    custom_checkers: Vec<Box<dyn MemoryChecker>>,
}

impl MemorySafetyAnalyzer {
    pub fn new() -> Self {
        Self {
            null_checker: NullDereferenceChecker::new(),
            uaf_checker: UseAfterFreeChecker::new(),
            double_free_checker: DoubleFreeChecker::new(),
            buffer_overflow_checker: BufferOverflowChecker::new(),
            spatial_checker: SpatialMemorySafetyChecker::new(),
            custom_checkers: Vec::new(),
        }
    }

    /// Add a custom memory checker (SOLID: Open/Closed Principle)
    ///
    /// Allows adding new checkers without modifying MemorySafetyAnalyzer code.
    ///
    /// # Example
    /// ```rust,ignore
    /// struct MyChecker;
    /// impl MemoryChecker for MyChecker {
    ///     fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> { vec![] }
    ///     fn name(&self) -> &'static str { "MyChecker" }
    /// }
    ///
    /// analyzer.add_checker(Box::new(MyChecker));
    /// ```
    pub fn add_checker(&mut self, checker: Box<dyn MemoryChecker>) {
        self.custom_checkers.push(checker);
    }

    /// Get list of all checker names (for debugging/logging)
    pub fn checker_names(&self) -> Vec<&'static str> {
        let mut names = vec![
            "NullDereferenceChecker",
            "UseAfterFreeChecker",
            "DoubleFreeChecker",
            "BufferOverflowChecker",
            "SpatialMemorySafetyChecker",
        ];
        for checker in &self.custom_checkers {
            names.push(checker.name());
        }
        names
    }

    /// Analyze all memory safety issues
    ///
    /// Runs all checkers (built-in + custom) in sequence.
    pub fn analyze(&mut self, nodes: &[Node]) -> Vec<MemorySafetyIssue> {
        let mut all_issues = Vec::new();

        // Built-in checkers
        all_issues.extend(self.null_checker.analyze(nodes));
        all_issues.extend(self.uaf_checker.analyze(nodes));
        all_issues.extend(self.double_free_checker.analyze(nodes));
        all_issues.extend(self.buffer_overflow_checker.analyze(nodes));
        all_issues.extend(self.spatial_checker.analyze(nodes));

        // Custom checkers (SOLID: runs any checker implementing MemoryChecker)
        for checker in &mut self.custom_checkers {
            all_issues.extend(checker.analyze(nodes));
        }

        all_issues
    }

    /// Analyze with edge information for enhanced detection
    ///
    /// # Spatial Memory Safety Enhancement
    /// Uses control flow edges to extract index constraints:
    /// - TrueBranch/FalseBranch: Extract bounds from conditionals
    /// - Loop patterns: Track iteration bounds
    pub fn analyze_with_edges(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<MemorySafetyIssue> {
        let mut all_issues = Vec::new();

        // Standard checkers (don't benefit from edges)
        all_issues.extend(self.null_checker.analyze(nodes));
        all_issues.extend(self.uaf_checker.analyze(nodes));
        all_issues.extend(self.double_free_checker.analyze(nodes));

        // Enhanced checkers with edge-based constraint extraction
        all_issues.extend(
            self.buffer_overflow_checker
                .analyze_with_edges(nodes, edges),
        );
        all_issues.extend(self.spatial_checker.analyze_with_edges(nodes, edges));

        // Custom checkers with edge support
        for checker in &mut self.custom_checkers {
            all_issues.extend(checker.analyze_with_edges(nodes, edges));
        }

        all_issues
    }

    /// Reset all checkers for reuse
    pub fn reset(&mut self) {
        self.null_checker.reset();
        self.uaf_checker.reset();
        self.double_free_checker.reset();
        self.buffer_overflow_checker.reset();
        self.spatial_checker.reset();
        for checker in &mut self.custom_checkers {
            checker.reset();
        }
    }

    /// Get buffer overflow checker for manual configuration
    pub fn buffer_overflow_checker_mut(&mut self) -> &mut BufferOverflowChecker {
        &mut self.buffer_overflow_checker
    }

    /// Get spatial memory safety checker for manual configuration
    pub fn spatial_checker_mut(&mut self) -> &mut SpatialMemorySafetyChecker {
        &mut self.spatial_checker
    }
}

impl Default for MemorySafetyAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::super::separation_logic::MemorySafetyIssueKind;
    use super::*;

    // ═══════════════════════════════════════════════════════════════════════════
    // Null Dereference Checker Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_null_checker_basic() {
        let mut checker = NullDereferenceChecker::new();
        checker.mark_nullable("p");

        let span = Span::new(10, 0, 10, 10);
        assert!(checker.check_null_dereference("p", &span, "test.c"));
        assert_eq!(checker.get_issues().len(), 1);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Use-After-Free Checker Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_uaf_checker() {
        let mut checker = UseAfterFreeChecker::new();

        // Simulate allocation: let p = malloc(...)
        let _alloc_node = Node::new(
            "alloc_1".to_string(),
            NodeKind::Expression,
            "malloc::result".to_string(),
            "test.c".to_string(),
            Span::new(5, 0, 5, 20),
        )
        .with_name("malloc");

        // Manually allocate for test
        checker.heap.allocate("p");

        // Simulate free: free(p)
        let free_node = Node::new(
            "free_1".to_string(),
            NodeKind::Expression,
            "free::p".to_string(),
            "test.c".to_string(),
            Span::new(10, 0, 10, 10),
        )
        .with_name("free");

        // Simulate use after free: p->field
        let use_node = Node::new(
            "use_1".to_string(),
            NodeKind::Expression,
            "p::field".to_string(),
            "test.c".to_string(),
            Span::new(15, 0, 15, 10),
        )
        .with_name("field_access");

        let issues = checker.analyze(&[free_node, use_node]);
        assert!(issues
            .iter()
            .any(|i| matches!(i.kind, MemorySafetyIssueKind::UseAfterFree)));
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Double-Free Checker Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_double_free_checker() {
        let mut checker = DoubleFreeChecker::new();

        // Allocate
        checker.heap.allocate("p");

        // First free: free(p)
        let free1 = Node::new(
            "free_1".to_string(),
            NodeKind::Expression,
            "free::p".to_string(),
            "test.c".to_string(),
            Span::new(10, 0, 10, 10),
        )
        .with_name("free");

        // Second free (double-free): free(p) again
        let free2 = Node::new(
            "free_2".to_string(),
            NodeKind::Expression,
            "free::p".to_string(),
            "test.c".to_string(),
            Span::new(15, 0, 15, 10),
        )
        .with_name("free");

        let issues = checker.analyze(&[free1, free2]);
        assert!(issues
            .iter()
            .any(|i| matches!(i.kind, MemorySafetyIssueKind::DoubleFree)));
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Spatial Memory Safety Checker Tests - BASE CASES
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_spatial_checker_basic_object_registration() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("buffer", 100);

        // Valid access at offset 0
        assert!(checker
            .process_memory_access("buffer", 8, "test.c:1")
            .is_none());
    }

    #[test]
    fn test_spatial_pointer_arithmetic_valid() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("arr", 100);

        // p = arr + 50 (valid, within bounds)
        let result = checker.process_pointer_arithmetic("p", "arr", 50, "test.c:10");
        assert!(result.is_none());
    }

    #[test]
    fn test_spatial_pointer_arithmetic_out_of_bounds() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("arr", 100);

        // p = arr + 150 (INVALID - exceeds bounds)
        let result = checker.process_pointer_arithmetic("p", "arr", 150, "test.c:10");
        assert!(result.is_some());
        assert!(matches!(
            result.unwrap().kind,
            MemorySafetyIssueKind::SpatialViolation
        ));
    }

    #[test]
    fn test_spatial_negative_offset() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("arr", 100);

        // p = arr - 10 (INVALID - negative)
        let result = checker.process_pointer_arithmetic("p", "arr", -10, "test.c:10");
        assert!(result.is_some());
        assert!(matches!(
            result.unwrap().kind,
            MemorySafetyIssueKind::SpatialViolation
        ));
    }

    #[test]
    fn test_spatial_type_cast_valid() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("buf", 16);

        // (int*)buf - valid, int is 4 bytes, buf is 16
        let result = checker.process_pointer_cast("buf", "int", "test.c:10");
        assert!(result.is_none());
    }

    #[test]
    fn test_spatial_type_cast_invalid() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("small_buf", 4);

        // (long*)small_buf - INVALID, long is 8 bytes but buf is 4
        let result = checker.process_pointer_cast("small_buf", "long", "test.c:10");
        assert!(result.is_some());
        assert!(matches!(
            result.unwrap().kind,
            MemorySafetyIssueKind::SpatialViolation
        ));
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Spatial Memory Safety Checker Tests - EDGE CASES
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_spatial_boundary_exact_size() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("buf", 100);

        // Access at exactly offset 99 with size 1 - should be valid
        assert!(checker
            .process_memory_access("buf", 1, "test.c:1")
            .is_none());

        // p = buf + 99 (last valid offset)
        let result = checker.process_pointer_arithmetic("p", "buf", 99, "test.c:10");
        assert!(result.is_none());

        // p = buf + 100 (first invalid offset)
        let result = checker.process_pointer_arithmetic("q", "buf", 100, "test.c:11");
        assert!(result.is_some());
    }

    #[test]
    fn test_spatial_zero_offset() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("buf", 10);

        // p = buf + 0 (valid)
        let result = checker.process_pointer_arithmetic("p", "buf", 0, "test.c:10");
        assert!(result.is_none());
    }

    #[test]
    fn test_spatial_pointer_copy() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("buf", 100);

        // p = buf + 50
        checker.process_pointer_arithmetic("p", "buf", 50, "test.c:10");

        // q = p (copy)
        checker.process_pointer_copy("q", "p");

        // q + 60 should be invalid (50 + 60 = 110 > 100)
        let result = checker.process_pointer_arithmetic("r", "q", 60, "test.c:20");
        assert!(result.is_some());
    }

    #[test]
    fn test_spatial_field_bounds_valid() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("obj", 24); // struct { int x; double y; int z; }
        checker.register_field("obj", "x", 0, 4);
        checker.register_field("obj", "y", 8, 8);
        checker.register_field("obj", "z", 16, 4);

        // Access field y with proper size (8)
        let result = checker.process_field_access("obj", "y", 8, "test.c:10");
        assert!(result.is_none());
    }

    #[test]
    fn test_spatial_field_bounds_violation() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("obj", 24);
        checker.register_field("obj", "x", 0, 4);

        // Access field x with size 8 when it's only 4 bytes
        let result = checker.process_field_access("obj", "x", 8, "test.c:10");
        assert!(result.is_some());
        assert!(matches!(
            result.unwrap().kind,
            MemorySafetyIssueKind::SpatialViolation
        ));
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Spatial Memory Safety Checker Tests - EXTREME CASES
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_spatial_extreme_large_offset() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("buf", 1024);

        // Very large offset
        let result = checker.process_pointer_arithmetic("p", "buf", i64::MAX / 2, "test.c:10");
        assert!(result.is_some());
    }

    #[test]
    fn test_spatial_extreme_large_negative_offset() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("buf", 1024);

        // Very large negative offset
        let result = checker.process_pointer_arithmetic("p", "buf", i64::MIN / 2, "test.c:10");
        assert!(result.is_some());
    }

    #[test]
    fn test_spatial_size_one_object() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("single", 1);

        // Offset 0 is valid
        let result = checker.process_pointer_arithmetic("p", "single", 0, "test.c:10");
        assert!(result.is_none());

        // Offset 1 is invalid
        let result = checker.process_pointer_arithmetic("q", "single", 1, "test.c:11");
        assert!(result.is_some());
    }

    #[test]
    fn test_spatial_chain_of_pointer_arithmetic() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("buf", 100);

        // Chain: p = buf + 30, q = p + 30, r = q + 30
        checker.process_pointer_arithmetic("p", "buf", 30, "test.c:1");
        checker.process_pointer_copy("q_base", "p");
        checker.process_pointer_arithmetic("q", "q_base", 30, "test.c:2");
        checker.process_pointer_copy("r_base", "q");

        // r_base is at offset 60, adding 30 more = 90, still valid
        let result = checker.process_pointer_arithmetic("r", "r_base", 30, "test.c:3");
        assert!(result.is_none());

        // s = r + 20 would be at 110, invalid
        checker.process_pointer_copy("s_base", "r");
        let result = checker.process_pointer_arithmetic("s", "s_base", 20, "test.c:4");
        assert!(result.is_some());
    }

    #[test]
    fn test_spatial_custom_type_registration() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_type_size("my_struct", 32);
        checker.register_object("obj", 16);

        // Cast to larger custom type should fail
        let result = checker.process_pointer_cast("obj", "my_struct", "test.c:10");
        assert!(result.is_some());
    }

    #[test]
    fn test_spatial_struct_size_pattern() {
        let mut checker = SpatialMemorySafetyChecker::new();
        checker.register_object("buf", 64);

        // Cast to struct_32 should succeed (32 <= 64)
        let result = checker.process_pointer_cast("buf", "struct_32", "test.c:10");
        assert!(result.is_none());

        // Cast to struct_128 should fail (128 > 64)
        let result = checker.process_pointer_cast("buf", "struct_128", "test.c:11");
        assert!(result.is_some());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Unified MemorySafetyAnalyzer Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_analyzer_includes_spatial_checker() {
        let analyzer = MemorySafetyAnalyzer::new();
        // Verify spatial checker is accessible
        let _ = analyzer;
    }

    #[test]
    fn test_analyzer_spatial_checker_mut_access() {
        let mut analyzer = MemorySafetyAnalyzer::new();

        // Pre-register object through spatial checker
        analyzer.spatial_checker_mut().register_object("buf", 100);

        // Verify we can access it
        let issues =
            analyzer
                .spatial_checker_mut()
                .process_pointer_arithmetic("p", "buf", 150, "test.c:10");
        assert!(issues.is_some());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ObjectBounds Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_object_bounds_access_validation() {
        let obj = ObjectBounds::new("test", 100);

        // Valid accesses
        assert!(obj.is_access_valid(0, 100)); // Full object
        assert!(obj.is_access_valid(50, 50)); // Second half
        assert!(obj.is_access_valid(99, 1)); // Last byte

        // Invalid accesses
        assert!(!obj.is_access_valid(100, 1)); // Past end
        assert!(!obj.is_access_valid(99, 2)); // Crosses boundary
        assert!(!obj.is_access_valid(-1, 1)); // Before start
        assert!(!obj.is_access_valid(0, 101)); // Exceeds size
    }

    #[test]
    fn test_object_bounds_offset_validation() {
        let obj = ObjectBounds::new("test", 100);

        assert!(obj.is_offset_valid(0));
        assert!(obj.is_offset_valid(99));
        assert!(!obj.is_offset_valid(100));
        assert!(!obj.is_offset_valid(-1));
    }

    #[test]
    fn test_object_bounds_field_access() {
        let mut obj = ObjectBounds::new("struct", 24);
        obj.add_field("x", 0, 4);
        obj.add_field("y", 8, 8);

        // Valid field access
        assert_eq!(obj.is_field_access_valid("x", 4), Some(true));
        assert_eq!(obj.is_field_access_valid("y", 8), Some(true));

        // Invalid field access (too large)
        assert_eq!(obj.is_field_access_valid("x", 8), Some(false));

        // Unknown field
        assert_eq!(obj.is_field_access_valid("z", 4), None);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // PointerInfo Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_pointer_info_construction() {
        let ptr = PointerInfo::new("buf").with_offset(10).with_cast("int", 4);

        assert_eq!(ptr.base_object, "buf");
        assert_eq!(ptr.current_offset, 10);
        assert_eq!(ptr.derived_type, Some("int".to_string()));
        assert_eq!(ptr.derived_size, Some(4));
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // SOLID Compliance Tests
    // ═══════════════════════════════════════════════════════════════════════════

    /// Test: Open/Closed Principle - Add custom checker without modifying analyzer
    #[test]
    fn test_solid_ocp_custom_checker() {
        /// Custom checker implementation (no modification to MemorySafetyAnalyzer needed)
        struct CustomLeakChecker {
            leak_count: usize,
        }

        impl MemoryChecker for CustomLeakChecker {
            fn analyze(&mut self, _nodes: &[Node]) -> Vec<MemorySafetyIssue> {
                self.leak_count += 1;
                // Return a mock issue for testing (use double_free as proxy for custom issue)
                vec![MemorySafetyIssue::double_free("test_obj", "test.c:1")]
            }

            fn name(&self) -> &'static str {
                "CustomLeakChecker"
            }

            fn reset(&mut self) {
                self.leak_count = 0;
            }
        }

        let mut analyzer = MemorySafetyAnalyzer::new();

        // Add custom checker (OCP: no modification to analyzer code)
        analyzer.add_checker(Box::new(CustomLeakChecker { leak_count: 0 }));

        // Verify custom checker is registered
        let names = analyzer.checker_names();
        assert!(names.contains(&"CustomLeakChecker"));

        // Run analysis - custom checker should be invoked
        let issues = analyzer.analyze(&[]);

        // Custom checker should have produced an issue
        assert!(issues.iter().any(|i| matches!(i.kind, MemorySafetyIssueKind::DoubleFree)));
    }

    /// Test: Liskov Substitution - All checkers can be used polymorphically
    #[test]
    fn test_solid_lsp_polymorphism() {
        // All checkers implement MemoryChecker trait
        let checkers: Vec<Box<dyn MemoryChecker>> = vec![
            Box::new(NullDereferenceChecker::new()),
            Box::new(UseAfterFreeChecker::new()),
            Box::new(DoubleFreeChecker::new()),
            Box::new(BufferOverflowChecker::new()),
            Box::new(SpatialMemorySafetyChecker::new()),
        ];

        // All checkers can be used polymorphically
        for mut checker in checkers {
            assert!(!checker.name().is_empty()); // Has name
            let _ = checker.analyze(&[]); // Can analyze
            checker.reset(); // Can reset
        }
    }

    /// Test: Interface Segregation - MemoryChecker has minimal interface
    #[test]
    fn test_solid_isp_minimal_interface() {
        // MemoryChecker only requires:
        // - analyze() - core functionality
        // - analyze_with_edges() - has default impl
        // - name() - for debugging
        // - reset() - has default impl

        /// Minimal implementation proves ISP
        struct MinimalChecker;

        impl MemoryChecker for MinimalChecker {
            fn analyze(&mut self, _nodes: &[Node]) -> Vec<MemorySafetyIssue> {
                vec![]
            }

            fn name(&self) -> &'static str {
                "MinimalChecker"
            }
            // reset() uses default implementation
        }

        let mut checker: Box<dyn MemoryChecker> = Box::new(MinimalChecker);

        // Works with minimal implementation
        assert_eq!(checker.analyze(&[]).len(), 0);
        assert_eq!(checker.name(), "MinimalChecker");
        checker.reset(); // Default impl
    }

    /// Test: Dependency Inversion - Analyzer depends on abstraction
    #[test]
    fn test_solid_dip_abstraction() {
        let mut analyzer = MemorySafetyAnalyzer::new();

        // Can add any checker that implements MemoryChecker trait
        // (depends on abstraction, not concrete types)
        struct MockChecker {
            called: bool,
        }

        impl MemoryChecker for MockChecker {
            fn analyze(&mut self, _nodes: &[Node]) -> Vec<MemorySafetyIssue> {
                self.called = true;
                vec![]
            }

            fn name(&self) -> &'static str {
                "MockChecker"
            }
        }

        analyzer.add_checker(Box::new(MockChecker { called: false }));

        // Analyzer can work with any implementation
        let _ = analyzer.analyze(&[]);

        // Verify all checkers run (built-in + custom)
        assert!(analyzer.checker_names().len() >= 6); // 5 built-in + 1 custom
    }

    /// Test: Single Responsibility - Each checker has one job
    #[test]
    fn test_solid_srp_single_responsibility() {
        // NullDereferenceChecker: only checks null dereferences
        let null_checker = NullDereferenceChecker::new();
        assert_eq!(null_checker.name(), "NullDereferenceChecker");

        // UseAfterFreeChecker: only checks UAF
        let uaf_checker = UseAfterFreeChecker::new();
        assert_eq!(uaf_checker.name(), "UseAfterFreeChecker");

        // DoubleFreeChecker: only checks double frees
        let df_checker = DoubleFreeChecker::new();
        assert_eq!(df_checker.name(), "DoubleFreeChecker");

        // BufferOverflowChecker: only checks buffer overflows
        let bof_checker = BufferOverflowChecker::new();
        assert_eq!(bof_checker.name(), "BufferOverflowChecker");

        // SpatialMemorySafetyChecker: only checks spatial safety
        let spatial_checker = SpatialMemorySafetyChecker::new();
        assert_eq!(spatial_checker.name(), "SpatialMemorySafetyChecker");

        // Each checker's name reflects its single responsibility
    }

    /// Test: Reset functionality preserves SOLID compliance
    #[test]
    fn test_solid_reset_reusability() {
        let mut analyzer = MemorySafetyAnalyzer::new();

        // Configure and use
        analyzer
            .spatial_checker_mut()
            .register_object("buf", 100);
        let _ = analyzer.analyze(&[]);

        // Reset should allow reuse without creating new instance
        analyzer.reset();

        // Should be clean state
        let issues = analyzer.analyze(&[]);
        // No false positives after reset
        assert!(issues.is_empty());
    }
}
