//! Extreme edge case tests for DependencyGraph
//!
//! Tests the most pathological cases that could break the system

#[cfg(feature = "cache")]
mod dependency_graph_extreme_tests {
    use codegraph_ir::features::cache::{DependencyGraph, FileId, Fingerprint, Language};

    // ═══════════════════════════════════════════════════════════════════
    // Extreme Graph Structures
    // ═══════════════════════════════════════════════════════════════════

    #[test]
    fn test_fully_connected_graph() {
        // Every file depends on every other file (N^2 edges)
        let mut graph = DependencyGraph::new();
        let n = 5;
        let mut files: Vec<FileId> = Vec::new();

        // Create files
        for i in 0..n {
            files.push(FileId::from_path_str(&format!("file{}.py", i), Language::Python));
        }

        // Register each file with ALL other files as dependencies
        for i in 0..n {
            let deps: Vec<FileId> = files.iter()
                .enumerate()
                .filter(|(j, _)| *j != i)  // Exclude self
                .map(|(_, f)| f.clone())
                .collect();

            graph.register_file(
                files[i].clone(),
                Fingerprint::compute(format!("file{}", i).as_bytes()),
                &deps,
            );
        }

        // If any file changes, ALL files should be affected
        let affected = graph.get_affected_files(&[files[0].clone()]);

        assert_eq!(affected.len(), n, "Fully connected graph: all files affected");
        for file in &files {
            assert!(affected.contains(file), "Should contain {:?}", file.path);
        }
    }

    #[test]
    fn test_star_topology() {
        // Central hub with many spokes (1 core, N peripherals)
        let mut graph = DependencyGraph::new();

        let hub = FileId::from_path_str("hub.py", Language::Python);
        let n = 10;
        let mut spokes: Vec<FileId> = Vec::new();

        // Register hub
        graph.register_file(hub.clone(), Fingerprint::compute(b"hub"), &[]);

        // Register spokes (all depend on hub)
        for i in 0..n {
            let spoke = FileId::from_path_str(&format!("spoke{}.py", i), Language::Python);
            spokes.push(spoke.clone());
            graph.register_file(
                spoke,
                Fingerprint::compute(format!("spoke{}", i).as_bytes()),
                &[hub.clone()],
            );
        }

        // If hub changes, all spokes + hub affected
        let affected = graph.get_affected_files(&[hub.clone()]);

        assert_eq!(affected.len(), 1 + n, "Hub + all spokes");
        assert!(affected.contains(&hub));
        for spoke in &spokes {
            assert!(affected.contains(spoke));
        }

        // If spoke changes, only that spoke affected
        let affected = graph.get_affected_files(&[spokes[0].clone()]);
        assert_eq!(affected.len(), 1, "Only the spoke itself");
    }

    #[test]
    fn test_binary_tree_dependency() {
        // Binary tree: root depends on 2 children, each child on 2 grandchildren, etc.
        let mut graph = DependencyGraph::new();

        let root = FileId::from_path_str("root.py", Language::Python);
        let left = FileId::from_path_str("left.py", Language::Python);
        let right = FileId::from_path_str("right.py", Language::Python);
        let ll = FileId::from_path_str("left_left.py", Language::Python);
        let lr = FileId::from_path_str("left_right.py", Language::Python);
        let rl = FileId::from_path_str("right_left.py", Language::Python);
        let rr = FileId::from_path_str("right_right.py", Language::Python);

        // Build tree (bottom-up dependencies)
        graph.register_file(ll.clone(), Fingerprint::compute(b"ll"), &[]);
        graph.register_file(lr.clone(), Fingerprint::compute(b"lr"), &[]);
        graph.register_file(rl.clone(), Fingerprint::compute(b"rl"), &[]);
        graph.register_file(rr.clone(), Fingerprint::compute(b"rr"), &[]);

        graph.register_file(left.clone(), Fingerprint::compute(b"left"), &[ll.clone(), lr.clone()]);
        graph.register_file(right.clone(), Fingerprint::compute(b"right"), &[rl.clone(), rr.clone()]);

        graph.register_file(root.clone(), Fingerprint::compute(b"root"), &[left.clone(), right.clone()]);

        // If leaf changes, should propagate up the tree
        let affected = graph.get_affected_files(&[ll.clone()]);

        assert!(affected.contains(&ll), "Leaf");
        assert!(affected.contains(&left), "Parent");
        assert!(affected.contains(&root), "Root");
        assert_eq!(affected.len(), 3, "Leaf + parent + root");
    }

    // ═══════════════════════════════════════════════════════════════════
    // Multiple Cycles
    // ═══════════════════════════════════════════════════════════════════

    #[test]
    fn test_multiple_disjoint_cycles() {
        // Two separate cycles in the same graph
        let mut graph = DependencyGraph::new();

        // Cycle 1: a -> b -> c -> a
        let a1 = FileId::from_path_str("a1.py", Language::Python);
        let b1 = FileId::from_path_str("b1.py", Language::Python);
        let c1 = FileId::from_path_str("c1.py", Language::Python);

        graph.register_file(a1.clone(), Fingerprint::compute(b"a1"), &[b1.clone()]);
        graph.register_file(b1.clone(), Fingerprint::compute(b"b1"), &[c1.clone()]);
        graph.register_file(c1.clone(), Fingerprint::compute(b"c1"), &[a1.clone()]);

        // Cycle 2: x -> y -> z -> x
        let x2 = FileId::from_path_str("x2.py", Language::Python);
        let y2 = FileId::from_path_str("y2.py", Language::Python);
        let z2 = FileId::from_path_str("z2.py", Language::Python);

        graph.register_file(x2.clone(), Fingerprint::compute(b"x2"), &[y2.clone()]);
        graph.register_file(y2.clone(), Fingerprint::compute(b"y2"), &[z2.clone()]);
        graph.register_file(z2.clone(), Fingerprint::compute(b"z2"), &[x2.clone()]);

        // Change in cycle 1 should NOT affect cycle 2
        let affected = graph.get_affected_files(&[a1.clone()]);

        assert!(affected.contains(&a1));
        assert!(affected.contains(&b1));
        assert!(affected.contains(&c1));
        assert!(!affected.contains(&x2), "Cycle 2 should not be affected");
        assert!(!affected.contains(&y2), "Cycle 2 should not be affected");
        assert!(!affected.contains(&z2), "Cycle 2 should not be affected");
        assert_eq!(affected.len(), 3, "Only cycle 1 files");
    }

    #[test]
    fn test_nested_cycles() {
        // Outer cycle contains inner cycle
        let mut graph = DependencyGraph::new();

        let a = FileId::from_path_str("a.py", Language::Python);
        let b = FileId::from_path_str("b.py", Language::Python);
        let c = FileId::from_path_str("c.py", Language::Python);
        let d = FileId::from_path_str("d.py", Language::Python);

        // Inner cycle: a <-> b
        // Outer cycle: a -> c -> d -> a
        graph.register_file(a.clone(), Fingerprint::compute(b"a"), &[b.clone(), c.clone()]);
        graph.register_file(b.clone(), Fingerprint::compute(b"b"), &[a.clone()]);
        graph.register_file(c.clone(), Fingerprint::compute(b"c"), &[d.clone()]);
        graph.register_file(d.clone(), Fingerprint::compute(b"d"), &[a.clone()]);

        // All should be affected (interconnected cycles)
        let affected = graph.get_affected_files(&[a.clone()]);

        assert_eq!(affected.len(), 4, "All files in nested cycles");
        assert!(affected.contains(&a));
        assert!(affected.contains(&b));
        assert!(affected.contains(&c));
        assert!(affected.contains(&d));
    }

    // ═══════════════════════════════════════════════════════════════════
    // Pathological Dependencies
    // ═══════════════════════════════════════════════════════════════════

    #[test]
    fn test_file_with_duplicate_dependencies() {
        // File lists same dependency multiple times
        let mut graph = DependencyGraph::new();

        let file_a = FileId::from_path_str("a.py", Language::Python);
        let file_b = FileId::from_path_str("b.py", Language::Python);

        // Register b with duplicate dependencies (pathological input)
        graph.register_file(file_b.clone(), Fingerprint::compute(b"b"), &[]);
        graph.register_file(
            file_a.clone(),
            Fingerprint::compute(b"a"),
            &[file_b.clone(), file_b.clone(), file_b.clone()],  // Duplicates!
        );

        let affected = graph.get_affected_files(&[file_b.clone()]);

        assert_eq!(affected.len(), 2, "Should deduplicate");
        assert!(affected.contains(&file_a));
        assert!(affected.contains(&file_b));
    }

    #[test]
    fn test_empty_dependencies_list() {
        // File with empty dependency list (leaf node)
        let mut graph = DependencyGraph::new();

        let file = FileId::from_path_str("isolated.py", Language::Python);

        graph.register_file(file.clone(), Fingerprint::compute(b"isolated"), &[]);

        let affected = graph.get_affected_files(&[file.clone()]);

        assert_eq!(affected.len(), 1);
        assert!(affected.contains(&file));
    }

    #[test]
    fn test_query_nonexistent_file() {
        // Query for file that was never registered
        let graph = DependencyGraph::new();

        let ghost = FileId::from_path_str("ghost.py", Language::Python);

        let affected = graph.get_affected_files(&[ghost.clone()]);

        // Should handle gracefully (either empty or just the file)
        assert!(affected.is_empty() || affected.len() == 1);
    }

    #[test]
    fn test_update_file_fingerprint() {
        // Register file twice with different fingerprints (file modified)
        let mut graph = DependencyGraph::new();

        let file = FileId::from_path_str("mutable.py", Language::Python);
        let dep = FileId::from_path_str("dep.py", Language::Python);

        // First registration
        graph.register_file(dep.clone(), Fingerprint::compute(b"dep_v1"), &[]);
        graph.register_file(file.clone(), Fingerprint::compute(b"v1"), &[dep.clone()]);

        // Update with new fingerprint (simulates file edit)
        graph.register_file(file.clone(), Fingerprint::compute(b"v2"), &[dep.clone()]);

        let affected = graph.get_affected_files(&[file.clone()]);

        assert_eq!(affected.len(), 1, "No dependents, only self");
        assert!(affected.contains(&file));
    }

    // ═══════════════════════════════════════════════════════════════════
    // Multi-Language Edge Cases
    // ═══════════════════════════════════════════════════════════════════

    #[test]
    fn test_same_filename_different_languages() {
        // util.py and util.js and util.rs in same graph
        let mut graph = DependencyGraph::new();

        let py_util = FileId::from_path_str("util.py", Language::Python);
        let js_util = FileId::from_path_str("util.js", Language::JavaScript);
        let rs_util = FileId::from_path_str("util.rs", Language::Rust);

        graph.register_file(py_util.clone(), Fingerprint::compute(b"py"), &[]);
        graph.register_file(js_util.clone(), Fingerprint::compute(b"js"), &[]);
        graph.register_file(rs_util.clone(), Fingerprint::compute(b"rs"), &[]);

        // All should be independent
        let affected = graph.get_affected_files(&[py_util.clone()]);
        assert_eq!(affected.len(), 1, "Only Python file");

        let affected = graph.get_affected_files(&[js_util.clone()]);
        assert_eq!(affected.len(), 1, "Only JavaScript file");

        let affected = graph.get_affected_files(&[rs_util.clone()]);
        assert_eq!(affected.len(), 1, "Only Rust file");
    }

    #[test]
    fn test_cross_language_cycle() {
        // Python -> TypeScript -> Rust -> Python (cross-language cycle)
        let mut graph = DependencyGraph::new();

        let py = FileId::from_path_str("main.py", Language::Python);
        let ts = FileId::from_path_str("main.ts", Language::TypeScript);
        let rs = FileId::from_path_str("main.rs", Language::Rust);

        graph.register_file(py.clone(), Fingerprint::compute(b"py"), &[ts.clone()]);
        graph.register_file(ts.clone(), Fingerprint::compute(b"ts"), &[rs.clone()]);
        graph.register_file(rs.clone(), Fingerprint::compute(b"rs"), &[py.clone()]);

        // All should be affected
        let affected = graph.get_affected_files(&[py.clone()]);

        assert_eq!(affected.len(), 3, "Cross-language cycle");
        assert!(affected.contains(&py));
        assert!(affected.contains(&ts));
        assert!(affected.contains(&rs));
    }

    // ═══════════════════════════════════════════════════════════════════
    // Batch Operations
    // ═══════════════════════════════════════════════════════════════════

    #[test]
    fn test_multiple_changed_files_disjoint() {
        // Multiple changed files with no overlap in affected sets
        let mut graph = DependencyGraph::new();

        let a1 = FileId::from_path_str("a1.py", Language::Python);
        let a2 = FileId::from_path_str("a2.py", Language::Python);
        graph.register_file(a2.clone(), Fingerprint::compute(b"a2"), &[a1.clone()]);
        graph.register_file(a1.clone(), Fingerprint::compute(b"a1"), &[]);

        let b1 = FileId::from_path_str("b1.py", Language::Python);
        let b2 = FileId::from_path_str("b2.py", Language::Python);
        graph.register_file(b2.clone(), Fingerprint::compute(b"b2"), &[b1.clone()]);
        graph.register_file(b1.clone(), Fingerprint::compute(b"b1"), &[]);

        // Query both roots at once
        let affected = graph.get_affected_files(&[a1.clone(), b1.clone()]);

        assert_eq!(affected.len(), 4, "Union of both chains");
        assert!(affected.contains(&a1));
        assert!(affected.contains(&a2));
        assert!(affected.contains(&b1));
        assert!(affected.contains(&b2));
    }

    #[test]
    fn test_multiple_changed_files_overlapping() {
        // Multiple changed files with overlapping affected sets
        let mut graph = DependencyGraph::new();

        let base = FileId::from_path_str("base.py", Language::Python);
        let mid = FileId::from_path_str("mid.py", Language::Python);
        let top = FileId::from_path_str("top.py", Language::Python);

        graph.register_file(base.clone(), Fingerprint::compute(b"base"), &[]);
        graph.register_file(mid.clone(), Fingerprint::compute(b"mid"), &[base.clone()]);
        graph.register_file(top.clone(), Fingerprint::compute(b"top"), &[mid.clone()]);

        // Query both base and mid (overlapping: mid affects top, base affects mid+top)
        let affected = graph.get_affected_files(&[base.clone(), mid.clone()]);

        assert_eq!(affected.len(), 3, "Should deduplicate overlaps");
        assert!(affected.contains(&base));
        assert!(affected.contains(&mid));
        assert!(affected.contains(&top));
    }

    // ═══════════════════════════════════════════════════════════════════
    // Special File Paths
    // ═══════════════════════════════════════════════════════════════════

    #[test]
    fn test_deeply_nested_paths() {
        let mut graph = DependencyGraph::new();

        let deep = FileId::from_path_str(
            "a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p/q/r/s/t/u/v/w/x/y/z/file.py",
            Language::Python,
        );
        let shallow = FileId::from_path_str("main.py", Language::Python);

        graph.register_file(shallow.clone(), Fingerprint::compute(b"shallow"), &[deep.clone()]);
        graph.register_file(deep.clone(), Fingerprint::compute(b"deep"), &[]);

        let affected = graph.get_affected_files(&[deep.clone()]);

        assert_eq!(affected.len(), 2);
        assert!(affected.contains(&deep));
        assert!(affected.contains(&shallow));
    }

    #[test]
    fn test_special_characters_in_filename() {
        let mut graph = DependencyGraph::new();

        let special = FileId::from_path_str("test-file_v2.0[final].py", Language::Python);
        let normal = FileId::from_path_str("normal.py", Language::Python);

        graph.register_file(normal.clone(), Fingerprint::compute(b"normal"), &[special.clone()]);
        graph.register_file(special.clone(), Fingerprint::compute(b"special"), &[]);

        let affected = graph.get_affected_files(&[special.clone()]);

        assert_eq!(affected.len(), 2);
        assert!(affected.contains(&special));
        assert!(affected.contains(&normal));
    }

    #[test]
    fn test_unicode_filename() {
        let mut graph = DependencyGraph::new();

        let unicode = FileId::from_path_str("файл.py", Language::Python);  // Russian
        let emoji = FileId::from_path_str("test_🔥.py", Language::Python);

        graph.register_file(unicode.clone(), Fingerprint::compute(b"unicode"), &[]);
        graph.register_file(emoji.clone(), Fingerprint::compute(b"emoji"), &[unicode.clone()]);

        let affected = graph.get_affected_files(&[unicode.clone()]);

        assert_eq!(affected.len(), 2);
        assert!(affected.contains(&unicode));
        assert!(affected.contains(&emoji));
    }

    // ═══════════════════════════════════════════════════════════════════
    // Regression Tests for Edge Cases
    // ═══════════════════════════════════════════════════════════════════

    #[test]
    fn test_register_then_query_immediately() {
        // Register and query in quick succession (no intermediate operations)
        let mut graph = DependencyGraph::new();

        let file = FileId::from_path_str("quick.py", Language::Python);
        graph.register_file(file.clone(), Fingerprint::compute(b"quick"), &[]);

        let affected = graph.get_affected_files(&[file.clone()]);

        assert_eq!(affected.len(), 1);
        assert!(affected.contains(&file));
    }

    #[test]
    fn test_idempotent_registration() {
        // Register same file multiple times with same data
        let mut graph = DependencyGraph::new();

        let file = FileId::from_path_str("idempotent.py", Language::Python);
        let fp = Fingerprint::compute(b"same");

        graph.register_file(file.clone(), fp.clone(), &[]);
        graph.register_file(file.clone(), fp.clone(), &[]);
        graph.register_file(file.clone(), fp.clone(), &[]);

        let affected = graph.get_affected_files(&[file.clone()]);

        assert_eq!(affected.len(), 1, "Should handle idempotent ops");
        assert!(affected.contains(&file));
    }

    #[test]
    fn test_change_dependencies_between_registrations() {
        // First register with dep A, then re-register with dep B
        let mut graph = DependencyGraph::new();

        let file = FileId::from_path_str("main.py", Language::Python);
        let dep_a = FileId::from_path_str("dep_a.py", Language::Python);
        let dep_b = FileId::from_path_str("dep_b.py", Language::Python);

        // First: main depends on A
        graph.register_file(dep_a.clone(), Fingerprint::compute(b"a"), &[]);
        graph.register_file(file.clone(), Fingerprint::compute(b"main_v1"), &[dep_a.clone()]);

        // Then: main depends on B (refactored)
        graph.register_file(dep_b.clone(), Fingerprint::compute(b"b"), &[]);
        graph.register_file(file.clone(), Fingerprint::compute(b"main_v2"), &[dep_b.clone()]);

        // Changing B should affect main
        let affected = graph.get_affected_files(&[dep_b.clone()]);
        assert!(affected.contains(&file), "New dependency should propagate");

        // Note: Old dependency A might still have edge (graph doesn't remove edges)
        // This is OK - conservative over-invalidation is safe
    }
}
