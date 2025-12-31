//! Shared models

mod edge;
mod edge_context;
mod error;
pub mod expression;
mod node;
pub mod occurrence;
pub mod occurrence_arena;
mod span;
pub mod span_ref;
pub mod template;
pub mod type_entities; // L1: High-Level Expression IR (SOTA 2025)

pub use edge::{Edge, EdgeKind, EdgeMetadata};
pub use edge_context::{ControlFlowContext, ReadWriteContext};
pub use error::{CodegraphError, Result};
pub use node::{Node, NodeBuilder, NodeKind};
pub use occurrence::{Occurrence, OccurrenceGenerator, SymbolRole, SymbolRoles};
pub use occurrence_arena::{ArenaStats, InternerStats, OccurrenceArena};
pub use span::Span;

// Template parsing models (SOTA 2025)
pub use template::{
    CodeBlock, DocumentSection, DocumentType, EscapeMode, ParsedDocument, SectionType,
    SlotContextKind, TemplateDoc, TemplateElement, TemplateSlot,
};

// Expression IR models (L1: High-Level IR - SOTA 2025)
pub use expression::{
    AccessKind, BinOp, BoolOp, CollectionKind, CompOp, ExprId, ExprKind, Expression, ExpressionIR,
    HeapAccess, LiteralKind, SymbolId, TypeInfo, UnaryOp, VarId,
};

// Type-safe entity wrappers (preferred for new code)
pub use type_entities::{
    SignatureEntity as SignatureEntityWrapper, TypeEntity as TypeEntityWrapper,
    VariableEntity as VariableEntityWrapper,
};

// Re-export CFG types from flow_graph domain
pub use crate::features::flow_graph::domain::cfg::{CFGBlock, CFGEdge};

// Re-export serde_json::Value for convenience (used by Expression and Chunk attrs)
pub use serde_json::Value;

// ═══════════════════════════════════════════════════════════════════════════
// Type Aliases (backward compatibility - to be deprecated)
// ═══════════════════════════════════════════════════════════════════════════

/// Node identifier type alias
pub type NodeId = String;

// TODO: Migrate to TypeEntityWrapper, SignatureEntityWrapper, VariableEntityWrapper
// These type aliases will be deprecated in future versions
#[deprecated(note = "Use TypeEntityWrapper for type safety")]
pub type TypeEntity = Node;
#[deprecated(note = "Use SignatureEntityWrapper for type safety")]
pub type SignatureEntity = Node;
#[deprecated(note = "Use VariableEntityWrapper for type safety")]
pub type VariableEntity = Node;
