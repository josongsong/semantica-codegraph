// Graph Builder - SOTA IR to Graph Conversion
//
// Converts Structural IR + Semantic IR → GraphDocument with SOTA optimizations:
//
// ## Performance Optimizations
// - Zero-copy arena allocation (typed-arena)
// - Parallel phase execution (Rayon)
// - String interning & deduplication
// - SIMD-accelerated index building
// - Incremental updates (change tracking)
//
// ## Architecture
// - Domain: Pure models (GraphNode, GraphEdge, GraphIndex)
// - Infrastructure: Builder implementation with 4 parallel phases
//
// ## Expected Performance
// - 10-20x faster than Python (949 LOC)
// - Target: <50ms for 10K nodes, <500ms for 100K nodes
// - Memory: 50% reduction via interning

pub mod application;
pub mod domain;
pub mod infrastructure;

// Re-export application layer
pub use application::{GraphBuilderUseCase, GraphBuilderUseCaseImpl};

// Re-exports
pub use domain::{GraphDocument, GraphEdge, GraphIndex, GraphNode};

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::GraphBuilder;
