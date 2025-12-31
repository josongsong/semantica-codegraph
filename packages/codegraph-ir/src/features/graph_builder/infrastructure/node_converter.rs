// Node Converter - IR Nodes → Graph Nodes
//
// Parallel conversion with role-based specialization

use ahash::AHashMap;
use dashmap::DashMap;
use rayon::prelude::*;
use std::collections::HashMap;
use std::path::Path;

use super::builder::{intern_str, GraphBuilderError, IRDocument, SemanticSnapshot};
use crate::features::graph_builder::domain::{GraphNode, InternedString};
use crate::shared::models::{CFGBlock, Node, NodeKind};

pub struct NodeConverter;

impl NodeConverter {
    pub fn new() -> Self {
        Self
    }

    /// Convert IR nodes to GraphNodes (PARALLEL)
    ///
    /// Returns: (IR nodes, Module nodes)
    pub fn convert_ir_nodes(
        &self,
        ir_doc: &IRDocument,
        module_cache: &DashMap<InternedString, GraphNode>,
    ) -> Result<(Vec<GraphNode>, Vec<GraphNode>), GraphBuilderError> {
        let total_nodes = ir_doc.nodes.len();

        // Parallel conversion of IR nodes
        let results: Vec<_> = ir_doc
            .nodes
            .par_iter()
            .filter_map(|node| {
                match self.convert_single_node(node, ir_doc) {
                    Ok(Some(graph_node)) => Some(Ok::<GraphNode, GraphBuilderError>(graph_node)),
                    Ok(None) => None, // Skipped (e.g., CALL nodes become edges)
                    Err(_e) => {
                        None // Continue with other nodes
                    }
                }
            })
            .collect();

        // Separate successes from errors
        let graph_nodes: Vec<GraphNode> = results.into_iter().filter_map(Result::ok).collect();

        // Generate module nodes from file paths (PARALLEL)
        let module_nodes = self.generate_module_nodes(ir_doc, module_cache)?;

        Ok((graph_nodes, module_nodes))
    }

    /// Convert semantic IR nodes (Type, Signature, CFG, DFG)
    pub fn convert_semantic_nodes(
        &self,
        ir_doc: &IRDocument,
        semantic: &SemanticSnapshot,
    ) -> Result<Vec<GraphNode>, GraphBuilderError> {
        let mut nodes = Vec::new();

        // Convert Type entities (PARALLEL)
        if let Some(types) = semantic.get("types").and_then(|v| v.as_array()) {
            let type_nodes: Vec<_> = types
                .par_iter()
                .filter_map(|type_value| {
                    let type_entity: Node = serde_json::from_value(type_value.clone()).ok()?;
                    self.convert_type_entity(&type_entity, ir_doc).ok()
                })
                .collect();
            nodes.extend(type_nodes);
        }

        // Convert Signature entities (PARALLEL)
        if let Some(signatures) = semantic.get("signatures").and_then(|v| v.as_array()) {
            let sig_nodes: Vec<_> = signatures
                .par_iter()
                .filter_map(|sig_value| {
                    let sig: Node = serde_json::from_value(sig_value.clone()).ok()?;
                    self.convert_signature_entity(&sig, ir_doc).ok()
                })
                .collect();
            nodes.extend(sig_nodes);
        }

        // Convert CFG blocks (PARALLEL)
        if let Some(cfg_blocks) = semantic.get("cfg_blocks").and_then(|v| v.as_array()) {
            let cfg_nodes: Vec<_> = cfg_blocks
                .par_iter()
                .filter_map(|block_value| {
                    let block: CFGBlock = serde_json::from_value(block_value.clone()).ok()?;
                    self.convert_cfg_block(&block, ir_doc).ok()
                })
                .collect();
            nodes.extend(cfg_nodes);
        }

        // Convert DFG variables (PARALLEL)
        if let Some(dfg) = semantic.get("dfg_snapshot").and_then(|v| v.as_object()) {
            if let Some(variables) = dfg.get("variables").and_then(|v| v.as_array()) {
                let var_nodes: Vec<_> = variables
                    .par_iter()
                    .filter_map(|var_value| {
                        let var: Node = serde_json::from_value(var_value.clone()).ok()?;
                        self.convert_variable_entity(&var, ir_doc).ok()
                    })
                    .collect();
                nodes.extend(var_nodes);
            }
        }

        Ok(nodes)
    }

    /// Convert single IR node to GraphNode
    fn convert_single_node(
        &self,
        node: &Node,
        ir_doc: &IRDocument,
    ) -> Result<Option<GraphNode>, GraphBuilderError> {
        // Map IR kind to Graph kind (with role-based specialization)
        let graph_kind = match self.map_ir_kind_to_graph_kind(&node.kind, node.role.as_deref()) {
            Ok(kind) => kind,
            Err(_) => return Ok(None), // Skip unsupported kinds
        };

        // Build attrs
        let mut attrs = AHashMap::new();
        attrs.insert("language".to_string(), serde_json::json!(&node.language));
        if let Some(doc) = &node.docstring {
            attrs.insert("docstring".to_string(), serde_json::json!(doc));
        }
        if let Some(role) = &node.role {
            attrs.insert("role".to_string(), serde_json::json!(role));
        }
        if let Some(is_test) = node.is_test_file {
            attrs.insert("is_test_file".to_string(), serde_json::json!(is_test));
        }
        if let Some(sig_id) = &node.signature_id {
            attrs.insert("signature_id".to_string(), serde_json::json!(sig_id));
        }
        if let Some(type_id) = &node.declared_type_id {
            attrs.insert("declared_type_id".to_string(), serde_json::json!(type_id));
        }
        if let Some(module_path) = &node.module_path {
            attrs.insert("module_path".to_string(), serde_json::json!(module_path));
        }

        // Merge node-specific attrs (if any)
        // Note: Node.attrs is Option<String> for PyO3 compat, not HashMap
        // Parse if needed, but for now skip since most attrs come from other fields

        Ok(Some(GraphNode {
            id: intern_str(&node.id),
            kind: graph_kind,
            repo_id: intern_str("default"),
            snapshot_id: Some(intern_str("default")),
            fqn: intern_str(&node.fqn),
            name: intern_str(node.name.as_deref().unwrap_or("")),
            path: Some(intern_str(&node.file_path)),
            span: Some(Box::new(node.span.clone())),
            attrs,
        }))
    }

    /// Map IR NodeKind to Graph NodeKind (with role-based specialization)
    fn map_ir_kind_to_graph_kind(
        &self,
        ir_kind: &NodeKind,
        role: Option<&str>,
    ) -> Result<NodeKind, ()> {
        // Role-based specialization (Route, Service, Repository, etc.)
        if let Some(role_str) = role {
            let role_lower = role_str.to_lowercase();
            if matches!(
                ir_kind,
                NodeKind::Function | NodeKind::Method | NodeKind::Class
            ) {
                if role_lower.contains("route") || role_lower.contains("controller") {
                    return Ok(NodeKind::Route);
                } else if role_lower.contains("service") {
                    return Ok(NodeKind::Service);
                } else if role_lower.contains("repo") || role_lower.contains("repository") {
                    return Ok(NodeKind::Repository);
                } else if role_lower.contains("config") {
                    return Ok(NodeKind::Config);
                } else if role_lower.contains("job") || role_lower.contains("task") {
                    return Ok(NodeKind::Job);
                } else if role_lower.contains("middleware") {
                    return Ok(NodeKind::Middleware);
                }
            }
        }

        // Standard 1:1 mapping
        match ir_kind {
            NodeKind::File => Ok(NodeKind::File),
            NodeKind::Module => Ok(NodeKind::Module),
            NodeKind::Class => Ok(NodeKind::Class),
            NodeKind::Interface => Ok(NodeKind::Interface),
            NodeKind::Function => Ok(NodeKind::Function),
            NodeKind::Method => Ok(NodeKind::Method),
            NodeKind::Variable => Ok(NodeKind::Variable),
            NodeKind::Field => Ok(NodeKind::Field),
            NodeKind::Import => Ok(NodeKind::Import),
            // CALL nodes don't become graph nodes - they become edges
            _ => Err(()),
        }
    }

    /// Generate MODULE nodes from file paths (PARALLEL)
    fn generate_module_nodes(
        &self,
        ir_doc: &IRDocument,
        module_cache: &DashMap<InternedString, GraphNode>,
    ) -> Result<Vec<GraphNode>, GraphBuilderError> {
        // Collect all file nodes
        let file_nodes: Vec<_> = ir_doc
            .nodes
            .iter()
            .filter(|n| n.kind == NodeKind::File)
            .collect();

        // Parallel module generation
        let new_modules: Vec<_> = file_nodes
            .par_iter()
            .flat_map(|file_node| {
                let file_path = &file_node.file_path;

                let path = Path::new(file_path);
                let parts: Vec<_> = path
                    .parent()
                    .map(|p| {
                        p.components()
                            .filter_map(|c| c.as_os_str().to_str())
                            .collect()
                    })
                    .unwrap_or_default();

                if parts.is_empty() {
                    return vec![];
                }

                let mut modules = Vec::new();
                let mut path_parts = Vec::new();
                let mut fqn_parts = Vec::new();

                for part in parts {
                    path_parts.push(part);
                    fqn_parts.push(part);

                    let current_path = path_parts.join("/");
                    let current_fqn = fqn_parts.join(".");
                    let repo_id_str = ir_doc.repo_id.as_deref().unwrap_or("unknown");
                    let module_id = intern_str(format!("module:{}::{}", repo_id_str, current_fqn));

                    // Skip if already in cache
                    if module_cache.contains_key(&module_id) {
                        continue;
                    }

                    let mut attrs = AHashMap::new();
                    let lang = &file_node.language;
                    attrs.insert("language".to_string(), serde_json::json!(lang));
                    attrs.insert("auto_generated".to_string(), serde_json::json!(true));

                    modules.push(GraphNode {
                        id: module_id,
                        kind: NodeKind::Module,
                        repo_id: intern_str("default"),
                        snapshot_id: Some(intern_str("default")),
                        fqn: intern_str(&current_fqn),
                        name: intern_str(part),
                        path: Some(intern_str(&current_path)),
                        span: None,
                        attrs,
                    });
                }

                modules
            })
            .collect();

        Ok(new_modules)
    }

    /// Convert TypeEntity (Node) to GraphNode
    fn convert_type_entity(
        &self,
        type_entity: &Node,
        ir_doc: &IRDocument,
    ) -> Result<GraphNode, GraphBuilderError> {
        let name = type_entity.name.as_deref().unwrap_or("");
        let mut attrs = AHashMap::new();
        if let Some(flavor) = &type_entity.flavor {
            attrs.insert("flavor".to_string(), serde_json::json!(flavor));
        }

        Ok(GraphNode {
            id: intern_str(&type_entity.id),
            kind: NodeKind::Type,
            repo_id: intern_str("default"),
            snapshot_id: Some(intern_str("default")),
            fqn: intern_str(&type_entity.fqn),
            name: intern_str(name),
            path: None,
            span: Some(Box::new(type_entity.span.clone())),
            attrs,
        })
    }

    /// Convert SignatureEntity to GraphNode
    fn convert_signature_entity(
        &self,
        sig: &crate::shared::models::SignatureEntity,
        ir_doc: &IRDocument,
    ) -> Result<GraphNode, GraphBuilderError> {
        let attrs = AHashMap::new();
        // SignatureEntity is type alias for Node
        // Use sig fields directly

        Ok(GraphNode {
            id: intern_str(&sig.id),
            kind: NodeKind::Signature,
            repo_id: intern_str("default"),
            snapshot_id: Some(intern_str("default")),
            fqn: intern_str(&sig.fqn),
            name: sig
                .name
                .as_deref()
                .map(|s| intern_str(s))
                .unwrap_or_else(|| intern_str("")),
            path: None,
            span: Some(Box::new(sig.span.clone())),
            attrs,
        })
    }

    /// Convert CFG block to GraphNode
    fn convert_cfg_block(
        &self,
        block: &crate::shared::models::CFGBlock,
        ir_doc: &IRDocument,
    ) -> Result<GraphNode, GraphBuilderError> {
        let mut attrs = AHashMap::new();
        attrs.insert("block_kind".to_string(), serde_json::json!(&block.kind));
        attrs.insert(
            "function_node_id".to_string(),
            serde_json::json!(&block.function_node_id),
        );

        Ok(GraphNode {
            id: intern_str(&block.id),
            kind: NodeKind::CfgBlock,
            repo_id: intern_str("default"),
            snapshot_id: Some(intern_str("default")),
            fqn: intern_str(&block.id),
            name: intern_str(format!("{:?}", block.kind)),
            path: None,
            span: block.span.clone().map(Box::new),
            attrs,
        })
    }

    /// Convert DFG variable to GraphNode
    fn convert_variable_entity(
        &self,
        var: &crate::shared::models::VariableEntity,
        ir_doc: &IRDocument,
    ) -> Result<GraphNode, GraphBuilderError> {
        let attrs = AHashMap::new();
        // VariableEntity is type alias for Node

        Ok(GraphNode {
            id: intern_str(&var.id),
            kind: NodeKind::Variable,
            repo_id: intern_str("default"),
            snapshot_id: Some(intern_str("default")),
            fqn: intern_str(&var.fqn),
            name: var
                .name
                .as_deref()
                .map(|s| intern_str(s))
                .unwrap_or_else(|| intern_str("")),
            path: None,
            span: Some(Box::new(var.span.clone())),
            attrs,
        })
    }
}

impl Default for NodeConverter {
    fn default() -> Self {
        Self::new()
    }
}
