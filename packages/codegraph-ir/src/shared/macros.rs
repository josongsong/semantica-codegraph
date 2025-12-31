//! Shared macros for the codebase
//!
//! Provides conditional tracing macros that are no-ops when trace feature is disabled

/// Conditional tracing macros - no-op when trace feature is disabled
#[cfg(not(feature = "trace"))]
#[macro_export]
macro_rules! debug {
    ($($arg:tt)*) => {};
}

#[cfg(not(feature = "trace"))]
#[macro_export]
macro_rules! info {
    ($($arg:tt)*) => {};
}

#[cfg(not(feature = "trace"))]
#[macro_export]
macro_rules! warn {
    ($($arg:tt)*) => {};
}

#[cfg(not(feature = "trace"))]
#[macro_export]
macro_rules! error {
    ($($arg:tt)*) => {};
}

#[cfg(not(feature = "trace"))]
#[macro_export]
macro_rules! trace {
    ($($arg:tt)*) => {};
}

// Re-export tracing macros when trace feature is enabled
#[cfg(feature = "trace")]
pub use tracing::{debug, error, info, trace, warn};
