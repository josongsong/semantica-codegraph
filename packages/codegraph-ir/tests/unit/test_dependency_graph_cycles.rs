//! Verification tests for DependencyGraph cycle handling

#[cfg(feature = "cache")]
mod dependency_graph_cycle_tests {
    use codegraph_ir::features::cache::{DependencyGraph, FileId, Fingerprint, Language};

    #[test]
    fn test_self_reference_does_not_hang() {
        // This test verifies that self-references don't cause infinite loops
        println!("Creating graph...");
        let mut graph = DependencyGraph::new();
        let file_a = FileId::from_path_str("a.py", Language::Python);

        // Register file with self-reference
        println!("Registering file with self-reference...");
        graph.register_file(file_a.clone(), Fingerprint::compute(b"a"), &[file_a.clone()]);

        println!("Calling get_affected_files...");
        // This should NOT hang - HashSet prevents duplicate visits
        let affected = graph.get_affected_files(&[file_a.clone()]);

        println!("Got {} affected files", affected.len());
        assert_eq!(affected.len(), 1, "Self-reference should only affect itself");
        assert!(affected.contains(&file_a), "Should contain the file itself");
        println!("Test passed!");
    }

    #[test]
    fn test_circular_dependency_does_not_hang() {
        // This test verifies that circular dependencies don't cause infinite loops
        let mut graph = DependencyGraph::new();

        let file_a = FileId::from_path_str("a.py", Language::Python);
        let file_b = FileId::from_path_str("b.py", Language::Python);
        let file_c = FileId::from_path_str("c.py", Language::Python);

        // Create cycle: a -> b -> c -> a
        graph.register_file(file_a.clone(), Fingerprint::compute(b"a"), &[file_b.clone()]);
        graph.register_file(file_b.clone(), Fingerprint::compute(b"b"), &[file_c.clone()]);
        graph.register_file(file_c.clone(), Fingerprint::compute(b"c"), &[file_a.clone()]);

        // This should NOT hang - HashSet prevents revisiting nodes
        let affected = graph.get_affected_files(&[file_a.clone()]);

        // All files in the cycle should be affected
        assert!(affected.len() >= 1, "Should affect at least the changed file");
        assert!(affected.contains(&file_a), "Should contain file_a");

        // In a cycle, all files are transitively dependent
        // BFS should visit each node exactly once
        println!("Affected files in cycle: {}", affected.len());
        for f in &affected {
            println!("  - {:?}", f.path);
        }
    }

    #[test]
    fn test_simple_chain_no_cycle() {
        // Baseline: normal chain should work correctly
        let mut graph = DependencyGraph::new();

        let file_a = FileId::from_path_str("a.py", Language::Python);
        let file_b = FileId::from_path_str("b.py", Language::Python);
        let file_c = FileId::from_path_str("c.py", Language::Python);

        // Chain: a -> b -> c (no cycle)
        graph.register_file(file_a.clone(), Fingerprint::compute(b"a"), &[file_b.clone()]);
        graph.register_file(file_b.clone(), Fingerprint::compute(b"b"), &[file_c.clone()]);
        graph.register_file(file_c.clone(), Fingerprint::compute(b"c"), &[]);

        // If c changes, all should be affected
        let affected = graph.get_affected_files(&[file_c.clone()]);

        assert_eq!(affected.len(), 3, "Should affect all 3 files in chain");
        assert!(affected.contains(&file_a));
        assert!(affected.contains(&file_b));
        assert!(affected.contains(&file_c));
    }
}
