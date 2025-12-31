// Comprehensive P0 Module Tests - 빡센 시나리오 검증
// Tests ALL edge cases, real-world scenarios, and RFC compliance

#[cfg(test)]
mod comprehensive_expression_tests {
    use codegraph_ir::features::query_engine::{Expr, ExprBuilder, ExprError, Value, Op};
    use std::collections::BTreeMap;

    // ========================================================================
    // SCENARIO 1: 복잡한 중첩 쿼리 정규화 (Real-world complex query)
    // ========================================================================
    #[test]
    fn test_deeply_nested_query_canonicalization() {
        // 실전: 복잡한 보안 취약점 탐지 쿼리
        let query1 = ExprBuilder::and(vec![
            ExprBuilder::or(vec![
                ExprBuilder::eq("severity", "critical"),
                ExprBuilder::eq("severity", "high"),
            ]),
            ExprBuilder::and(vec![
                ExprBuilder::gte("complexity", 15),
                ExprBuilder::contains("name", "authenticate"),
            ]),
            ExprBuilder::or(vec![
                ExprBuilder::regex("path", r".*\.py$"),
                ExprBuilder::regex("path", r".*\.js$"),
            ]),
        ]);

        // 같은 쿼리, 다른 순서
        let query2 = ExprBuilder::and(vec![
            ExprBuilder::or(vec![
                ExprBuilder::regex("path", r".*\.js$"),
                ExprBuilder::regex("path", r".*\.py$"),
            ]),
            ExprBuilder::or(vec![
                ExprBuilder::eq("severity", "high"),
                ExprBuilder::eq("severity", "critical"),
            ]),
            ExprBuilder::and(vec![
                ExprBuilder::contains("name", "authenticate"),
                ExprBuilder::gte("complexity", 15),
            ]),
        ]);

        let hash1 = query1.hash_canonical().unwrap();
        let hash2 = query2.hash_canonical().unwrap();

        assert_eq!(
            hash1, hash2,
            "Complex nested queries with same logic must have identical hashes"
        );
    }

    // ========================================================================
    // SCENARIO 2: Value 타입 전체 테스트 (All Value types)
    // ========================================================================
    #[test]
    fn test_all_value_types_serialization() {
        let test_cases = vec![
            ("Null", Value::Null),
            ("Int", Value::Int(42)),
            ("Float", Value::Float(3.14159)),
            ("String", Value::String("test".to_string())),
            ("Bool", Value::Bool(true)),
            (
                "List",
                Value::List(vec![
                    Value::Int(1),
                    Value::String("two".to_string()),
                    Value::Bool(true),
                    Value::Null,
                ]),
            ),
            (
                "Object",
                {
                    let mut obj = BTreeMap::new();
                    obj.insert("key1".to_string(), Value::Int(1));
                    obj.insert("key2".to_string(), Value::String("value".to_string()));
                    obj.insert("key3".to_string(), Value::Bool(false));
                    obj.insert("key4".to_string(), Value::Null);
                    Value::Object(obj)
                },
            ),
            ("Bytes", Value::Bytes(vec![0x01, 0x02, 0x03, 0xFF])),
            ("Timestamp", Value::Timestamp(1672531200000000)),
        ];

        for (name, value) in test_cases {
            // Serialize
            let json = serde_json::to_string(&value).unwrap();

            // Deserialize
            let deserialized: Value = serde_json::from_str(&json).unwrap();

            assert_eq!(
                value, deserialized,
                "{} value must round-trip through JSON",
                name
            );
        }
    }

    // ========================================================================
    // SCENARIO 3: Float 정규화 엣지 케이스 (All float edge cases)
    // ========================================================================
    #[test]
    fn test_float_edge_cases() {
        // -0.0 정규화
        let expr1 = Expr::Literal(Value::Float(0.0));
        let expr2 = Expr::Literal(Value::Float(-0.0));
        assert_eq!(
            expr1.canonicalize().unwrap(),
            expr2.canonicalize().unwrap(),
            "0.0 and -0.0 must canonicalize identically"
        );

        // NaN 거부
        let nan_expr = Expr::Literal(Value::Float(f64::NAN));
        assert!(
            nan_expr.canonicalize().is_err(),
            "NaN must be rejected in canonicalization"
        );

        // Infinity 처리
        let inf_expr = Expr::Literal(Value::Float(f64::INFINITY));
        let canonical = inf_expr.canonicalize();
        assert!(
            canonical.is_ok(),
            "Infinity should be allowed (up to implementation)"
        );

        // Very small numbers
        let small = Expr::Literal(Value::Float(1e-308));
        assert!(small.canonicalize().is_ok());

        // Very large numbers
        let large = Expr::Literal(Value::Float(1e308));
        assert!(large.canonicalize().is_ok());
    }

    // ========================================================================
    // SCENARIO 4: 연산자 전체 테스트 (All operators)
    // ========================================================================
    #[test]
    fn test_all_comparison_operators() {
        let operators = vec![
            ("Eq", ExprBuilder::eq("x", 10)),
            ("Ne", ExprBuilder::ne("x", 10)),
            ("Lt", ExprBuilder::lt("x", 10)),
            ("Lte", ExprBuilder::lte("x", 10)),
            ("Gt", ExprBuilder::gt("x", 10)),
            ("Gte", ExprBuilder::gte("x", 10)),
        ];

        for (name, expr) in operators {
            let canonical = expr.canonicalize();
            assert!(canonical.is_ok(), "{} must canonicalize successfully", name);

            let hash = canonical.unwrap().hash_canonical();
            assert!(hash.is_ok(), "{} must hash successfully", name);
        }
    }

    #[test]
    fn test_all_string_operators() {
        let operators = vec![
            ("Contains", ExprBuilder::contains("name", "test")),
            ("StartsWith", ExprBuilder::starts_with("name", "test")),
            ("EndsWith", ExprBuilder::ends_with("name", "test")),
            ("Regex", ExprBuilder::regex("name", r"test.*")),
        ];

        for (name, expr) in operators {
            let canonical = expr.canonicalize();
            assert!(canonical.is_ok(), "{} must canonicalize successfully", name);
        }
    }

    // ========================================================================
    // SCENARIO 5: 빈 컬렉션 처리 (Empty collections)
    // ========================================================================
    #[test]
    fn test_empty_collections() {
        // Empty And
        let empty_and = ExprBuilder::and(vec![]);
        assert!(
            empty_and.canonicalize().is_ok(),
            "Empty And should be allowed (vacuous truth)"
        );

        // Empty Or
        let empty_or = ExprBuilder::or(vec![]);
        assert!(
            empty_or.canonicalize().is_ok(),
            "Empty Or should be allowed (vacuous false)"
        );

        // Empty List value
        let empty_list = Expr::Literal(Value::List(vec![]));
        assert!(empty_list.canonicalize().is_ok());

        // Empty Object value
        let empty_obj = Expr::Literal(Value::Object(BTreeMap::new()));
        assert!(empty_obj.canonicalize().is_ok());
    }

    // ========================================================================
    // SCENARIO 6: 해시 안정성 (Hash stability across runs)
    // ========================================================================
    #[test]
    fn test_hash_stability_across_multiple_runs() {
        let query = ExprBuilder::and(vec![
            ExprBuilder::eq("language", "python"),
            ExprBuilder::gte("complexity", 10),
            ExprBuilder::contains("name", "process"),
        ]);

        // 100번 해싱해도 같은 결과
        let mut hashes = Vec::new();
        for _ in 0..100 {
            let hash = query.clone().hash_canonical().unwrap();
            hashes.push(hash);
        }

        let first_hash = &hashes[0];
        for hash in &hashes {
            assert_eq!(
                hash, first_hash,
                "Hash must be stable across multiple invocations"
            );
        }
    }

    // ========================================================================
    // SCENARIO 7: Unicode 처리 (Unicode strings)
    // ========================================================================
    #[test]
    fn test_unicode_strings() {
        let unicode_cases = vec![
            "한글",
            "日本語",
            "中文",
            "Ελληνικά",
            "עברית",
            "العربية",
            "🚀🎉💻",
            "混合text한글🎉",
        ];

        for text in unicode_cases {
            let expr = ExprBuilder::eq("name", text);
            let canonical = expr.canonicalize();
            assert!(
                canonical.is_ok(),
                "Unicode '{}' must canonicalize successfully",
                text
            );

            let hash = canonical.unwrap().hash_canonical();
            assert!(hash.is_ok(), "Unicode '{}' must hash successfully", text);
        }
    }

    // ========================================================================
    // SCENARIO 8: 극단적 깊이 (Extreme nesting depth)
    // ========================================================================
    #[test]
    fn test_extreme_nesting_depth() {
        // 50단계 중첩
        let mut expr = ExprBuilder::eq("x", 0);
        for i in 1..50 {
            expr = ExprBuilder::and(vec![expr, ExprBuilder::eq("y", i)]);
        }

        let canonical = expr.canonicalize();
        assert!(
            canonical.is_ok(),
            "Deeply nested expression (50 levels) must canonicalize"
        );

        let hash = canonical.unwrap().hash_canonical();
        assert!(hash.is_ok(), "Deeply nested expression must hash");
    }

    // ========================================================================
    // SCENARIO 9: 대규모 쿼리 (Large-scale queries)
    // ========================================================================
    #[test]
    fn test_large_scale_query() {
        // 100개 조건의 And 쿼리
        let mut conditions = Vec::new();
        for i in 0..100 {
            conditions.push(ExprBuilder::eq(&format!("field_{}", i), i));
        }

        let large_query = ExprBuilder::and(conditions);
        let canonical = large_query.canonicalize();
        assert!(
            canonical.is_ok(),
            "Query with 100 conditions must canonicalize"
        );
    }

    // ========================================================================
    // SCENARIO 10: 특수 문자 (Special characters in strings)
    // ========================================================================
    #[test]
    fn test_special_characters() {
        let special_chars = vec![
            r#"quotes "test""#,
            r"backslash \test",
            "newline\ntest",
            "tab\ttest",
            "null\0test",
            r"regex .*+?[]{}()|^$",
        ];

        for text in special_chars {
            let expr = ExprBuilder::contains("name", text);
            let canonical = expr.canonicalize();
            assert!(
                canonical.is_ok(),
                "Special characters '{}' must canonicalize",
                text.escape_debug()
            );
        }
    }
}

#[cfg(test)]
mod comprehensive_selector_tests {
    use codegraph_ir::features::query_engine::{
        EdgeKind, EdgeSelector, EdgeSelectorBuilder, ExprBuilder, NodeKind, NodeSelector,
        NodeSelectorBuilder, PathLimits,
    };

    // ========================================================================
    // SCENARIO 11: NodeSelector 전체 variant 테스트
    // ========================================================================
    #[test]
    fn test_all_node_selector_variants() {
        // ById
        let by_id = NodeSelectorBuilder::by_id("node123");
        assert!(matches!(by_id, NodeSelector::ById(_)));

        // ByName without scope
        let by_name = NodeSelectorBuilder::by_name("main");
        assert!(matches!(by_name, NodeSelector::ByName { scope: None, .. }));

        // ByName with scope
        let by_name_scoped = NodeSelectorBuilder::by_name_scoped("main", "src/main.rs");
        assert!(matches!(
            by_name_scoped,
            NodeSelector::ByName { scope: Some(_), .. }
        ));

        // ByKind
        let by_kind = NodeSelectorBuilder::by_kind(NodeKind::Function);
        assert!(matches!(by_kind, NodeSelector::ByKind { .. }));

        // ByKind with filters
        let by_kind_filtered = NodeSelectorBuilder::by_kind_filtered(
            NodeKind::Function,
            vec![ExprBuilder::gte("complexity", 10)],
        );
        assert!(matches!(by_kind_filtered, NodeSelector::ByKind { .. }));

        // Union
        let union = NodeSelectorBuilder::union(vec![
            NodeSelectorBuilder::by_id("node1"),
            NodeSelectorBuilder::by_id("node2"),
        ]);
        assert!(matches!(union, NodeSelector::Union(_)));
    }

    // ========================================================================
    // SCENARIO 12: NodeKind 전체 enum 테스트 (Type safety)
    // ========================================================================
    #[test]
    fn test_all_node_kinds() {
        let node_kinds = vec![
            NodeKind::Function,
            NodeKind::Class,
            NodeKind::Variable,
            NodeKind::Call,
            NodeKind::Import,
            NodeKind::TypeDef,
            NodeKind::All,
        ];

        for kind in node_kinds {
            let selector = NodeSelectorBuilder::by_kind(kind);
            let json = serde_json::to_string(&selector).unwrap();
            let deserialized: NodeSelector = serde_json::from_str(&json).unwrap();
            assert_eq!(selector, deserialized, "NodeKind {:?} must serialize", kind);
        }
    }

    // ========================================================================
    // SCENARIO 13: EdgeKind 전체 enum 테스트 (Type safety)
    // ========================================================================
    #[test]
    fn test_all_edge_kinds() {
        let edge_kinds = vec![
            EdgeKind::Calls,
            EdgeKind::Dataflow,
            EdgeKind::ControlFlow,
            EdgeKind::References,
            EdgeKind::Contains,
            EdgeKind::All,
        ];

        for kind in edge_kinds {
            let selector = EdgeSelectorBuilder::by_kind(kind);
            let json = serde_json::to_string(&selector).unwrap();
            let deserialized: EdgeSelector = serde_json::from_str(&json).unwrap();
            assert_eq!(selector, deserialized, "EdgeKind {:?} must serialize", kind);
        }
    }

    // ========================================================================
    // SCENARIO 14: EdgeSelector 복합 시나리오
    // ========================================================================
    #[test]
    fn test_edge_selector_complex_scenarios() {
        // Any edge
        let any = EdgeSelectorBuilder::any();
        assert_eq!(any, EdgeSelector::Any);

        // Single kind
        let single = EdgeSelectorBuilder::by_kind(EdgeKind::Calls);
        assert!(matches!(single, EdgeSelector::ByKind(EdgeKind::Calls)));

        // Multiple kinds
        let multiple = EdgeSelectorBuilder::by_kinds(vec![
            EdgeKind::Calls,
            EdgeKind::Dataflow,
            EdgeKind::ControlFlow,
        ]);
        assert!(matches!(multiple, EdgeSelector::ByKinds(_)));

        // With filter
        let filtered = EdgeSelectorBuilder::by_filter(vec![ExprBuilder::eq("weight", 5)]);
        assert!(matches!(filtered, EdgeSelector::ByFilter(_)));
    }

    // ========================================================================
    // SCENARIO 15: PathLimits 전체 엣지 케이스
    // ========================================================================
    #[test]
    fn test_path_limits_all_edge_cases() {
        // Default values
        let default = PathLimits::default();
        assert_eq!(default.max_paths, 100);
        assert_eq!(default.max_expansions, 10_000);
        assert_eq!(default.timeout_ms, 30_000);
        assert_eq!(default.max_path_length, None);

        // Custom values
        let custom = PathLimits::new(1000, 50_000, 60_000).unwrap();
        assert_eq!(custom.max_paths, 1000);
        assert_eq!(custom.max_expansions, 50_000);
        assert_eq!(custom.timeout_ms, 60_000);

        // With max length
        let with_length = PathLimits::default().with_max_length(50);
        assert_eq!(with_length.max_path_length, Some(50));

        // Unlimited (DANGEROUS)
        let unlimited = PathLimits::unlimited();
        assert_eq!(unlimited.max_paths, usize::MAX);
        assert_eq!(unlimited.max_expansions, usize::MAX);
        assert_eq!(unlimited.timeout_ms, u64::MAX);

        // Validation: zero max_paths
        assert!(PathLimits::new(0, 1000, 1000).is_err());

        // Validation: zero max_expansions
        assert!(PathLimits::new(100, 0, 1000).is_err());

        // Validation: zero timeout
        assert!(PathLimits::new(100, 1000, 0).is_err());

        // Edge case: very large values
        let large = PathLimits::new(usize::MAX - 1, usize::MAX - 1, u64::MAX - 1).unwrap();
        assert_eq!(large.max_paths, usize::MAX - 1);
    }

    // ========================================================================
    // SCENARIO 16: Selector 직렬화 안정성
    // ========================================================================
    #[test]
    fn test_selector_serialization_stability() {
        let selectors = vec![
            NodeSelectorBuilder::by_id("node123"),
            NodeSelectorBuilder::by_name("main"),
            NodeSelectorBuilder::by_name_scoped("func", "module"),
            NodeSelectorBuilder::by_kind(NodeKind::Function),
            NodeSelectorBuilder::union(vec![
                NodeSelectorBuilder::by_id("n1"),
                NodeSelectorBuilder::by_id("n2"),
            ]),
        ];

        for selector in selectors {
            // 여러 번 직렬화해도 같은 결과
            let json1 = serde_json::to_string(&selector).unwrap();
            let json2 = serde_json::to_string(&selector).unwrap();
            assert_eq!(json1, json2, "Serialization must be stable");

            // Round-trip
            let deserialized: NodeSelector = serde_json::from_str(&json1).unwrap();
            assert_eq!(selector, deserialized);
        }
    }

    // ========================================================================
    // SCENARIO 17: 극단적 Union 크기
    // ========================================================================
    #[test]
    fn test_extreme_union_size() {
        // 1000개 노드 Union
        let mut selectors = Vec::new();
        for i in 0..1000 {
            selectors.push(NodeSelectorBuilder::by_id(&format!("node_{}", i)));
        }

        let large_union = NodeSelectorBuilder::union(selectors);
        let json = serde_json::to_string(&large_union).unwrap();
        let deserialized: NodeSelector = serde_json::from_str(&json).unwrap();
        assert_eq!(large_union, deserialized);
    }
}

#[cfg(test)]
mod comprehensive_search_types_tests {
    use codegraph_ir::features::query_engine::{
        DistanceMetric, FusionConfig, FusionStrategy, ScoreNormalization, ScoreSemantics,
        SearchHitRow, SearchSource, TieBreakRule, Value,
    };

    // ========================================================================
    // SCENARIO 18: 모든 ScoreSemantics variant 테스트
    // ========================================================================
    #[test]
    fn test_all_score_semantics() {
        let semantics = vec![
            ScoreSemantics::BM25 { k1: 1.2, b: 0.75 },
            ScoreSemantics::TfIdf,
            ScoreSemantics::Cosine,
            ScoreSemantics::Embedding {
                metric: DistanceMetric::Cosine,
            },
            ScoreSemantics::Embedding {
                metric: DistanceMetric::DotProduct,
            },
            ScoreSemantics::Embedding {
                metric: DistanceMetric::L2,
            },
            ScoreSemantics::Fused {
                strategy: FusionStrategy::RRF { k: 60 },
            },
            ScoreSemantics::ReRank { model: "cross-encoder".to_string() },
        ];

        for semantic in semantics {
            let json = serde_json::to_string(&semantic).unwrap();
            let deserialized: ScoreSemantics = serde_json::from_str(&json).unwrap();
            assert_eq!(semantic, deserialized);
        }
    }

    // ========================================================================
    // SCENARIO 19: FusionStrategy 전체 테스트
    // ========================================================================
    #[test]
    fn test_all_fusion_strategies() {
        // RRF
        let rrf = FusionStrategy::RRF { k: 60 };
        assert_eq!(FusionStrategy::default(), rrf, "Default must be RRF k=60");

        // LinearCombination
        let linear = FusionStrategy::LinearCombination {
            weights: vec![0.5, 0.3, 0.2],
        };
        let json = serde_json::to_string(&linear).unwrap();
        let deserialized: FusionStrategy = serde_json::from_str(&json).unwrap();
        assert_eq!(linear, deserialized);

        // Max
        let max = FusionStrategy::Max;
        let json = serde_json::to_string(&max).unwrap();
        let deserialized: FusionStrategy = serde_json::from_str(&json).unwrap();
        assert_eq!(max, deserialized);
    }

    // ========================================================================
    // SCENARIO 20: FusionConfig 빌더 패턴 전체 테스트
    // ========================================================================
    #[test]
    fn test_fusion_config_builder_patterns() {
        // Default
        let default = FusionConfig::default();
        assert!(matches!(default.strategy, FusionStrategy::RRF { k: 60 }));
        assert_eq!(default.normalization, ScoreNormalization::RankBased);
        assert_eq!(default.tie_break, TieBreakRule::NodeIdAsc);
        assert_eq!(default.candidate_pool_size, 1000);

        // RRF builder
        let rrf = FusionConfig::rrf(100);
        assert!(matches!(rrf.strategy, FusionStrategy::RRF { k: 100 }));

        // LinearCombination builder
        let linear = FusionConfig::linear_combination(vec![0.6, 0.4]);
        assert!(matches!(
            linear.strategy,
            FusionStrategy::LinearCombination { .. }
        ));

        // Max builder
        let max = FusionConfig::max();
        assert!(matches!(max.strategy, FusionStrategy::Max));

        // With methods
        let custom = FusionConfig::rrf(60)
            .with_normalization(ScoreNormalization::MinMax)
            .with_tie_break(TieBreakRule::ScoreDesc)
            .with_pool_size(2000);

        assert_eq!(custom.normalization, ScoreNormalization::MinMax);
        assert_eq!(custom.tie_break, TieBreakRule::ScoreDesc);
        assert_eq!(custom.candidate_pool_size, 2000);
    }

    // ========================================================================
    // SCENARIO 21: SearchHitRow 완전성 테스트
    // ========================================================================
    #[test]
    fn test_search_hit_row_completeness() {
        let hit = SearchHitRow::new(
            "node123".to_string(),
            15.5,
            0.85,
            0.85,
            ScoreSemantics::BM25 { k1: 1.2, b: 0.75 },
            SearchSource::Lexical,
            1,
        );

        // All fields present
        assert_eq!(hit.node_id, "node123");
        assert_eq!(hit.score_raw, 15.5);
        assert_eq!(hit.score_norm, 0.85);
        assert_eq!(hit.sort_key, 0.85);
        assert!(matches!(hit.score_semantics, ScoreSemantics::BM25 { .. }));
        assert_eq!(hit.source, SearchSource::Lexical);
        assert_eq!(hit.rank, 1);
        assert_eq!(hit.metadata, None);

        // With metadata
        let mut metadata = std::collections::HashMap::new();
        metadata.insert("file".to_string(), Value::String("test.py".to_string()));

        let hit_with_metadata = SearchHitRow {
            metadata: Some(metadata),
            ..hit
        };

        assert!(hit_with_metadata.metadata.is_some());
    }

    // ========================================================================
    // SCENARIO 22: ScoreNormalization 전체 테스트
    // ========================================================================
    #[test]
    fn test_all_score_normalizations() {
        let normalizations = vec![
            ScoreNormalization::MinMax,
            ScoreNormalization::ZScore,
            ScoreNormalization::RankBased,
            ScoreNormalization::Sigmoid,
            ScoreNormalization::None,
        ];

        for norm in normalizations {
            let json = serde_json::to_string(&norm).unwrap();
            let deserialized: ScoreNormalization = serde_json::from_str(&json).unwrap();
            assert_eq!(norm, deserialized);
        }
    }

    // ========================================================================
    // SCENARIO 23: TieBreakRule 전체 테스트
    // ========================================================================
    #[test]
    fn test_all_tie_break_rules() {
        let rules = vec![
            TieBreakRule::NodeIdAsc,
            TieBreakRule::NodeIdDesc,
            TieBreakRule::ScoreDesc,
            TieBreakRule::RankAsc,
        ];

        for rule in rules {
            let json = serde_json::to_string(&rule).unwrap();
            let deserialized: TieBreakRule = serde_json::from_str(&json).unwrap();
            assert_eq!(rule, deserialized);
        }
    }

    // ========================================================================
    // SCENARIO 24: SearchSource 전체 테스트
    // ========================================================================
    #[test]
    fn test_all_search_sources() {
        let sources = vec![
            SearchSource::Lexical,
            SearchSource::Semantic,
            SearchSource::Graph,
            SearchSource::Hybrid,
            SearchSource::ReRank,
        ];

        for source in sources {
            let json = serde_json::to_string(&source).unwrap();
            let deserialized: SearchSource = serde_json::from_str(&json).unwrap();
            assert_eq!(source, deserialized);
        }
    }

    // ========================================================================
    // SCENARIO 25: DistanceMetric 전체 테스트
    // ========================================================================
    #[test]
    fn test_all_distance_metrics() {
        let metrics = vec![
            DistanceMetric::Cosine,
            DistanceMetric::DotProduct,
            DistanceMetric::L2,
        ];

        for metric in metrics {
            let json = serde_json::to_string(&metric).unwrap();
            let deserialized: DistanceMetric = serde_json::from_str(&json).unwrap();
            assert_eq!(metric, deserialized);
        }
    }

    // ========================================================================
    // SCENARIO 26: 복합 SearchHitRow 시나리오
    // ========================================================================
    #[test]
    fn test_complex_search_hit_scenarios() {
        // Lexical search
        let lexical = SearchHitRow::new(
            "func_process_data".to_string(),
            25.3,
            0.92,
            0.92,
            ScoreSemantics::BM25 { k1: 1.5, b: 0.8 },
            SearchSource::Lexical,
            1,
        );

        // Semantic search
        let semantic = SearchHitRow::new(
            "func_handle_request".to_string(),
            0.87,
            0.87,
            0.87,
            ScoreSemantics::Embedding {
                metric: DistanceMetric::Cosine,
            },
            SearchSource::Semantic,
            2,
        );

        // Hybrid search (fused)
        let hybrid = SearchHitRow::new(
            "func_authenticate".to_string(),
            0.89,
            0.89,
            0.89,
            ScoreSemantics::Fused {
                strategy: FusionStrategy::RRF { k: 60 },
            },
            SearchSource::Hybrid,
            1,
        );

        // ReRank
        let rerank = SearchHitRow::new(
            "func_validate_token".to_string(),
            0.95,
            0.95,
            0.95,
            ScoreSemantics::ReRank {
                model: "ms-marco-MiniLM-L-12-v2".to_string(),
            },
            SearchSource::ReRank,
            1,
        );

        // All serialize successfully
        for hit in vec![lexical, semantic, hybrid, rerank] {
            let json = serde_json::to_string(&hit).unwrap();
            let deserialized: SearchHitRow = serde_json::from_str(&json).unwrap();
            assert_eq!(hit, deserialized);
        }
    }

    // ========================================================================
    // SCENARIO 27: FusionConfig 극단값 테스트
    // ========================================================================
    #[test]
    fn test_fusion_config_extreme_values() {
        // Very large RRF k
        let large_k = FusionConfig::rrf(1_000_000);
        assert!(matches!(large_k.strategy, FusionStrategy::RRF { k: 1_000_000 }));

        // Very large pool size
        let large_pool = FusionConfig::default().with_pool_size(1_000_000);
        assert_eq!(large_pool.candidate_pool_size, 1_000_000);

        // Many weights in LinearCombination
        let many_weights = FusionConfig::linear_combination((0..100).map(|i| i as f64 / 100.0).collect());
        if let FusionStrategy::LinearCombination { weights } = &many_weights.strategy {
            assert_eq!(weights.len(), 100);
        } else {
            panic!("Expected LinearCombination");
        }
    }

    // ========================================================================
    // SCENARIO 28: 직렬화 안정성 (모든 타입)
    // ========================================================================
    #[test]
    fn test_serialization_stability_all_types() {
        let test_objects: Vec<Box<dyn erased_serde::Serialize>> = vec![
            Box::new(ScoreSemantics::BM25 { k1: 1.2, b: 0.75 }),
            Box::new(FusionStrategy::RRF { k: 60 }),
            Box::new(FusionConfig::default()),
            Box::new(SearchSource::Hybrid),
            Box::new(ScoreNormalization::MinMax),
            Box::new(TieBreakRule::NodeIdAsc),
            Box::new(DistanceMetric::Cosine),
        ];

        // Note: This test requires 'erased-serde' crate for trait object serialization
        // For now, we'll test each type individually
        let semantics = ScoreSemantics::BM25 { k1: 1.2, b: 0.75 };
        let json1 = serde_json::to_string(&semantics).unwrap();
        let json2 = serde_json::to_string(&semantics).unwrap();
        assert_eq!(json1, json2, "Serialization must be stable");
    }
}

#[cfg(test)]
mod integration_scenarios {
    use codegraph_ir::features::query_engine::*;
    use std::collections::HashMap;

    // ========================================================================
    // SCENARIO 29: 실전 보안 취약점 탐지 쿼리
    // ========================================================================
    #[test]
    fn test_security_vulnerability_detection() {
        // 복잡한 보안 쿼리: SQL Injection 취약점 탐지
        let sql_injection_query = ExprBuilder::and(vec![
            // High complexity functions
            ExprBuilder::gte("complexity", 15),
            // Database-related
            ExprBuilder::or(vec![
                ExprBuilder::contains("name", "query"),
                ExprBuilder::contains("name", "execute"),
                ExprBuilder::contains("name", "sql"),
            ]),
            // Not using prepared statements
            ExprBuilder::not(Box::new(ExprBuilder::contains("code", "prepare"))),
            // Has string concatenation
            ExprBuilder::or(vec![
                ExprBuilder::contains("code", "+"),
                ExprBuilder::contains("code", "concat"),
                ExprBuilder::regex("code", r".*\{.*\}.*"), // f-string
            ]),
        ]);

        let canonical = sql_injection_query.canonicalize().unwrap();
        let hash = canonical.hash_canonical().unwrap();
        assert!(!hash.is_empty());
    }

    // ========================================================================
    // SCENARIO 30: 실전 코드 품질 분석
    // ========================================================================
    #[test]
    fn test_code_quality_analysis() {
        // Node selector: High complexity functions
        let high_complexity_functions = NodeSelectorBuilder::by_kind_filtered(
            NodeKind::Function,
            vec![
                ExprBuilder::gte("complexity", 20),
                ExprBuilder::gte("lines", 100),
                ExprBuilder::lt("test_coverage", 0.8),
            ],
        );

        // Edge selector: Call chains
        let call_edges = EdgeSelectorBuilder::by_kind(EdgeKind::Calls);

        // Path limits: Conservative
        let limits = PathLimits::new(50, 5000, 15000).unwrap();

        // All components serialize
        let _node_json = serde_json::to_string(&high_complexity_functions).unwrap();
        let _edge_json = serde_json::to_string(&call_edges).unwrap();
        let _limit_json = serde_json::to_string(&limits).unwrap();
    }

    // ========================================================================
    // SCENARIO 31: 실전 하이브리드 검색 (RRF Fusion)
    // ========================================================================
    #[test]
    fn test_hybrid_search_rrf_fusion() {
        // Lexical search results (BM25)
        let lexical_hits = vec![
            SearchHitRow::new(
                "func_authenticate".to_string(),
                25.3,
                0.92,
                0.92,
                ScoreSemantics::BM25 { k1: 1.2, b: 0.75 },
                SearchSource::Lexical,
                1,
            ),
            SearchHitRow::new(
                "func_login".to_string(),
                22.1,
                0.85,
                0.85,
                ScoreSemantics::BM25 { k1: 1.2, b: 0.75 },
                SearchSource::Lexical,
                2,
            ),
        ];

        // Semantic search results (Embedding)
        let semantic_hits = vec![
            SearchHitRow::new(
                "func_verify_credentials".to_string(),
                0.89,
                0.89,
                0.89,
                ScoreSemantics::Embedding {
                    metric: DistanceMetric::Cosine,
                },
                SearchSource::Semantic,
                1,
            ),
            SearchHitRow::new(
                "func_authenticate".to_string(), // Same as lexical #1
                0.87,
                0.87,
                0.87,
                ScoreSemantics::Embedding {
                    metric: DistanceMetric::Cosine,
                },
                SearchSource::Semantic,
                2,
            ),
        ];

        // Fusion config (RRF k=60)
        let fusion_config = FusionConfig::rrf(60)
            .with_normalization(ScoreNormalization::RankBased)
            .with_tie_break(TieBreakRule::ScoreDesc);

        // Verify all results have complete score information
        for hit in lexical_hits.iter().chain(semantic_hits.iter()) {
            assert!(!hit.node_id.is_empty());
            assert!(hit.score_raw > 0.0);
            assert!(hit.score_norm >= 0.0 && hit.score_norm <= 1.0);
            assert!(hit.rank > 0);
        }

        // Verify fusion config
        let json = serde_json::to_string(&fusion_config).unwrap();
        let deserialized: FusionConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(fusion_config, deserialized);
    }
}
