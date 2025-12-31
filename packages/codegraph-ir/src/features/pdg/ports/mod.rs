//! PDG Ports - Interface Layer (Hexagonal Architecture)
//!
//! Defines port interfaces for Program Dependence Graph operations.
//! Implementation: see `infrastructure/pdg.rs` (1,207 LOC)
//!
//! ## SOLID Compliance
//! - **D (Dependency Inversion)**: Application depends on traits, not concrete types
//! - **I (Interface Segregation)**: Separate traits for separate responsibilities

use std::collections::HashSet;

// Re-export PDGPort from slicing for now (shared trait)
// In a full refactor, this would be the canonical location
pub use crate::features::slicing::ports::PDGPort;

// ═══════════════════════════════════════════════════════════════════════════
// PDG Builder Port
// ═══════════════════════════════════════════════════════════════════════════

/// PDG Builder Port - Interface for building PDGs
///
/// # SOLID Compliance
/// - **S**: Single responsibility - construct PDG from IR
/// - **O**: Extensible via trait implementation
pub trait PDGBuilderPort: Send + Sync {
    /// Build PDG from CFG and DFG
    fn build(&mut self, cfg_nodes: &[String], dfg_edges: &[(String, String, DependencyType)]) -> Box<dyn PDGPort>;

    /// Build PDG from function IR
    fn build_from_function(&mut self, function_id: &str) -> Option<Box<dyn PDGPort>>;

    /// Reset builder state
    fn reset(&mut self);
}

/// Dependency type in PDG
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum DependencyType {
    /// Control dependency (if/else affects statement)
    Control,
    /// Data dependency (def-use chain)
    Data,
    /// Both control and data
    Both,
}

impl DependencyType {
    /// Check if includes control dependency
    pub fn includes_control(&self) -> bool {
        matches!(self, DependencyType::Control | DependencyType::Both)
    }

    /// Check if includes data dependency
    pub fn includes_data(&self) -> bool {
        matches!(self, DependencyType::Data | DependencyType::Both)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// PDG Query Port
// ═══════════════════════════════════════════════════════════════════════════

/// PDG Query Port - Interface for advanced PDG queries
///
/// Extends basic PDGPort with more sophisticated queries.
pub trait PDGQueryPort: PDGPort {
    /// Get direct predecessors of node
    fn get_predecessors(&self, node: &str) -> Vec<String>;

    /// Get direct successors of node
    fn get_successors(&self, node: &str) -> Vec<String>;

    /// Get dependency type between nodes
    fn get_dependency_type(&self, from: &str, to: &str) -> Option<DependencyType>;

    /// Find all paths between two nodes
    fn find_paths(&self, source: &str, target: &str, max_length: Option<usize>) -> Vec<Vec<String>>;

    /// Get strongly connected components
    fn get_sccs(&self) -> Vec<HashSet<String>>;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dependency_type_includes() {
        assert!(DependencyType::Control.includes_control());
        assert!(!DependencyType::Control.includes_data());

        assert!(!DependencyType::Data.includes_control());
        assert!(DependencyType::Data.includes_data());

        assert!(DependencyType::Both.includes_control());
        assert!(DependencyType::Both.includes_data());
    }
}
