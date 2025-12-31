//! Node extractors - extract metadata from syntax nodes

pub mod call;
pub mod class;
pub mod fqn_resolver;
pub mod function;
pub mod identifier;
pub mod import; // RFC-062: Import extraction
pub mod multi_lang_variable; // Multi-language variable extraction
pub mod parameter;
pub mod variable; // SOTA: FQN resolution for built-ins and imports

pub use class::*;
pub use function::*;
pub use parameter::*;
pub use variable::*;
// Multi-language variable extraction (only export trait and factory, not VariableAssignment to avoid conflict)
pub use call::*;
pub use fqn_resolver::*;
pub use identifier::*;
pub use import::*; // RFC-062: Import extraction
pub use multi_lang_variable::{
    get_variable_extractor, GoVariableExtractor, JavaVariableExtractor, KotlinVariableExtractor,
    PythonVariableExtractor, RustVariableExtractor, TypeScriptVariableExtractor, VariableExtractor,
}; // SOTA: FQN resolution
