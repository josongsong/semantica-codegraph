pub mod application;
/// Concurrency Analysis Feature
///
/// Python async/await race condition and deadlock detection.
///
/// ## Features
/// - **Async Race Detection**: RacerD-inspired race condition detector
/// - **Deadlock Detection**: Wait-for graph based deadlock finder
/// - **Must-alias Support**: 100% proven verdicts via alias analysis
///
/// ## Architecture
/// - **Domain**: Models (AccessType, RaceSeverity, RaceCondition, etc.)
/// - **Infrastructure**: AsyncRaceDetector, DeadlockDetector
/// - **Application**: Concurrency analysis use cases
/// - **Ports**: ConcurrencyAnalyzerPort trait
///
/// ## Performance
/// - Target: < 100ms per async function
/// - Algorithm: O(statements + accesses² × shared_vars)
///
/// ## Academic References
/// - RacerD: Blackshear et al. (Facebook Infer, 2018)
/// - Tarjan's SCC: Tarjan (1972)
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
