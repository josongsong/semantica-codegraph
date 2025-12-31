//! Report generation
//!
//! Generates benchmark reports in multiple formats: JSON, Markdown, Terminal.

pub mod json;
pub mod markdown;
pub mod terminal;

pub use json::JsonReporter;
pub use markdown::MarkdownReporter;
pub use terminal::TerminalReporter;
