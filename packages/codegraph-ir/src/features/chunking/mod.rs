//! Chunking feature module
//!
//! Provides chunk generation and management functionality.
//!
//! # Architecture (Hexagonal)
//!
//! ```text
//! External Callers (Pipeline, Adapters)
//!           ↓
//! application/ (UseCase) ← Entry Point
//!           ↓
//! domain/ (Entities)
//!           ↓
//! ports/ (Abstractions)
//!           ↑
//! infrastructure/ (Implementations)
//! ```
//!
//! # Usage
//!
//! ```ignore
//! use crate::features::chunking::application::{ChunkingUseCase, ChunkingUseCaseImpl, BuildChunksInput};
//!
//! let usecase = ChunkingUseCaseImpl::new();
//! let output = usecase.build_chunks(BuildChunksInput { ... });
//! ```

pub mod application; // UseCase layer (entry point for external callers)
pub mod domain;
pub mod infrastructure;
pub mod ports; // Dependency Inversion Principle (DIP)

// Re-export application layer (primary interface)
pub use application::{
    BuildChunksInput, BuildChunksOutput, ChunkingStats, ChunkingUseCase, ChunkingUseCaseImpl,
};

// Re-export domain types
pub use domain::{
    Chunk, ChunkHierarchy, ChunkId, ChunkIdContext, ChunkIdGenerator, ChunkKind, ChunkToGraph,
    ChunkToIR,
};

// Re-export infrastructure (for internal use only - prefer application layer)
#[doc(hidden)]
pub use infrastructure::{ChunkBuilder, FQNBuilder, TestDetector, Visibility, VisibilityExtractor};
