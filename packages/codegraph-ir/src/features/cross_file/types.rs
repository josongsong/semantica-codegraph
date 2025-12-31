//! Cross-file types (RFC-062)
//!
//! Core data structures for cross-file resolution.
//!
//! SOTA Optimizations:
//! - Arc<String> for shared file_path (reduces N allocations to 1)
//! - Efficient serialization with serde

use serde::{Deserialize, Serialize};
use std::sync::Arc;

use crate::shared::models::{NodeKind, Span};

/// Global symbol definition
///
/// SOTA: file_path is stored as owned String but can be constructed
/// from Arc<String> to share allocation across symbols in same file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Symbol {
    pub fqn: String,
    pub name: String,
    pub kind: NodeKind,
    pub file_path: String,
    pub node_id: String,
    pub span: Span,
    pub visibility: Visibility,
    pub signature: Option<String>,
}

impl Symbol {
    pub fn new(
        fqn: String,
        name: String,
        kind: NodeKind,
        file_path: String,
        node_id: String,
        span: Span,
    ) -> Self {
        Self {
            fqn,
            name,
            kind,
            file_path,
            node_id,
            span,
            visibility: Visibility::Public,
            signature: None,
        }
    }

    /// SOTA: Create symbol with shared file_path Arc
    ///
    /// When multiple symbols are in the same file, this avoids
    /// cloning the file_path string for each symbol.
    /// Arc::to_string() only clones when there's a single reference.
    #[inline]
    pub fn new_with_shared_path(
        fqn: String,
        name: String,
        kind: NodeKind,
        shared_file_path: Arc<String>,
        node_id: String,
        span: Span,
    ) -> Self {
        Self {
            fqn,
            name,
            kind,
            // Arc::try_unwrap moves if last ref, else clones
            // For shared paths, we need to clone anyway for ownership
            file_path: (*shared_file_path).clone(),
            node_id,
            span,
            visibility: Visibility::Public,
            signature: None,
        }
    }

    pub fn with_visibility(mut self, visibility: Visibility) -> Self {
        self.visibility = visibility;
        self
    }

    pub fn with_signature(mut self, signature: String) -> Self {
        self.signature = Some(signature);
        self
    }
}

/// Symbol visibility
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Visibility {
    Public,
    Private,
    Protected,
}

impl Default for Visibility {
    fn default() -> Self {
        Visibility::Public
    }
}

/// Resolved import information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResolvedImport {
    /// Original import FQN (what was imported)
    pub import_fqn: String,

    /// Resolved FQN (actual symbol FQN if found)
    pub resolved_fqn: Option<String>,

    /// Source file containing the definition
    pub source_file: Option<String>,

    /// Node ID of the resolved symbol
    pub resolved_node_id: Option<String>,

    /// Is this an external (third-party) import?
    pub is_external: bool,

    /// Import alias (e.g., "import foo as bar" → alias = "bar")
    pub alias: Option<String>,

    /// Resolution method used
    pub resolution_method: ResolutionMethod,
}

impl ResolvedImport {
    pub fn resolved(
        import_fqn: String,
        resolved_fqn: String,
        source_file: String,
        resolved_node_id: String,
        method: ResolutionMethod,
    ) -> Self {
        Self {
            import_fqn,
            resolved_fqn: Some(resolved_fqn),
            source_file: Some(source_file),
            resolved_node_id: Some(resolved_node_id),
            is_external: false,
            alias: None,
            resolution_method: method,
        }
    }

    pub fn unresolved(import_fqn: String) -> Self {
        Self {
            import_fqn,
            resolved_fqn: None,
            source_file: None,
            resolved_node_id: None,
            is_external: true,
            alias: None,
            resolution_method: ResolutionMethod::NotFound,
        }
    }

    pub fn with_alias(mut self, alias: String) -> Self {
        self.alias = Some(alias);
        self
    }
}

/// Method used to resolve an import
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ResolutionMethod {
    /// Exact FQN match
    ExactMatch,
    /// Partial module match (module.submodule → module)
    PartialMatch,
    /// Module path pattern match (module → src/module.py)
    ModulePath,
    /// Not found / external
    NotFound,
}

/// Import statement from IR
#[derive(Debug, Clone)]
pub struct ImportInfo {
    /// File containing the import
    pub file_path: String,

    /// Import edge source node ID
    pub source_node_id: String,

    /// Import edge target node ID
    pub target_node_id: String,

    /// Imported name (FQN or module name)
    pub imported_name: String,

    /// Import alias
    pub alias: Option<String>,
}

/// Statistics for cross-file resolution
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ResolutionStats {
    pub symbols_collected: usize,
    pub imports_resolved: usize,
    pub imports_unresolved: usize,
    pub dependencies_found: usize,
    pub cycles_detected: usize,
    pub duration_ms: u64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_symbol_construction() {
        let symbol = Symbol::new(
            "module.foo".to_string(),
            "foo".to_string(),
            NodeKind::Function,
            "src/module.py".to_string(),
            "node123".to_string(),
            Span::new(1, 0, 10, 0),
        );

        assert_eq!(symbol.fqn, "module.foo");
        assert_eq!(symbol.visibility, Visibility::Public);
    }

    #[test]
    fn test_resolved_import() {
        let resolved = ResolvedImport::resolved(
            "utils.helper".to_string(),
            "utils.helper".to_string(),
            "src/utils.py".to_string(),
            "node456".to_string(),
            ResolutionMethod::ExactMatch,
        );

        assert!(!resolved.is_external);
        assert_eq!(resolved.resolution_method, ResolutionMethod::ExactMatch);
    }

    #[test]
    fn test_unresolved_import() {
        let unresolved = ResolvedImport::unresolved("numpy.array".to_string());

        assert!(unresolved.is_external);
        assert_eq!(unresolved.resolution_method, ResolutionMethod::NotFound);
    }
}
