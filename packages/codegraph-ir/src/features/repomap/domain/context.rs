//! Context Provider Domain - Pure business logic for context sources
//!
//! Defines the abstraction for context providers that feed into Personalized PageRank.
//! Context sources include: IDE selection, query terms, git changes, and history.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Context type - where the context comes from
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ContextType {
    /// IDE context (cursor position, open files, selected text)
    Ide,
    /// User query (search terms, semantic search results)
    Query,
    /// Git changes (staged, unstaged, recent commits)
    GitChanges,
    /// History (recently viewed/edited files)
    History,
}

/// Context item with source metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextItem {
    /// Node ID in the RepoMap
    pub node_id: String,

    /// Context type
    pub context_type: ContextType,

    /// Relevance weight [0.0, 1.0]
    /// Higher = more relevant to current context
    pub weight: f64,

    /// Source metadata (file path, line number, etc.)
    pub metadata: HashMap<String, String>,
}

impl ContextItem {
    /// Create a new context item
    pub fn new(node_id: String, context_type: ContextType, weight: f64) -> Self {
        Self {
            node_id,
            context_type,
            weight: weight.clamp(0.0, 1.0),
            metadata: HashMap::new(),
        }
    }

    /// Add metadata
    pub fn with_metadata(mut self, key: String, value: String) -> Self {
        self.metadata.insert(key, value);
        self
    }
}

/// Context set - aggregated from multiple providers
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextSet {
    /// All context items
    pub items: Vec<ContextItem>,

    /// Weights for each context type (for fusion)
    pub type_weights: HashMap<ContextType, f64>,
}

impl ContextSet {
    /// Create empty context set
    pub fn new() -> Self {
        let mut type_weights = HashMap::new();
        type_weights.insert(ContextType::Ide, 0.4);
        type_weights.insert(ContextType::Query, 0.3);
        type_weights.insert(ContextType::GitChanges, 0.2);
        type_weights.insert(ContextType::History, 0.1);

        Self {
            items: Vec::new(),
            type_weights,
        }
    }

    /// Add context item
    pub fn add_item(&mut self, item: ContextItem) {
        self.items.push(item);
    }

    /// Set weight for context type
    pub fn set_type_weight(&mut self, context_type: ContextType, weight: f64) {
        self.type_weights
            .insert(context_type, weight.clamp(0.0, 1.0));
    }

    /// Get combined weight for a node (across all context types)
    ///
    /// Returns weighted sum of all context items for this node.
    /// Uses type_weights for fusion.
    pub fn get_combined_weight(&self, node_id: &str) -> f64 {
        let mut total_weight = 0.0;

        for item in &self.items {
            if item.node_id == node_id {
                let type_weight = self
                    .type_weights
                    .get(&item.context_type)
                    .copied()
                    .unwrap_or(1.0);
                total_weight += item.weight * type_weight;
            }
        }

        total_weight.clamp(0.0, 1.0)
    }

    /// Get all unique node IDs in context
    pub fn get_context_nodes(&self) -> Vec<String> {
        let mut nodes: Vec<String> = self.items.iter().map(|item| item.node_id.clone()).collect();
        nodes.sort();
        nodes.dedup();
        nodes
    }

    /// Normalize weights to sum to 1.0
    pub fn normalize(&mut self) {
        let total: f64 = self.items.iter().map(|item| item.weight).sum();
        if total > 0.0 {
            for item in &mut self.items {
                item.weight /= total;
            }
        }
    }
}

impl Default for ContextSet {
    fn default() -> Self {
        Self::new()
    }
}

/// Port (interface) for context providers
///
/// Implementations provide context from different sources:
/// - IDE: cursor position, open files, selected text
/// - Query: search results, semantic similarity
/// - Git: staged/unstaged changes, recent commits
/// - History: recently viewed/edited files
pub trait ContextProvider: Send + Sync {
    /// Get context items from this provider
    fn get_context(&self) -> Result<Vec<ContextItem>, String>;

    /// Get context type
    fn context_type(&self) -> ContextType;

    /// Provider name (for debugging)
    fn name(&self) -> &str;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_context_item_creation() {
        let item = ContextItem::new("node1".to_string(), ContextType::Ide, 0.8);
        assert_eq!(item.node_id, "node1");
        assert_eq!(item.context_type, ContextType::Ide);
        assert_eq!(item.weight, 0.8);
        assert!(item.metadata.is_empty());
    }

    #[test]
    fn test_context_item_weight_clamping() {
        let item1 = ContextItem::new("node1".to_string(), ContextType::Ide, 1.5);
        assert_eq!(item1.weight, 1.0); // Clamped to max

        let item2 = ContextItem::new("node2".to_string(), ContextType::Query, -0.5);
        assert_eq!(item2.weight, 0.0); // Clamped to min
    }

    #[test]
    fn test_context_item_with_metadata() {
        let item = ContextItem::new("node1".to_string(), ContextType::Ide, 0.8)
            .with_metadata("file".to_string(), "main.rs".to_string())
            .with_metadata("line".to_string(), "42".to_string());

        assert_eq!(item.metadata.get("file"), Some(&"main.rs".to_string()));
        assert_eq!(item.metadata.get("line"), Some(&"42".to_string()));
    }

    #[test]
    fn test_context_set_default_weights() {
        let ctx = ContextSet::new();
        assert_eq!(ctx.type_weights.get(&ContextType::Ide), Some(&0.4));
        assert_eq!(ctx.type_weights.get(&ContextType::Query), Some(&0.3));
        assert_eq!(ctx.type_weights.get(&ContextType::GitChanges), Some(&0.2));
        assert_eq!(ctx.type_weights.get(&ContextType::History), Some(&0.1));
    }

    #[test]
    fn test_context_set_add_item() {
        let mut ctx = ContextSet::new();
        ctx.add_item(ContextItem::new("node1".to_string(), ContextType::Ide, 0.8));
        ctx.add_item(ContextItem::new(
            "node2".to_string(),
            ContextType::Query,
            0.6,
        ));

        assert_eq!(ctx.items.len(), 2);
    }

    #[test]
    fn test_context_set_combined_weight() {
        let mut ctx = ContextSet::new();

        // Node1: IDE (0.8) + Query (0.6)
        ctx.add_item(ContextItem::new("node1".to_string(), ContextType::Ide, 0.8));
        ctx.add_item(ContextItem::new(
            "node1".to_string(),
            ContextType::Query,
            0.6,
        ));

        // Node2: GitChanges (1.0)
        ctx.add_item(ContextItem::new(
            "node2".to_string(),
            ContextType::GitChanges,
            1.0,
        ));

        // Combined weight for node1: (0.8 * 0.4) + (0.6 * 0.3) = 0.32 + 0.18 = 0.50
        let weight1 = ctx.get_combined_weight("node1");
        assert!((weight1 - 0.50).abs() < 0.01);

        // Combined weight for node2: (1.0 * 0.2) = 0.20
        let weight2 = ctx.get_combined_weight("node2");
        assert!((weight2 - 0.20).abs() < 0.01);
    }

    #[test]
    fn test_context_set_get_context_nodes() {
        let mut ctx = ContextSet::new();
        ctx.add_item(ContextItem::new("node1".to_string(), ContextType::Ide, 0.8));
        ctx.add_item(ContextItem::new(
            "node2".to_string(),
            ContextType::Query,
            0.6,
        ));
        ctx.add_item(ContextItem::new(
            "node1".to_string(),
            ContextType::GitChanges,
            0.5,
        ));

        let nodes = ctx.get_context_nodes();
        assert_eq!(nodes.len(), 2); // Deduplicated
        assert!(nodes.contains(&"node1".to_string()));
        assert!(nodes.contains(&"node2".to_string()));
    }

    #[test]
    fn test_context_set_normalize() {
        let mut ctx = ContextSet::new();
        ctx.add_item(ContextItem::new("node1".to_string(), ContextType::Ide, 0.5));
        ctx.add_item(ContextItem::new(
            "node2".to_string(),
            ContextType::Query,
            0.3,
        ));
        ctx.add_item(ContextItem::new(
            "node3".to_string(),
            ContextType::GitChanges,
            0.2,
        ));

        ctx.normalize();

        let total: f64 = ctx.items.iter().map(|item| item.weight).sum();
        assert!((total - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_context_set_set_type_weight() {
        let mut ctx = ContextSet::new();
        ctx.set_type_weight(ContextType::Ide, 0.7);
        ctx.set_type_weight(ContextType::Query, 0.3);

        assert_eq!(ctx.type_weights.get(&ContextType::Ide), Some(&0.7));
        assert_eq!(ctx.type_weights.get(&ContextType::Query), Some(&0.3));
    }

    #[test]
    fn test_context_set_empty_weight() {
        let ctx = ContextSet::new();
        let weight = ctx.get_combined_weight("nonexistent");
        assert_eq!(weight, 0.0);
    }
}
