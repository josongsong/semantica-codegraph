//! Pipeline Preprocessors
//!
//! SOTA 2025: Preprocessing stages before IR build
//!
//! Preprocessors handle file-specific parsing that Python does better:
//! - Template parsing (JSX/Vue via tree-sitter + custom logic)
//! - Document parsing (Markdown/Notebook via specialized libraries)
//! - Syntax highlighting (Pygments integration)

pub mod template_parser;
pub use template_parser::get_template_preprocessor;
pub use template_parser::TemplatePreprocessor;
