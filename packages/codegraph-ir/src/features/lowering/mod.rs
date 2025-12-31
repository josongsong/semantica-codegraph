//! Progressive Lowering - L1 (Expression IR) → L2 (Node IR)
//!
//! SOTA Design (MLIR-inspired):
//! - Multi-level IR with progressive lowering
//! - Preserve high-level semantics in L1
//! - Lower to SSA-friendly Node IR in L2
//! - Enable optimization at each level
//!
//! ## Architecture
//!
//! ```text
//! L1: Expression IR (High-Level Semantic)
//!   - ExprKind::BinOp, ExprKind::Call, ExprKind::Attribute
//!   - Type info, heap access, symbol resolution
//!   ↓ Progressive Lowering
//! L2: Node IR (SSA-Friendly, Typed)
//!   - Node::BinaryOp, Node::FunctionCall, Node::FieldAccess
//!   - Explicit control flow, data flow
//!   ↓ Progressive Lowering
//! L3: Analysis IR (CFG, DFG, PDG)
//!   - CFGBlock, SSA ϕ-nodes, Heap summaries
//! ```
//!
//! ## Key Principles
//!
//! 1. **Semantic Preservation**: High-level info preserved in L1, available at L2
//! 2. **Progressive**: Each level more explicit (expression → statement → basic block)
//! 3. **Bidirectional**: Can go up (L2→L1) for debugging/visualization
//! 4. **Pluggable**: Each level can be optimized independently

pub mod application;
pub mod domain;
pub mod infrastructure;

// Re-export application layer
pub use application::{LoweringUseCase, LoweringUseCaseImpl};

pub use domain::ExpressionLowering;
// DEPRECATED: Old expression lowering (not used in current pipeline)
// pub use infrastructure::python_lowering::PythonExpressionLowering;
