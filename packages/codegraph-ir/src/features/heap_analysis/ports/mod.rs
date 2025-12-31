//! Heap Analysis Ports - Interface Layer (Hexagonal Architecture)
//!
//! This module defines the port interfaces (traits) that abstract the heap analysis
//! infrastructure from the domain and application layers.
//!
//! ## SOLID Compliance
//! - **D (Dependency Inversion)**: Application depends on traits, not concrete types
//! - **I (Interface Segregation)**: Separate traits for separate responsibilities
//!
//! ## Hexagonal Architecture
//! - **Ports**: Define interfaces for adapters (this module)
//! - **Adapters**: Implement ports (infrastructure module)
//!
//! ## Usage
//! ```rust,ignore
//! use heap_analysis::ports::HeapAnalyzer;
//!
//! fn analyze<A: HeapAnalyzer>(analyzer: &mut A, nodes: &[Node]) {
//!     let issues = analyzer.analyze(nodes);
//!     // ...
//! }
//! ```

use crate::shared::models::{Edge, Node};
use super::domain::{HeapIssue, EscapeState, OwnershipState};
use std::collections::HashMap;

// ═══════════════════════════════════════════════════════════════════════════
// Primary Ports (Driving/Input)
// ═══════════════════════════════════════════════════════════════════════════

/// Memory Checker Port - Interface for all memory safety checkers
///
/// # SOLID Compliance
/// - **S**: Single responsibility - detect memory issues
/// - **I**: Minimal interface for memory checking
/// - **L**: Any implementor can substitute another
///
/// # Implementors
/// - `NullDereferenceChecker`
/// - `UseAfterFreeChecker`
/// - `DoubleFreeChecker`
/// - `BufferOverflowChecker`
/// - `SpatialMemorySafetyChecker`
pub trait MemoryCheckerPort: Send + Sync {
    /// Analyze nodes for memory safety issues
    fn analyze(&mut self, nodes: &[Node]) -> Vec<HeapIssue>;

    /// Analyze with edge information for enhanced detection
    fn analyze_with_edges(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue> {
        self.analyze(nodes)
    }

    /// Checker name for debugging and logging
    fn name(&self) -> &'static str;

    /// Reset checker state for reuse
    fn reset(&mut self) {}
}

/// Escape Analyzer Port - Interface for escape analysis
///
/// # SOLID Compliance
/// - **S**: Single responsibility - determine object escape behavior
/// - **O**: Extensible via trait implementation
pub trait EscapeAnalyzerPort: Send + Sync {
    /// Analyze escape behavior for variables
    fn analyze_escapes(&mut self, nodes: &[Node]) -> HashMap<String, EscapeState>;

    /// Check if a specific variable escapes
    fn does_escape(&self, var: &str) -> bool;

    /// Get escape state for a variable
    fn get_escape_state(&self, var: &str) -> Option<EscapeState>;

    /// Reset analyzer state
    fn reset(&mut self);
}

/// Ownership Analyzer Port - Interface for ownership tracking
///
/// # SOLID Compliance
/// - **S**: Single responsibility - track ownership/borrows
/// - **D**: Depends on abstract ownership states
pub trait OwnershipAnalyzerPort: Send + Sync {
    /// Track ownership state changes
    fn track_ownership(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue>;

    /// Get current ownership state for a variable
    fn get_ownership_state(&self, var: &str) -> Option<OwnershipState>;

    /// Check if move is valid
    fn is_move_valid(&self, var: &str) -> bool;

    /// Reset tracker state
    fn reset(&mut self);
}

/// Security Analyzer Port - Interface for security analysis
///
/// # SOLID Compliance
/// - **S**: Single responsibility - detect security vulnerabilities
pub trait SecurityAnalyzerPort: Send + Sync {
    /// Analyze for security vulnerabilities
    fn analyze_security(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue>;

    /// Get vulnerability categories detected
    fn get_detected_categories(&self) -> Vec<String>;

    /// Reset analyzer state
    fn reset(&mut self);
}

// ═══════════════════════════════════════════════════════════════════════════
// Secondary Ports (Driven/Output)
// ═══════════════════════════════════════════════════════════════════════════

/// Symbolic Heap Port - Interface for symbolic heap operations
///
/// Used by checkers to query/modify symbolic heap state.
pub trait SymbolicHeapPort {
    /// Allocate a new heap object
    fn allocate(&mut self, var: &str, type_name: Option<&str>) -> String;

    /// Deallocate a heap object
    fn deallocate(&mut self, loc: &str) -> bool;

    /// Check if location is allocated
    fn is_allocated(&self, loc: &str) -> bool;

    /// Check if variable may be null
    fn may_be_null(&self, var: &str) -> bool;

    /// Get all allocated locations
    fn get_allocations(&self) -> Vec<String>;
}

/// Separation Logic Port - Interface for separation logic operations
///
/// Used for entailment checking and frame inference.
pub trait SeparationLogicPort {
    /// Check entailment: H₁ ⊢ H₂
    fn entails(&self, h1: &str, h2: &str) -> bool;

    /// Infer frame: H₁ * ?F ⊢ H₂
    fn infer_frame(&self, h1: &str, h2: &str) -> Option<String>;

    /// Bi-abduction: H₁ * ?A ⊢ H₂ * ?F
    fn bi_abduct(&self, h1: &str, h2: &str) -> Option<(String, String)>;
}

// ═══════════════════════════════════════════════════════════════════════════
// Composite Port
// ═══════════════════════════════════════════════════════════════════════════

/// Heap Analyzer Port - Composite interface for full heap analysis
///
/// Combines all heap analysis capabilities into a single interface.
/// This is the main port used by the application layer.
///
/// # SOLID Compliance
/// - **I**: While composite, each sub-capability is accessible separately
/// - **D**: Application depends on this trait, not concrete HeapAnalyzer
pub trait HeapAnalyzerPort: Send + Sync {
    /// Run full memory safety analysis
    fn analyze_memory_safety(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue>;

    /// Run escape analysis
    fn analyze_escapes(&mut self, nodes: &[Node]) -> HashMap<String, EscapeState>;

    /// Run ownership analysis
    fn analyze_ownership(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue>;

    /// Run security analysis
    fn analyze_security(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<HeapIssue>;

    /// Run all analyses and return combined results
    fn analyze_all(&mut self, nodes: &[Node], edges: &[Edge]) -> HeapAnalysisResult;

    /// Reset all analyzer state
    fn reset(&mut self);
}

/// Combined result from all heap analyses
#[derive(Debug, Clone, Default)]
pub struct HeapAnalysisResult {
    /// Memory safety issues (null, UAF, double-free, buffer overflow)
    pub memory_issues: Vec<HeapIssue>,

    /// Escape analysis results
    pub escape_states: HashMap<String, EscapeState>,

    /// Ownership issues (use-after-move, borrow conflicts)
    pub ownership_issues: Vec<HeapIssue>,

    /// Security vulnerabilities (OWASP, etc.)
    pub security_issues: Vec<HeapIssue>,
}

impl HeapAnalysisResult {
    /// Create empty result
    pub fn new() -> Self {
        Self::default()
    }

    /// Get all issues combined
    pub fn all_issues(&self) -> Vec<&HeapIssue> {
        let mut all = Vec::new();
        all.extend(self.memory_issues.iter());
        all.extend(self.ownership_issues.iter());
        all.extend(self.security_issues.iter());
        all
    }

    /// Get total issue count
    pub fn total_issues(&self) -> usize {
        self.memory_issues.len() + self.ownership_issues.len() + self.security_issues.len()
    }

    /// Check if any issues were found
    pub fn has_issues(&self) -> bool {
        self.total_issues() > 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_heap_analysis_result_empty() {
        let result = HeapAnalysisResult::new();
        assert!(!result.has_issues());
        assert_eq!(result.total_issues(), 0);
    }

    #[test]
    fn test_heap_analysis_result_all_issues() {
        let mut result = HeapAnalysisResult::new();
        result.memory_issues.push(HeapIssue::null_dereference("x", 1, "test.rs"));
        result.ownership_issues.push(HeapIssue::use_after_move("y", 2, "test.rs"));
        result.security_issues.push(HeapIssue::security("sql_injection", 3, "test.rs"));

        assert!(result.has_issues());
        assert_eq!(result.total_issues(), 3);
        assert_eq!(result.all_issues().len(), 3);
    }
}
