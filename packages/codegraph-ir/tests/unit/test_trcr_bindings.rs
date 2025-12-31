//! Test TRCR PyO3 bindings
//!
//! This test validates that Rust can call Python TRCR through PyO3.

#[cfg(all(test, feature = "python"))]
mod tests {
    use codegraph_ir::adapters::pyo3::trcr_bindings::TRCRBridge;
    use codegraph_ir::shared::models::{Node, NodeKind, Span};

    #[test]
    fn test_trcr_bridge_creation() {
        // Test 1: Create TRCR bridge
        let result = TRCRBridge::new();
        assert!(result.is_ok(), "Failed to create TRCR bridge: {:?}", result.err());
    }

    #[test]
    fn test_trcr_compile_atoms() {
        // Test 2: Compile Python atoms
        let mut bridge = TRCRBridge::new().expect("Failed to create bridge");

        let atoms_path = "packages/codegraph-trcr/rules/atoms/python.atoms.yaml";
        let result = bridge.compile_atoms(atoms_path);

        assert!(result.is_ok(), "Failed to compile atoms: {:?}", result.err());
    }

    #[test]
    fn test_trcr_execute() {
        // Test 3: Execute rules against mock nodes
        let mut bridge = TRCRBridge::new().expect("Failed to create bridge");

        // Compile atoms
        let atoms_path = "packages/codegraph-trcr/rules/atoms/python.atoms.yaml";
        bridge.compile_atoms(atoms_path).expect("Failed to compile atoms");

        // Create mock nodes with proper structure
        let nodes = vec![
            Node {
                id: "n1".to_string(),
                name: Some("input".to_string()),
                fqn: "input".to_string(),
                kind: NodeKind::Call,
                file_path: "test.py".to_string(),
                span: Span::default(),
                language: "python".to_string(),
                stable_id: None,
                content_hash: None,
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
            },
            Node {
                id: "n2".to_string(),
                name: Some("execute".to_string()),
                fqn: "sqlite3.Cursor.execute".to_string(),
                kind: NodeKind::Call,
                file_path: "test.py".to_string(),
                span: Span::default(),
                language: "python".to_string(),
                stable_id: None,
                content_hash: None,
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
            },
        ];

        // Execute rules
        let matches = bridge.execute(&nodes).expect("Failed to execute rules");

        // Should find at least 2 matches (source + sink)
        assert!(matches.len() >= 2, "Expected at least 2 matches, got {}", matches.len());

        // Verify we have a source and a sink
        let has_source = matches.iter().any(|m| m.effect_kind == "source");
        let has_sink = matches.iter().any(|m| m.effect_kind == "sink");

        assert!(has_source, "Should have at least one source match");
        assert!(has_sink, "Should have at least one sink match");

        // Print matches for debugging
        for m in &matches {
            println!("  - {}: {} (confidence={:.2})", m.rule_id, m.effect_kind, m.confidence);
        }
    }
}
