//! Code Clone Detection
//!
//! SOTA-level code clone detection implementing 4 types of clones:
//! - Type-1: Exact clones (identical code, whitespace/comments differ)
//! - Type-2: Renamed clones (parameters/variables renamed)
//! - Type-3: Gapped clones (statements added/removed/modified)
//! - Type-4: Semantic clones (different syntax, same behavior)
//!
//! # Hexagonal Architecture
//!
//! ```text
//! External (Pipeline/Adapters)
//!           ↓
//! application/ (UseCase - entry point)
//!           ↓
//! domain/ (clone types, similarity metrics)
//!           ↓
//! infrastructure/ (detectors)
//! ```
//!
//! # Usage
//!
//! ```ignore
//! use crate::features::clone_detection::application::{
//!     CloneDetectionUseCase, CloneDetectionUseCaseImpl, CloneDetectionInput,
//! };
//!
//! let usecase = CloneDetectionUseCaseImpl::new();
//! let output = usecase.detect_clones(CloneDetectionInput { fragments, config: None });
//! ```

pub mod application; // UseCase layer (entry point)
pub mod domain;
pub mod infrastructure;

// Re-export application layer (primary interface)
pub use application::{
    CloneDetectionInput, CloneDetectionOutput, CloneDetectionStats, CloneDetectionUseCase,
    CloneDetectionUseCaseImpl,
};

// Re-export domain types
pub use domain::{
    CloneDeduplicator, CloneMetrics, ClonePair, CloneType, CodeFragment, DetectionInfo,
    DetectorConfig, FragmentMetadata,
};

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::{
    CloneDetector, HybridCloneDetector, HybridDetectorStats, MultiLevelDetector, Type1Detector,
    Type2Detector, Type3Detector, Type4Detector,
};
