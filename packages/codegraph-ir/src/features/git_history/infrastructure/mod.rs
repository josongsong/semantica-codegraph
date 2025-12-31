pub mod error;
/// Git History Infrastructure
pub mod git_executor;

pub use error::*;
pub use git_executor::*;

// Note: Full analyzers (Blame, Churn, CoChange) would be here
// Simplified for initial implementation
