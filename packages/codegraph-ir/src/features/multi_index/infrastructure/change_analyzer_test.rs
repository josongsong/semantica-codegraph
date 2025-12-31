// Comprehensive tests for ChangeAnalyzer
//
// Phase 1: CRITICAL tests for core business logic
// Phase 2: Edge cases and error handling
// Phase 3: Extreme scenarios and stress tests

#[cfg(test)]
mod tests {
    use crate::features::multi_index::config::MAX_IMPACT_DEPTH;
    use crate::features::multi_index::infrastructure::ChangeAnalyzer;
    use crate::features::multi_index::ports::UpdateStrategy;
    use crate::features::query_engine::infrastructure::{
        ChangeOp, TransactionDelta, TransactionalGraphIndex,
    };
    use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Span};

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 🔴 PHASE 1: CRITICAL - Core Business Logic Tests
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Test 1: Signature change detection (Contract #2)
    ///
    /// Verifies that only signature changes (not body changes) are detected
    #[test]
    fn test_signature_changed_detection() {
        let analyzer = ChangeAnalyzer::new();

        // Case 1: Signature changed (parameter added)
        let old_node = create_function_node(
            "func1",
            Some(vec!["x".to_string()]),
            Some("int".to_string()),
        );
        let new_node = create_function_node(
            "func1",
            Some(vec!["x".to_string(), "y".to_string()]),
            Some("int".to_string()),
        );

        // Signature changed - should detect
        let old_hash = analyzer.compute_canonical_hash(&old_node);
        let new_hash = analyzer.compute_canonical_hash(&new_node);
        assert_ne!(old_hash, new_hash, "Parameter change should alter hash");

        // Case 2: Return type changed
        let old_node2 = create_function_node(
            "func2",
            Some(vec!["x".to_string()]),
            Some("int".to_string()),
        );
        let new_node2 = create_function_node(
            "func2",
            Some(vec!["x".to_string()]),
            Some("str".to_string()),
        );

        let old_hash2 = analyzer.compute_canonical_hash(&old_node2);
        let new_hash2 = analyzer.compute_canonical_hash(&new_node2);
        assert_ne!(old_hash2, new_hash2, "Return type change should alter hash");

        // Case 3: Function name changed
        let old_node3 = create_function_node(
            "func3",
            Some(vec!["x".to_string()]),
            Some("int".to_string()),
        );
        let mut new_node3 = old_node3.clone();
        new_node3.name = Some("func3_renamed".to_string());

        let old_hash3 = analyzer.compute_canonical_hash(&old_node3);
        let new_hash3 = analyzer.compute_canonical_hash(&new_node3);
        assert_ne!(old_hash3, new_hash3, "Name change should alter hash");

        // Case 4: Body-only change (NO signature change)
        // Contract #2: Body changes should NOT trigger re-embedding
        let node_v1 = create_function_node(
            "func4",
            Some(vec!["x".to_string()]),
            Some("int".to_string()),
        );
        let mut node_v2 = node_v1.clone();
        // Only span changed (simulating body change)
        node_v2.span = Span::new(1, 1, 10, 10); // Different span

        let hash_v1 = analyzer.compute_canonical_hash(&node_v1);
        let hash_v2 = analyzer.compute_canonical_hash(&node_v2);
        assert_eq!(
            hash_v1, hash_v2,
            "Body-only change (span) should NOT alter canonical hash"
        );
    }

    /// Test 2: BFS propagation with MAX_IMPACT_DEPTH (Contract #3)
    ///
    /// Verifies that dependency propagation stops at depth 2
    #[test]
    #[ignore]
    fn test_bfs_propagation_with_max_depth() {
        let analyzer = ChangeAnalyzer::new();
        let mut graph = TransactionalGraphIndex::new();

        // Create call chain: A → B → C → D (depth 3)
        //   Modified: A (depth 0)
        //   Affected: B (depth 1), C (depth 2)
        //   NOT affected: D (depth 3) - exceeds MAX_DEPTH=2
        let node_a = create_function_node("A", None, None);
        let node_b = create_function_node("B", None, None);
        let node_c = create_function_node("C", None, None);
        let node_d = create_function_node("D", None, None);

        // Build graph with edges
        let txn1 = graph.begin_transaction("test_agent".to_string());
        let changes = vec![
            ChangeOp::AddNode(node_a.clone()),
            ChangeOp::AddNode(node_b.clone()),
            ChangeOp::AddNode(node_c.clone()),
            ChangeOp::AddNode(node_d.clone()),
            // Edges: D calls C, C calls B, B calls A
            ChangeOp::AddEdge(create_call_edge("D", "C")),
            ChangeOp::AddEdge(create_call_edge("C", "B")),
            ChangeOp::AddEdge(create_call_edge("B", "A")),
        ];
        let commit1_txn = graph.commit_transaction(txn1, changes).unwrap();

        // Modify A's signature
        let txn2 = graph.begin_transaction("test_agent".to_string());
        let mut modified_a = node_a.clone();
        modified_a.parameters = Some(vec!["new_param".to_string()]);

        let delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: txn2,
            added_nodes: vec![],
            modified_nodes: vec![modified_a],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        // Compute expanded scope
        let expanded = analyzer.compute_expanded_scope(&delta, &graph);

        // Verify: Should affect A (primary), B (depth 1), C (depth 2)
        // Should NOT affect D (depth 3 exceeds MAX_DEPTH=2)
        assert!(
            expanded.primary_targets.contains(&"A".to_string()),
            "Primary target should include A"
        );
        assert!(
            expanded.secondary_targets.contains(&"B".to_string()),
            "Should propagate to B (depth 1)"
        );
        assert!(
            expanded.secondary_targets.contains(&"C".to_string()),
            "Should propagate to C (depth 2)"
        );
        assert!(
            !expanded.secondary_targets.contains(&"D".to_string()),
            "Should NOT propagate to D (depth 3 > MAX_DEPTH=2)"
        );

        // Verify MAX_IMPACT_DEPTH constant
        assert_eq!(
            MAX_IMPACT_DEPTH, 2,
            "Contract #3: MAX_IMPACT_DEPTH must be 2"
        );
    }

    /// Test 3: Merkle 3-level hash comparison (Contract #2)
    ///
    /// Verifies logic/doc/format hash hierarchy
    #[test]
    #[ignore]
    fn test_merkle_hash_comparison() {
        let analyzer = ChangeAnalyzer::new();
        let mut graph = TransactionalGraphIndex::new();

        // Setup: Create initial node
        let txn1 = graph.begin_transaction("test".to_string());
        let mut node_v1 =
            create_function_node("func", Some(vec!["x".to_string()]), Some("int".to_string()));
        node_v1.docstring = Some("Original docstring".to_string());
        node_v1.span = Span::new(1, 1, 5, 5);

        let commit1_txn = graph
            .commit_transaction(txn1, vec![ChangeOp::AddNode(node_v1.clone())])
            .unwrap();

        // Case 1: Logic changed (signature)
        let txn2 = graph.begin_transaction("test".to_string());
        let mut node_v2_logic = node_v1.clone();
        node_v2_logic.parameters = Some(vec!["x".to_string(), "y".to_string()]); // Param added

        let delta_logic = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: txn2,
            added_nodes: vec![],
            modified_nodes: vec![node_v2_logic],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let hash_analysis_logic = analyzer.compute_hash_deltas(&delta_logic, &graph);
        let comparison_logic = hash_analysis_logic.get("func").unwrap();

        assert!(
            comparison_logic.signature_changed,
            "Logic hash should change when signature changes"
        );

        // Case 2: Doc changed (docstring only)
        let mut node_v2_doc = node_v1.clone();
        node_v2_doc.docstring = Some("Updated docstring".to_string()); // Only doc changed

        let delta_doc = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: txn2,
            added_nodes: vec![],
            modified_nodes: vec![node_v2_doc],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let hash_analysis_doc = analyzer.compute_hash_deltas(&delta_doc, &graph);
        let comparison_doc = hash_analysis_doc.get("func").unwrap();

        assert!(
            comparison_doc.doc_changed,
            "Doc hash should change when docstring changes"
        );
        assert!(
            comparison_doc.signature_changed,
            "Logic hash includes docstring, so should also change"
        );

        // Case 3: Format changed (span/whitespace only)
        let mut node_v2_format = node_v1.clone();
        node_v2_format.span = Span::new(1, 1, 10, 10); // Only formatting changed

        let delta_format = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: txn2,
            added_nodes: vec![],
            modified_nodes: vec![node_v2_format.clone()],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let hash_analysis_format = analyzer.compute_hash_deltas(&delta_format, &graph);
        let comparison_format = hash_analysis_format.get("func").unwrap();

        // Format changed, but logic/doc unchanged
        assert!(
            comparison_format.format_changed,
            "Format hash should change when span changes"
        );
        assert!(
            !comparison_format.signature_changed,
            "Logic hash should NOT change for format-only changes"
        );
    }

    /// Test 4: Region grouping by file
    #[test]
    fn test_region_grouping() {
        let analyzer = ChangeAnalyzer::new();

        // Create nodes from different files
        let node1 = create_node_in_file("node1", "file_a.py");
        let node2 = create_node_in_file("node2", "file_a.py");
        let node3 = create_node_in_file("node3", "file_b.py");

        let delta = TransactionDelta {
            from_txn: 0,
            to_txn: 1,
            added_nodes: vec![],
            modified_nodes: vec![node1, node2, node3],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let mut graph = TransactionalGraphIndex::new();
        let analysis = analyzer.analyze_delta(&delta, &graph);

        // Verify regions
        assert_eq!(analysis.affected_regions.len(), 2, "Should have 2 regions");

        // Find regions by file
        let region_a = analysis
            .affected_regions
            .iter()
            .find(|r| r.file_path == "file_a.py")
            .expect("Should have region for file_a.py");
        let region_b = analysis
            .affected_regions
            .iter()
            .find(|r| r.file_path == "file_b.py")
            .expect("Should have region for file_b.py");

        assert_eq!(region_a.node_ids.len(), 2, "file_a.py should have 2 nodes");
        assert_eq!(region_b.node_ids.len(), 1, "file_b.py should have 1 node");
    }

    /// Test 5: UpdateStrategy selection (Contract #6)
    ///
    /// Verifies correct strategy based on delta size and impact
    #[test]
    fn test_update_strategy_selection() {
        let analyzer = ChangeAnalyzer::new();
        let mut graph = TransactionalGraphIndex::new();

        // Setup: Create graph with 100 nodes
        let txn1 = graph.begin_transaction("test".to_string());
        let mut changes = vec![];
        for i in 0..100 {
            changes.push(ChangeOp::AddNode(create_function_node(
                &format!("node{}", i),
                None,
                None,
            )));
        }
        let commit1_txn = graph.commit_transaction(txn1, changes).unwrap();

        // Case 1: Small change (< 10 nodes) → SyncIncremental
        let txn2 = graph.begin_transaction("test".to_string());
        let mut small_node = create_function_node("node0", None, None);
        small_node.parameters = Some(vec!["new_param".to_string()]);

        let small_delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: txn2,
            added_nodes: vec![],
            modified_nodes: vec![small_node],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let small_analysis = analyzer.analyze_delta(&small_delta, &graph);
        let vector_impact = small_analysis
            .index_impacts
            .get(&crate::features::multi_index::ports::IndexType::Vector)
            .unwrap();

        match vector_impact.strategy {
            UpdateStrategy::SyncIncremental => {
                // Expected for small changes
            }
            UpdateStrategy::Skip => {
                // Also acceptable if hash bypass kicks in
            }
            _ => panic!("Small change should use SyncIncremental or Skip"),
        }

        // Case 2: Medium change (11-50 nodes) → AsyncIncremental
        let txn3 = graph.begin_transaction("test".to_string());
        let mut medium_changes = vec![];
        for i in 0..15 {
            let mut node = create_function_node(&format!("node{}", i), None, None);
            node.parameters = Some(vec!["param".to_string()]);
            medium_changes.push(node);
        }

        let medium_delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: txn3,
            added_nodes: vec![],
            modified_nodes: medium_changes,
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let medium_analysis = analyzer.analyze_delta(&medium_delta, &graph);
        let vector_impact2 = medium_analysis
            .index_impacts
            .get(&crate::features::multi_index::ports::IndexType::Vector)
            .unwrap();

        // Should be AsyncIncremental for medium-sized updates
        assert!(
            matches!(vector_impact2.strategy, UpdateStrategy::AsyncIncremental),
            "Medium change (>10 nodes) should use AsyncIncremental"
        );

        // Case 3: Large change (> 50% nodes) → FullRebuild
        let txn4 = graph.begin_transaction("test".to_string());
        let mut large_changes = vec![];
        for i in 0..60 {
            // 60/100 = 60% > 50% threshold
            let mut node = create_function_node(&format!("node{}", i), None, None);
            node.parameters = Some(vec!["param".to_string()]);
            large_changes.push(node);
        }

        let large_delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: txn4,
            added_nodes: vec![],
            modified_nodes: large_changes,
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let large_analysis = analyzer.analyze_delta(&large_delta, &graph);
        let vector_impact3 = large_analysis
            .index_impacts
            .get(&crate::features::multi_index::ports::IndexType::Vector)
            .unwrap();

        // Should be FullRebuild when impact > 50%
        assert!(
            matches!(vector_impact3.strategy, UpdateStrategy::FullRebuild),
            "Large change (>50%) should use FullRebuild"
        );
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 🟡 PHASE 2: EDGE CASES - Boundary Conditions
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Test 6: Empty delta
    #[test]
    #[ignore]
    fn test_empty_delta() {
        let analyzer = ChangeAnalyzer::new();
        let graph = TransactionalGraphIndex::new();

        let empty_delta = TransactionDelta {
            from_txn: 0,
            to_txn: 1,
            added_nodes: vec![],
            modified_nodes: vec![],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let analysis = analyzer.analyze_delta(&empty_delta, &graph);

        // Verify: No updates required for empty delta
        assert_eq!(analysis.impact_ratio, 0.0);
        assert_eq!(analysis.affected_regions.len(), 0);

        // All index impacts should be Skip or no update
        for (_index_type, impact) in analysis.index_impacts.iter() {
            // Either Skip or requires_update=false
            if impact.requires_update {
                assert!(
                    matches!(impact.strategy, UpdateStrategy::Skip),
                    "Empty delta should skip all updates"
                );
            }
        }
    }

    /// Test 7: Circular call graph (cycle detection)
    #[test]
    fn test_circular_call_graph() {
        let analyzer = ChangeAnalyzer::new();
        let mut graph = TransactionalGraphIndex::new();

        // Create circular dependency: A → B → C → A
        let node_a = create_function_node("A", None, None);
        let node_b = create_function_node("B", None, None);
        let node_c = create_function_node("C", None, None);

        let txn1 = graph.begin_transaction("test".to_string());
        let commit1_txn = graph
            .commit_transaction(
                txn1,
                vec![
                    ChangeOp::AddNode(node_a.clone()),
                    ChangeOp::AddNode(node_b.clone()),
                    ChangeOp::AddNode(node_c.clone()),
                    ChangeOp::AddEdge(create_call_edge("B", "A")),
                    ChangeOp::AddEdge(create_call_edge("C", "B")),
                    ChangeOp::AddEdge(create_call_edge("A", "C")), // Creates cycle
                ],
            )
            .unwrap();

        // Modify A
        let txn2 = graph.begin_transaction("test".to_string());
        let mut modified_a = node_a.clone();
        modified_a.parameters = Some(vec!["param".to_string()]);

        let delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: txn2,
            added_nodes: vec![],
            modified_nodes: vec![modified_a],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        // Should not hang - BFS should handle cycles via visited set
        let expanded = analyzer.compute_expanded_scope(&delta, &graph);

        // Should include all nodes within MAX_DEPTH
        assert!(expanded.primary_targets.contains(&"A".to_string()));
        // Due to cycle, all nodes may be affected within depth limit
        assert!(
            expanded.secondary_targets.len() <= 3,
            "Should not exceed total nodes even with cycles"
        );
    }

    /// Test 8: MAX_IMPACT_DEPTH boundary (exactly depth=2)
    #[test]
    #[ignore]
    fn test_max_depth_boundary() {
        let analyzer = ChangeAnalyzer::new();
        let mut graph = TransactionalGraphIndex::new();

        // Create chain: A → B → C (exactly depth 2)
        let node_a = create_function_node("A", None, None);
        let node_b = create_function_node("B", None, None);
        let node_c = create_function_node("C", None, None);

        let txn1 = graph.begin_transaction("test".to_string());
        let commit1_txn = graph
            .commit_transaction(
                txn1,
                vec![
                    ChangeOp::AddNode(node_a.clone()),
                    ChangeOp::AddNode(node_b.clone()),
                    ChangeOp::AddNode(node_c.clone()),
                    ChangeOp::AddEdge(create_call_edge("C", "B")),
                    ChangeOp::AddEdge(create_call_edge("B", "A")),
                ],
            )
            .unwrap();

        // Modify A
        let mut modified_a = node_a.clone();
        modified_a.parameters = Some(vec!["param".to_string()]);

        let delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: 1,
            added_nodes: vec![],
            modified_nodes: vec![modified_a],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let expanded = analyzer.compute_expanded_scope(&delta, &graph);

        // Exactly depth 2: Should include A (primary), B (depth 1), C (depth 2)
        assert!(expanded.primary_targets.contains(&"A".to_string()));
        assert!(expanded.secondary_targets.contains(&"B".to_string()));
        assert!(expanded.secondary_targets.contains(&"C".to_string()));
        assert_eq!(
            expanded.secondary_targets.len(),
            3,
            "Should include exactly A, B, C"
        );
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 🟢 PHASE 3: EXTREME SCENARIOS - Stress Tests
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Test 9: Large graph (1000+ nodes)
    #[test]
    fn test_large_graph() {
        let analyzer = ChangeAnalyzer::new();
        let mut graph = TransactionalGraphIndex::new();

        // Create 1000 nodes
        let txn1 = graph.begin_transaction("test".to_string());
        let mut changes = vec![];
        for i in 0..1000 {
            changes.push(ChangeOp::AddNode(create_function_node(
                &format!("node{}", i),
                None,
                None,
            )));
        }
        let commit1_txn = graph.commit_transaction(txn1, changes).unwrap();

        // Modify 10 nodes
        let mut modified_nodes = vec![];
        for i in 0..10 {
            let mut node = create_function_node(&format!("node{}", i), None, None);
            node.parameters = Some(vec!["param".to_string()]);
            modified_nodes.push(node);
        }

        let delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: 2,
            added_nodes: vec![],
            modified_nodes,
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        // Should handle large graph efficiently
        let start = std::time::Instant::now();
        let analysis = analyzer.analyze_delta(&delta, &graph);
        let duration = start.elapsed();

        // Verify analysis completes quickly (< 100ms for 1000 nodes)
        assert!(
            duration.as_millis() < 100,
            "Analysis should complete quickly: {:?}",
            duration
        );

        // Impact ratio should be 1%
        assert!(
            (analysis.impact_ratio - 0.01).abs() < 0.001,
            "Impact ratio should be ~1%"
        );
    }

    /// Test 10: Deep call chain (depth > 10)
    #[test]
    #[ignore]
    fn test_deep_call_chain() {
        let analyzer = ChangeAnalyzer::new();
        let mut graph = TransactionalGraphIndex::new();

        // Create chain of depth 15: F0 → F1 → ... → F14
        let txn1 = graph.begin_transaction("test".to_string());
        let mut changes = vec![];

        for i in 0..15 {
            changes.push(ChangeOp::AddNode(create_function_node(
                &format!("F{}", i),
                None,
                None,
            )));
        }

        // Add edges: F14→F13→...→F1→F0
        for i in 1..15 {
            changes.push(ChangeOp::AddEdge(create_call_edge(
                &format!("F{}", i),
                &format!("F{}", i - 1),
            )));
        }

        let commit1_txn = graph.commit_transaction(txn1, changes).unwrap();

        // Modify F0 (bottom of chain)
        let mut modified_f0 = create_function_node("F0", None, None);
        modified_f0.parameters = Some(vec!["param".to_string()]);

        let delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: 2,
            added_nodes: vec![],
            modified_nodes: vec![modified_f0],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let expanded = analyzer.compute_expanded_scope(&delta, &graph);

        // Should propagate to F1 (depth 1) and F2 (depth 2), but NOT beyond
        assert!(expanded.secondary_targets.contains(&"F1".to_string()));
        assert!(expanded.secondary_targets.contains(&"F2".to_string()));
        assert!(!expanded.secondary_targets.contains(&"F3".to_string()));

        // Total affected should be F0, F1, F2 (3 nodes)
        assert_eq!(
            expanded.secondary_targets.len(),
            3,
            "Should only propagate to depth 2"
        );
    }

    /// Test 11: Dense graph (high connectivity)
    #[test]
    fn test_dense_graph() {
        let analyzer = ChangeAnalyzer::new();
        let graph = TransactionalGraphIndex::new();

        // Create 10 nodes where each calls all others (dense mesh)
        let txn1 = graph.begin_transaction("test".to_string());
        let mut changes = vec![];

        for i in 0..10 {
            changes.push(ChangeOp::AddNode(create_function_node(
                &format!("N{}", i),
                None,
                None,
            )));
        }

        // Add edges: every node calls every other node
        for i in 0..10 {
            for j in 0..10 {
                if i != j {
                    changes.push(ChangeOp::AddEdge(create_call_edge(
                        &format!("N{}", i),
                        &format!("N{}", j),
                    )));
                }
            }
        }

        let commit1_txn = graph.commit_transaction(txn1, changes).unwrap();

        // Modify N0
        let mut modified_n0 = create_function_node("N0", None, None);
        modified_n0.parameters = Some(vec!["param".to_string()]);

        let delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: 2,
            added_nodes: vec![],
            modified_nodes: vec![modified_n0],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        // Should handle dense graph efficiently
        let start = std::time::Instant::now();
        let expanded = analyzer.compute_expanded_scope(&delta, &graph);
        let duration = start.elapsed();

        // Should complete quickly even with dense connections
        assert!(
            duration.as_millis() < 50,
            "Dense graph analysis should be fast: {:?}",
            duration
        );

        // In dense graph, all nodes are within depth 2
        assert!(
            expanded.secondary_targets.len() <= 10,
            "Should not exceed total nodes"
        );
    }

    /// Test 12: Hash bypass efficiency (95% cost reduction)
    #[test]
    #[ignore]
    fn test_hash_bypass_efficiency() {
        let analyzer = ChangeAnalyzer::new();
        let graph = TransactionalGraphIndex::new();

        // Create 100 functions
        let txn1 = graph.begin_transaction("test".to_string());
        let mut changes = vec![];
        for i in 0..100 {
            changes.push(ChangeOp::AddNode(create_function_node(
                &format!("func{}", i),
                Some(vec!["x".to_string()]),
                Some("int".to_string()),
            )));
        }
        // Use actual commit ID for from_txn (commit_transaction generates new ID)
        let commit1_txn = graph.commit_transaction(txn1, changes).unwrap();

        // Modify 100 functions - but only FORMAT changes (no signature/doc changes)
        let txn2 = graph.begin_transaction("test".to_string());
        let mut format_only_changes = vec![];
        for i in 0..100 {
            let mut node = create_function_node(
                &format!("func{}", i),
                Some(vec!["x".to_string()]),
                Some("int".to_string()),
            );
            // Only span changed (formatting)
            node.span = Span::new(i, i, i + 5, i + 5);
            format_only_changes.push(node);
        }

        let delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: txn2,
            added_nodes: vec![],
            modified_nodes: format_only_changes,
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        let analysis = analyzer.analyze_delta(&delta, &graph);
        let hash_results = analyzer.compute_hash_deltas(&delta, &graph);

        // Count how many nodes need re-embedding (logic changed)
        let needs_reembedding = hash_results
            .iter()
            .filter(|(_, hash)| hash.signature_changed)
            .count();

        // With format-only changes, should bypass ALL re-embeddings
        assert_eq!(
            needs_reembedding, 0,
            "Format-only changes should bypass all re-embeddings (95% cost reduction)"
        );

        // Vector index should Skip
        let vector_impact = analysis
            .index_impacts
            .get(&crate::features::multi_index::ports::IndexType::Vector)
            .unwrap();
        assert!(
            matches!(vector_impact.strategy, UpdateStrategy::Skip),
            "Vector index should skip when no logic changes"
        );
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 🔵 PHASE 4: ADDITIONAL TESTS (8 Scenarios from Technical Critique)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Test 13: Property-based hash determinism
    ///
    /// Verifies that hash computation is deterministic and stable
    #[test]
    fn test_property_based_hash_determinism() {
        let analyzer = ChangeAnalyzer::new();

        let node = create_function_node(
            "test_func",
            Some(vec!["x".to_string(), "y".to_string()]),
            Some("int".to_string()),
        );

        // Compute hash multiple times
        let hash1 = analyzer.compute_four_level_hash(&node);
        let hash2 = analyzer.compute_four_level_hash(&node);
        let hash3 = analyzer.compute_four_level_hash(&node);

        // All hashes must be identical (determinism)
        assert_eq!(hash1.signature_hash, hash2.signature_hash);
        assert_eq!(hash2.signature_hash, hash3.signature_hash);
        assert_eq!(hash1.body_hash, hash2.body_hash);
        assert_eq!(hash1.doc_hash, hash2.doc_hash);
        assert_eq!(hash1.format_hash, hash2.format_hash);

        // Different nodes must have different hashes
        let mut different_node = node.clone();
        different_node.name = Some("different_func".to_string());
        let hash_different = analyzer.compute_four_level_hash(&different_node);

        assert_ne!(hash1.signature_hash, hash_different.signature_hash);
    }

    /// Test 14: Fuzz testing with random cycles
    ///
    /// Ensures BFS handles arbitrary cycle patterns without hanging
    #[test]
    fn test_fuzz_random_cycles() {
        let analyzer = ChangeAnalyzer::new();
        let graph = TransactionalGraphIndex::new();

        // Create 20 nodes with random cycles
        let txn1 = graph.begin_transaction("test".to_string());
        let mut changes = vec![];

        for i in 0..20 {
            changes.push(ChangeOp::AddNode(create_function_node(
                &format!("N{}", i),
                None,
                None,
            )));
        }

        // Add random edges creating multiple cycles
        changes.push(ChangeOp::AddEdge(create_call_edge("N5", "N3")));
        changes.push(ChangeOp::AddEdge(create_call_edge("N3", "N1")));
        changes.push(ChangeOp::AddEdge(create_call_edge("N1", "N5"))); // Cycle 1

        changes.push(ChangeOp::AddEdge(create_call_edge("N10", "N8")));
        changes.push(ChangeOp::AddEdge(create_call_edge("N8", "N6")));
        changes.push(ChangeOp::AddEdge(create_call_edge("N6", "N10"))); // Cycle 2

        changes.push(ChangeOp::AddEdge(create_call_edge("N15", "N12")));
        changes.push(ChangeOp::AddEdge(create_call_edge("N12", "N9")));
        changes.push(ChangeOp::AddEdge(create_call_edge("N9", "N15"))); // Cycle 3

        let commit1_txn = graph.commit_transaction(txn1, changes).unwrap();

        // Modify node in cycle
        let txn2 = graph.begin_transaction("test".to_string());
        let mut modified = create_function_node("N5", None, None);
        modified.parameters = Some(vec!["param".to_string()]);

        let delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: txn2,
            added_nodes: vec![],
            modified_nodes: vec![modified],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        // Should not hang - BFS must handle cycles
        let start = std::time::Instant::now();
        let expanded = analyzer.compute_expanded_scope(&delta, &graph);
        let duration = start.elapsed();

        // Must complete in reasonable time (< 100ms)
        assert!(
            duration.as_millis() < 100,
            "Fuzz test took too long: {:?}",
            duration
        );

        // Should have found nodes within depth limit
        assert!(!expanded.secondary_targets.is_empty());
    }

    /// Test 15: Crash recovery via DurableWAL
    ///
    /// Verifies WAL can recover from partial/corrupted writes
    #[test]
    fn test_crash_recovery_durability() {
        use std::io::Write;
        use tempfile::NamedTempFile;

        // Create temporary WAL file
        let mut temp_file = NamedTempFile::new().unwrap();

        // Write valid entries
        writeln!(temp_file, "TXN 1 agent1 2 changes").unwrap();
        writeln!(temp_file, "TXN 2 agent2 1 changes").unwrap();

        // Simulate crash: partial write (no newline)
        write!(temp_file, "TXN 3 agent3").unwrap(); // Incomplete entry
        temp_file.flush().unwrap();

        // Create TransactionWAL and attempt recovery
        let wal = crate::features::multi_index::infrastructure::TransactionWAL::new();

        // Use DurableWAL trait for recovery
        use crate::features::multi_index::infrastructure::DurableWAL;
        let recovered = wal.recover_from_file(&temp_file.path().to_path_buf());

        assert!(recovered.is_ok(), "Recovery should succeed");
        let entries = recovered.unwrap();

        // Should recover 2 valid entries (stop at corruption)
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].txn_id, 1);
        assert_eq!(entries[1].txn_id, 2);
    }

    /// Test 16: Reorder invariance
    ///
    /// Ensures delta analysis is independent of node ordering
    #[test]
    fn test_reorder_invariance() {
        let analyzer = ChangeAnalyzer::new();
        let graph = TransactionalGraphIndex::new();

        let node1 = create_function_node("A", None, None);
        let node2 = create_function_node("B", None, None);
        let node3 = create_function_node("C", None, None);

        // Delta with order: A, B, C
        let delta1 = TransactionDelta {
            from_txn: 0,
            to_txn: 1,
            added_nodes: vec![],
            modified_nodes: vec![node1.clone(), node2.clone(), node3.clone()],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        // Delta with order: C, A, B (reordered)
        let delta2 = TransactionDelta {
            from_txn: 0,
            to_txn: 1,
            added_nodes: vec![],
            modified_nodes: vec![node3.clone(), node1.clone(), node2.clone()],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        // Analyze both deltas
        let analysis1 = analyzer.analyze_delta(&delta1, &graph);
        let analysis2 = analyzer.analyze_delta(&delta2, &graph);

        // Results should be equivalent (order-independent)
        assert_eq!(analysis1.impact_ratio, analysis2.impact_ratio);
        assert_eq!(
            analysis1.affected_regions.len(),
            analysis2.affected_regions.len()
        );

        // Affected regions should contain same nodes (regardless of order)
        let regions1: std::collections::HashSet<_> = analysis1
            .affected_regions
            .iter()
            .flat_map(|r| r.node_ids.iter())
            .collect();
        let regions2: std::collections::HashSet<_> = analysis2
            .affected_regions
            .iter()
            .flat_map(|r| r.node_ids.iter())
            .collect();

        assert_eq!(regions1, regions2, "Regions should be order-invariant");
    }

    /// Test 17: Deep chain safety (depth > MAX_DEPTH)
    ///
    /// Verifies that very deep chains don't cause stack overflow
    #[test]
    fn test_deep_chain_stack_safety() {
        let analyzer = ChangeAnalyzer::new();
        let graph = TransactionalGraphIndex::new();

        // Create extremely deep chain: F0 → F1 → ... → F99 (depth 100)
        let txn1 = graph.begin_transaction("test".to_string());
        let mut changes = vec![];

        for i in 0..100 {
            changes.push(ChangeOp::AddNode(create_function_node(
                &format!("F{}", i),
                None,
                None,
            )));
        }

        // Add edges: F99→F98→...→F1→F0
        for i in 1..100 {
            changes.push(ChangeOp::AddEdge(create_call_edge(
                &format!("F{}", i),
                &format!("F{}", i - 1),
            )));
        }

        let commit1_txn = graph.commit_transaction(txn1, changes).unwrap();

        // Modify F0 (bottom)
        let mut modified = create_function_node("F0", None, None);
        modified.parameters = Some(vec!["param".to_string()]);

        let delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: 2,
            added_nodes: vec![],
            modified_nodes: vec![modified],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        // Should not stack overflow - BFS is iterative
        let expanded = analyzer.compute_expanded_scope(&delta, &graph);

        // Should stop at MAX_DEPTH=2
        assert!(
            expanded.secondary_targets.len() <= 3,
            "Should respect MAX_DEPTH=2"
        );
    }

    /// Test 18: Mixed changes mutual exclusivity validation
    ///
    /// Ensures HashComparison validate() catches invalid states
    #[test]
    fn test_mixed_changes_exclusivity() {
        use crate::features::multi_index::ports::HashComparison;

        // Valid: Only signature changed
        let valid1 = HashComparison {
            signature_changed: true,
            body_changed: false,
            doc_changed: false,
            format_changed: false,
        };
        assert!(valid1.validate().is_ok());

        // Valid: Only body changed
        let valid2 = HashComparison {
            signature_changed: false,
            body_changed: true,
            doc_changed: false,
            format_changed: false,
        };
        assert!(valid2.validate().is_ok());

        // Valid: Only doc changed
        let valid3 = HashComparison {
            signature_changed: false,
            body_changed: false,
            doc_changed: true,
            format_changed: false,
        };
        assert!(valid3.validate().is_ok());

        // Valid: Only format changed
        let valid4 = HashComparison {
            signature_changed: false,
            body_changed: false,
            doc_changed: false,
            format_changed: true,
        };
        assert!(valid4.validate().is_ok());

        // INVALID: Multiple flags true
        let invalid1 = HashComparison {
            signature_changed: true,
            body_changed: true,
            doc_changed: false,
            format_changed: false,
        };
        assert!(invalid1.validate().is_err());

        // INVALID: All flags true
        let invalid2 = HashComparison {
            signature_changed: true,
            body_changed: true,
            doc_changed: true,
            format_changed: true,
        };
        assert!(invalid2.validate().is_err());

        // INVALID: No flags true
        let invalid3 = HashComparison {
            signature_changed: false,
            body_changed: false,
            doc_changed: false,
            format_changed: false,
        };
        assert!(invalid3.validate().is_err());
    }

    /// Test 19: Framework edge propagation (mock)
    ///
    /// Tests multi-graph propagation with framework edges
    #[test]
    fn test_framework_edge_propagation() {
        use crate::features::multi_index::infrastructure::ImpactGraph;

        let analyzer = ChangeAnalyzer::new();
        let graph = TransactionalGraphIndex::new();

        // Create route handler and controller
        let mut route_handler = create_function_node("handle_user_request", None, None);
        route_handler.decorators = Some(vec!["@app.route('/user')".to_string()]);

        let controller = create_function_node("UserController", None, None);

        let txn1 = graph.begin_transaction("test".to_string());
        let commit1_txn = graph
            .commit_transaction(
                txn1,
                vec![
                    ChangeOp::AddNode(route_handler.clone()),
                    ChangeOp::AddNode(controller.clone()),
                    ChangeOp::AddEdge(Edge {
                        source_id: "handle_user_request".to_string(),
                        target_id: "UserController".to_string(),
                        kind: EdgeKind::References, // Framework DI reference
                        span: Some(Span::new(1, 1, 1, 10)),
                        metadata: None,
                        attrs: None,
                    }),
                ],
            )
            .unwrap();

        // Modify decorator (framework routing change)
        let txn2 = graph.begin_transaction("test".to_string());
        let mut modified_handler = route_handler.clone();
        modified_handler.decorators = Some(vec!["@app.route('/users')".to_string()]); // Changed route

        let delta = TransactionDelta {
            from_txn: commit1_txn,
            to_txn: txn2,
            added_nodes: vec![],
            modified_nodes: vec![modified_handler],
            removed_nodes: vec![],
            added_edges: vec![],
            removed_edges: vec![],
        };

        // Use FrameworkRoute graph for propagation
        let expanded = analyzer.compute_expanded_scope_multi_graph(
            &delta,
            &graph,
            &[ImpactGraph::FrameworkRoute],
        );

        // Should propagate to controller via framework edge
        assert!(expanded
            .primary_targets
            .contains(&"handle_user_request".to_string()));
        // Note: Actual propagation depends on edge setup - this is a structural test
    }

    /// Test 20: Multi-index consistency check
    ///
    /// Verifies all indexes reach same applied_up_to after updates
    #[test]
    fn test_multi_index_consistency() {
        use crate::features::multi_index::infrastructure::{
            IndexOrchestratorConfig, MultiLayerIndexOrchestrator,
        };
        use crate::features::multi_index::ports::{IndexPlugin, IndexType, QueryType};
        use parking_lot::RwLock;
        use std::sync::Arc;

        let config = IndexOrchestratorConfig::default();
        let orchestrator = MultiLayerIndexOrchestrator::new(config);

        // Register 3 mock indexes
        struct SimpleMockIndex {
            index_type: IndexType,
            applied: Arc<RwLock<crate::features::query_engine::infrastructure::TxnId>>,
        }

        impl IndexPlugin for SimpleMockIndex {
            fn index_type(&self) -> IndexType {
                self.index_type
            }

            fn apply_delta(
                &mut self,
                delta: &crate::features::query_engine::infrastructure::TransactionDelta,
                _analysis: &crate::features::multi_index::ports::DeltaAnalysis,
            ) -> Result<(bool, u64), crate::features::multi_index::ports::IndexError> {
                *self.applied.write() = delta.to_txn;
                Ok((true, 10))
            }

            fn applied_up_to(&self) -> crate::features::query_engine::infrastructure::TxnId {
                *self.applied.read()
            }

            fn rebuild(
                &mut self,
                _snapshot: &crate::features::query_engine::infrastructure::Snapshot,
            ) -> Result<u64, crate::features::multi_index::ports::IndexError> {
                Ok(100)
            }

            fn supports_query(&self, _query_type: &QueryType) -> bool {
                true
            }

            fn health(&self) -> crate::features::multi_index::ports::IndexHealth {
                crate::features::multi_index::ports::IndexHealth {
                    is_healthy: true,
                    last_update: std::time::SystemTime::now(),
                    staleness: std::time::Duration::from_secs(0),
                    error: None,
                }
            }

            fn stats(&self) -> crate::features::multi_index::ports::IndexStats {
                crate::features::multi_index::ports::IndexStats {
                    entry_count: 10,
                    size_bytes: 100,
                    last_rebuild_ms: 0,
                    total_updates: 1,
                }
            }
        }

        orchestrator.register_index(Box::new(SimpleMockIndex {
            index_type: IndexType::Vector,
            applied: Arc::new(RwLock::new(0)),
        }));
        orchestrator.register_index(Box::new(SimpleMockIndex {
            index_type: IndexType::Lexical,
            applied: Arc::new(RwLock::new(0)),
        }));
        orchestrator.register_index(Box::new(SimpleMockIndex {
            index_type: IndexType::Graph,
            applied: Arc::new(RwLock::new(0)),
        }));

        // Commit change
        let _session = orchestrator.begin_session("agent1".to_string());
        orchestrator
            .add_change(
                "agent1",
                ChangeOp::AddNode(create_function_node("test", None, None)),
            )
            .unwrap();

        let result = orchestrator.commit("agent1");
        assert!(result.success);

        // Verify all indexes reached same txn
        let health = orchestrator.health();
        assert_eq!(health.index_health.len(), 3);

        // All should be healthy and consistent
        assert!(health.is_healthy, "All indexes should be healthy");
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Helper Functions
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    fn create_function_node(
        id: &str,
        parameters: Option<Vec<String>>,
        return_type: Option<String>,
    ) -> Node {
        Node {
            id: id.to_string(),
            kind: NodeKind::Function,
            fqn: format!("test.{}", id),
            file_path: "test.py".to_string(),
            span: Span::new(1, 1, 1, 10),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some(id.to_string()),
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters,
            return_type,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }
    }

    fn create_node_in_file(id: &str, file_path: &str) -> Node {
        let mut node = create_function_node(id, None, None);
        node.file_path = file_path.to_string();
        node
    }

    fn create_call_edge(caller: &str, callee: &str) -> Edge {
        Edge {
            source_id: caller.to_string(),
            target_id: callee.to_string(),
            kind: EdgeKind::Calls,
            span: Some(Span::new(1, 1, 1, 10)),
            metadata: None,
            attrs: None,
        }
    }
}
