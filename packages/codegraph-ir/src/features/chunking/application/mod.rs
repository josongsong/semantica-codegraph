//! Chunking Application Layer (UseCase)
//!
//! This layer implements the Hexagonal Architecture pattern:
//! - External callers (Pipeline, Adapters) → Application (UseCase) → Domain/Infrastructure
//! - Never bypass this layer to call infrastructure directly
//!
//! # Key UseCases
//! - `ChunkingUseCase`: Main entry point for all chunking operations
//! - `BuildChunksUseCase`: Build chunk hierarchy from IR nodes

mod chunking_usecase;

pub use chunking_usecase::{
    BuildChunksInput, BuildChunksOutput, ChunkingStats, ChunkingUseCase, ChunkingUseCaseImpl,
};
