//! Import Resolver with Rayon Parallelism (RFC-062)
//!
//! Resolves imports in parallel using Rayon.
//! Uses SymbolIndex for O(1) lookups.

use dashmap::DashMap;
use rayon::prelude::*;
use std::collections::HashMap;

use super::scope_index::ScopeAwareIndex;
use super::symbol_index::SymbolIndex;
use super::types::{ImportInfo, ResolutionMethod, ResolvedImport};
use super::IRDocument;
use crate::shared::models::{EdgeKind, Node};

/// Import resolver with parallel processing
///
/// SOTA: Supports both file-level and scope-aware resolution
pub struct ImportResolver<'a> {
    symbol_index: &'a SymbolIndex,

    /// Optional scope-aware index for function-scoped imports
    ///
    /// When present, aliases are registered in appropriate scope
    /// instead of file-level only
    scope_index: Option<&'a ScopeAwareIndex>,
}

impl<'a> ImportResolver<'a> {
    /// Create resolver with file-level scope only
    pub fn new(symbol_index: &'a SymbolIndex) -> Self {
        Self {
            symbol_index,
            scope_index: None,
        }
    }

    /// SOTA: Create resolver with scope-aware resolution
    ///
    /// When scope_index is provided, imports are registered in the
    /// appropriate scope (function/class/module) instead of file-level only.
    pub fn new_with_scope(symbol_index: &'a SymbolIndex, scope_index: &'a ScopeAwareIndex) -> Self {
        Self {
            symbol_index,
            scope_index: Some(scope_index),
        }
    }

    /// Resolve all imports from IR documents (parallel)
    ///
    /// Returns: file_path → Vec<ResolvedImport>
    pub fn resolve_all(&self, irs: &[IRDocument]) -> HashMap<String, Vec<ResolvedImport>> {
        // Collect all imports from all files
        let all_imports: Vec<(String, ImportInfo)> = irs
            .par_iter()
            .flat_map(|ir| self.collect_imports(ir))
            .collect();

        // Group by file
        let imports_by_file: DashMap<String, Vec<ImportInfo>> = DashMap::new();
        for (file_path, import_info) in all_imports {
            imports_by_file
                .entry(file_path)
                .or_insert_with(Vec::new)
                .push(import_info);
        }

        // Resolve imports in parallel
        // Convert DashMap to Vec for parallel iteration with Rayon
        let file_imports: Vec<(String, Vec<ImportInfo>)> = imports_by_file.into_iter().collect();

        // Parallel resolution
        file_imports
            .into_par_iter()
            .map(|(file_path, imports)| {
                let resolved_imports: Vec<ResolvedImport> =
                    imports.iter().map(|imp| self.resolve_single(imp)).collect();
                (file_path, resolved_imports)
            })
            .collect()
    }

    /// Collect imports from a single IR document
    fn collect_imports(&self, ir: &IRDocument) -> Vec<(String, ImportInfo)> {
        // Build node index for O(1) lookup
        let node_by_id: HashMap<&str, &Node> =
            ir.nodes.iter().map(|n| (n.id.as_str(), n)).collect();

        let mut imports = Vec::new();

        for edge in &ir.edges {
            if edge.kind != EdgeKind::Imports {
                continue;
            }

            // Get imported name from target node
            let imported_name = if let Some(target_node) = node_by_id.get(edge.target_id.as_str()) {
                // Target ID is a node ID - look up the node and extract FQN
                if !target_node.fqn.is_empty() {
                    target_node.fqn.clone()
                } else {
                    target_node.name.clone().unwrap_or_default()
                }
            } else {
                // Target ID is not a node ID - check if it's already an FQN
                // This happens when IR builder uses FQN as target_id directly
                if !edge.target_id.is_empty() {
                    edge.target_id.clone()
                } else {
                    continue;
                }
            };

            if imported_name.is_empty() {
                continue;
            }

            // SOTA: Extract alias from edge metadata
            let alias = edge.metadata.as_ref().and_then(|m| m.alias.clone());

            let import_info = ImportInfo {
                file_path: ir.file_path.clone(),
                source_node_id: edge.source_id.clone(),
                target_node_id: edge.target_id.clone(),
                imported_name,
                alias,
            };

            imports.push((ir.file_path.clone(), import_info));
        }

        imports
    }

    /// Resolve a single import
    fn resolve_single(&self, import: &ImportInfo) -> ResolvedImport {
        let fqn = &import.imported_name;

        // Strategy 1: Exact FQN match
        if let Some(symbol) = self.symbol_index.resolve_exact(fqn) {
            let mut resolved = ResolvedImport::resolved(
                fqn.clone(),
                symbol.fqn.clone(),
                symbol.file_path.clone(),
                symbol.node_id.clone(),
                ResolutionMethod::ExactMatch,
            );

            // SOTA: Register alias in appropriate scope
            if let Some(ref alias) = import.alias {
                self.register_alias_in_scope(import, alias, &symbol.fqn);
                resolved = resolved.with_alias(alias.clone());
            }

            return resolved;
        }

        // Strategy 2: Partial match (module.submodule.Class → module.submodule)
        if let Some((symbol, matched_fqn)) = self.symbol_index.resolve_partial(fqn) {
            let mut resolved = ResolvedImport::resolved(
                fqn.clone(),
                matched_fqn.clone(),
                symbol.file_path.clone(),
                symbol.node_id.clone(),
                ResolutionMethod::PartialMatch,
            );

            // SOTA: Register alias in appropriate scope
            if let Some(ref alias) = import.alias {
                self.register_alias_in_scope(import, alias, &matched_fqn);
                resolved = resolved.with_alias(alias.clone());
            }

            return resolved;
        }

        // Strategy 3: Module path pattern match
        if let Some(symbol) = self.symbol_index.resolve_by_module_path(fqn) {
            let mut resolved = ResolvedImport::resolved(
                fqn.clone(),
                symbol.fqn.clone(),
                symbol.file_path.clone(),
                symbol.node_id.clone(),
                ResolutionMethod::ModulePath,
            );

            // SOTA: Register alias in appropriate scope
            if let Some(ref alias) = import.alias {
                self.register_alias_in_scope(import, alias, &symbol.fqn);
                resolved = resolved.with_alias(alias.clone());
            }

            return resolved;
        }

        // Strategy 4: Try relative import resolution
        if fqn.starts_with('.') {
            if let Some(mut resolved) = self.resolve_relative_import(import) {
                // SOTA: Register alias in appropriate scope
                if let Some(ref alias) = import.alias {
                    if let Some(ref resolved_fqn) = resolved.resolved_fqn {
                        self.register_alias_in_scope(import, alias, resolved_fqn);
                        resolved = resolved.with_alias(alias.clone());
                    }
                }
                return resolved;
            }
        }

        // Not found - external or unresolved
        let mut unresolved = ResolvedImport::unresolved(fqn.clone());

        // SOTA: Even for unresolved imports, register alias for external libraries
        // Example: "import numpy as np" where numpy is external
        if let Some(ref alias) = import.alias {
            self.register_alias_in_scope(import, alias, fqn);
            unresolved = unresolved.with_alias(alias.clone());
        }

        unresolved
    }

    /// SOTA: Register alias in appropriate scope
    ///
    /// If scope_index is available, determines the scope of the import node
    /// and registers the alias in that scope. Otherwise falls back to file-level.
    fn register_alias_in_scope(&self, import: &ImportInfo, alias: &str, fqn: &str) {
        if let Some(scope_index) = self.scope_index {
            // Try to find the scope for the import's source node
            if let Some(scope_id) = scope_index.get_node_scope(&import.source_node_id) {
                // Register in the node's scope
                scope_index.add_alias_to_scope(&scope_id, alias.to_string(), fqn.to_string());
                return;
            }

            // Fallback: Try file scope
            if let Some(file_scope_id) = scope_index.get_file_scope(&import.file_path) {
                scope_index.add_alias_to_scope(&file_scope_id, alias.to_string(), fqn.to_string());
                return;
            }
        }

        // No scope index or scope not found - use file-level fallback
        self.symbol_index.register_alias(
            import.file_path.clone(),
            alias.to_string(),
            fqn.to_string(),
        );
    }

    /// Resolve relative import (e.g., ".utils" from "package/main.py")
    fn resolve_relative_import(&self, import: &ImportInfo) -> Option<ResolvedImport> {
        let fqn = &import.imported_name;
        let file_path = &import.file_path;

        // Count leading dots
        let dots = fqn.chars().take_while(|c| *c == '.').count();
        let remainder = &fqn[dots..];

        // Get current module path from file path
        let module_parts: Vec<&str> = file_path
            .trim_end_matches(".py")
            .split('/')
            .filter(|s| !s.is_empty() && *s != "src")
            .collect();

        if module_parts.len() < dots {
            return None;
        }

        // Build absolute module path
        let base_parts = &module_parts[..module_parts.len() - dots + 1];
        let absolute_fqn = if remainder.is_empty() {
            base_parts.join(".")
        } else {
            format!("{}.{}", base_parts.join("."), remainder)
        };

        // Try to resolve the absolute FQN
        if let Some(symbol) = self.symbol_index.resolve_exact(&absolute_fqn) {
            return Some(ResolvedImport::resolved(
                fqn.clone(),
                absolute_fqn,
                symbol.file_path.clone(),
                symbol.node_id.clone(),
                ResolutionMethod::ExactMatch,
            ));
        }

        if let Some((symbol, matched_fqn)) = self.symbol_index.resolve_partial(&absolute_fqn) {
            return Some(ResolvedImport::resolved(
                fqn.clone(),
                matched_fqn,
                symbol.file_path.clone(),
                symbol.node_id.clone(),
                ResolutionMethod::PartialMatch,
            ));
        }

        None
    }
}

/// Resolve imports for a subset of files (for incremental updates)
pub fn resolve_imports_for_files(
    symbol_index: &SymbolIndex,
    irs: &[IRDocument],
    file_paths: &[String],
) -> HashMap<String, Vec<ResolvedImport>> {
    let file_set: std::collections::HashSet<&String> = file_paths.iter().collect();

    let filtered_irs: Vec<&IRDocument> = irs
        .iter()
        .filter(|ir| file_set.contains(&ir.file_path))
        .collect();

    let resolver = ImportResolver::new(symbol_index);

    filtered_irs
        .par_iter()
        .map(|ir| {
            let imports = resolver.collect_imports(ir);
            let resolved: Vec<ResolvedImport> = imports
                .iter()
                .map(|(_, imp)| resolver.resolve_single(imp))
                .collect();
            (ir.file_path.clone(), resolved)
        })
        .collect()
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

    fn make_import_node(id: &str, fqn: &str, file_path: &str, name: &str) -> Node {
        Node::new(
            id.to_string(),
            NodeKind::Import,
            fqn.to_string(),
            file_path.to_string(),
            Span::new(1, 0, 1, 20),
        )
        .with_name(name.to_string())
    }

    fn make_import_edge(source_id: &str, target_id: &str) -> Edge {
        Edge::new(
            source_id.to_string(),
            target_id.to_string(),
            EdgeKind::Imports,
        )
    }

    #[test]
    fn test_resolve_exact_match() {
        // utils.py defines helper
        let ir_utils = IRDocument {
            file_path: "src/utils.py".to_string(),
            nodes: vec![make_test_node(
                "utils_helper",
                "utils.helper",
                "src/utils.py",
                "helper",
            )],
            edges: vec![],
            repo_id: None,
        };

        // main.py imports helper
        let ir_main = IRDocument {
            file_path: "src/main.py".to_string(),
            nodes: vec![
                make_test_node("main_func", "main.main_func", "src/main.py", "main_func"),
                make_import_node("import_helper", "utils.helper", "src/main.py", "helper"),
            ],
            edges: vec![make_import_edge("main_func", "import_helper")],
            repo_id: None,
        };

        let index = SymbolIndex::build_from_irs(&[ir_utils, ir_main.clone()]);
        let resolver = ImportResolver::new(&index);
        let resolved = resolver.resolve_all(&[ir_main]);

        assert!(resolved.contains_key("src/main.py"));
        let imports = resolved.get("src/main.py").unwrap();
        assert_eq!(imports.len(), 1);
        assert!(!imports[0].is_external);
        assert_eq!(imports[0].resolution_method, ResolutionMethod::ExactMatch);
    }

    #[test]
    fn test_resolve_partial_match() {
        // module.py defines submodule
        let ir_module = IRDocument {
            file_path: "src/module.py".to_string(),
            nodes: vec![make_test_node(
                "mod_sub",
                "module.submodule",
                "src/module.py",
                "submodule",
            )],
            edges: vec![],
            repo_id: None,
        };

        // main.py imports module.submodule.Class (Class doesn't exist)
        let ir_main = IRDocument {
            file_path: "src/main.py".to_string(),
            nodes: vec![
                make_test_node("main_func", "main.main_func", "src/main.py", "main_func"),
                make_import_node(
                    "import_class",
                    "module.submodule.Class",
                    "src/main.py",
                    "Class",
                ),
            ],
            edges: vec![make_import_edge("main_func", "import_class")],
            repo_id: None,
        };

        let index = SymbolIndex::build_from_irs(&[ir_module, ir_main.clone()]);
        let resolver = ImportResolver::new(&index);
        let resolved = resolver.resolve_all(&[ir_main]);

        let imports = resolved.get("src/main.py").unwrap();
        assert_eq!(imports.len(), 1);
        assert!(!imports[0].is_external);
        assert_eq!(imports[0].resolution_method, ResolutionMethod::PartialMatch);
        assert_eq!(
            imports[0].resolved_fqn,
            Some("module.submodule".to_string())
        );
    }

    #[test]
    fn test_resolve_external() {
        let ir_main = IRDocument {
            file_path: "src/main.py".to_string(),
            nodes: vec![
                make_test_node("main_func", "main.main_func", "src/main.py", "main_func"),
                make_import_node("import_np", "numpy", "src/main.py", "numpy"),
            ],
            edges: vec![make_import_edge("main_func", "import_np")],
            repo_id: None,
        };

        let index = SymbolIndex::build_from_irs(&[ir_main.clone()]);
        let resolver = ImportResolver::new(&index);
        let resolved = resolver.resolve_all(&[ir_main]);

        let imports = resolved.get("src/main.py").unwrap();
        assert_eq!(imports.len(), 1);
        assert!(imports[0].is_external);
        assert_eq!(imports[0].resolution_method, ResolutionMethod::NotFound);
    }

    #[test]
    fn test_resolve_multiple_files_parallel() {
        let irs: Vec<IRDocument> = (0..10)
            .map(|i| IRDocument {
                file_path: format!("src/module_{}.py", i),
                nodes: vec![make_test_node(
                    &format!("func_{}", i),
                    &format!("module_{}.func", i),
                    &format!("src/module_{}.py", i),
                    "func",
                )],
                edges: vec![],
                repo_id: None,
            })
            .collect();

        let index = SymbolIndex::build_from_irs(&irs);
        assert_eq!(index.len(), 10);

        let resolver = ImportResolver::new(&index);
        let resolved = resolver.resolve_all(&irs);
        assert_eq!(resolved.len(), 0); // No imports in these files
    }
}
