pub mod application;
/// Effect Analysis Feature
///
/// Purity tracking and side effect inference.
///
/// ## Features
/// - **Local Effect Analysis**: Detect effects from source code
/// - **Interprocedural Propagation**: Callee → Caller propagation
/// - **Trusted Library DB**: Pre-defined effects for common libraries
/// - **Unknown Handling**: Pessimistic defaults for unknown calls
///
/// ## Effect Types
/// - Pure, I/O, State mutations, Database, Network, Logging, etc.
///
/// ## Performance
/// - Target: < 50ms per function
/// - Algorithm: Local analysis + interprocedural propagation
///
/// ## Academic References
/// - Effect Systems: Lucassen & Gifford (1988)
/// - Type and Effect Systems: Nielson & Nielson (1999)
pub mod domain;
pub mod infrastructure;
pub mod ports;

// Re-export application layer (primary interface)
pub use application::*;

// Re-export domain types
pub use domain::*;

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::*;

pub use ports::*;
