//! Chunking Ports - Abstractions for external dependencies
//!
//! Implements Dependency Inversion Principle (DIP):
//! - Domain depends on abstractions (ports), not concrete implementations
//! - Infrastructure implements ports
//! - Easy to swap implementations without changing domain logic

pub mod chunk_repository;

pub use chunk_repository::{ChunkDto, ChunkId, ChunkRepository};

#[cfg(test)]
pub use chunk_repository::MockChunkRepository;
