//! Ports - Interface definitions for File Watcher
//!
//! Domain-driven design: Pure trait definitions with no external dependencies

use std::path::PathBuf;
use std::time::Duration;

/// File change event types
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FileChangeEvent {
    Created(PathBuf),
    Modified(PathBuf),
    Deleted(PathBuf),
}

impl FileChangeEvent {
    pub fn path(&self) -> &PathBuf {
        match self {
            FileChangeEvent::Created(p) => p,
            FileChangeEvent::Modified(p) => p,
            FileChangeEvent::Deleted(p) => p,
        }
    }

    pub fn event_type(&self) -> &str {
        match self {
            FileChangeEvent::Created(_) => "created",
            FileChangeEvent::Modified(_) => "modified",
            FileChangeEvent::Deleted(_) => "deleted",
        }
    }
}

/// Configuration for file watcher
#[derive(Debug, Clone)]
pub struct WatchConfig {
    /// Root directory to watch
    pub root_path: PathBuf,

    /// File extensions to watch (e.g., ["py", "rs", "ts"])
    /// If empty, watches all files
    pub extensions: Vec<String>,

    /// Debounce delay - ignore duplicate events within this window
    pub debounce_duration: Duration,

    /// Patterns to ignore (glob patterns)
    pub ignore_patterns: Vec<String>,

    /// Enable recursive watching of subdirectories
    pub recursive: bool,
}

impl Default for WatchConfig {
    fn default() -> Self {
        Self {
            root_path: PathBuf::from("."),
            extensions: vec!["py".to_string(), "rs".to_string(), "ts".to_string()],
            debounce_duration: Duration::from_millis(100),
            ignore_patterns: vec![
                "**/node_modules/**".to_string(),
                "**/.git/**".to_string(),
                "**/target/**".to_string(),
                "**/__pycache__/**".to_string(),
            ],
            recursive: true,
        }
    }
}

/// Trait for handling file change events
pub trait FileEventHandler: Send + Sync {
    /// Called when a file change is detected (after debouncing)
    fn handle_event(&mut self, event: FileChangeEvent) -> Result<(), String>;

    /// Called when an error occurs in the watcher
    fn handle_error(&mut self, error: String);
}
