//! Occurrence types for IR
//!
//! SCIP-compatible occurrence tracking.
//! Generated alongside nodes/edges in L1 for performance.

use super::edge::{Edge, EdgeKind};
use super::node::{Node, NodeKind};
use super::Span;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Symbol role bitflags (SCIP-compatible)
/// Using u8 for efficient bit operations
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SymbolRole {
    None = 0,
    Definition = 1,
    Import = 2,
    WriteAccess = 4,
    ReadAccess = 8,
    Generated = 16,
    Test = 32,
    ForwardDefinition = 64,
}

impl SymbolRole {
    /// Convert to bitflag value
    pub fn value(&self) -> u8 {
        *self as u8
    }
}

/// Combined roles as bitflags
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
pub struct SymbolRoles(pub u8);

impl SymbolRoles {
    pub fn new() -> Self {
        Self(0)
    }

    pub fn definition() -> Self {
        Self(SymbolRole::Definition as u8)
    }

    pub fn import() -> Self {
        Self(SymbolRole::Import as u8)
    }

    pub fn read_access() -> Self {
        Self(SymbolRole::ReadAccess as u8)
    }

    pub fn write_access() -> Self {
        Self(SymbolRole::WriteAccess as u8)
    }

    pub fn add(&mut self, role: SymbolRole) {
        self.0 |= role as u8;
    }

    pub fn has(&self, role: SymbolRole) -> bool {
        self.0 & (role as u8) != 0
    }

    pub fn is_definition(&self) -> bool {
        self.has(SymbolRole::Definition)
    }

    pub fn is_reference(&self) -> bool {
        self.has(SymbolRole::ReadAccess)
    }

    pub fn is_write(&self) -> bool {
        self.has(SymbolRole::WriteAccess)
    }
}

/// SCIP-compatible Occurrence
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Occurrence {
    /// Unique occurrence ID
    pub id: String,

    /// Symbol ID (node.id for definitions, edge.target_id for references)
    pub symbol_id: String,

    /// Source location
    pub span: Span,

    /// Role bitflags
    pub roles: u8,

    /// File path
    pub file_path: String,

    /// Importance score (0.0 - 1.0)
    pub importance_score: f32,

    /// Parent symbol ID (for scope context)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_symbol_id: Option<String>,

    /// Syntax kind (e.g., "call_expression", "assignment")
    #[serde(skip_serializing_if = "Option::is_none")]
    pub syntax_kind: Option<String>,
}

impl Occurrence {
    /// Create definition occurrence from Node
    pub fn from_node(node: &Node, occ_counter: &mut u64) -> Option<Self> {
        // Only create occurrences for symbol nodes
        if !Self::is_symbol_kind(&node.kind) {
            return None;
        }

        *occ_counter += 1;
        let id = format!("occ:def:{}:{}", node.id, occ_counter);

        let importance = Self::estimate_importance(node);

        Some(Self {
            id,
            symbol_id: node.id.clone(),
            span: node.span.clone(),
            roles: SymbolRole::Definition as u8,
            file_path: node.file_path.clone(),
            importance_score: importance,
            parent_symbol_id: node.parent_id.clone(),
            syntax_kind: Some(node.kind.as_str().to_string()),
        })
    }

    /// Create reference occurrence from Edge
    pub fn from_edge(edge: &Edge, source_node: &Node, occ_counter: &mut u64) -> Option<Self> {
        let roles = Self::edge_kind_to_roles(&edge.kind)?;

        *occ_counter += 1;
        let ref_type = if roles & (SymbolRole::Import as u8) != 0 {
            "import"
        } else if roles & (SymbolRole::WriteAccess as u8) != 0 {
            "write"
        } else {
            "ref"
        };

        let id = format!("occ:{}:{}:{}", ref_type, edge.source_id, occ_counter);

        // Use edge span if available, otherwise use source node span
        let span = edge
            .span
            .clone()
            .unwrap_or_else(|| source_node.span.clone());

        Some(Self {
            id,
            symbol_id: edge.target_id.clone(),
            span,
            roles,
            file_path: source_node.file_path.clone(),
            importance_score: 0.5, // References have base importance
            parent_symbol_id: Some(edge.source_id.clone()),
            syntax_kind: Some(edge.kind.as_str().to_string()),
        })
    }

    /// Check if node kind should have occurrence
    fn is_symbol_kind(kind: &NodeKind) -> bool {
        matches!(
            kind,
            NodeKind::Class
                | NodeKind::Function
                | NodeKind::Method
                | NodeKind::Variable
                | NodeKind::Parameter
                | NodeKind::Field
                | NodeKind::Lambda
        )
    }

    /// Map EdgeKind to SymbolRole
    fn edge_kind_to_roles(kind: &EdgeKind) -> Option<u8> {
        match kind {
            // Read access patterns
            EdgeKind::Calls
            | EdgeKind::Invokes
            | EdgeKind::Reads
            | EdgeKind::References
            | EdgeKind::Inherits
            | EdgeKind::Implements
            | EdgeKind::Extends
            | EdgeKind::ImplementsTrait
            | EdgeKind::BoundedBy
            | EdgeKind::TypeArgumentOf
            | EdgeKind::ChannelReceive
            | EdgeKind::Overrides
            | EdgeKind::DelegatesTo
            | EdgeKind::DefUse => Some(SymbolRole::ReadAccess as u8),
            // Write access patterns
            EdgeKind::Writes | EdgeKind::ChannelSend | EdgeKind::Captures => {
                Some(SymbolRole::WriteAccess as u8)
            }
            // Import patterns
            EdgeKind::Imports => Some(SymbolRole::Import as u8),
            // Structural edges don't create occurrences
            EdgeKind::Contains | EdgeKind::Defines => None,
            // Data flow edges - informational, no occurrence
            EdgeKind::DataFlow
            | EdgeKind::ControlFlow
            | EdgeKind::TrueBranch
            | EdgeKind::FalseBranch
            | EdgeKind::TypeAnnotation => None,
            // Other edges that may or may not create occurrences
            EdgeKind::AnnotatedWith
            | EdgeKind::DecoratedWith
            | EdgeKind::Throws
            | EdgeKind::Catches
            | EdgeKind::Shadows
            | EdgeKind::Instantiates
            | EdgeKind::BorrowsFrom
            | EdgeKind::LifetimeOf
            | EdgeKind::MacroExpands
            | EdgeKind::SuspendsTo
            | EdgeKind::SpawnsGoroutine
            | EdgeKind::Finally => None,
            // CFG-specific edges
            EdgeKind::CfgNext | EdgeKind::CfgBranch | EdgeKind::CfgLoop | EdgeKind::CfgHandler => {
                None
            }
            // Symbol reference edges
            EdgeKind::ReferencesType | EdgeKind::ReferencesSymbol => {
                Some(SymbolRole::ReadAccess as u8)
            }
            // Web/Framework edges
            EdgeKind::Decorates
            | EdgeKind::RouteHandler
            | EdgeKind::HandlesRequest
            | EdgeKind::UsesRepository => None,
        }
    }

    /// Estimate importance score based on node properties
    fn estimate_importance(node: &Node) -> f32 {
        let mut score = 0.5f32;

        // Public API bonus (+0.2)
        if let Some(ref name) = node.name {
            if !name.starts_with('_') || name.starts_with("__") {
                score += 0.2;
            }
        }

        // Docstring bonus (+0.1)
        if node.docstring.is_some() {
            score += 0.1;
        }

        // Top-level bonus (+0.1)
        if node.parent_id.is_none() {
            score += 0.1;
        }

        // Kind bonus
        score += match node.kind {
            NodeKind::Class => 0.1,
            NodeKind::Function | NodeKind::Method => 0.05,
            _ => 0.0,
        };

        score.min(1.0)
    }
}

/// Occurrence generator for a single file
#[derive(Debug, Default)]
pub struct OccurrenceGenerator {
    counter: u64,
}

impl OccurrenceGenerator {
    pub fn new() -> Self {
        Self { counter: 0 }
    }

    /// Generate all occurrences for nodes and edges
    pub fn generate(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<Occurrence> {
        let mut occurrences = Vec::with_capacity(nodes.len() + edges.len());

        // Build node index for edge lookup
        let node_by_id: HashMap<&str, &Node> = nodes.iter().map(|n| (n.id.as_str(), n)).collect();

        // Definition occurrences from nodes
        for node in nodes {
            if let Some(occ) = Occurrence::from_node(node, &mut self.counter) {
                occurrences.push(occ);
            }
        }

        // Reference occurrences from edges
        for edge in edges {
            if let Some(source_node) = node_by_id.get(edge.source_id.as_str()) {
                if let Some(occ) = Occurrence::from_edge(edge, source_node, &mut self.counter) {
                    occurrences.push(occ);
                }
            }
        }

        occurrences
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_symbol_roles() {
        let mut roles = SymbolRoles::new();
        assert!(!roles.is_definition());

        roles.add(SymbolRole::Definition);
        assert!(roles.is_definition());

        roles.add(SymbolRole::Test);
        assert!(roles.has(SymbolRole::Test));
        assert_eq!(roles.0, 0b00100001); // Definition | Test
    }

    #[test]
    fn test_occurrence_from_node() {
        let node = Node::new(
            "node:1".to_string(),
            NodeKind::Function,
            "foo".to_string(),
            "test.py".to_string(),
            Span::new(1, 0, 5, 0),
        );

        let mut counter = 0u64;
        let occ = Occurrence::from_node(&node, &mut counter).unwrap();

        assert!(occ.id.starts_with("occ:def:"));
        assert_eq!(occ.symbol_id, "node:1");
        assert_eq!(occ.roles, SymbolRole::Definition as u8);
    }
}
