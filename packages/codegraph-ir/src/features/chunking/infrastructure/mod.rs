//! Chunking infrastructure components

pub mod chunk_builder;
pub mod chunk_store;
pub mod fqn_builder;
pub mod test_detector;
pub mod visibility_extractor; // P0-2: Partial chunk regeneration

pub use chunk_builder::ChunkBuilder;
pub use chunk_store::{ChunkStore, FileId};
pub use fqn_builder::FQNBuilder;
pub use test_detector::TestDetector;
pub use visibility_extractor::{Visibility, VisibilityExtractor}; // P0-2
