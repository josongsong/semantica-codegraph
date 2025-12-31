// Integration tests for P0 modules only
// This allows testing expression, selectors, search_types without broken modules

#[cfg(test)]
mod p0_expression_tests {
    use codegraph_ir::features::query_engine::{Expr, ExprBuilder, ExprError, Value};
    use std::collections::BTreeMap;

    #[test]
    fn test_canonicalize_and_ordering() {
        let expr1 = ExprBuilder::and(vec![
            ExprBuilder::eq("language", "python"),
            ExprBuilder::gte("complexity", 10),
        ]);

        let expr2 = ExprBuilder::and(vec![
            ExprBuilder::gte("complexity", 10),
            ExprBuilder::eq("language", "python"),
        ]);

        let hash1 = expr1.hash_canonical().unwrap();
        let hash2 = expr2.hash_canonical().unwrap();

        assert_eq!(
            hash1, hash2,
            "Expressions with same operands in different order should have identical hashes"
        );
    }

    #[test]
    fn test_canonicalize_float_normalization() {
        let expr1 = Expr::Literal(Value::Float(0.0));
        let expr2 = Expr::Literal(Value::Float(-0.0));

        let canonical1 = expr1.canonicalize().unwrap();
        let canonical2 = expr2.canonicalize().unwrap();

        assert_eq!(
            canonical1, canonical2,
            "0.0 and -0.0 should canonicalize to the same value"
        );
    }

    #[test]
    fn test_canonicalize_nan_rejection() {
        let expr = Expr::Literal(Value::Float(f64::NAN));
        let result = expr.canonicalize();

        assert!(result.is_err(), "NaN should be rejected");
        assert_eq!(result.unwrap_err(), ExprError::NaNNotAllowed);
    }

    #[test]
    fn test_value_types() {
        // Null
        let null_value = Value::Null;
        let json = serde_json::to_string(&null_value).unwrap();
        assert_eq!(json, "null");

        // List
        let list = Value::List(vec![Value::Int(1), Value::Int(2), Value::Int(3)]);
        let json = serde_json::to_string(&list).unwrap();
        assert!(json.contains("["));

        // Object with deterministic ordering
        let mut obj = BTreeMap::new();
        obj.insert("key1".to_string(), Value::String("value1".to_string()));
        obj.insert("key2".to_string(), Value::Int(42));
        let value = Value::Object(obj.clone());
        let json = serde_json::to_string(&value).unwrap();
        let deserialized: Value = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, value);

        // Timestamp
        let ts = Value::Timestamp(1672531200000000);
        let json = serde_json::to_string(&ts).unwrap();
        let deserialized: Value = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, ts);
    }

    #[test]
    fn test_deterministic_hash_stability() {
        let expr = ExprBuilder::and(vec![
            ExprBuilder::eq("language", "python"),
            ExprBuilder::gte("complexity", 10),
            ExprBuilder::contains("name", "process"),
        ]);

        let hash1 = expr.hash_canonical().unwrap();
        let hash2 = expr.clone().hash_canonical().unwrap();
        let hash3 = expr.hash_canonical().unwrap();

        assert_eq!(hash1, hash2);
        assert_eq!(hash2, hash3);
    }
}

#[cfg(test)]
mod p0_selector_tests {
    use codegraph_ir::features::query_engine::{
        NodeSelectorBuilder, EdgeSelectorBuilder, PathLimits,
        NodeSelector, EdgeSelector,
    };

    #[test]
    fn test_node_selector_by_id() {
        let selector = NodeSelectorBuilder::by_id("node123");
        assert_eq!(selector, NodeSelector::ById("node123".to_string()));
    }

    #[test]
    fn test_path_limits_default() {
        let limits = PathLimits::default();
        assert_eq!(limits.max_paths, 100);
        assert_eq!(limits.max_expansions, 10_000);
        assert_eq!(limits.timeout_ms, 30_000);
        assert_eq!(limits.max_path_length, None);
    }

    #[test]
    fn test_path_limits_validation() {
        assert!(PathLimits::new(0, 1000, 1000).is_err());
        assert!(PathLimits::new(100, 0, 1000).is_err());
        assert!(PathLimits::new(100, 1000, 0).is_err());
    }

    #[test]
    fn test_edge_selector_any() {
        let selector = EdgeSelectorBuilder::any();
        assert_eq!(selector, EdgeSelector::Any);
    }
}

#[cfg(test)]
mod p0_search_types_tests {
    use codegraph_ir::features::query_engine::{
        FusionStrategy, FusionConfig, ScoreSemantics, ScoreNormalization,
        TieBreakRule, SearchHitRow, SearchSource, Value,
    };
    use std::collections::HashMap;

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
    fn test_fusion_config_serialization() {
        let config = FusionConfig::default();
        let json = serde_json::to_string(&config).unwrap();

        let deserialized: FusionConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, config);
    }
}
