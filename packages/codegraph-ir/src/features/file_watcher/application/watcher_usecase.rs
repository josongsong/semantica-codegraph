//! File Watcher UseCase

use std::path::PathBuf;

/// File Watcher UseCase Trait
pub trait FileWatcherUseCase: Send + Sync {
    fn watch(&self, path: &PathBuf) -> Result<(), String>;
    fn unwatch(&self, path: &PathBuf) -> Result<(), String>;
}

/// File Watcher UseCase Implementation
#[derive(Debug, Default)]
pub struct FileWatcherUseCaseImpl;

impl FileWatcherUseCaseImpl {
    pub fn new() -> Self {
        Self
    }
}

impl FileWatcherUseCase for FileWatcherUseCaseImpl {
    fn watch(&self, _path: &PathBuf) -> Result<(), String> {
        Ok(())
    }

    fn unwatch(&self, _path: &PathBuf) -> Result<(), String> {
        Ok(())
    }
}
