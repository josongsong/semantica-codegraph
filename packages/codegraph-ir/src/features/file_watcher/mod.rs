//! RFC-073: File Watcher - SOTA Rust-native file system monitoring
//!
//! Provides cross-platform file system event detection with:
//! - Zero-copy performance (10-100x faster than Python watchdog)
//! - Debouncing and duplicate event filtering
//! - Integration with TransactionalGraphIndex
//! - Tree-sitter AST parsing on file changes
//! - Concurrent processing with Rayon

pub mod application;
pub mod infrastructure;
pub mod ports;

// Re-export application layer (primary interface)
pub use application::{FileWatcherUseCase, FileWatcherUseCaseImpl};

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::FileWatcher;

pub use ports::{FileChangeEvent, FileEventHandler, WatchConfig};
