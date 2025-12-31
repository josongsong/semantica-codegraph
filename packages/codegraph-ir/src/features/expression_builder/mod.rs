//! Expression Builder - AST → Expression IR (L1)
//!
//! SOTA Design:
//! - Visitor pattern for tree-sitter AST traversal
//! - Multi-language support (Python, TypeScript, Java, Kotlin, Rust, Go)
//! - Incremental ID generation
//! - Automatic parent/child relationship tracking
//! - Type inference integration (optional)
//!
//! ## Architecture
//!
//! ```text
//! tree-sitter AST
//!       ↓
//! ExpressionBuilder (Visitor)
//!       ↓
//! Expression IR (L1)
//! ```

pub mod application;
pub mod domain;
pub mod infrastructure;

// Re-export application layer
pub use application::{ExpressionBuilderUseCase, ExpressionBuilderUseCaseImpl};

pub use domain::ExpressionBuilderTrait;

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::python::PythonExpressionBuilder;
