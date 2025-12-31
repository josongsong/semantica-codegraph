//! Domain Model Tests
//!
//! TDD: Comprehensive test coverage for all domain models.
//!
//! Test Categories:
//! 1. Construction & Basic Operations
//! 2. Invariant Validation
//! 3. Edge Cases
//! 4. Corner Cases
//! 5. Extreme Cases

use super::metrics::ImportanceWeights;
use super::*;

// ============================================================================
// RepoMapNode Tests
// ============================================================================

#[test]
fn test_node_creation_basic() {
    let node = RepoMapNode::new(
        "test:root".to_string(),
        NodeKind::Repository,
        "test-repo".to_string(),
        "/".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    assert_eq!(node.id, "test:root");
    assert_eq!(node.kind, NodeKind::Repository);
    assert_eq!(node.name, "test-repo");
    assert_eq!(node.path, "/");
    assert_eq!(node.parent_id, None);
    assert!(node.children_ids.is_empty());
    assert_eq!(node.depth, 0);
}

#[test]
fn test_node_with_parent() {
    let node = RepoMapNode::new(
        "test:child".to_string(),
        NodeKind::Directory,
        "src".to_string(),
        "/src".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    )
    .with_parent("test:root".to_string())
    .with_depth(1);

    assert_eq!(node.parent_id, Some("test:root".to_string()));
    assert_eq!(node.depth, 1);
}

#[test]
fn test_node_add_child() {
    let mut parent = RepoMapNode::new(
        "test:parent".to_string(),
        NodeKind::Directory,
        "src".to_string(),
        "/src".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    parent.add_child("test:child1".to_string());
    parent.add_child("test:child2".to_string());

    assert_eq!(parent.children_ids.len(), 2);
    assert!(parent.children_ids.contains(&"test:child1".to_string()));
    assert!(parent.children_ids.contains(&"test:child2".to_string()));
}

#[test]
fn test_node_add_child_duplicate() {
    let mut parent = RepoMapNode::new(
        "test:parent".to_string(),
        NodeKind::Directory,
        "src".to_string(),
        "/src".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    parent.add_child("test:child1".to_string());
    parent.add_child("test:child1".to_string()); // Duplicate

    // Should not add duplicate
    assert_eq!(parent.children_ids.len(), 1);
}

#[test]
fn test_node_is_leaf() {
    let leaf = RepoMapNode::new(
        "test:leaf".to_string(),
        NodeKind::Function,
        "foo".to_string(),
        "/src/main.py".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    assert!(leaf.is_leaf());

    let mut non_leaf = leaf.clone();
    non_leaf.add_child("test:child".to_string());
    assert!(!non_leaf.is_leaf());
}

#[test]
fn test_node_is_root() {
    let root = RepoMapNode::new(
        "test:root".to_string(),
        NodeKind::Repository,
        "test-repo".to_string(),
        "/".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    assert!(root.is_root());

    let non_root = root.clone().with_parent("test:parent".to_string());
    assert!(!non_root.is_root());
}

// ============================================================================
// RepoMapSnapshot Tests
// ============================================================================

#[test]
fn test_snapshot_creation_basic() {
    let root = RepoMapNode::new(
        "repo:root".to_string(),
        NodeKind::Repository,
        "test-repo".to_string(),
        "/".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    let snapshot = RepoMapSnapshot::new("repo-1".to_string(), "v1".to_string(), vec![root]);

    assert_eq!(snapshot.repo_id, "repo-1");
    assert_eq!(snapshot.snapshot_id, "v1");
    assert_eq!(snapshot.nodes.len(), 1);
    assert_eq!(snapshot.root_id, "repo:root");
}

#[test]
fn test_snapshot_with_hierarchy() {
    let root = RepoMapNode::new(
        "repo:root".to_string(),
        NodeKind::Repository,
        "test-repo".to_string(),
        "/".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    let mut dir = RepoMapNode::new(
        "repo:src".to_string(),
        NodeKind::Directory,
        "src".to_string(),
        "/src".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    )
    .with_parent("repo:root".to_string())
    .with_depth(1);

    let file = RepoMapNode::new(
        "repo:src:main.py".to_string(),
        NodeKind::File,
        "main.py".to_string(),
        "/src/main.py".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    )
    .with_parent("repo:src".to_string())
    .with_depth(2);

    dir.add_child("repo:src:main.py".to_string());

    let mut root_with_children = root;
    root_with_children.add_child("repo:src".to_string());

    let snapshot = RepoMapSnapshot::new(
        "repo-1".to_string(),
        "v1".to_string(),
        vec![root_with_children, dir, file],
    );

    assert_eq!(snapshot.nodes.len(), 3);

    // Test get_children
    let children = snapshot.get_children("repo:root");
    assert_eq!(children.len(), 1);
    assert_eq!(children[0].id, "repo:src");
}

#[test]
fn test_snapshot_validation_valid() {
    let root = RepoMapNode::new(
        "repo:root".to_string(),
        NodeKind::Repository,
        "test-repo".to_string(),
        "/".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    let snapshot = RepoMapSnapshot::new("repo-1".to_string(), "v1".to_string(), vec![root]);

    assert!(snapshot.validate().is_ok());
}

#[test]
#[should_panic(expected = "RepoMapSnapshot must have exactly one root node")]
fn test_snapshot_no_root_panics() {
    let non_root = RepoMapNode::new(
        "repo:src".to_string(),
        NodeKind::Directory,
        "src".to_string(),
        "/src".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    )
    .with_parent("repo:root".to_string());

    // Should panic: no root node
    RepoMapSnapshot::new("repo-1".to_string(), "v1".to_string(), vec![non_root]);
}

#[test]
fn test_snapshot_validation_invalid_parent() {
    let root = RepoMapNode::new(
        "repo:root".to_string(),
        NodeKind::Repository,
        "test-repo".to_string(),
        "/".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    let orphan = RepoMapNode::new(
        "repo:orphan".to_string(),
        NodeKind::File,
        "orphan.py".to_string(),
        "/orphan.py".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    )
    .with_parent("repo:nonexistent".to_string());

    let snapshot = RepoMapSnapshot::new("repo-1".to_string(), "v1".to_string(), vec![root, orphan]);

    let result = snapshot.validate();
    assert!(result.is_err());

    let errors = result.unwrap_err();
    assert!(errors
        .iter()
        .any(|e| e.contains("references non-existent parent")));
}

#[test]
fn test_snapshot_validation_cycle_detection() {
    // Create a cycle: node1 -> node2 -> node1
    let root = RepoMapNode::new(
        "repo:root".to_string(),
        NodeKind::Repository,
        "test-repo".to_string(),
        "/".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    let mut node1 = RepoMapNode::new(
        "repo:node1".to_string(),
        NodeKind::Directory,
        "node1".to_string(),
        "/node1".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    )
    .with_parent("repo:root".to_string());

    let mut node2 = RepoMapNode::new(
        "repo:node2".to_string(),
        NodeKind::Directory,
        "node2".to_string(),
        "/node2".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    )
    .with_parent("repo:node1".to_string());

    // Create cycle
    node1.add_child("repo:node2".to_string());
    node2.add_child("repo:node1".to_string()); // Cycle!

    let mut root_with_child = root;
    root_with_child.add_child("repo:node1".to_string());

    let snapshot = RepoMapSnapshot::new(
        "repo-1".to_string(),
        "v1".to_string(),
        vec![root_with_child, node1, node2],
    );

    let result = snapshot.validate();
    assert!(result.is_err());

    let errors = result.unwrap_err();
    assert!(errors.iter().any(|e| e.contains("Cycle detected")));
}

// ============================================================================
// RepoMapMetrics Tests
// ============================================================================

#[test]
fn test_metrics_default() {
    let metrics = RepoMapMetrics::default();

    assert_eq!(metrics.loc, 0);
    assert_eq!(metrics.symbol_count, 0);
    assert_eq!(metrics.complexity, 0);
    assert_eq!(metrics.pagerank, 0.0);
    assert!(metrics.authority_score.is_none());
    assert!(metrics.hub_score.is_none());
}

#[test]
fn test_metrics_with_loc() {
    let metrics = RepoMapMetrics::with_loc(100);

    assert_eq!(metrics.loc, 100);
    assert_eq!(metrics.symbol_count, 0);
}

#[test]
fn test_metrics_with_pagerank() {
    let metrics = RepoMapMetrics::with_loc(100).with_pagerank(0.8);

    assert_eq!(metrics.pagerank, 0.8);
}

#[test]
fn test_metrics_with_hits() {
    let metrics = RepoMapMetrics::with_loc(100).with_hits(0.7, 0.6);

    assert_eq!(metrics.authority_score, Some(0.7));
    assert_eq!(metrics.hub_score, Some(0.6));
}

#[test]
fn test_metrics_combined_importance() {
    let metrics = RepoMapMetrics::with_loc(100)
        .with_pagerank(0.8)
        .with_hits(0.7, 0.6)
        .with_git_metrics(5.0, 1234567890, 150);

    let weights = ImportanceWeights::default(); // 0.5, 0.3, 0.2
    let importance = metrics.combined_importance(&weights);

    // Expected: 0.5 * 0.8 + 0.3 * 0.7 + 0.2 * 5.0 = 0.4 + 0.21 + 1.0 = 1.61
    assert!((importance - 1.61).abs() < 0.01);
}

// ============================================================================
// Edge Cases
// ============================================================================

#[test]
fn test_empty_snapshot_name() {
    let root = RepoMapNode::new(
        "repo:root".to_string(),
        NodeKind::Repository,
        "".to_string(), // Empty name
        "/".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    let snapshot = RepoMapSnapshot::new("repo-1".to_string(), "v1".to_string(), vec![root]);

    // Should not crash, empty name is allowed
    assert_eq!(snapshot.nodes.len(), 1);
}

#[test]
fn test_very_deep_hierarchy() {
    // Create a very deep tree (1000 levels)
    let mut nodes = Vec::new();

    let root = RepoMapNode::new(
        "repo:root".to_string(),
        NodeKind::Repository,
        "test-repo".to_string(),
        "/".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );
    nodes.push(root);

    for i in 0..1000 {
        let parent_id = if i == 0 {
            "repo:root".to_string()
        } else {
            format!("repo:node{}", i - 1)
        };

        let node = RepoMapNode::new(
            format!("repo:node{}", i),
            NodeKind::Directory,
            format!("dir{}", i),
            format!("/dir{}", i),
            "repo-1".to_string(),
            "v1".to_string(),
        )
        .with_parent(parent_id.clone())
        .with_depth(i + 1);

        // Add to parent's children
        if i == 0 {
            nodes[0].add_child(node.id.clone());
        } else {
            nodes[i].add_child(node.id.clone());
        }

        nodes.push(node);
    }

    let snapshot = RepoMapSnapshot::new("repo-1".to_string(), "v1".to_string(), nodes);

    assert_eq!(snapshot.nodes.len(), 1001); // root + 1000 dirs
    assert!(snapshot.validate().is_ok());
}

#[test]
fn test_very_wide_tree() {
    // Create a very wide tree (10000 children)
    let mut root = RepoMapNode::new(
        "repo:root".to_string(),
        NodeKind::Repository,
        "test-repo".to_string(),
        "/".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    let mut nodes = vec![root.clone()];

    for i in 0..10000 {
        let child = RepoMapNode::new(
            format!("repo:child{}", i),
            NodeKind::File,
            format!("file{}.py", i),
            format!("/file{}.py", i),
            "repo-1".to_string(),
            "v1".to_string(),
        )
        .with_parent("repo:root".to_string())
        .with_depth(1);

        root.add_child(child.id.clone());
        nodes.push(child);
    }

    nodes[0] = root; // Update root with all children

    let snapshot = RepoMapSnapshot::new("repo-1".to_string(), "v1".to_string(), nodes);

    assert_eq!(snapshot.nodes.len(), 10001);
    assert_eq!(snapshot.get_children("repo:root").len(), 10000);
}

// ============================================================================
// Corner Cases
// ============================================================================

#[test]
fn test_unicode_names() {
    let node = RepoMapNode::new(
        "repo:unicode".to_string(),
        NodeKind::File,
        "测试文件.py".to_string(), // Chinese
        "/测试文件.py".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    assert_eq!(node.name, "测试文件.py");
}

#[test]
fn test_special_characters_in_path() {
    let node = RepoMapNode::new(
        "repo:special".to_string(),
        NodeKind::File,
        "file with spaces & symbols!.py".to_string(),
        "/path/with spaces/file with spaces & symbols!.py".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    assert!(node.path.contains(" "));
    assert!(node.path.contains("&"));
    assert!(node.path.contains("!"));
}

#[test]
fn test_metrics_extreme_values() {
    let mut metrics = RepoMapMetrics::with_loc(usize::MAX);
    metrics.symbol_count = usize::MAX;
    metrics.complexity = usize::MAX;
    metrics.pagerank = f64::MAX;

    // Should not crash
    assert_eq!(metrics.loc, usize::MAX);
    assert_eq!(metrics.pagerank, f64::MAX);
}

#[test]
fn test_metrics_negative_pagerank() {
    // PageRank should be 0.0-1.0, but test robustness
    let metrics = RepoMapMetrics::with_loc(100).with_pagerank(-0.5);

    assert_eq!(metrics.pagerank, -0.5);

    // combined_importance should handle this gracefully
    let weights = ImportanceWeights::default();
    let importance = metrics.combined_importance(&weights);

    // Should not be NaN
    assert!(!importance.is_nan());
}

#[test]
fn test_snapshot_serialization_roundtrip() {
    let root = RepoMapNode::new(
        "repo:root".to_string(),
        NodeKind::Repository,
        "test-repo".to_string(),
        "/".to_string(),
        "repo-1".to_string(),
        "v1".to_string(),
    );

    let snapshot = RepoMapSnapshot::new("repo-1".to_string(), "v1".to_string(), vec![root]);

    // Serialize to JSON
    let json = serde_json::to_string(&snapshot).expect("Failed to serialize");

    // Deserialize back
    let deserialized: RepoMapSnapshot = serde_json::from_str(&json).expect("Failed to deserialize");

    assert_eq!(deserialized.repo_id, snapshot.repo_id);
    assert_eq!(deserialized.snapshot_id, snapshot.snapshot_id);
    assert_eq!(deserialized.nodes.len(), snapshot.nodes.len());
}
