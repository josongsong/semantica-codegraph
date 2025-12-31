//! Slicing Ports - Interface Layer (Hexagonal Architecture)
//!
//! Defines port interfaces for program slicing operations.
//! Implementation: see `infrastructure/slicer.rs` (1,115 LOC)
//!
//! ## SOLID Compliance
//! - **D (Dependency Inversion)**: Application depends on traits, not concrete types
//! - **I (Interface Segregation)**: Separate traits for separate responsibilities

use std::collections::HashSet;

// ═══════════════════════════════════════════════════════════════════════════
// Slicer Port - Primary Interface
// ═══════════════════════════════════════════════════════════════════════════

/// Program Slicer Port - Interface for slicing operations
///
/// # SOLID Compliance
/// - **S**: Single responsibility - compute program slices
/// - **I**: Minimal interface for slicing
/// - **L**: Any implementor can substitute another
///
/// # Implementors
/// - `ProgramSlicer` (infrastructure/slicer.rs)
pub trait SlicerPort: Send + Sync {
    /// Compute backward slice from target node
    ///
    /// Returns all statements that affect the target node.
    fn backward_slice(
        &mut self,
        pdg: &dyn PDGPort,
        target_node: &str,
        max_depth: Option<usize>,
    ) -> SliceResult;

    /// Compute forward slice from source node
    ///
    /// Returns all statements affected by the source node.
    fn forward_slice(
        &mut self,
        pdg: &dyn PDGPort,
        source_node: &str,
        max_depth: Option<usize>,
    ) -> SliceResult;

    /// Compute thin slice (data dependencies only)
    ///
    /// Returns backward slice excluding control dependencies.
    /// Based on Sridharan et al. "Thin Slicing" (PLDI 2007)
    fn thin_slice(
        &mut self,
        pdg: &dyn PDGPort,
        target_node: &str,
        max_depth: Option<usize>,
    ) -> SliceResult;

    /// Compute chop between source and target
    ///
    /// Returns statements on paths from source to target.
    /// Based on Jackson & Rollins "Chopping" (FSE 1994)
    fn chop(
        &mut self,
        pdg: &dyn PDGPort,
        source_node: &str,
        target_node: &str,
        max_depth: Option<usize>,
    ) -> SliceResult;

    /// Reset slicer state
    fn reset(&mut self);
}

// ═══════════════════════════════════════════════════════════════════════════
// PDG Port - Secondary Interface
// ═══════════════════════════════════════════════════════════════════════════

/// Program Dependence Graph Port - Interface for PDG operations
///
/// # SOLID Compliance
/// - **S**: Single responsibility - represent program dependencies
/// - **I**: Minimal interface for dependency queries
pub trait PDGPort: Send + Sync {
    /// Check if node exists in PDG
    fn contains_node(&self, node: &str) -> bool;

    /// Get backward slice with filtering
    fn backward_slice_filtered(
        &self,
        target: &str,
        max_depth: Option<usize>,
        include_control: bool,
        include_data: bool,
    ) -> HashSet<String>;

    /// Get forward slice with filtering
    fn forward_slice_filtered(
        &self,
        source: &str,
        max_depth: Option<usize>,
        include_control: bool,
        include_data: bool,
    ) -> HashSet<String>;

    /// Get thin slice (data only backward)
    fn thin_slice(&self, target: &str, max_depth: Option<usize>) -> HashSet<String> {
        self.backward_slice_filtered(target, max_depth, false, true)
    }

    /// Get chop with filtering
    fn chop_filtered(
        &self,
        source: &str,
        target: &str,
        max_depth: Option<usize>,
        include_control: bool,
        include_data: bool,
    ) -> HashSet<String>;

    /// Get all nodes in PDG
    fn get_all_nodes(&self) -> Vec<String>;

    /// Get node count
    fn node_count(&self) -> usize;
}

// ═══════════════════════════════════════════════════════════════════════════
// Result Types
// ═══════════════════════════════════════════════════════════════════════════

/// Slice result from slicing operations
#[derive(Debug, Clone)]
pub struct SliceResult {
    /// Target variable/node for the slice
    pub target_variable: String,

    /// Type of slice
    pub slice_type: SliceType,

    /// Nodes in the slice
    pub slice_nodes: HashSet<String>,

    /// Code fragments (if extracted)
    pub code_fragments: Vec<String>,

    /// Control context (control flow statements)
    pub control_context: Vec<String>,

    /// Total token count
    pub total_tokens: usize,

    /// Confidence score (0.0 - 1.0)
    pub confidence: f64,

    /// Additional metadata
    pub metadata: std::collections::HashMap<String, String>,
}

impl SliceResult {
    /// Create empty slice result
    pub fn empty(target: &str, slice_type: SliceType) -> Self {
        Self {
            target_variable: target.to_string(),
            slice_type,
            slice_nodes: HashSet::new(),
            code_fragments: Vec::new(),
            control_context: Vec::new(),
            total_tokens: 0,
            confidence: 0.0,
            metadata: std::collections::HashMap::new(),
        }
    }

    /// Create slice result with error
    pub fn with_error(target: &str, slice_type: SliceType, error: &str) -> Self {
        let mut result = Self::empty(target, slice_type);
        result.metadata.insert("error".to_string(), error.to_string());
        result
    }

    /// Get slice size
    pub fn size(&self) -> usize {
        self.slice_nodes.len()
    }

    /// Check if slice is empty
    pub fn is_empty(&self) -> bool {
        self.slice_nodes.is_empty()
    }

    /// Check if slice has error
    pub fn has_error(&self) -> bool {
        self.metadata.contains_key("error")
    }
}

/// Type of slice
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SliceType {
    /// Backward slice (what affects target)
    Backward,
    /// Forward slice (what target affects)
    Forward,
    /// Hybrid (chop, etc.)
    Hybrid,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_slice_result_empty() {
        let result = SliceResult::empty("x", SliceType::Backward);
        assert!(result.is_empty());
        assert_eq!(result.size(), 0);
        assert!(!result.has_error());
    }

    #[test]
    fn test_slice_result_with_error() {
        let result = SliceResult::with_error("x", SliceType::Backward, "NODE_NOT_FOUND");
        assert!(result.has_error());
        assert_eq!(result.metadata.get("error"), Some(&"NODE_NOT_FOUND".to_string()));
    }
}
