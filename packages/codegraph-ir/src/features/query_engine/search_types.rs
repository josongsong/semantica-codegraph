// Search Score Semantics and Fusion Config - RFC-RUST-SDK-002 P0
//
// Provides complete semantic contracts for search reproducibility:
// - ScoreSemantics: Explicit score interpretation
// - FusionStrategy: Hybrid search fusion methods
// - FusionConfig: Complete fusion specification
//
// Design: RFC-RUST-SDK-002 Sections 9.1.4 and 9.1.5

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use crate::features::query_engine::expression::Value;

/// Score semantics for reproducibility (P0 CRITICAL)
///
/// Makes explicit how scores should be interpreted, enabling:
/// - Reproducible search results
/// - Correct score normalization
/// - Proper tie-breaking
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ScoreSemantics {
    /// BM25: unbounded, higher = better
    BM25 { k1: f64, b: f64 },

    /// Cosine similarity: [-1, 1], higher = better
    CosineSimilarity,

    /// Dot product: unbounded, higher = better
    DotProduct,

    /// L2 distance: [0, ∞), lower = better (inverted for sort_key)
    L2Distance,

    /// Fused score (hybrid search)
    Fused { strategy: FusionStrategy },
}

/// Distance metrics for vector search
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum DistanceMetric {
    /// Cosine similarity (normalized dot product)
    Cosine,

    /// Dot product (unnormalized)
    DotProduct,

    /// L2 (Euclidean) distance
    L2,
}

/// Fusion strategies for hybrid search (UPDATED with full spec)
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum FusionStrategy {
    /// Reciprocal Rank Fusion with k parameter
    ///
    /// Score = sum(1 / (k + rank_i)) for all channels
    /// Default k=60 from research literature
    RRF { k: usize },

    /// Weighted linear combination
    ///
    /// Score = sum(weight_i * score_i) for all channels
    LinearCombination {
        weights: HashMap<String, f64>,
        normalize_weights: bool,  // auto-normalize to sum=1?
    },

    /// Take max score across channels
    Max,
}

impl Default for FusionStrategy {
    fn default() -> Self {
        FusionStrategy::RRF { k: 60 }
    }
}

/// Score normalization methods
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ScoreNormalization {
    /// No normalization (use raw scores)
    None,

    /// Min-max normalization: (x - min) / (max - min)
    MinMax,

    /// Z-score normalization: (x - mean) / stddev
    ZScore,

    /// Rank-based (convert to percentile rank)
    RankBased,
}

impl Default for ScoreNormalization {
    fn default() -> Self {
        ScoreNormalization::RankBased
    }
}

/// Tie-breaking rules for deterministic ordering
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum TieBreakRule {
    /// Stable sort by node_id (lexicographic)
    NodeIdAsc,

    /// By original channel rank (channel priority order)
    ChannelPriority(Vec<String>),

    /// Custom field
    Field { name: String, ascending: bool },
}

impl Default for TieBreakRule {
    fn default() -> Self {
        TieBreakRule::NodeIdAsc
    }
}

/// Fusion configuration (complete contract for determinism)
///
/// Specifies ALL parameters needed for reproducible hybrid search:
/// - Strategy (RRF/LinearCombination/Max)
/// - Score normalization per channel
/// - Tie-breaking rule
/// - Candidate pool size
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FusionConfig {
    pub strategy: FusionStrategy,
    pub normalization: ScoreNormalization,
    pub tie_break: TieBreakRule,

    /// Per-channel top-N before fusion (default: 1000)
    pub candidate_pool_size: usize,
}

impl Default for FusionConfig {
    fn default() -> Self {
        Self {
            strategy: FusionStrategy::default(),
            normalization: ScoreNormalization::default(),
            tie_break: TieBreakRule::default(),
            candidate_pool_size: 1000,
        }
    }
}

impl FusionConfig {
    /// Create RRF fusion config
    pub fn rrf(k: usize) -> Self {
        Self {
            strategy: FusionStrategy::RRF { k },
            ..Default::default()
        }
    }

    /// Create linear combination fusion config
    pub fn linear(weights: HashMap<String, f64>) -> Self {
        Self {
            strategy: FusionStrategy::LinearCombination {
                weights,
                normalize_weights: true,
            },
            ..Default::default()
        }
    }

    /// Create max fusion config
    pub fn max() -> Self {
        Self {
            strategy: FusionStrategy::Max,
            ..Default::default()
        }
    }

    /// Set normalization method
    pub fn with_normalization(mut self, normalization: ScoreNormalization) -> Self {
        self.normalization = normalization;
        self
    }

    /// Set tie-breaking rule
    pub fn with_tie_break(mut self, tie_break: TieBreakRule) -> Self {
        self.tie_break = tie_break;
        self
    }

    /// Set candidate pool size
    pub fn with_pool_size(mut self, size: usize) -> Self {
        self.candidate_pool_size = size;
        self
    }
}

/// Search result row with complete score semantics (P0 CRITICAL)
///
/// Provides ALL information needed for reproducible search:
/// - score_raw: Original engine output
/// - score_norm: Normalized [0, 1]
/// - sort_key: Always "higher = better" for deterministic sorting
/// - score_semantics: How to interpret scores
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchHitRow {
    pub node_id: String,

    /// Raw score from search engine (unnormalized)
    pub score_raw: f64,

    /// Normalized score [0, 1] where higher = better
    /// Normalization: (score - min) / (max - min) within result set
    pub score_norm: f64,

    /// Sort key (always higher = better, deterministic)
    pub sort_key: f64,

    /// Score semantics (how to interpret score_raw)
    pub score_semantics: ScoreSemantics,

    /// Search source (Lexical / Semantic / Hybrid)
    pub source: SearchSource,

    /// 1-based rank
    pub rank: usize,

    /// Additional metadata
    pub metadata: HashMap<String, Value>,
}

/// Search source type
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum SearchSource {
    Lexical,
    Semantic,
    Hybrid,
}

impl SearchHitRow {
    /// Create new search hit
    pub fn new(
        node_id: String,
        score_raw: f64,
        score_norm: f64,
        sort_key: f64,
        score_semantics: ScoreSemantics,
        source: SearchSource,
        rank: usize,
    ) -> Self {
        Self {
            node_id,
            score_raw,
            score_norm,
            sort_key,
            score_semantics,
            source,
            rank,
            metadata: HashMap::new(),
        }
    }

    /// Add metadata
    pub fn with_metadata(mut self, key: String, value: Value) -> Self {
        self.metadata.insert(key, value);
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fusion_strategy_default() {
        let strategy = FusionStrategy::default();
        match strategy {
            FusionStrategy::RRF { k } => assert_eq!(k, 60),
            _ => panic!("Expected RRF as default"),
        }
    }

    #[test]
    fn test_fusion_config_default() {
        let config = FusionConfig::default();
        assert!(matches!(config.strategy, FusionStrategy::RRF { k: 60 }));
        assert_eq!(config.normalization, ScoreNormalization::RankBased);
        assert_eq!(config.tie_break, TieBreakRule::NodeIdAsc);
        assert_eq!(config.candidate_pool_size, 1000);
    }

    #[test]
    fn test_fusion_config_rrf() {
        let config = FusionConfig::rrf(100);
        match config.strategy {
            FusionStrategy::RRF { k } => assert_eq!(k, 100),
            _ => panic!("Expected RRF"),
        }
    }

    #[test]
    fn test_fusion_config_linear() {
        let mut weights = HashMap::new();
        weights.insert("lexical".to_string(), 0.3);
        weights.insert("semantic".to_string(), 0.7);

        let config = FusionConfig::linear(weights.clone());
        match config.strategy {
            FusionStrategy::LinearCombination {
                weights: w,
                normalize_weights,
            } => {
                assert_eq!(w, weights);
                assert!(normalize_weights);
            }
            _ => panic!("Expected LinearCombination"),
        }
    }

    #[test]
    fn test_fusion_config_builder() {
        let config = FusionConfig::rrf(60)
            .with_normalization(ScoreNormalization::MinMax)
            .with_pool_size(500);

        assert_eq!(config.normalization, ScoreNormalization::MinMax);
        assert_eq!(config.candidate_pool_size, 500);
    }

    #[test]
    fn test_search_hit_row_creation() {
        let hit = SearchHitRow::new(
            "node123".to_string(),
            15.5,
            0.85,
            0.85,
            ScoreSemantics::BM25 { k1: 1.2, b: 0.75 },
            SearchSource::Lexical,
            1,
        );

        assert_eq!(hit.node_id, "node123");
        assert_eq!(hit.score_raw, 15.5);
        assert_eq!(hit.score_norm, 0.85);
        assert_eq!(hit.rank, 1);
        assert_eq!(hit.source, SearchSource::Lexical);
    }

    #[test]
    fn test_search_hit_with_metadata() {
        let hit = SearchHitRow::new(
            "node123".to_string(),
            10.0,
            0.5,
            0.5,
            ScoreSemantics::CosineSimilarity,
            SearchSource::Semantic,
            1,
        )
        .with_metadata("file_path".to_string(), Value::String("main.rs".to_string()));

        assert_eq!(hit.metadata.len(), 1);
        assert!(hit.metadata.contains_key("file_path"));
    }

    #[test]
    fn test_score_semantics_serialization() {
        let semantics = ScoreSemantics::BM25 { k1: 1.2, b: 0.75 };
        let json = serde_json::to_string(&semantics).unwrap();
        assert!(json.contains("BM25"));

        let deserialized: ScoreSemantics = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, semantics);
    }

    #[test]
    fn test_fusion_config_serialization() {
        let config = FusionConfig::default();
        let json = serde_json::to_string(&config).unwrap();

        let deserialized: FusionConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, config);
    }

    #[test]
    fn test_tie_break_rule_variants() {
        let rule1 = TieBreakRule::NodeIdAsc;
        let rule2 = TieBreakRule::ChannelPriority(vec!["lexical".to_string()]);
        let rule3 = TieBreakRule::Field {
            name: "timestamp".to_string(),
            ascending: false,
        };

        assert_eq!(rule1, TieBreakRule::default());
        assert_ne!(rule1, rule2);
        assert_ne!(rule2, rule3);
    }

    #[test]
    fn test_distance_metric_variants() {
        let metrics = vec![
            DistanceMetric::Cosine,
            DistanceMetric::DotProduct,
            DistanceMetric::L2,
        ];

        for metric in metrics {
            let json = serde_json::to_string(&metric).unwrap();
            let deserialized: DistanceMetric = serde_json::from_str(&json).unwrap();
            assert_eq!(deserialized, metric);
        }
    }
}
