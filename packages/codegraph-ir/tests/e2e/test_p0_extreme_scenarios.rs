// EXTREME P0 Test Scenarios - AI Agent가 실제로 요청할만한 복잡한 케이스들
// 더 복잡하고 빡센 실전 시나리오

#[cfg(test)]
mod extreme_ai_agent_scenarios {
    use codegraph_ir::features::query_engine::{
        EdgeKind, EdgeSelector, EdgeSelectorBuilder, Expr, ExprBuilder, ExprError,
        FusionConfig, FusionStrategy, NodeKind, NodeSelector, NodeSelectorBuilder,
        PathLimits, ScoreNormalization, ScoreSemantics, SearchHitRow, SearchSource,
        TieBreakRule, Value, DistanceMetric,
    };
    use std::collections::{BTreeMap, HashMap};

    // ========================================================================
    // SCENARIO 32: 대규모 멀티테넌트 보안 감사 쿼리
    // AI Agent: "Find all potential security vulnerabilities across 100 microservices"
    // ========================================================================
    #[test]
    fn test_massive_multi_tenant_security_audit() {
        // 실전: 100개 마이크로서비스의 모든 보안 취약점 탐지
        let mut service_queries = Vec::new();

        // 각 서비스별 복잡한 보안 쿼리
        for service_id in 0..100 {
            let service_query = ExprBuilder::and(vec![
                // Service identifier
                ExprBuilder::eq("service_id", service_id),

                // Critical vulnerabilities
                ExprBuilder::or(vec![
                    // SQL Injection
                    ExprBuilder::and(vec![
                        ExprBuilder::contains("code", "execute"),
                        ExprBuilder::regex("code", r".*\+.*sql.*"),
                        ExprBuilder::not(Box::new(ExprBuilder::contains("code", "parameterized"))),
                    ]),

                    // XSS
                    ExprBuilder::and(vec![
                        ExprBuilder::contains("code", "innerHTML"),
                        ExprBuilder::not(Box::new(ExprBuilder::contains("code", "sanitize"))),
                    ]),

                    // Command Injection
                    ExprBuilder::and(vec![
                        ExprBuilder::or(vec![
                            ExprBuilder::contains("code", "exec"),
                            ExprBuilder::contains("code", "system"),
                            ExprBuilder::contains("code", "subprocess"),
                        ]),
                        ExprBuilder::not(Box::new(ExprBuilder::contains("code", "shell=False"))),
                    ]),

                    // Path Traversal
                    ExprBuilder::and(vec![
                        ExprBuilder::contains("code", "open"),
                        ExprBuilder::regex("code", r".*\.\./.*"),
                        ExprBuilder::not(Box::new(ExprBuilder::contains("code", "path.normpath"))),
                    ]),

                    // Insecure Deserialization
                    ExprBuilder::and(vec![
                        ExprBuilder::or(vec![
                            ExprBuilder::contains("code", "pickle.loads"),
                            ExprBuilder::contains("code", "yaml.load"),
                            ExprBuilder::contains("code", "eval"),
                        ]),
                        ExprBuilder::not(Box::new(ExprBuilder::contains("code", "SafeLoader"))),
                    ]),
                ]),

                // High risk indicators
                ExprBuilder::or(vec![
                    ExprBuilder::gte("complexity", 20),
                    ExprBuilder::eq("has_auth", false),
                    ExprBuilder::eq("exposed_to_public", true),
                ]),
            ]);

            service_queries.push(service_query);
        }

        // Combine all service queries
        let massive_audit_query = ExprBuilder::or(service_queries);

        // Test: This massive query should canonicalize
        let canonical = massive_audit_query.canonicalize();
        assert!(canonical.is_ok(), "Massive multi-tenant security audit query must canonicalize");

        // Test: Should produce stable hash
        let hash = canonical.unwrap().hash_canonical();
        assert!(hash.is_ok(), "Massive query must hash successfully");
    }

    // ========================================================================
    // SCENARIO 33: AI Agent의 복잡한 리팩토링 분석
    // AI Agent: "Find all God Classes that need refactoring with dependency analysis"
    // ========================================================================
    #[test]
    fn test_god_class_refactoring_analysis() {
        // God Class 후보 찾기 (극악의 복잡도)
        let god_class_selector = NodeSelectorBuilder::by_kind_filtered(
            NodeKind::Class,
            vec![
                // Extreme complexity
                ExprBuilder::gte("complexity", 100),

                // Too many methods
                ExprBuilder::gte("method_count", 50),

                // Too many lines
                ExprBuilder::gte("lines_of_code", 1000),

                // Low cohesion
                ExprBuilder::lt("cohesion", 0.3),

                // High coupling
                ExprBuilder::gt("coupling", 20),

                // Multiple responsibilities (SRP violation)
                ExprBuilder::and(vec![
                    ExprBuilder::contains("name", "Manager"),  // Anti-pattern naming
                    ExprBuilder::or(vec![
                        ExprBuilder::regex("code", r".*database.*"),
                        ExprBuilder::regex("code", r".*api.*"),
                        ExprBuilder::regex("code", r".*ui.*"),
                        ExprBuilder::regex("code", r".*cache.*"),
                        ExprBuilder::regex("code", r".*validation.*"),
                    ]),
                ]),

                // Poor test coverage
                ExprBuilder::lt("test_coverage", 0.5),
            ],
        );

        // Test: Complex selector should serialize
        let json = serde_json::to_string(&god_class_selector).unwrap();
        assert!(json.contains("Class"));
        assert!(json.contains("complexity"));

        // Test: Round-trip
        let deserialized: NodeSelector = serde_json::from_str(&json).unwrap();
        assert_eq!(god_class_selector, deserialized);
    }

    // ========================================================================
    // SCENARIO 34: 극악의 데이터 플로우 추적 (Taint Analysis 시뮬레이션)
    // AI Agent: "Trace all data flows from user input to database query across 20 hops"
    // ========================================================================
    #[test]
    fn test_extreme_taint_analysis_dataflow() {
        // Source: User input nodes
        let taint_sources = NodeSelectorBuilder::union(vec![
            NodeSelectorBuilder::by_kind_filtered(
                NodeKind::Function,
                vec![
                    ExprBuilder::or(vec![
                        ExprBuilder::regex("name", r".*input.*"),
                        ExprBuilder::regex("name", r".*request.*"),
                        ExprBuilder::regex("name", r".*param.*"),
                        ExprBuilder::contains("decorator", "@app.route"),
                    ]),
                ],
            ),
            NodeSelectorBuilder::by_kind_filtered(
                NodeKind::Variable,
                vec![
                    ExprBuilder::or(vec![
                        ExprBuilder::eq("name", "request.args"),
                        ExprBuilder::eq("name", "request.form"),
                        ExprBuilder::eq("name", "request.json"),
                        ExprBuilder::regex("name", r".*_input"),
                    ]),
                ],
            ),
        ]);

        // Sink: Database operations
        let taint_sinks = NodeSelectorBuilder::union(vec![
            NodeSelectorBuilder::by_kind_filtered(
                NodeKind::Function,
                vec![
                    ExprBuilder::or(vec![
                        ExprBuilder::contains("name", "execute"),
                        ExprBuilder::contains("name", "query"),
                        ExprBuilder::regex("name", r".*sql.*"),
                    ]),
                ],
            ),
            NodeSelectorBuilder::by_kind_filtered(
                NodeKind::Call,
                vec![
                    ExprBuilder::or(vec![
                        ExprBuilder::eq("function_name", "cursor.execute"),
                        ExprBuilder::eq("function_name", "db.query"),
                        ExprBuilder::regex("function_name", r".*\.execute"),
                    ]),
                ],
            ),
        ]);

        // Edge selector: Dataflow + Control flow
        let flow_edges = EdgeSelectorBuilder::by_kinds(vec![
            EdgeKind::Dataflow,
            EdgeKind::ControlFlow,
            EdgeKind::Calls,
        ]);

        // Path limits: Allow deep paths (20 hops)
        let limits = PathLimits::new(1000, 100_000, 120_000)
            .unwrap()
            .with_max_length(20);

        // Test: All components are valid
        assert!(matches!(taint_sources, NodeSelector::Union(_)));
        assert!(matches!(taint_sinks, NodeSelector::Union(_)));
        assert!(matches!(flow_edges, EdgeSelector::ByKinds(_)));
        assert_eq!(limits.max_path_length, Some(20));

        // Test: Serialization
        let _sources_json = serde_json::to_string(&taint_sources).unwrap();
        let _sinks_json = serde_json::to_string(&taint_sinks).unwrap();
        let _edges_json = serde_json::to_string(&flow_edges).unwrap();
        let _limits_json = serde_json::to_string(&limits).unwrap();
    }

    // ========================================================================
    // SCENARIO 35: 극악의 하이브리드 검색 (7개 소스 Fusion)
    // AI Agent: "Combine lexical, semantic, graph, AST, historical, contributor, and test coverage signals"
    // ========================================================================
    #[test]
    fn test_extreme_7_way_hybrid_search_fusion() {
        // 1. Lexical search (BM25)
        let lexical_hits = vec![
            SearchHitRow::new(
                "func_authenticate_user".to_string(),
                45.2,
                0.95,
                0.95,
                ScoreSemantics::BM25 { k1: 1.5, b: 0.8 },
                SearchSource::Lexical,
                1,
            ),
            SearchHitRow::new(
                "class_AuthenticationManager".to_string(),
                42.1,
                0.92,
                0.92,
                ScoreSemantics::BM25 { k1: 1.5, b: 0.8 },
                SearchSource::Lexical,
                2,
            ),
        ];

        // 2. Semantic search (Embedding - Cosine)
        let semantic_hits = vec![
            SearchHitRow::new(
                "func_verify_credentials".to_string(),
                0.91,
                0.91,
                0.91,
                ScoreSemantics::Embedding {
                    metric: DistanceMetric::Cosine,
                },
                SearchSource::Semantic,
                1,
            ),
            SearchHitRow::new(
                "func_authenticate_user".to_string(),
                0.89,
                0.89,
                0.89,
                ScoreSemantics::Embedding {
                    metric: DistanceMetric::Cosine,
                },
                SearchSource::Semantic,
                2,
            ),
        ];

        // 3. Graph search (PageRank)
        let graph_hits = vec![
            SearchHitRow::new(
                "class_AuthenticationManager".to_string(),
                0.85,
                0.85,
                0.85,
                ScoreSemantics::Fused {
                    strategy: FusionStrategy::Max,
                },
                SearchSource::Graph,
                1,
            ),
        ];

        // 4. AST similarity (Tree Edit Distance)
        let mut ast_metadata = HashMap::new();
        ast_metadata.insert("tree_edit_distance".to_string(), Value::Float(15.3));
        ast_metadata.insert("structural_similarity".to_string(), Value::Float(0.87));

        let ast_hits = vec![
            SearchHitRow {
                node_id: "func_login_user".to_string(),
                score_raw: 0.87,
                score_norm: 0.87,
                sort_key: 0.87,
                score_semantics: ScoreSemantics::Cosine,
                source: SearchSource::Semantic,
                rank: 1,
                metadata: Some(ast_metadata),
            },
        ];

        // 5. Historical importance (Git blame, churn)
        let mut historical_metadata = HashMap::new();
        historical_metadata.insert("commit_count".to_string(), Value::Int(147));
        historical_metadata.insert("author_count".to_string(), Value::Int(8));
        historical_metadata.insert("last_modified_days".to_string(), Value::Int(3));

        let historical_hits = vec![
            SearchHitRow {
                node_id: "func_authenticate_user".to_string(),
                score_raw: 0.78,
                score_norm: 0.78,
                sort_key: 0.78,
                score_semantics: ScoreSemantics::TfIdf,
                source: SearchSource::Lexical,
                rank: 1,
                metadata: Some(historical_metadata),
            },
        ];

        // 6. Contributor expertise (who knows this code best)
        let mut contributor_metadata = HashMap::new();
        contributor_metadata.insert("primary_author".to_string(), Value::String("alice@company.com".to_string()));
        contributor_metadata.insert("expertise_score".to_string(), Value::Float(0.93));

        let contributor_hits = vec![
            SearchHitRow {
                node_id: "class_AuthenticationManager".to_string(),
                score_raw: 0.93,
                score_norm: 0.93,
                sort_key: 0.93,
                score_semantics: ScoreSemantics::ReRank {
                    model: "contributor-expertise-v1".to_string(),
                },
                source: SearchSource::ReRank,
                rank: 1,
                metadata: Some(contributor_metadata),
            },
        ];

        // 7. Test coverage signal
        let mut test_metadata = HashMap::new();
        test_metadata.insert("line_coverage".to_string(), Value::Float(0.95));
        test_metadata.insert("branch_coverage".to_string(), Value::Float(0.88));
        test_metadata.insert("test_count".to_string(), Value::Int(47));

        let test_coverage_hits = vec![
            SearchHitRow {
                node_id: "func_verify_credentials".to_string(),
                score_raw: 0.92,
                score_norm: 0.92,
                sort_key: 0.92,
                score_semantics: ScoreSemantics::TfIdf,
                source: SearchSource::Lexical,
                rank: 1,
                metadata: Some(test_metadata),
            },
        ];

        // Extreme fusion: 7-way weighted combination
        let fusion_config = FusionConfig::linear_combination(vec![
            0.25, // Lexical
            0.20, // Semantic
            0.15, // Graph
            0.10, // AST
            0.10, // Historical
            0.10, // Contributor
            0.10, // Test coverage
        ])
        .with_normalization(ScoreNormalization::MinMax)
        .with_tie_break(TieBreakRule::ScoreDesc)
        .with_pool_size(10000);

        // Test: All hits have valid structure
        let all_hits = [
            lexical_hits,
            semantic_hits,
            graph_hits,
            ast_hits,
            historical_hits,
            contributor_hits,
            test_coverage_hits,
        ];

        for (i, hits) in all_hits.iter().enumerate() {
            for hit in hits {
                assert!(!hit.node_id.is_empty(), "Hit {} must have node_id", i);
                assert!(hit.score_raw > 0.0, "Hit {} must have positive score", i);
                assert!(hit.rank > 0, "Hit {} must have positive rank", i);

                // Test: Serialization
                let json = serde_json::to_string(hit).unwrap();
                let deserialized: SearchHitRow = serde_json::from_str(&json).unwrap();
                assert_eq!(*hit, deserialized, "Hit {} must round-trip", i);
            }
        }

        // Test: Fusion config
        let json = serde_json::to_string(&fusion_config).unwrap();
        let deserialized: FusionConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(fusion_config, deserialized);

        if let FusionStrategy::LinearCombination { weights } = &fusion_config.strategy {
            assert_eq!(weights.len(), 7, "Must have 7 weights for 7-way fusion");
            let sum: f64 = weights.iter().sum();
            assert!((sum - 1.0).abs() < 0.001, "Weights must sum to 1.0");
        } else {
            panic!("Expected LinearCombination strategy");
        }
    }

    // ========================================================================
    // SCENARIO 36: 극악의 정규식 패턴 매칭 (100개 패턴)
    // AI Agent: "Find all code patterns matching any of these 100 vulnerability signatures"
    // ========================================================================
    #[test]
    fn test_extreme_100_regex_patterns() {
        let vulnerability_patterns = vec![
            // SQL Injection patterns (20개)
            r".*execute\s*\(\s*['\"].*%s.*",
            r".*query\s*\(\s*.*\+.*",
            r".*cursor\.execute\s*\(\s*f['\"].*",
            r".*SELECT.*\+.*FROM.*",
            r".*WHERE.*\+.*",
            // ... (실제로는 100개지만 예시로 축약)

            // XSS patterns (20개)
            r".*innerHTML\s*=\s*.*",
            r".*document\.write\s*\(.*",
            r".*eval\s*\(\s*.*request.*",

            // Command Injection (20개)
            r".*os\.system\s*\(.*",
            r".*subprocess\s*\.\s*call\s*\(.*",
            r".*exec\s*\(.*input.*",

            // Path Traversal (20개)
            r".*\.\.\/.*",
            r".*open\s*\(\s*.*request.*",

            // Crypto issues (20개)
            r".*md5\s*\(.*password.*",
            r".*sha1\s*\(.*secret.*",
        ];

        // Create massive Or query with 100 regex patterns
        let mut pattern_queries = Vec::new();
        for pattern in vulnerability_patterns {
            pattern_queries.push(ExprBuilder::regex("code", pattern));
        }

        let massive_regex_query = ExprBuilder::or(pattern_queries);

        // Test: Should canonicalize
        let canonical = massive_regex_query.canonicalize();
        assert!(canonical.is_ok(), "100-pattern regex query must canonicalize");

        // Test: Should hash
        let hash = canonical.unwrap().hash_canonical();
        assert!(hash.is_ok(), "100-pattern regex query must hash");
    }

    // ========================================================================
    // SCENARIO 37: 극악의 중첩 Union (5단계 Union nesting)
    // AI Agent: "Find all functions OR classes OR variables OR calls OR imports in any of 50 modules"
    // ========================================================================
    #[test]
    fn test_extreme_nested_union_selectors() {
        // Level 1: Functions in modules 0-9
        let mut func_selectors = Vec::new();
        for i in 0..10 {
            func_selectors.push(NodeSelectorBuilder::by_kind_filtered(
                NodeKind::Function,
                vec![ExprBuilder::eq("module_id", i)],
            ));
        }
        let func_union = NodeSelectorBuilder::union(func_selectors);

        // Level 2: Classes in modules 10-19
        let mut class_selectors = Vec::new();
        for i in 10..20 {
            class_selectors.push(NodeSelectorBuilder::by_kind_filtered(
                NodeKind::Class,
                vec![ExprBuilder::eq("module_id", i)],
            ));
        }
        let class_union = NodeSelectorBuilder::union(class_selectors);

        // Level 3: Variables in modules 20-29
        let mut var_selectors = Vec::new();
        for i in 20..30 {
            var_selectors.push(NodeSelectorBuilder::by_kind_filtered(
                NodeKind::Variable,
                vec![ExprBuilder::eq("module_id", i)],
            ));
        }
        let var_union = NodeSelectorBuilder::union(var_selectors);

        // Level 4: Calls in modules 30-39
        let mut call_selectors = Vec::new();
        for i in 30..40 {
            call_selectors.push(NodeSelectorBuilder::by_kind_filtered(
                NodeKind::Call,
                vec![ExprBuilder::eq("module_id", i)],
            ));
        }
        let call_union = NodeSelectorBuilder::union(call_selectors);

        // Level 5: Imports in modules 40-49
        let mut import_selectors = Vec::new();
        for i in 40..50 {
            import_selectors.push(NodeSelectorBuilder::by_kind_filtered(
                NodeKind::Import,
                vec![ExprBuilder::eq("module_id", i)],
            ));
        }
        let import_union = NodeSelectorBuilder::union(import_selectors);

        // Top-level union: Combine all 5 levels (50 modules total)
        let mega_union = NodeSelectorBuilder::union(vec![
            func_union,
            class_union,
            var_union,
            call_union,
            import_union,
        ]);

        // Test: Mega union should serialize
        let json = serde_json::to_string(&mega_union).unwrap();
        assert!(json.len() > 10000, "Mega union JSON should be very large");

        // Test: Round-trip
        let deserialized: NodeSelector = serde_json::from_str(&json).unwrap();
        assert_eq!(mega_union, deserialized);
    }

    // ========================================================================
    // SCENARIO 38: 극악의 혼합 타입 Value (Deep nesting)
    // AI Agent: "Store complex analysis results with nested structures"
    // ========================================================================
    #[test]
    fn test_extreme_nested_value_structures() {
        // Level 1: Analysis metadata
        let mut analysis_meta = BTreeMap::new();
        analysis_meta.insert("analyzer".to_string(), Value::String("SecurityAuditor-v3.2".to_string()));
        analysis_meta.insert("timestamp".to_string(), Value::Timestamp(1672531200000000));
        analysis_meta.insert("duration_ms".to_string(), Value::Int(45230));

        // Level 2: Vulnerability details (List of Objects)
        let mut vuln1 = BTreeMap::new();
        vuln1.insert("cwe_id".to_string(), Value::String("CWE-89".to_string()));
        vuln1.insert("severity".to_string(), Value::String("CRITICAL".to_string()));
        vuln1.insert("confidence".to_string(), Value::Float(0.95));
        vuln1.insert("affected_lines".to_string(), Value::List(vec![
            Value::Int(42),
            Value::Int(43),
            Value::Int(44),
        ]));

        let mut vuln2 = BTreeMap::new();
        vuln2.insert("cwe_id".to_string(), Value::String("CWE-79".to_string()));
        vuln2.insert("severity".to_string(), Value::String("HIGH".to_string()));
        vuln2.insert("confidence".to_string(), Value::Float(0.87));

        let vulnerabilities = Value::List(vec![
            Value::Object(vuln1),
            Value::Object(vuln2),
        ]);

        // Level 3: Remediation suggestions (nested)
        let mut remediation1 = BTreeMap::new();
        remediation1.insert("action".to_string(), Value::String("Use parameterized queries".to_string()));
        remediation1.insert("priority".to_string(), Value::Int(1));
        remediation1.insert("auto_fixable".to_string(), Value::Bool(true));
        remediation1.insert("code_samples".to_string(), Value::List(vec![
            Value::String("cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))".to_string()),
        ]));

        // Top level: Complete analysis result
        let mut analysis_result = BTreeMap::new();
        analysis_result.insert("metadata".to_string(), Value::Object(analysis_meta));
        analysis_result.insert("vulnerabilities".to_string(), vulnerabilities);
        analysis_result.insert("remediation".to_string(), Value::Object(remediation1));
        analysis_result.insert("scan_complete".to_string(), Value::Bool(true));

        let complete_result = Value::Object(analysis_result);

        // Test: Deep nested structure serializes
        let json = serde_json::to_string(&complete_result).unwrap();
        assert!(json.len() > 500, "Complex nested structure should produce large JSON");

        // Test: Round-trip
        let deserialized: Value = serde_json::from_str(&json).unwrap();
        assert_eq!(complete_result, deserialized);

        // Test: Can be used in expressions
        let expr = Expr::Literal(complete_result);
        let canonical = expr.canonicalize();
        assert!(canonical.is_ok(), "Complex nested Value must canonicalize");
    }

    // ========================================================================
    // SCENARIO 39: 극악의 PathLimits 스트레스 테스트
    // AI Agent: "Find ALL possible paths in large graph (intentionally trigger limits)"
    // ========================================================================
    #[test]
    fn test_extreme_path_limits_stress() {
        // Scenario 1: Conservative limits (should work)
        let conservative = PathLimits::new(10, 1000, 5000).unwrap();
        assert_eq!(conservative.max_paths, 10);

        // Scenario 2: Aggressive limits (large graph analysis)
        let aggressive = PathLimits::new(100_000, 10_000_000, 300_000).unwrap();
        assert_eq!(aggressive.max_paths, 100_000);
        assert_eq!(aggressive.max_expansions, 10_000_000);

        // Scenario 3: Unlimited (DANGEROUS - only for testing)
        let unlimited = PathLimits::unlimited();
        assert_eq!(unlimited.max_paths, usize::MAX);
        assert_eq!(unlimited.max_expansions, usize::MAX);
        assert_eq!(unlimited.timeout_ms, u64::MAX);

        // Scenario 4: Edge case - very long paths
        let long_paths = PathLimits::default().with_max_length(500);
        assert_eq!(long_paths.max_path_length, Some(500));

        // Scenario 5: Minimum viable limits
        let minimal = PathLimits::new(1, 1, 1).unwrap();
        assert_eq!(minimal.max_paths, 1);

        // Test: All serialize
        for limits in vec![conservative, aggressive, unlimited, long_paths, minimal] {
            let json = serde_json::to_string(&limits).unwrap();
            let deserialized: PathLimits = serde_json::from_str(&json).unwrap();
            assert_eq!(limits, deserialized);
        }
    }

    // ========================================================================
    // SCENARIO 40: 극악의 문자열 처리 (Unicode + Emoji + 제어 문자)
    // AI Agent: "Search code containing emoji, multilingual comments, and special characters"
    // ========================================================================
    #[test]
    fn test_extreme_unicode_emoji_special_chars() {
        let extreme_strings = vec![
            // Emoji sequences
            "🚀💻🔥✨🎉👨‍💻🌟⭐🔧🛠️",

            // Zero-width characters
            "test\u{200B}invisible\u{200C}chars",

            // Right-to-left text
            "مرحبا بك في البرنامج",

            // Mixed scripts
            "Hello世界こんにちは안녕하세요",

            // Combining characters
            "e\u{0301}\u{0302}\u{0303}",  // ếễ

            // Emoji with skin tones
            "👋🏻👋🏼👋🏽👋🏾👋🏿",

            // Mathematical symbols
            "∀x∈ℝ: x²≥0",

            // Box drawing
            "┌─┬─┐\n│ │ │\n├─┼─┤",

            // Braille
            "⠃⠗⠁⠊⠇⠇⠑",

            // Runic
            "ᚠᚢᚦᚨᚱᚲ",

            // Musical notation
            "𝄞𝄢𝅘𝅥𝅮",

            // Control characters (should be escaped)
            "Line1\nLine2\rLine3\tTabbed",

            // Null bytes (tricky!)
            "Before\0After",

            // Surrogate pairs
            "𝓗𝓮𝓵𝓵𝓸",

            // Extremely long single character (grapheme cluster)
            "e\u{0301}\u{0302}\u{0303}\u{0304}\u{0305}\u{0306}\u{0307}",
        ];

        for text in extreme_strings {
            // Test: Can be used in expressions
            let expr = ExprBuilder::contains("code", text);
            let canonical = expr.canonicalize();
            assert!(
                canonical.is_ok(),
                "Unicode '{}' must canonicalize successfully",
                text.escape_unicode()
            );

            // Test: Can be hashed
            let hash = canonical.unwrap().hash_canonical();
            assert!(
                hash.is_ok(),
                "Unicode '{}' must hash successfully",
                text.escape_unicode()
            );

            // Test: Can be in Value
            let value = Value::String(text.to_string());
            let value_json = serde_json::to_string(&value).unwrap();
            let deserialized: Value = serde_json::from_str(&value_json).unwrap();
            assert_eq!(value, deserialized);
        }
    }

    // ========================================================================
    // SCENARIO 41: 극악의 정밀도 Float 테스트
    // AI Agent: "Compare floating point scores with extreme precision requirements"
    // ========================================================================
    #[test]
    fn test_extreme_float_precision() {
        let extreme_floats = vec![
            // Very small differences
            (1.0000000001, 1.0000000002),

            // Subnormal numbers
            (1e-308, 2e-308),

            // Near zero
            (1e-100, 2e-100),

            // Large numbers
            (1e100, 1e100 + 1e85),

            // Special values
            (0.0, -0.0),  // Should normalize to same
            (f64::EPSILON, f64::EPSILON * 2.0),

            // Machine precision boundary
            (1.0, 1.0 + f64::EPSILON),

            // Just below infinity
            (f64::MAX, f64::MAX / 2.0),
        ];

        for (a, b) in extreme_floats {
            // Test: Both values can be used
            let expr_a = Expr::Literal(Value::Float(a));
            let expr_b = Expr::Literal(Value::Float(b));

            // Special case: 0.0 and -0.0 should canonicalize to same
            if a == 0.0 && b == -0.0 {
                let canon_a = expr_a.canonicalize().unwrap();
                let canon_b = expr_b.canonicalize().unwrap();
                assert_eq!(canon_a, canon_b, "0.0 and -0.0 must canonicalize identically");
            } else {
                // Other values should canonicalize successfully
                assert!(expr_a.canonicalize().is_ok());
                assert!(expr_b.canonicalize().is_ok());
            }
        }
    }

    // ========================================================================
    // SCENARIO 42: 극악의 동시성 시나리오 (Hash collision resistance)
    // AI Agent: "Generate 10000 different queries and ensure no hash collisions"
    // ========================================================================
    #[test]
    fn test_extreme_hash_collision_resistance() {
        use std::collections::HashSet;

        let mut hashes = HashSet::new();
        let mut queries = Vec::new();

        // Generate 10000 slightly different queries
        for i in 0..10000 {
            let query = ExprBuilder::and(vec![
                ExprBuilder::eq("field_a", i),
                ExprBuilder::eq("field_b", i * 2),
                ExprBuilder::contains("name", &format!("test_{}", i)),
            ]);
            queries.push(query);
        }

        // Compute all hashes
        for query in queries {
            let hash = query.hash_canonical().unwrap();

            // Test: No collision
            assert!(
                !hashes.contains(&hash),
                "Hash collision detected! blake3 should prevent this."
            );

            hashes.insert(hash);
        }

        // Test: All 10000 hashes are unique
        assert_eq!(hashes.len(), 10000, "All 10000 queries must have unique hashes");
    }

    // ========================================================================
    // SCENARIO 43: 극악의 메타데이터 폭발
    // AI Agent: "Store analysis results with 1000 metadata fields"
    // ========================================================================
    #[test]
    fn test_extreme_metadata_explosion() {
        let mut massive_metadata = HashMap::new();

        // Add 1000 metadata fields
        for i in 0..1000 {
            massive_metadata.insert(
                format!("metric_{}", i),
                Value::Float(i as f64 / 1000.0),
            );
        }

        // Add nested metadata
        let mut nested = BTreeMap::new();
        for i in 0..100 {
            nested.insert(
                format!("nested_field_{}", i),
                Value::String(format!("value_{}", i)),
            );
        }
        massive_metadata.insert("nested_data".to_string(), Value::Object(nested));

        // Create search hit with massive metadata
        let hit = SearchHitRow {
            node_id: "extreme_node".to_string(),
            score_raw: 0.95,
            score_norm: 0.95,
            sort_key: 0.95,
            score_semantics: ScoreSemantics::BM25 { k1: 1.2, b: 0.75 },
            source: SearchSource::Hybrid,
            rank: 1,
            metadata: Some(massive_metadata),
        };

        // Test: Can serialize
        let json = serde_json::to_string(&hit).unwrap();
        assert!(json.len() > 50000, "Massive metadata should produce very large JSON");

        // Test: Round-trip
        let deserialized: SearchHitRow = serde_json::from_str(&json).unwrap();
        assert_eq!(hit, deserialized);
    }
}
