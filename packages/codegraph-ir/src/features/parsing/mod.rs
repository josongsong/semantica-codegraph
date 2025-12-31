//! Parsing Feature (L1)
//!
//! Responsible for AST parsing and syntax tree traversal.
//!
//! ## Structure
//! - `domain/` - ParsedTree, SyntaxNode models
//! - `ports/` - Parser trait, LanguagePlugin trait
//! - `application/` - ParseFileUseCase
//! - `infrastructure/` - TreeSitterParser, Extractors
//! - `plugins/` - Language-specific plugins (Python, Java, TypeScript, etc.)

pub mod application;
pub mod domain;
pub mod infrastructure;
pub mod plugins;
pub mod ports;

// Re-exports
pub use domain::ParsedTree;

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::TreeSitterParser;
pub use plugins::{
    create_full_registry, create_registry, GoPlugin, JavaPlugin, KotlinPlugin, PythonPlugin,
    RustPlugin, TypeScriptPlugin,
};
pub use ports::{
    ExtractionContext, ExtractionResult, IdGenerator, LanguageId, LanguagePlugin, LanguageRegistry,
    Parser, SpanExt,
};
