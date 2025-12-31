//! Clone Detection Domain Models
//!
//! Pure business logic layer for code clone detection.
//! Contains type definitions, metrics, and algorithms with zero external dependencies.
//!
//! # Clone Types (Bellon et al. 2007)
//!
//! - **Type-1**: Exact clones (whitespace/comments differ)
//! - **Type-2**: Renamed clones (identifiers/types/literals differ)
//! - **Type-3**: Gapped clones (statements added/removed/modified)
//! - **Type-4**: Semantic clones (different syntax, same behavior)
//!
//! # Architecture
//!
//! ```text
//! domain/
//! ├── clone_type.rs       # Clone type classification
//! ├── code_fragment.rs    # Code fragment representation
//! ├── clone_pair.rs       # Clone pair with metrics
//! ├── similarity.rs       # Similarity algorithms
//! ├── deduplicator.rs     # Duplicate removal (O(n) performance)
//! └── detector_config.rs  # Configuration for detectors
//! ```

pub mod clone_pair;
pub mod clone_type;
pub mod code_fragment;
pub mod deduplicator;
pub mod detector_config;
pub mod similarity;

// Re-exports for convenience
pub use clone_pair::{CloneMetrics, ClonePair, DetectionInfo};
pub use clone_type::CloneType;
pub use code_fragment::{CodeFragment, FragmentMetadata};
pub use deduplicator::CloneDeduplicator;
pub use detector_config::DetectorConfig;
pub use similarity::{
    containment_coefficient, cosine_similarity, dice_coefficient, jaccard_similarity,
    jaccard_similarity_vec, lcs_length, lcs_similarity, levenshtein_distance,
    normalized_levenshtein_similarity, overlap_coefficient, token_cosine_similarity,
};
