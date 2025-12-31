pub mod application;
/// Git History Analysis Feature
///
/// Git blame, churn, and co-change analysis.
///
/// ## Features
/// - **Blame Analysis**: Track authorship and modification history
/// - **Churn Analysis**: Identify volatile/risky files
/// - **Co-change Analysis**: Find logically coupled files
///
/// ## Note
/// This feature requires git command-line tool.
/// Performance depends on repository size.
pub mod domain;
pub mod infrastructure;

// Re-export application layer (primary interface)
pub use application::*;

// Re-export domain types
pub use domain::*;

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::*;
