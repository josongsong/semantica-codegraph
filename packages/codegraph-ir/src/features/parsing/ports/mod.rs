//! Parsing ports (interfaces)

mod language_plugin;
mod parser;

pub use language_plugin::{
    ControlFlowType, // ✅ Export ControlFlowType enum
    ExtractionContext,
    ExtractionResult,
    IdGenerator,
    LanguageId,
    LanguagePlugin,
    LanguageRegistry,
    NodeKindMapper,
    SpanExt,
};
pub use parser::Parser;
