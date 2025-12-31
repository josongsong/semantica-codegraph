//! Chunking domain models

pub mod chunk;
pub mod chunk_id_generator;
pub mod chunk_kind;

pub use chunk::{Chunk, ChunkHierarchy, ChunkId, ChunkToGraph, ChunkToIR};
pub use chunk_id_generator::{ChunkIdContext, ChunkIdGenerator};
pub use chunk_kind::ChunkKind;
