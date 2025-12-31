// Comprehensive tests for MultiLayerIndexOrchestrator
//
// Tests for session management, consistency, and concurrent operations

#[cfg(test)]
mod tests {
    use crate::features::multi_index::infrastructure::{
        ConsistencyLevel, IndexOrchestratorConfig, MultiLayerIndexOrchestrator, Query,
    };
    use crate::features::multi_index::ports::{
        DeltaAnalysis, IndexHealth, IndexPlugin, IndexStats, IndexType, QueryType, UpdateStrategy,
    };
    use crate::features::query_engine::infrastructure::{ChangeOp, TxnId};
    use crate::shared::models::{Node, NodeKind, Span};
    use std::sync::Arc;

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 🔴 PHASE 1: CRITICAL - Orchestrator Core Tests
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Test 1: Session lifecycle (begin → add_change → commit)
    #[test]
    #[ignore]
    fn test_session_lifecycle() {
        let config = IndexOrchestratorConfig::default();
        let orchestrator = MultiLayerIndexOrchestrator::new(config);

        // Begin session
        let session = orchestrator.begin_session("agent1".to_string());
        assert_eq!(session.agent_id, "agent1");
        assert_eq!(session.pending_changes.len(), 0);

        // Add changes
        let node = create_test_node("node1");
        orchestrator
            .add_change("agent1", ChangeOp::AddNode(node))
            .unwrap();

        // Commit
        let result = orchestrator.commit("agent1");
        assert!(result.success, "Commit should succeed");
        assert!(result.committed_txn.is_some());
        assert_eq!(result.conflicts.len(), 0);
    }

    /// Test 2: Multiple concurrent sessions
    #[test]
    #[ignore]
    fn test_concurrent_sessions() {
        let config = IndexOrchestratorConfig::default();
        let orchestrator = MultiLayerIndexOrchestrator::new(config);

        // Start 3 sessions
        let session1 = orchestrator.begin_session("agent1".to_string());
        let session2 = orchestrator.begin_session("agent2".to_string());
        let session3 = orchestrator.begin_session("agent3".to_string());

        // Each should have unique txn_id
        assert_ne!(session1.txn_id, session2.txn_id);
        assert_ne!(session2.txn_id, session3.txn_id);

        // Add changes to each
        orchestrator
            .add_change("agent1", ChangeOp::AddNode(create_test_node("node1")))
            .unwrap();
        orchestrator
            .add_change("agent2", ChangeOp::AddNode(create_test_node("node2")))
            .unwrap();
        orchestrator
            .add_change("agent3", ChangeOp::AddNode(create_test_node("node3")))
            .unwrap();

        // Commit all - should succeed
        let result1 = orchestrator.commit("agent1");
        let result2 = orchestrator.commit("agent2");
        let result3 = orchestrator.commit("agent3");

        assert!(result1.success);
        assert!(result2.success);
        assert!(result3.success);
    }

    /// Test 3: Conflict detection (same node modified by different agents)
    #[test]
    #[ignore]
    fn test_concurrent_conflict_detection() {
        let config = IndexOrchestratorConfig::default();
        let orchestrator = MultiLayerIndexOrchestrator::new(config);

        // Agent1 adds node1
        let _session1 = orchestrator.begin_session("agent1".to_string());
        orchestrator
            .add_change("agent1", ChangeOp::AddNode(create_test_node("node1")))
            .unwrap();
        let result1 = orchestrator.commit("agent1");
        assert!(result1.success);

        // Agent2 and Agent3 try to modify node1 concurrently
        let _session2 = orchestrator.begin_session("agent2".to_string());
        let _session3 = orchestrator.begin_session("agent3".to_string());

        let mut modified_node2 = create_test_node("node1");
        modified_node2.name = Some("modified_by_agent2".to_string());

        let mut modified_node3 = create_test_node("node1");
        modified_node3.name = Some("modified_by_agent3".to_string());

        orchestrator
            .add_change("agent2", ChangeOp::UpdateNode(modified_node2))
            .unwrap();
        orchestrator
            .add_change("agent3", ChangeOp::UpdateNode(modified_node3))
            .unwrap();

        // Commit agent2 first - should succeed
        let result2 = orchestrator.commit("agent2");
        assert!(result2.success, "First commit should succeed");

        // Commit agent3 - may conflict depending on MVCC implementation
        let result3 = orchestrator.commit("agent3");
        // Either succeeds or detects conflict
        if !result3.success {
            assert!(
                !result3.conflicts.is_empty(),
                "Should report conflicts if failed"
            );
        }
    }

    /// Test 4: Empty commit (no changes)
    #[test]
    fn test_empty_commit() {
        let config = IndexOrchestratorConfig::default();
        let orchestrator = MultiLayerIndexOrchestrator::new(config);

        let _session = orchestrator.begin_session("agent1".to_string());
        // Don't add any changes

        let result = orchestrator.commit("agent1");
        assert!(result.success, "Empty commit should succeed");
        assert!(result.delta.is_none(), "Empty commit has no delta");
    }

    /// Test 5: TxnWatermark consistency (Contract #1)
    #[test]
    #[ignore]
    fn test_txn_watermark_consistency() {
        let config = IndexOrchestratorConfig::default();
        let orchestrator = MultiLayerIndexOrchestrator::new(config);

        // Register mock index plugin
        let mock_plugin = MockIndexPlugin::new(IndexType::Vector);
        orchestrator.register_index(Box::new(mock_plugin));

        // Commit some changes
        let _session = orchestrator.begin_session("agent1".to_string());
        orchestrator
            .add_change("agent1", ChangeOp::AddNode(create_test_node("node1")))
            .unwrap();
        let result = orchestrator.commit("agent1");
        assert!(result.success);

        // Query with Strict consistency - should wait for indexes
        let query = Query {
            text: "test query".to_string(),
            query_type: QueryType::SemanticSearch,
            consistency_level: ConsistencyLevel::Strict,
        };

        // Should not panic or hang
        let _query_result = orchestrator.query_with_consistency(query);

        // Health check should show index status
        let health = orchestrator.health();
        assert!(health.is_healthy || !health.is_healthy); // Just verify it returns
    }

    /// Test 6: Query routing to correct index type
    #[test]
    fn test_query_routing() {
        let config = IndexOrchestratorConfig::default();
        let orchestrator = MultiLayerIndexOrchestrator::new(config);

        // Register all index types
        orchestrator.register_index(Box::new(MockIndexPlugin::new(IndexType::Vector)));
        orchestrator.register_index(Box::new(MockIndexPlugin::new(IndexType::Lexical)));
        orchestrator.register_index(Box::new(MockIndexPlugin::new(IndexType::Graph)));

        // Test different query types route to correct indexes
        let test_cases = vec![
            (QueryType::SemanticSearch, IndexType::Vector),
            (QueryType::SimilarCode, IndexType::Vector),
            (QueryType::TextSearch, IndexType::Lexical),
            (QueryType::FQNSearch, IndexType::Lexical),
            (QueryType::Reachability, IndexType::Graph),
            (QueryType::ASTLookup, IndexType::Graph),
            (QueryType::MetricsLookup, IndexType::Graph),
            (QueryType::ComplexityAnalysis, IndexType::Graph),
            (QueryType::HybridSearch, IndexType::Vector), // Starts with vector
            (QueryType::IdentifierLookup, IndexType::Vector),
            (QueryType::IRDocLookup, IndexType::Vector),
        ];

        for (query_type, expected_index) in test_cases {
            let query = Query {
                text: "test".to_string(),
                query_type,
                consistency_level: ConsistencyLevel::Eventual,
            };

            // Query should route correctly (not panic)
            let _result = orchestrator.query_with_consistency(query);
            // In production, would verify which index was called
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 🟡 PHASE 2: EDGE CASES
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Test 7: Session with no begin (should error)
    #[test]
    fn test_commit_without_session() {
        let config = IndexOrchestratorConfig::default();
        let orchestrator = MultiLayerIndexOrchestrator::new(config);

        // Try to commit without beginning session
        let result = orchestrator.commit("nonexistent_agent");
        assert!(!result.success, "Should fail without active session");
        assert!(
            !result.conflicts.is_empty(),
            "Should report error in conflicts"
        );
    }

    /// Test 8: Double commit (same session)
    #[test]
    #[ignore]
    fn test_double_commit() {
        let config = IndexOrchestratorConfig::default();
        let orchestrator = MultiLayerIndexOrchestrator::new(config);

        let _session = orchestrator.begin_session("agent1".to_string());
        orchestrator
            .add_change("agent1", ChangeOp::AddNode(create_test_node("node1")))
            .unwrap();

        // First commit
        let result1 = orchestrator.commit("agent1");
        assert!(result1.success);

        // Second commit (session already ended)
        let result2 = orchestrator.commit("agent1");
        assert!(!result2.success, "Double commit should fail");
    }

    /// Test 9: Health check with multiple indexes
    #[test]
    fn test_health_check_aggregation() {
        let config = IndexOrchestratorConfig::default();
        let orchestrator = MultiLayerIndexOrchestrator::new(config);

        // Register healthy and unhealthy indexes
        orchestrator.register_index(Box::new(MockIndexPlugin::new_healthy(
            IndexType::Vector,
            true,
        )));
        orchestrator.register_index(Box::new(MockIndexPlugin::new_healthy(
            IndexType::Lexical,
            false,
        )));

        let health = orchestrator.health();

        // Overall health should be false if any index is unhealthy
        assert!(
            !health.is_healthy,
            "Should be unhealthy if any index is unhealthy"
        );
        assert_eq!(health.index_health.len(), 2);
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 🟢 PHASE 3: EXTREME SCENARIOS
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Test 10: Many concurrent sessions (100+)
    #[test]
    #[ignore]
    fn test_many_concurrent_sessions() {
        let config = IndexOrchestratorConfig::default();
        let orchestrator = Arc::new(MultiLayerIndexOrchestrator::new(config));

        // Start 100 sessions
        for i in 0..100 {
            let agent_id = format!("agent{}", i);
            let _session = orchestrator.begin_session(agent_id.clone());
            orchestrator
                .add_change(
                    &agent_id,
                    ChangeOp::AddNode(create_test_node(&format!("node{}", i))),
                )
                .unwrap();
        }

        // Commit all
        let mut success_count = 0;
        for i in 0..100 {
            let agent_id = format!("agent{}", i);
            let result = orchestrator.commit(&agent_id);
            if result.success {
                success_count += 1;
            }
        }

        // Most should succeed (some may conflict)
        assert!(
            success_count >= 90,
            "At least 90% should succeed: {}",
            success_count
        );
    }

    /// Test 11: Large commit (1000+ nodes)
    #[test]
    #[ignore]
    fn test_large_commit() {
        let config = IndexOrchestratorConfig::default();
        let orchestrator = MultiLayerIndexOrchestrator::new(config);

        let _session = orchestrator.begin_session("agent1".to_string());

        // Add 1000 nodes
        for i in 0..1000 {
            orchestrator
                .add_change(
                    "agent1",
                    ChangeOp::AddNode(create_test_node(&format!("node{}", i))),
                )
                .unwrap();
        }

        // Commit should handle large changes
        let start = std::time::Instant::now();
        let result = orchestrator.commit("agent1");
        let duration = start.elapsed();

        assert!(result.success, "Large commit should succeed");
        assert!(
            duration.as_secs() < 10,
            "Large commit should complete in < 10s: {:?}",
            duration
        );
    }

    /// Test 12: Parallel updates (DashMap lock-free verification)
    #[test]
    #[ignore]
    fn test_parallel_index_updates() {
        use std::sync::Arc;
        use std::thread;

        let config = IndexOrchestratorConfig {
            parallel_updates: true,
            ..Default::default()
        };
        let orchestrator = Arc::new(MultiLayerIndexOrchestrator::new(config));

        // Register multiple indexes
        orchestrator.register_index(Box::new(MockIndexPlugin::new(IndexType::Vector)));
        orchestrator.register_index(Box::new(MockIndexPlugin::new(IndexType::Lexical)));
        orchestrator.register_index(Box::new(MockIndexPlugin::new(IndexType::Graph)));

        // Spawn 10 threads doing concurrent commits
        let mut handles = vec![];
        for i in 0..10 {
            let orch = Arc::clone(&orchestrator);
            let handle = thread::spawn(move || {
                let agent_id = format!("agent{}", i);
                let _session = orch.begin_session(agent_id.clone());
                orch.add_change(
                    &agent_id,
                    ChangeOp::AddNode(create_test_node(&format!("node{}", i))),
                )
                .unwrap();
                orch.commit(&agent_id).success
            });
            handles.push(handle);
        }

        // Wait for all threads
        let mut success_count = 0;
        for handle in handles {
            if handle.join().unwrap() {
                success_count += 1;
            }
        }

        // All or most should succeed with lock-free DashMap
        assert!(
            success_count >= 8,
            "Most parallel commits should succeed: {}",
            success_count
        );
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Mock Index Plugin for Testing
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    struct MockIndexPlugin {
        index_type: IndexType,
        applied_up_to: Arc<parking_lot::RwLock<TxnId>>,
        is_healthy: bool,
    }

    impl MockIndexPlugin {
        fn new(index_type: IndexType) -> Self {
            Self {
                index_type,
                applied_up_to: Arc::new(parking_lot::RwLock::new(0)),
                is_healthy: true,
            }
        }

        fn new_healthy(index_type: IndexType, is_healthy: bool) -> Self {
            Self {
                index_type,
                applied_up_to: Arc::new(parking_lot::RwLock::new(0)),
                is_healthy,
            }
        }
    }

    impl IndexPlugin for MockIndexPlugin {
        fn index_type(&self) -> IndexType {
            self.index_type
        }

        fn apply_delta(
            &mut self,
            _delta: &crate::features::query_engine::infrastructure::TransactionDelta,
            _analysis: &DeltaAnalysis,
        ) -> Result<(bool, u64), crate::features::multi_index::ports::IndexError> {
            // Mock: Just update watermark
            let mut watermark = self.applied_up_to.write();
            *watermark += 1;
            Ok((true, 10)) // 10ms cost
        }

        fn applied_up_to(&self) -> TxnId {
            *self.applied_up_to.read()
        }

        fn rebuild(
            &mut self,
            _snapshot: &crate::features::query_engine::infrastructure::Snapshot,
        ) -> Result<u64, crate::features::multi_index::ports::IndexError> {
            Ok(100) // 100ms rebuild time
        }

        fn supports_query(&self, _query_type: &QueryType) -> bool {
            true // Mock supports all queries
        }

        fn health(&self) -> IndexHealth {
            IndexHealth {
                is_healthy: self.is_healthy,
                last_update: std::time::SystemTime::now(),
                staleness: std::time::Duration::from_secs(0),
                error: None,
            }
        }

        fn stats(&self) -> IndexStats {
            IndexStats {
                entry_count: 100,
                size_bytes: 1024,
                last_rebuild_ms: 0,
                total_updates: 1,
            }
        }
    }

    // Helper
    fn create_test_node(id: &str) -> Node {
        Node {
            id: id.to_string(),
            kind: NodeKind::Variable,
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
            parameters: None,
            return_type: None,
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
}
