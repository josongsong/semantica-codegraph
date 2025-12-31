//! Infrastructure - External dependency implementations
//!
//! Uses `notify` crate for cross-platform file system events

mod file_watcher;

#[cfg(test)]
mod file_watcher_test;

#[cfg(test)]
mod integration_test;

#[cfg(test)]
mod e2e_test_simple;

pub use file_watcher::FileWatcher;
