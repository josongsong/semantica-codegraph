//! Clone Detection UseCase Implementation

use crate::features::clone_detection::domain::{ClonePair, CloneType, CodeFragment, DetectorConfig};
use crate::features::clone_detection::infrastructure::{
    HybridCloneDetector, HybridDetectorStats, MultiLevelDetector,
};

/// Input for clone detection
pub struct CloneDetectionInput<'a> {
    pub fragments: &'a [CodeFragment],
    pub config: Option<DetectorConfig>,
}

/// Output from clone detection
#[derive(Debug, Clone)]
pub struct CloneDetectionOutput {
    pub clone_pairs: Vec<ClonePair>,
    pub stats: CloneDetectionStats,
}

/// Clone detection statistics
#[derive(Debug, Clone, Default)]
pub struct CloneDetectionStats {
    pub total_fragments: usize,
    pub type1_clones: usize,
    pub type2_clones: usize,
    pub type3_clones: usize,
    pub type4_clones: usize,
    pub execution_time_ms: u64,
}

impl CloneDetectionStats {
    fn from_pairs(pairs: &[ClonePair], fragments_count: usize, elapsed_ms: u64) -> Self {
        let mut stats = Self {
            total_fragments: fragments_count,
            execution_time_ms: elapsed_ms,
            ..Default::default()
        };

        for pair in pairs {
            match pair.clone_type {
                CloneType::Type1 => stats.type1_clones += 1,
                CloneType::Type2 => stats.type2_clones += 1,
                CloneType::Type3 => stats.type3_clones += 1,
                CloneType::Type4 => stats.type4_clones += 1,
            }
        }

        stats
    }
}

/// Clone Detection UseCase Trait
pub trait CloneDetectionUseCase: Send + Sync {
    /// Detect clones in code fragments
    fn detect_clones(&self, input: CloneDetectionInput) -> CloneDetectionOutput;

    /// Detect clones using hybrid detector (faster)
    fn detect_clones_hybrid(&self, input: CloneDetectionInput) -> CloneDetectionOutput;
}

/// Clone Detection UseCase Implementation
#[derive(Debug, Default)]
pub struct CloneDetectionUseCaseImpl;

impl CloneDetectionUseCaseImpl {
    pub fn new() -> Self {
        Self
    }
}

impl CloneDetectionUseCase for CloneDetectionUseCaseImpl {
    fn detect_clones(&self, input: CloneDetectionInput) -> CloneDetectionOutput {
        let start = std::time::Instant::now();

        let mut detector = MultiLevelDetector::new();
        let clone_pairs = detector.detect_all(input.fragments);

        let elapsed = start.elapsed();
        let stats =
            CloneDetectionStats::from_pairs(&clone_pairs, input.fragments.len(), elapsed.as_millis() as u64);

        CloneDetectionOutput { clone_pairs, stats }
    }

    fn detect_clones_hybrid(&self, input: CloneDetectionInput) -> CloneDetectionOutput {
        let start = std::time::Instant::now();

        let mut detector = HybridCloneDetector::new();
        let clone_pairs = detector.detect_all(input.fragments);

        let elapsed = start.elapsed();
        let stats =
            CloneDetectionStats::from_pairs(&clone_pairs, input.fragments.len(), elapsed.as_millis() as u64);

        CloneDetectionOutput { clone_pairs, stats }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_clone_usecase_creation() {
        let _usecase = CloneDetectionUseCaseImpl::new();
    }

    #[test]
    fn test_empty_fragments() {
        let usecase = CloneDetectionUseCaseImpl::new();
        let input = CloneDetectionInput {
            fragments: &[],
            config: None,
        };

        let output = usecase.detect_clones(input);

        assert_eq!(output.clone_pairs.len(), 0);
        assert_eq!(output.stats.total_fragments, 0);
    }
}
