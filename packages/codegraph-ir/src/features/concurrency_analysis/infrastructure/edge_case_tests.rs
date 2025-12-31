/// Edge case and stress tests for AsyncRaceDetector
///
/// Tests cover:
/// - Empty IR documents
/// - Async functions with no await points
/// - Multiple races in single function
/// - Null/None values
/// - Large IR documents

#[cfg(test)]
mod edge_case_tests {
    use crate::features::concurrency_analysis::domain::*;
    use crate::features::concurrency_analysis::infrastructure::AsyncRaceDetector;
    use crate::features::cross_file::IRDocument;
    use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Span};

    /// Helper to create a minimal node
    fn create_node(id: &str, kind: NodeKind, is_async: bool) -> Node {
        Node {
            id: id.to_string(),
            kind,
            fqn: id.to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(1, 0, 1, 10),
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
            is_async: Some(is_async),
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

    #[test]
    fn test_empty_ir_document() {
        let detector = AsyncRaceDetector::new();
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![],
            edges: vec![],
            repo_id: None,
        };

        let result = detector.analyze_async_function(&ir_doc, "nonexistent");
        assert!(result.is_err(), "Should error on nonexistent function");
    }

    #[test]
    fn test_async_function_no_await_points() {
        let detector = AsyncRaceDetector::new();

        let func_node = create_node("async_func", NodeKind::Function, true);

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func_node],
            edges: vec![],
            repo_id: None,
        };

        let result = detector
            .analyze_async_function(&ir_doc, "async_func")
            .unwrap();
        assert_eq!(result.len(), 0, "No races without await points");
    }

    #[test]
    fn test_non_async_function() {
        let detector = AsyncRaceDetector::new();

        let func_node = create_node("sync_func", NodeKind::Function, false);

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func_node],
            edges: vec![],
            repo_id: None,
        };

        let result = detector
            .analyze_async_function(&ir_doc, "sync_func")
            .unwrap();
        assert_eq!(result.len(), 0, "No races in non-async function");
    }

    #[test]
    fn test_single_variable_access() {
        let detector = AsyncRaceDetector::new();

        let mut func_node = create_node("async_func", NodeKind::Function, true);
        func_node.is_async = Some(true);

        let mut var_node = create_node("var1", NodeKind::Variable, false);
        var_node.parent_id = Some("async_func".to_string());
        var_node.span = Span::new(5, 0, 5, 10);

        let mut await_node = create_node("await_expr", NodeKind::Expression, false);
        await_node.name = Some("await asyncio.sleep(0)".to_string());
        await_node.parent_id = Some("async_func".to_string());
        await_node.span = Span::new(3, 0, 3, 20);

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func_node, var_node, await_node],
            edges: vec![],
            repo_id: None,
        };

        let result = detector
            .analyze_async_function(&ir_doc, "async_func")
            .unwrap();
        assert_eq!(result.len(), 0, "No race with single variable access");
    }

    #[test]
    fn test_multiple_races_same_function() {
        use crate::shared::models::{Edge, EdgeKind};

        let detector = AsyncRaceDetector::new();

        let mut func_node = create_node("async_func", NodeKind::Function, true);
        func_node.is_async = Some(true);

        // Two SHARED variables (self.xxx pattern), each accessed via edges
        // Variable 1: self.count
        let mut var1 = create_node("self.count", NodeKind::Variable, false);
        var1.name = Some("self.count".to_string());
        var1.parent_id = Some("async_func".to_string());
        var1.span = Span::new(5, 0, 5, 20);

        // Variable 2: self.total
        let mut var2 = create_node("self.total", NodeKind::Variable, false);
        var2.name = Some("self.total".to_string());
        var2.parent_id = Some("async_func".to_string());
        var2.span = Span::new(8, 0, 8, 20);

        // Await node
        let mut await_node = create_node("await_expr", NodeKind::Expression, false);
        await_node.name = Some("await asyncio.sleep(0)".to_string());
        await_node.parent_id = Some("async_func".to_string());
        await_node.span = Span::new(6, 0, 6, 20);

        // Edges: read/write for both variables (PRODUCTION implementation uses edges!)
        let edges = vec![
            // self.count: read at line 5, write at line 7
            Edge::new(
                "async_func".to_string(),
                "self.count".to_string(),
                EdgeKind::Reads,
            )
            .with_span(Span::new(5, 0, 5, 10)),
            Edge::new(
                "async_func".to_string(),
                "self.count".to_string(),
                EdgeKind::Writes,
            )
            .with_span(Span::new(7, 0, 7, 10)),
            // self.total: read at line 8, write at line 10
            Edge::new(
                "async_func".to_string(),
                "self.total".to_string(),
                EdgeKind::Reads,
            )
            .with_span(Span::new(8, 0, 8, 10)),
            Edge::new(
                "async_func".to_string(),
                "self.total".to_string(),
                EdgeKind::Writes,
            )
            .with_span(Span::new(10, 0, 10, 10)),
        ];

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func_node, var1, var2, await_node],
            edges,
            repo_id: None,
        };

        let result = detector
            .analyze_async_function(&ir_doc, "async_func")
            .unwrap();
        assert_eq!(
            result.len(),
            2,
            "Should detect 2 races (self.count and self.total)"
        );

        // Verify severity
        for race in &result {
            assert!(
                race.severity == RaceSeverity::High,
                "Read-Write races should be High severity"
            );
        }
    }

    #[test]
    fn test_large_ir_document() {
        let detector = AsyncRaceDetector::new();

        // Create IR with 100 functions, 1000 variables
        let mut nodes = vec![];

        for i in 0..100 {
            let mut func_node = create_node(&format!("func_{}", i), NodeKind::Function, true);
            func_node.is_async = Some(i % 2 == 0); // Half async, half sync
            nodes.push(func_node);

            // Add 10 variables per function
            for j in 0..10 {
                let mut var_node =
                    create_node(&format!("var_{}_{}", i, j), NodeKind::Variable, false);
                var_node.parent_id = Some(format!("func_{}", i));
                var_node.name = Some(format!("var_{}", j % 5)); // Create some duplicates
                var_node.span = Span::new(j as u32 + 1, 0, j as u32 + 1, 10);
                nodes.push(var_node);
            }

            // Add await point for async functions
            if i % 2 == 0 {
                let mut await_node =
                    create_node(&format!("await_{}", i), NodeKind::Expression, false);
                await_node.name = Some("await asyncio.sleep(0)".to_string());
                await_node.parent_id = Some(format!("func_{}", i));
                await_node.span = Span::new(5, 0, 5, 20);
                nodes.push(await_node);
            }
        }

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes,
            edges: vec![],
            repo_id: None,
        };

        // Test each async function
        for i in (0..100).step_by(2) {
            let func_name = format!("func_{}", i);
            let result = detector.analyze_async_function(&ir_doc, &func_name);
            assert!(result.is_ok(), "Should handle large IR for {}", func_name);
        }
    }

    #[test]
    fn test_null_parent_id() {
        let detector = AsyncRaceDetector::new();

        let func_node = create_node("async_func", NodeKind::Function, true);

        // Variable with None parent_id (orphaned)
        let mut var_node = create_node("var1", NodeKind::Variable, false);
        var_node.parent_id = None; // Orphaned variable

        let mut await_node = create_node("await_expr", NodeKind::Expression, false);
        await_node.name = Some("await asyncio.sleep(0)".to_string());
        await_node.parent_id = Some("async_func".to_string());

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func_node, var_node, await_node],
            edges: vec![],
            repo_id: None,
        };

        let result = detector
            .analyze_async_function(&ir_doc, "async_func")
            .unwrap();
        assert_eq!(result.len(), 0, "Orphaned variables should be ignored");
    }

    #[test]
    fn test_none_name_fallback() {
        let detector = AsyncRaceDetector::new();

        let mut func_node = create_node("async_func", NodeKind::Function, true);
        func_node.is_async = Some(true);

        // Variable with None name (should use id as fallback)
        let mut var1 = create_node("var_id_1", NodeKind::Variable, false);
        var1.name = None;
        var1.parent_id = Some("async_func".to_string());
        var1.span = Span::new(5, 0, 5, 10);

        let mut var2 = create_node("var_id_2", NodeKind::Variable, false);
        var2.name = None;
        var2.parent_id = Some("async_func".to_string());
        var2.span = Span::new(7, 0, 7, 10);

        let mut await_node = create_node("await_expr", NodeKind::Expression, false);
        await_node.name = Some("await asyncio.sleep(0)".to_string());
        await_node.parent_id = Some("async_func".to_string());

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func_node, var1, var2, await_node],
            edges: vec![],
            repo_id: None,
        };

        let result = detector.analyze_async_function(&ir_doc, "async_func");
        // Should not crash, may or may not detect race depending on id matching
        assert!(result.is_ok(), "Should handle None names without crashing");
    }
}
