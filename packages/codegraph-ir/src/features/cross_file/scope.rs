//! Scope-aware resolution (SOTA - Priority 2)
//!
//! Implements Python LEGB (Local, Enclosing, Global, Built-in) scoping model.
//!
//! Academic SOTA:
//! - Scope Graph (TU Delft 2018): Declarative scope resolution
//! - Pyright: Python-specific LEGB with type narrowing
//! - rust-analyzer: Per-function scope tables
//!
//! Industry SOTA:
//! - Sourcegraph SCIP: Hierarchical scope tree
//! - GitHub Copilot: Context-aware symbol resolution
//! - JetBrains PSI: Program Structure Interface with scopes
//!
//! Key features:
//! - Hierarchical scope tree (Module → Class → Function → Comprehension)
//! - LEGB chain resolution
//! - Function-scoped imports
//! - Shadowing (inner scope overrides outer scope)
//! - Incremental updates

use dashmap::DashMap;
use serde::{Deserialize, Serialize};

use crate::shared::models::Span;

/// Python scope kinds (LEGB model)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ScopeKind {
    /// Module-level scope (Global in LEGB)
    Module,

    /// Class definition scope
    Class,

    /// Function/Method scope (Local in LEGB)
    Function,

    /// Lambda expression scope
    Lambda,

    /// List/Dict/Set comprehension scope
    ///
    /// Python 3+: comprehensions have their own scope
    /// ```python
    /// x = [i for i in range(10)]  # `i` is local to comprehension
    /// # print(i)  # NameError!
    /// ```
    Comprehension,
}

impl ScopeKind {
    /// Check if this scope can define imports
    ///
    /// In Python, imports can be at module or function level,
    /// but not in comprehensions or lambdas.
    pub fn can_import(&self) -> bool {
        matches!(
            self,
            ScopeKind::Module | ScopeKind::Function | ScopeKind::Class
        )
    }

    /// Check if this scope creates a new namespace
    ///
    /// Classes and modules create new namespaces,
    /// but comprehensions are expression-scoped.
    pub fn creates_namespace(&self) -> bool {
        matches!(
            self,
            ScopeKind::Module | ScopeKind::Class | ScopeKind::Function
        )
    }
}

/// Scope node in hierarchical scope tree
///
/// Represents a single scope in the Python LEGB chain.
/// Each scope tracks symbols and aliases defined within it.
///
/// SOTA Optimizations:
/// - DashMap for lock-free concurrent access
/// - Arc for zero-copy sharing across threads
/// - Parent chain for efficient LEGB lookup
#[derive(Debug, Clone)]
pub struct Scope {
    /// Unique scope identifier
    ///
    /// Format: `{file_path}::{node_id}`
    pub id: String,

    /// Scope kind (Module, Class, Function, etc.)
    pub kind: ScopeKind,

    /// File containing this scope
    pub file_path: String,

    /// Parent scope ID for LEGB chain
    ///
    /// None for module-level scope
    pub parent_id: Option<String>,

    /// Symbols defined in THIS scope only
    ///
    /// name → FQN
    /// Example: `x` → `module.foo.x`
    symbols: DashMap<String, String>,

    /// Aliases defined in THIS scope only
    ///
    /// alias → FQN
    /// Example: `np` → `numpy`
    aliases: DashMap<String, String>,

    /// Source code span for this scope
    pub span: Span,

    /// Node ID that defines this scope
    ///
    /// For function scope: function node ID
    /// For module scope: module node ID
    pub defining_node_id: Option<String>,
}

impl Scope {
    /// Create new scope
    pub fn new(
        id: String,
        kind: ScopeKind,
        file_path: String,
        parent_id: Option<String>,
        span: Span,
        defining_node_id: Option<String>,
    ) -> Self {
        Self {
            id,
            kind,
            file_path,
            parent_id,
            symbols: DashMap::new(),
            aliases: DashMap::new(),
            span,
            defining_node_id,
        }
    }

    /// Register a symbol in this scope
    pub fn add_symbol(&self, name: String, fqn: String) {
        self.symbols.insert(name, fqn);
    }

    /// Register an alias in this scope
    pub fn add_alias(&self, alias: String, fqn: String) {
        self.aliases.insert(alias, fqn);
    }

    /// Lookup symbol in THIS scope only (no parent lookup)
    pub fn get_symbol(&self, name: &str) -> Option<String> {
        self.symbols.get(name).map(|v| v.clone())
    }

    /// Lookup alias in THIS scope only (no parent lookup)
    pub fn get_alias(&self, alias: &str) -> Option<String> {
        self.aliases.get(alias).map(|v| v.clone())
    }

    /// Get all symbols in this scope
    pub fn get_all_symbols(&self) -> Vec<(String, String)> {
        self.symbols
            .iter()
            .map(|entry| (entry.key().clone(), entry.value().clone()))
            .collect()
    }

    /// Get all aliases in this scope
    pub fn get_all_aliases(&self) -> Vec<(String, String)> {
        self.aliases
            .iter()
            .map(|entry| (entry.key().clone(), entry.value().clone()))
            .collect()
    }

    /// Check if a name is defined in this scope
    pub fn contains(&self, name: &str) -> bool {
        self.symbols.contains_key(name) || self.aliases.contains_key(name)
    }

    /// Remove all symbols (for incremental updates)
    pub fn clear(&self) {
        self.symbols.clear();
        self.aliases.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_scope_creation() {
        let scope = Scope::new(
            "main.py::func1".to_string(),
            ScopeKind::Function,
            "main.py".to_string(),
            Some("main.py::module".to_string()),
            Span::new(1, 0, 10, 0),
            Some("func1_node".to_string()),
        );

        assert_eq!(scope.kind, ScopeKind::Function);
        assert!(scope.parent_id.is_some());
        assert!(scope.symbols.is_empty());
    }

    #[test]
    fn test_scope_symbol_management() {
        let scope = Scope::new(
            "test::scope".to_string(),
            ScopeKind::Function,
            "test.py".to_string(),
            None,
            Span::new(1, 0, 10, 0),
            None,
        );

        // Add symbols
        scope.add_symbol("x".to_string(), "test.foo.x".to_string());
        scope.add_symbol("y".to_string(), "test.foo.y".to_string());

        // Lookup
        assert_eq!(scope.get_symbol("x"), Some("test.foo.x".to_string()));
        assert_eq!(scope.get_symbol("y"), Some("test.foo.y".to_string()));
        assert_eq!(scope.get_symbol("z"), None);

        // Contains
        assert!(scope.contains("x"));
        assert!(!scope.contains("z"));
    }

    #[test]
    fn test_scope_alias_management() {
        let scope = Scope::new(
            "test::scope".to_string(),
            ScopeKind::Module,
            "test.py".to_string(),
            None,
            Span::new(1, 0, 100, 0),
            None,
        );

        // Add aliases
        scope.add_alias("np".to_string(), "numpy".to_string());
        scope.add_alias("pd".to_string(), "pandas".to_string());

        // Lookup
        assert_eq!(scope.get_alias("np"), Some("numpy".to_string()));
        assert_eq!(scope.get_alias("pd"), Some("pandas".to_string()));
        assert_eq!(scope.get_alias("tf"), None);
    }

    #[test]
    fn test_scope_kind_capabilities() {
        assert!(ScopeKind::Module.can_import());
        assert!(ScopeKind::Function.can_import());
        assert!(ScopeKind::Class.can_import());
        assert!(!ScopeKind::Lambda.can_import());
        assert!(!ScopeKind::Comprehension.can_import());

        assert!(ScopeKind::Module.creates_namespace());
        assert!(ScopeKind::Class.creates_namespace());
        assert!(ScopeKind::Function.creates_namespace());
        assert!(!ScopeKind::Comprehension.creates_namespace());
    }
}
