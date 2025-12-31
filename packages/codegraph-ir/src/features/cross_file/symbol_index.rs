//! Symbol Index with DashMap (RFC-062)
//!
//! Lock-free concurrent symbol index using DashMap.
//! Supports parallel symbol collection with Rayon.
//!
//! SOTA Optimizations:
//! - Arc<String> for file_path sharing (same file → same Arc)
//! - Parallel to_hashmap conversion with Rayon
//! - Pre-allocated Vec capacities
//! - Minimized cloning with Arc references

use dashmap::DashMap;
use rayon::prelude::*;
use std::collections::HashMap;
use std::sync::Arc;

use super::types::Symbol;
use super::IRDocument;

/// Lock-free concurrent symbol index
///
/// Uses DashMap for O(1) concurrent access without locks.
/// Supports parallel construction with Rayon.
///
/// SOTA: Arc<Symbol> allows zero-copy sharing across threads.
pub struct SymbolIndex {
    /// FQN → Symbol (lock-free concurrent access)
    /// Arc<Symbol> enables zero-copy reads
    symbols: DashMap<String, Arc<Symbol>>,

    /// File → FQNs defined in this file
    file_symbols: DashMap<String, Vec<String>>,

    /// Name → FQNs (for partial matching)
    name_to_fqns: DashMap<String, Vec<String>>,

    /// SOTA: Alias → FQN mapping (for import alias resolution)
    /// Example: "np" → "numpy", "pd" → "pandas"
    /// Key: (file_path, alias) → Value: FQN
    alias_to_fqn: DashMap<(String, String), String>,
}

impl SymbolIndex {
    /// Create empty symbol index
    pub fn new() -> Self {
        Self {
            symbols: DashMap::new(),
            file_symbols: DashMap::new(),
            name_to_fqns: DashMap::new(),
            alias_to_fqn: DashMap::new(),
        }
    }

    /// Build symbol index from IR documents (parallel)
    ///
    /// Uses Rayon for parallel processing of files.
    /// Each file's symbols are collected independently, then merged.
    ///
    /// SOTA Optimizations:
    /// - Arc<String> file_path: shared across all nodes in same file (1 alloc vs N)
    /// - Pre-allocated Vec with capacity
    /// - Minimized .clone() calls
    pub fn build_from_irs(irs: &[IRDocument]) -> Self {
        let index = Self::new();

        // Parallel symbol collection
        irs.par_iter().for_each(|ir| {
            // Pre-allocate with estimated capacity
            let mut file_fqns = Vec::with_capacity(ir.nodes.len());

            // SOTA: Share file_path Arc across all symbols in this file (1 alloc vs N)
            let shared_file_path = Arc::new(ir.file_path.clone());

            for node in &ir.nodes {
                // Skip import nodes - they should not be in symbol table
                // Import nodes are references, not definitions
                if matches!(node.kind, crate::shared::models::NodeKind::Import) {
                    continue;
                }

                // Only index nodes with valid FQN
                if node.fqn.is_empty() {
                    continue;
                }

                // Extract name once
                let name = node.name.clone().unwrap_or_else(|| extract_name(&node.fqn));

                // Create symbol with shared file_path
                let symbol = Arc::new(Symbol::new_with_shared_path(
                    node.fqn.clone(),
                    name.clone(),
                    node.kind,
                    Arc::clone(&shared_file_path),
                    node.id.clone(),
                    node.span,
                ));

                // Store FQN for later use (avoid re-cloning)
                let fqn = node.fqn.clone();

                // Add to main symbol table
                index.symbols.insert(fqn.clone(), Arc::clone(&symbol));
                file_fqns.push(fqn.clone());

                // Add to name index for partial matching
                index
                    .name_to_fqns
                    .entry(name)
                    .or_insert_with(Vec::new)
                    .push(fqn);
            }

            // Store file → symbols mapping
            if !file_fqns.is_empty() {
                index.file_symbols.insert(ir.file_path.clone(), file_fqns);
            }
        });

        index
    }

    /// Get symbol by FQN (O(1) lookup)
    pub fn get(&self, fqn: &str) -> Option<Arc<Symbol>> {
        self.symbols.get(fqn).map(|v| v.clone())
    }

    /// Check if FQN exists
    pub fn contains(&self, fqn: &str) -> bool {
        self.symbols.contains_key(fqn)
    }

    /// Get all FQNs for a given name (for partial matching)
    pub fn get_by_name(&self, name: &str) -> Vec<String> {
        self.name_to_fqns
            .get(name)
            .map(|v| v.clone())
            .unwrap_or_default()
    }

    /// Get symbols defined in a file
    pub fn get_file_symbols(&self, file_path: &str) -> Vec<Arc<Symbol>> {
        self.file_symbols
            .get(file_path)
            .map(|fqns| fqns.iter().filter_map(|fqn| self.get(fqn)).collect())
            .unwrap_or_default()
    }

    /// Get total symbol count
    pub fn len(&self) -> usize {
        self.symbols.len()
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.symbols.is_empty()
    }

    /// Convert to HashMap for Python interop
    /// SOTA: Conditional parallel iteration (only beneficial for large tables)
    pub fn to_hashmap(&self) -> HashMap<String, Symbol> {
        // Parallel iteration only helps with large collections (>10k symbols)
        // For smaller collections, overhead outweighs benefits
        if self.len() < 10_000 {
            self.symbols
                .iter()
                .map(|entry| {
                    let symbol: &Symbol = entry.value().as_ref();
                    (entry.key().clone(), symbol.clone())
                })
                .collect()
        } else {
            use rayon::prelude::*;
            self.symbols
                .par_iter()
                .map(|entry| {
                    let symbol: &Symbol = entry.value().as_ref();
                    (entry.key().clone(), symbol.clone())
                })
                .collect()
        }
    }

    /// SOTA: Direct iterator access without cloning (for msgpack serialization)
    pub fn iter_symbols(
        &self,
    ) -> impl Iterator<Item = dashmap::mapref::multiple::RefMulti<'_, String, Arc<Symbol>>> {
        self.symbols.iter()
    }

    /// Try exact FQN match
    pub fn resolve_exact(&self, fqn: &str) -> Option<Arc<Symbol>> {
        self.get(fqn)
    }

    /// Try partial FQN match (module.submodule.Class → module.submodule → module)
    pub fn resolve_partial(&self, fqn: &str) -> Option<(Arc<Symbol>, String)> {
        let parts: Vec<&str> = fqn.split('.').collect();

        // Try progressively shorter prefixes
        for i in (1..parts.len()).rev() {
            let partial = parts[..i].join(".");
            if let Some(symbol) = self.get(&partial) {
                return Some((symbol, partial));
            }
        }

        None
    }

    /// Try to resolve by module path pattern
    ///
    /// Tries common patterns:
    /// - module.py
    /// - src/module.py
    /// - module/__init__.py
    /// - src/module/__init__.py
    pub fn resolve_by_module_path(&self, module_name: &str) -> Option<Arc<Symbol>> {
        // Get the first part of the module name
        let base_module = module_name.split('.').next().unwrap_or(module_name);

        // Look for any symbol in files matching common patterns
        let patterns = [
            format!("{}.py", base_module),
            format!("src/{}.py", base_module),
            format!("{}/__init__.py", base_module),
            format!("src/{}/__init__.py", base_module),
        ];

        for pattern in &patterns {
            if let Some(fqns) = self.file_symbols.get(pattern) {
                // Return the first symbol (usually module-level)
                if let Some(fqn) = fqns.first() {
                    if let Some(symbol) = self.get(fqn) {
                        return Some(symbol);
                    }
                }
            }
        }

        None
    }

    /// Register an import alias for a file
    ///
    /// Example: `register_alias("main.py", "np", "numpy")`
    ///
    /// This allows resolving `np.array(...)` → `numpy.array(...)`
    pub fn register_alias(&self, file_path: String, alias: String, fqn: String) {
        self.alias_to_fqn.insert((file_path, alias), fqn);
    }

    /// Resolve an alias in a specific file context
    ///
    /// Returns the FQN if alias exists, None otherwise
    ///
    /// Example:
    /// ```ignore
    /// // In main.py: import numpy as np
    /// index.resolve_alias("main.py", "np") → Some("numpy")
    /// index.resolve_alias("other.py", "np") → None (different file scope)
    /// ```
    pub fn resolve_alias(&self, file_path: &str, alias: &str) -> Option<String> {
        self.alias_to_fqn
            .get(&(file_path.to_string(), alias.to_string()))
            .map(|v| v.clone())
    }

    /// Get all aliases defined in a file
    ///
    /// Returns HashMap of alias → FQN for the given file
    ///
    /// Example:
    /// ```ignore
    /// // main.py has: import numpy as np, import pandas as pd
    /// get_file_aliases("main.py") → {"np": "numpy", "pd": "pandas"}
    /// ```
    pub fn get_file_aliases(&self, file_path: &str) -> HashMap<String, String> {
        self.alias_to_fqn
            .iter()
            .filter(|entry| entry.key().0 == file_path)
            .map(|entry| (entry.key().1.clone(), entry.value().clone()))
            .collect()
    }

    /// Remove symbols from a file (for incremental updates)
    pub fn remove_file(&self, file_path: &str) -> Vec<String> {
        if let Some((_, fqns)) = self.file_symbols.remove(file_path) {
            for fqn in &fqns {
                self.symbols.remove(fqn);
            }

            // SOTA: Also remove aliases for this file
            self.alias_to_fqn.retain(|k, _| k.0 != file_path);

            fqns
        } else {
            Vec::new()
        }
    }

    /// Add symbols from an IR document
    pub fn add_from_ir(&self, ir: &IRDocument) {
        let mut file_fqns = Vec::new();

        for node in &ir.nodes {
            // Skip import nodes - they should not be in symbol table
            if matches!(node.kind, crate::shared::models::NodeKind::Import) {
                continue;
            }

            if node.fqn.is_empty() {
                continue;
            }

            let symbol = Arc::new(Symbol::new(
                node.fqn.clone(),
                node.name.clone().unwrap_or_else(|| extract_name(&node.fqn)),
                node.kind,
                ir.file_path.clone(),
                node.id.clone(),
                node.span,
            ));

            self.symbols.insert(node.fqn.clone(), symbol.clone());
            file_fqns.push(node.fqn.clone());

            let name = symbol.name.clone();
            self.name_to_fqns
                .entry(name)
                .or_insert_with(Vec::new)
                .push(node.fqn.clone());
        }

        if !file_fqns.is_empty() {
            self.file_symbols.insert(ir.file_path.clone(), file_fqns);
        }
    }
}

impl Default for SymbolIndex {
    fn default() -> Self {
        Self::new()
    }
}

/// Extract name from FQN (last component)
fn extract_name(fqn: &str) -> String {
    fqn.split('.').last().unwrap_or(fqn).to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Span};

    fn make_test_node(id: &str, fqn: &str, file_path: &str, name: &str) -> Node {
        Node::new(
            id.to_string(),
            NodeKind::Function,
            fqn.to_string(),
            file_path.to_string(),
            Span::new(1, 0, 10, 0),
        )
        .with_name(name.to_string())
    }

    #[test]
    fn test_symbol_index_empty() {
        let index = SymbolIndex::new();
        assert!(index.is_empty());
        assert_eq!(index.len(), 0);
    }

    #[test]
    fn test_symbol_index_build() {
        let ir = IRDocument {
            file_path: "src/main.py".to_string(),
            nodes: vec![
                make_test_node("node1", "main.foo", "src/main.py", "foo"),
                make_test_node("node2", "main.bar", "src/main.py", "bar"),
            ],
            edges: vec![],
            repo_id: None,
        };

        let index = SymbolIndex::build_from_irs(&[ir]);
        assert_eq!(index.len(), 2);
        assert!(index.contains("main.foo"));
        assert!(index.contains("main.bar"));
    }

    #[test]
    fn test_symbol_index_exact_resolve() {
        let ir = IRDocument {
            file_path: "src/utils.py".to_string(),
            nodes: vec![make_test_node(
                "node1",
                "utils.helper",
                "src/utils.py",
                "helper",
            )],
            edges: vec![],
            repo_id: None,
        };

        let index = SymbolIndex::build_from_irs(&[ir]);

        let symbol = index.resolve_exact("utils.helper");
        assert!(symbol.is_some());
        assert_eq!(symbol.unwrap().name, "helper");

        assert!(index.resolve_exact("utils.nonexistent").is_none());
    }

    #[test]
    fn test_symbol_index_partial_resolve() {
        let ir = IRDocument {
            file_path: "src/module.py".to_string(),
            nodes: vec![make_test_node(
                "node1",
                "module.submodule",
                "src/module.py",
                "submodule",
            )],
            edges: vec![],
            repo_id: None,
        };

        let index = SymbolIndex::build_from_irs(&[ir]);

        // Try to resolve longer path
        let result = index.resolve_partial("module.submodule.Class");
        assert!(result.is_some());
        let (symbol, matched) = result.unwrap();
        assert_eq!(matched, "module.submodule");
    }

    #[test]
    fn test_symbol_index_get_by_name() {
        let ir1 = IRDocument {
            file_path: "src/a.py".to_string(),
            nodes: vec![make_test_node("node1", "a.foo", "src/a.py", "foo")],
            edges: vec![],
            repo_id: None,
        };

        let ir2 = IRDocument {
            file_path: "src/b.py".to_string(),
            nodes: vec![make_test_node("node2", "b.foo", "src/b.py", "foo")],
            edges: vec![],
            repo_id: None,
        };

        let index = SymbolIndex::build_from_irs(&[ir1, ir2]);

        let fqns = index.get_by_name("foo");
        assert_eq!(fqns.len(), 2);
        assert!(fqns.contains(&"a.foo".to_string()));
        assert!(fqns.contains(&"b.foo".to_string()));
    }

    #[test]
    fn test_symbol_index_incremental() {
        let ir1 = IRDocument {
            file_path: "src/main.py".to_string(),
            nodes: vec![make_test_node("node1", "main.foo", "src/main.py", "foo")],
            edges: vec![],
            repo_id: None,
        };

        let index = SymbolIndex::build_from_irs(&[ir1]);
        assert_eq!(index.len(), 1);

        // Remove file
        let removed = index.remove_file("src/main.py");
        assert_eq!(removed.len(), 1);
        assert_eq!(index.len(), 0);

        // Add new IR
        let ir2 = IRDocument {
            file_path: "src/main.py".to_string(),
            nodes: vec![make_test_node("node1", "main.bar", "src/main.py", "bar")],
            edges: vec![],
            repo_id: None,
        };

        index.add_from_ir(&ir2);
        assert_eq!(index.len(), 1);
        assert!(index.contains("main.bar"));
        assert!(!index.contains("main.foo"));
    }

    #[test]
    fn test_alias_tracking() {
        let index = SymbolIndex::new();

        // Register aliases
        index.register_alias("main.py".to_string(), "np".to_string(), "numpy".to_string());
        index.register_alias(
            "main.py".to_string(),
            "pd".to_string(),
            "pandas".to_string(),
        );
        index.register_alias(
            "utils.py".to_string(),
            "np".to_string(),
            "numpy".to_string(),
        );

        // Test resolve_alias - file-scoped
        assert_eq!(
            index.resolve_alias("main.py", "np"),
            Some("numpy".to_string())
        );
        assert_eq!(
            index.resolve_alias("main.py", "pd"),
            Some("pandas".to_string())
        );
        assert_eq!(
            index.resolve_alias("utils.py", "np"),
            Some("numpy".to_string())
        );

        // Different file scope - no alias
        assert_eq!(index.resolve_alias("other.py", "np"), None);
        assert_eq!(index.resolve_alias("utils.py", "pd"), None);

        // Test get_file_aliases
        let main_aliases = index.get_file_aliases("main.py");
        assert_eq!(main_aliases.len(), 2);
        assert_eq!(main_aliases.get("np"), Some(&"numpy".to_string()));
        assert_eq!(main_aliases.get("pd"), Some(&"pandas".to_string()));

        let utils_aliases = index.get_file_aliases("utils.py");
        assert_eq!(utils_aliases.len(), 1);
        assert_eq!(utils_aliases.get("np"), Some(&"numpy".to_string()));
    }

    #[test]
    fn test_alias_removal_on_file_remove() {
        let index = SymbolIndex::new();

        // Register symbols and aliases
        let ir = IRDocument {
            file_path: "main.py".to_string(),
            nodes: vec![make_test_node("node1", "main.foo", "main.py", "foo")],
            edges: vec![],
            repo_id: None,
        };
        index.add_from_ir(&ir);

        index.register_alias("main.py".to_string(), "np".to_string(), "numpy".to_string());
        index.register_alias(
            "main.py".to_string(),
            "pd".to_string(),
            "pandas".to_string(),
        );

        // Verify aliases exist
        assert_eq!(
            index.resolve_alias("main.py", "np"),
            Some("numpy".to_string())
        );
        assert_eq!(
            index.resolve_alias("main.py", "pd"),
            Some("pandas".to_string())
        );

        // Remove file
        index.remove_file("main.py");

        // Aliases should be gone
        assert_eq!(index.resolve_alias("main.py", "np"), None);
        assert_eq!(index.resolve_alias("main.py", "pd"), None);
        assert_eq!(index.get_file_aliases("main.py").len(), 0);
    }
}
