//! Indexing UseCase

/// Indexing UseCase Trait
pub trait IndexingUseCase: Send + Sync {
    fn index_file(&self, file_path: &str) -> IndexResult;
    fn index_directory(&self, dir_path: &str) -> IndexResult;
}

#[derive(Debug, Clone, Default)]
pub struct IndexResult {
    pub indexed_files: usize,
    pub total_symbols: usize,
}

/// Indexing UseCase Implementation
#[derive(Debug, Default)]
pub struct IndexingUseCaseImpl;

impl IndexingUseCaseImpl {
    pub fn new() -> Self {
        Self
    }
}

impl IndexingUseCase for IndexingUseCaseImpl {
    fn index_file(&self, _file_path: &str) -> IndexResult {
        IndexResult::default()
    }

    fn index_directory(&self, _dir_path: &str) -> IndexResult {
        IndexResult::default()
    }
}
