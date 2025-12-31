//! Clone Detector Configuration
//!
//! Centralized configuration for all clone detection types.
//! Ensures consistent thresholds and parameters across detectors.

use super::CloneType;

/// Clone detection configuration
///
/// Provides consistent configuration for all detector types.
/// Each detector can override defaults through this struct.
///
/// # Example
/// ```
/// use codegraph_ir::features::clone_detection::domain::DetectorConfig;
///
/// // Type-1 detector config
/// let type1_config = DetectorConfig::for_type1();
/// assert_eq!(type1_config.min_tokens, 20);
///
/// // Custom config
/// let custom_config = DetectorConfig::new(15, 2, 0.85);
/// ```
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DetectorConfig {
    /// Minimum token count to consider a fragment
    pub min_tokens: usize,

    /// Minimum lines of code to consider a fragment
    pub min_loc: usize,

    /// Similarity threshold (0.0-1.0)
    pub similarity_threshold: f64,
}

impl DetectorConfig {
    /// Create new configuration
    pub fn new(min_tokens: usize, min_loc: usize, similarity_threshold: f64) -> Self {
        assert!(
            (0.0..=1.0).contains(&similarity_threshold),
            "Similarity threshold must be between 0.0 and 1.0"
        );

        Self {
            min_tokens,
            min_loc,
            similarity_threshold,
        }
    }

    /// Default configuration for Type-1 (Exact) clones
    ///
    /// - Min tokens: 20 (avoid trivial matches)
    /// - Min LOC: 3 (at least 3 lines)
    /// - Similarity: 1.0 (exact match)
    pub fn for_type1() -> Self {
        Self {
            min_tokens: 20,
            min_loc: 3,
            similarity_threshold: 1.0,
        }
    }

    /// Default configuration for Type-2 (Renamed) clones
    ///
    /// - Min tokens: 20 (same as Type-1)
    /// - Min LOC: 3
    /// - Similarity: 0.8 (allow some renaming)
    pub fn for_type2() -> Self {
        Self {
            min_tokens: 20,
            min_loc: 3,
            similarity_threshold: 0.8,
        }
    }

    /// Default configuration for Type-3 (Gapped) clones
    ///
    /// - Min tokens: 15 (slightly lower for gapped code)
    /// - Min LOC: 2
    /// - Similarity: 0.6 (allow gaps)
    pub fn for_type3() -> Self {
        Self {
            min_tokens: 15,
            min_loc: 2,
            similarity_threshold: 0.6,
        }
    }

    /// Default configuration for Type-4 (Semantic) clones
    ///
    /// - Min tokens: 5 (very permissive)
    /// - Min LOC: 1
    /// - Similarity: 0.5 (semantic similarity)
    pub fn for_type4() -> Self {
        Self {
            min_tokens: 5,
            min_loc: 1,
            similarity_threshold: 0.5,
        }
    }

    /// Get default configuration for a specific clone type
    pub fn for_type(clone_type: CloneType) -> Self {
        match clone_type {
            CloneType::Type1 => Self::for_type1(),
            CloneType::Type2 => Self::for_type2(),
            CloneType::Type3 => Self::for_type3(),
            CloneType::Type4 => Self::for_type4(),
        }
    }
}

impl Default for DetectorConfig {
    fn default() -> Self {
        Self::for_type1()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_type1_config() {
        let config = DetectorConfig::for_type1();
        assert_eq!(config.min_tokens, 20);
        assert_eq!(config.min_loc, 3);
        assert_eq!(config.similarity_threshold, 1.0);
    }

    #[test]
    fn test_type2_config() {
        let config = DetectorConfig::for_type2();
        assert_eq!(config.min_tokens, 20);
        assert_eq!(config.similarity_threshold, 0.8);
    }

    #[test]
    fn test_type3_config() {
        let config = DetectorConfig::for_type3();
        assert_eq!(config.min_tokens, 15);
        assert_eq!(config.similarity_threshold, 0.6);
    }

    #[test]
    fn test_type4_config() {
        let config = DetectorConfig::for_type4();
        assert_eq!(config.min_tokens, 5);
        assert_eq!(config.min_loc, 1);
        assert_eq!(config.similarity_threshold, 0.5);
    }

    #[test]
    fn test_for_type() {
        assert_eq!(
            DetectorConfig::for_type(CloneType::Type1),
            DetectorConfig::for_type1()
        );
        assert_eq!(
            DetectorConfig::for_type(CloneType::Type4),
            DetectorConfig::for_type4()
        );
    }

    #[test]
    #[should_panic(expected = "Similarity threshold must be between 0.0 and 1.0")]
    fn test_invalid_similarity() {
        DetectorConfig::new(10, 1, 1.5); // Invalid similarity > 1.0
    }

    #[test]
    fn test_custom_config() {
        let config = DetectorConfig::new(30, 5, 0.9);
        assert_eq!(config.min_tokens, 30);
        assert_eq!(config.min_loc, 5);
        assert_eq!(config.similarity_threshold, 0.9);
    }
}
