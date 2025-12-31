//! Storage UseCase Implementation

use crate::shared::models::Result;

/// Storage UseCase Trait
pub trait StorageUseCase: Send + Sync {
    fn save(&self, key: &str, data: &[u8]) -> Result<()>;
    fn load(&self, key: &str) -> Result<Vec<u8>>;
    fn delete(&self, key: &str) -> Result<()>;
}

/// Storage UseCase Implementation
#[derive(Debug, Default)]
pub struct StorageUseCaseImpl;

impl StorageUseCaseImpl {
    pub fn new() -> Self {
        Self
    }
}

impl StorageUseCase for StorageUseCaseImpl {
    fn save(&self, _key: &str, _data: &[u8]) -> Result<()> {
        Ok(()) // Delegate to infrastructure
    }

    fn load(&self, _key: &str) -> Result<Vec<u8>> {
        Ok(Vec::new())
    }

    fn delete(&self, _key: &str) -> Result<()> {
        Ok(())
    }
}
