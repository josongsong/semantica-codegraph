// Virtual Layer: Per-agent isolated editing spaces
//
// # Non-Negotiable Contract 3-4 (P2-9)
// - Overlay + merge-on-read만 허용
// - Snapshot clone 금지

use crate::features::query_engine::infrastructure::{ChangeOp, Snapshot, TxnId};

/// P2-9: Virtual layer with overlay pattern (NO full clone)
///
/// # Non-Negotiable Contract 3-4
/// Overlay + merge-on-read만 허용
/// Snapshot clone 금지
///
/// Memory usage = O(pending_changes) not O(total_nodes)
#[derive(Debug, Clone)]
pub struct VirtualLayer {
    pub agent_id: String,
    pub base_txn: TxnId,
    pub pending_changes: Vec<ChangeOp>,
    // P2-9: IMMUTABLE - NO snapshot clone field allowed
    // PROHIBITED: pub virtual_index: HashMap<String, Node>
}

impl VirtualLayer {
    pub fn new(agent_id: String, base_txn: TxnId) -> Self {
        Self {
            agent_id,
            base_txn,
            pending_changes: Vec::new(),
            // No clone! Memory usage = O(pending_changes) not O(total_nodes)
        }
    }

    /// Add change to pending overlay
    pub fn add_change(&mut self, change: ChangeOp) {
        self.pending_changes.push(change);
    }

    /// Merge-on-Read: Combine base snapshot + pending changes
    ///
    /// # P2-9: Overlay Pattern
    /// Reads base snapshot on-demand (not stored in VirtualLayer)
    /// Applies pending changes as overlay
    pub fn merge(&self, base_snapshot: Snapshot) -> Snapshot {
        let mut merged = base_snapshot;

        // Apply pending changes (overlay)
        for change in &self.pending_changes {
            match change {
                ChangeOp::AddNode(node) => {
                    merged.nodes.insert(node.id.clone(), node.clone());
                }
                ChangeOp::RemoveNode(id) => {
                    merged.nodes.remove(id);
                }
                ChangeOp::UpdateNode(node) => {
                    merged.nodes.insert(node.id.clone(), node.clone());
                }
                ChangeOp::AddEdge(edge) => {
                    // Edges is a Vec, just push directly
                    merged.edges.push(edge.clone());
                }
                ChangeOp::RemoveEdge(src, tgt) => {
                    // Remove edge from Vec by filtering
                    merged
                        .edges
                        .retain(|e| !(e.source_id == *src && e.target_id == *tgt));
                }
            }
        }

        merged
    }

    /// Get pending change count
    pub fn change_count(&self) -> usize {
        self.pending_changes.len()
    }

    /// Clear all pending changes
    pub fn clear(&mut self) {
        self.pending_changes.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{Node, NodeKind, Span};

    #[test]
    fn test_virtual_layer_overlay_pattern() {
        // Create virtual layer
        let mut layer = VirtualLayer::new("agent1".to_string(), 42);

        // Add changes
        layer.add_change(ChangeOp::AddNode(create_test_node("node1")));
        layer.add_change(ChangeOp::AddNode(create_test_node("node2")));

        assert_eq!(layer.change_count(), 2);

        // Merge should not store base snapshot
        let base = Snapshot::default();
        let merged = layer.merge(base.clone());

        // Merged should have 2 nodes
        assert_eq!(merged.nodes.len(), 2);

        // Original base unchanged
        assert_eq!(base.nodes.len(), 0);
    }

    #[test]
    fn test_virtual_layer_memory_efficiency() {
        let layer = VirtualLayer::new("agent1".to_string(), 42);

        // VirtualLayer should NOT have a snapshot clone field
        // Memory usage = O(pending_changes) only
        assert_eq!(layer.change_count(), 0);
        assert_eq!(
            std::mem::size_of::<VirtualLayer>(),
            std::mem::size_of::<String>()
                + std::mem::size_of::<TxnId>()
                + std::mem::size_of::<Vec<ChangeOp>>()
        );
    }

    fn create_test_node(id: &str) -> Node {
        Node {
            id: id.to_string(),
            kind: NodeKind::Variable,
            fqn: format!("test.{}", id),
            file_path: "test.py".to_string(),
            span: Span::new(1, 1, 1, 10),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some(id.to_string()),
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }
    }
}
