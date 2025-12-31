// Edge Converter - IR Edges → Graph Edges
//
// Parallel edge conversion with auto-generation of derived edges

use ahash::AHashMap;
use rayon::prelude::*;

use super::builder::{intern_str, GraphBuilderError, IRDocument, SemanticSnapshot};
use crate::features::graph_builder::domain::{GraphEdge, GraphNode, InternedString};
use crate::shared::models::{CFGBlock, CFGEdge, Edge, EdgeKind, NodeKind};

pub struct EdgeConverter;

impl EdgeConverter {
    pub fn new() -> Self {
        Self
    }

    /// Convert all edges from IR + Semantic (PARALLEL)
    pub fn convert_edges(
        &self,
        ir_doc: &IRDocument,
        semantic: Option<&SemanticSnapshot>,
        graph_nodes: &AHashMap<InternedString, GraphNode>,
    ) -> Result<Vec<GraphEdge>, GraphBuilderError> {
        let mut all_edges = Vec::new();

        // Convert IR edges (PARALLEL)
        let ir_edges = self.convert_ir_edges(ir_doc)?;
        all_edges.extend(ir_edges);

        // Generate type reference edges (PARALLEL)
        let type_ref_edges = self.generate_type_reference_edges(ir_doc)?;
        all_edges.extend(type_ref_edges);

        // Convert CFG edges (PARALLEL)
        if let Some(semantic) = semantic {
            if let Some(cfg_edges_values) = semantic.get("cfg_edges").and_then(|v| v.as_array()) {
                let cfg_edges: Vec<CFGEdge> = cfg_edges_values
                    .iter()
                    .filter_map(|v| serde_json::from_value(v.clone()).ok())
                    .collect();
                let cfg_graph_edges = self.convert_cfg_edges(&cfg_edges)?;
                all_edges.extend(cfg_graph_edges);
            }

            // Generate DFG edges (READS/WRITES) (PARALLEL)
            if let Some(cfg_blocks_values) = semantic.get("cfg_blocks").and_then(|v| v.as_array()) {
                let cfg_blocks: Vec<CFGBlock> = cfg_blocks_values
                    .iter()
                    .filter_map(|v| serde_json::from_value(v.clone()).ok())
                    .collect();
                let dfg_edges = self.generate_dfg_edges(&cfg_blocks, graph_nodes)?;
                all_edges.extend(dfg_edges);
            }
        }

        Ok(all_edges)
    }

    /// Convert IR edges to graph edges (PARALLEL)
    fn convert_ir_edges(&self, ir_doc: &IRDocument) -> Result<Vec<GraphEdge>, GraphBuilderError> {
        let edges: Vec<_> = ir_doc
            .edges
            .par_iter()
            .enumerate()
            .filter_map(|(idx, ir_edge)| {
                match self.map_ir_edge_to_graph_edge(&ir_edge.kind) {
                    Ok(graph_edge_kind) => {
                        let edge_id = intern_str(format!(
                            "edge:{}:{}",
                            graph_edge_kind.to_string().to_lowercase(),
                            idx
                        ));

                        let mut attrs = AHashMap::new();
                        if let Some(span) = &ir_edge.span {
                            attrs.insert("span".to_string(), serde_json::json!(span));
                        }
                        if let Some(edge_attrs) = &ir_edge.attrs {
                            for (k, v) in edge_attrs {
                                attrs.insert(k.clone(), v.clone());
                            }
                        }

                        Some(GraphEdge {
                            id: edge_id,
                            kind: graph_edge_kind,
                            source_id: intern_str(&ir_edge.source_id),
                            target_id: intern_str(&ir_edge.target_id),
                            attrs,
                        })
                    }
                    Err(_) => None, // Skip unsupported edge kinds
                }
            })
            .collect();

        Ok(edges)
    }

    /// Generate REFERENCES_TYPE edges from declared_type_id (PARALLEL)
    fn generate_type_reference_edges(
        &self,
        ir_doc: &IRDocument,
    ) -> Result<Vec<GraphEdge>, GraphBuilderError> {
        let edges: Vec<_> = ir_doc
            .nodes
            .par_iter()
            .enumerate()
            .filter_map(|(idx, node)| {
                node.declared_type_id.as_ref().map(|type_id| {
                    let edge_id = intern_str(format!("edge:references_type:{}", idx));

                    GraphEdge {
                        id: edge_id,
                        kind: EdgeKind::ReferencesType,
                        source_id: intern_str(&node.id),
                        target_id: intern_str(type_id),
                        attrs: AHashMap::new(),
                    }
                })
            })
            .collect();

        Ok(edges)
    }

    /// Convert CFG edges to graph edges (PARALLEL)
    fn convert_cfg_edges(
        &self,
        cfg_edges: &[crate::shared::models::CFGEdge],
    ) -> Result<Vec<GraphEdge>, GraphBuilderError> {
        let edges: Vec<_> = cfg_edges
            .par_iter()
            .enumerate()
            .map(|(idx, cfg_edge)| {
                let graph_edge_kind = self.map_cfg_edge_to_graph_edge(&cfg_edge.kind);
                let edge_id = intern_str(format!(
                    "edge:{}:{}",
                    graph_edge_kind.to_string().to_lowercase(),
                    idx
                ));

                let mut attrs = AHashMap::new();
                attrs.insert(
                    "cfg_edge_kind".to_string(),
                    serde_json::json!(&cfg_edge.kind),
                );

                GraphEdge {
                    id: edge_id,
                    kind: graph_edge_kind,
                    source_id: intern_str(&cfg_edge.source_block_id),
                    target_id: intern_str(&cfg_edge.target_block_id),
                    attrs,
                }
            })
            .collect();

        Ok(edges)
    }

    /// Generate DFG edges (READS/WRITES) from CFG blocks (PARALLEL)
    fn generate_dfg_edges(
        &self,
        cfg_blocks: &[crate::shared::models::CFGBlock],
        graph_nodes: &AHashMap<InternedString, GraphNode>,
    ) -> Result<Vec<GraphEdge>, GraphBuilderError> {
        let edges: Vec<_> = cfg_blocks
            .par_iter()
            .flat_map(|cfg_block| {
                let block_id_interned = intern_str(&cfg_block.id);

                // Skip if CFG block not in graph
                if !graph_nodes.contains_key(&block_id_interned) {
                    return vec![];
                }

                let mut block_edges = Vec::new();

                // Generate WRITES edges
                for var_id in &cfg_block.defined_variable_ids {
                    let var_id_interned = intern_str(var_id);
                    if !graph_nodes.contains_key(&var_id_interned) {
                        continue;
                    }

                    let edge_id = intern_str(format!("edge:writes:{}:{}", cfg_block.id, var_id));
                    let mut attrs = AHashMap::new();
                    attrs.insert(
                        "function_node_id".to_string(),
                        serde_json::json!(&cfg_block.function_node_id),
                    );

                    block_edges.push(GraphEdge {
                        id: edge_id,
                        kind: EdgeKind::Writes,
                        source_id: block_id_interned.clone(),
                        target_id: var_id_interned,
                        attrs,
                    });
                }

                // Generate READS edges
                for var_id in &cfg_block.used_variable_ids {
                    let var_id_interned = intern_str(var_id);
                    if !graph_nodes.contains_key(&var_id_interned) {
                        continue;
                    }

                    let edge_id = intern_str(format!("edge:reads:{}:{}", cfg_block.id, var_id));
                    let mut attrs = AHashMap::new();
                    attrs.insert(
                        "function_node_id".to_string(),
                        serde_json::json!(&cfg_block.function_node_id),
                    );

                    block_edges.push(GraphEdge {
                        id: edge_id,
                        kind: EdgeKind::Reads,
                        source_id: block_id_interned.clone(),
                        target_id: var_id_interned,
                        attrs,
                    });
                }

                block_edges
            })
            .collect();

        Ok(edges)
    }

    /// Map IR EdgeKind to Graph EdgeKind
    fn map_ir_edge_to_graph_edge(&self, ir_edge_kind: &EdgeKind) -> Result<EdgeKind, ()> {
        match ir_edge_kind {
            EdgeKind::Contains => Ok(EdgeKind::Contains),
            EdgeKind::Calls => Ok(EdgeKind::Calls),
            EdgeKind::Imports => Ok(EdgeKind::Imports),
            EdgeKind::Inherits => Ok(EdgeKind::Inherits),
            EdgeKind::Implements => Ok(EdgeKind::Implements),
            EdgeKind::References => Ok(EdgeKind::ReferencesSymbol),
            _ => Err(()), // Unsupported edge kind
        }
    }

    /// Map CFG EdgeKind to Graph EdgeKind
    fn map_cfg_edge_to_graph_edge(
        &self,
        cfg_edge_kind: &crate::features::flow_graph::domain::CFGEdgeKind,
    ) -> EdgeKind {
        use crate::features::flow_graph::domain::CFGEdgeKind;

        match cfg_edge_kind {
            CFGEdgeKind::Sequential | CFGEdgeKind::Normal => EdgeKind::CfgNext,
            CFGEdgeKind::TrueBranch | CFGEdgeKind::FalseBranch => EdgeKind::CfgBranch,
            CFGEdgeKind::LoopBack => EdgeKind::CfgLoop,
            CFGEdgeKind::LoopExit => EdgeKind::CfgNext, // Loop exit is sequential flow
            CFGEdgeKind::Exception => EdgeKind::CfgHandler,
            CFGEdgeKind::Finally => EdgeKind::Finally,
        }
    }
}

impl Default for EdgeConverter {
    fn default() -> Self {
        Self::new()
    }
}
