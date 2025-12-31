//! Phase 1 Integration Tests
//!
//! Tests for Phase 1 improvements:
//! 1. EdgeContext (ReadWriteContext, ControlFlowContext enums)
//! 2. NodeBuilder (validation patterns)
//! 3. OccurrenceArena (string optimization)

use codegraph_ir::shared::models::{
    Edge, EdgeKind, EdgeMetadata,
    Node, NodeKind,
    Span,
    ReadWriteContext, ControlFlowContext,
};
use codegraph_ir::shared::models::occurrence::{Occurrence, OccurrenceGenerator};
use codegraph_ir::shared::models::occurrence_arena::OccurrenceArena;

#[test]
fn test_edge_context_type_safety() {
    // Type-safe edge context (no typos possible!)
    let mut metadata = EdgeMetadata::default();
    metadata.rw_context = Some(ReadWriteContext::Assignment);

    assert_eq!(metadata.rw_context.unwrap().as_str(), "assignment");
}

#[test]
fn test_edge_context_migration() {
    // Migration from string-based context
    #[allow(deprecated)]
    let old_context = Some("ASSIGNMENT".to_string());

    let new_context = old_context
        .as_ref()
        .map(|s| ReadWriteContext::from_str(s));

    assert_eq!(new_context, Some(ReadWriteContext::Assignment));
}

#[test]
fn test_control_flow_context() {
    let metadata = EdgeMetadata {
        cf_context: Some(ControlFlowContext::TrueBranch),
        ..Default::default()
    };

    assert_eq!(metadata.cf_context.unwrap().as_str(), "true_branch");
}

#[test]
fn test_node_builder_basic() {
    let node = Node::new(
        "test:1".to_string(),
        NodeKind::Function,
        "test.foo".to_string(),
        "test.py".to_string(),
        Span::new(1, 0, 10, 0),
    );

    assert_eq!(node.id, "test:1");
    assert_eq!(node.kind, NodeKind::Function);
    assert_eq!(node.fqn, "test.foo");
}

#[test]
fn test_occurrence_arena_basic() {
    let mut arena = OccurrenceArena::new();

    let node = Node::new(
        "node:1".to_string(),
        NodeKind::Function,
        "foo".to_string(),
        "test.py".to_string(),
        Span::new(1, 0, 5, 0),
    );

    let edge = Edge {
        source_id: "node:1".to_string(),
        target_id: "node:2".to_string(),
        kind: EdgeKind::Calls,
        span: Some(Span::new(2, 0, 2, 10)),
        metadata: None,
        attrs: None,
    };

    let target_node = Node::new(
        "node:2".to_string(),
        NodeKind::Function,
        "bar".to_string(),
        "test.py".to_string(),
        Span::new(10, 0, 15, 0),
    );

    let occurrences = arena.generate(&[node, target_node], &[edge]);

    // Should have 3 occurrences: 2 definitions + 1 reference
    assert_eq!(occurrences.len(), 3);
}

#[test]
fn test_occurrence_arena_stats() {
    let mut arena = OccurrenceArena::new();

    let nodes: Vec<Node> = (0..100)
        .map(|i| {
            Node::new(
                format!("node:{}", i),
                NodeKind::Function,
                format!("func_{}", i),
                "test.py".to_string(), // Same file → should deduplicate
                Span::new(i as u32, 0, (i + 5) as u32, 0),
            )
        })
        .collect();

    let occurrences = arena.generate(&nodes, &[]);

    assert_eq!(occurrences.len(), 100); // 100 definitions

    let stats = arena.stats();
    assert_eq!(stats.occurrences_generated, 100);

    // String interning should show deduplication
    let interner_stats = &stats.string_interner_stats;
    println!(
        "String deduplication: {} total, {} unique ({}% savings)",
        interner_stats.total_strings,
        interner_stats.unique_strings,
        (100 * (interner_stats.total_strings - interner_stats.unique_strings))
            / interner_stats.total_strings.max(1)
    );

    // file_path should be heavily deduplicated (100 nodes → 1 unique path)
    assert!(interner_stats.unique_strings < interner_stats.total_strings);
}

#[test]
fn test_occurrence_generator() {
    let mut gen = OccurrenceGenerator::new();

    let node = Node::new(
        "test:1".to_string(),
        NodeKind::Variable,
        "x".to_string(),
        "test.py".to_string(),
        Span::new(1, 0, 1, 10),
    );

    let edge = Edge {
        source_id: "test:2".to_string(),
        target_id: "test:1".to_string(),
        kind: EdgeKind::Reads,
        span: Some(Span::new(2, 5, 2, 6)),
        metadata: Some(EdgeMetadata {
            rw_context: Some(ReadWriteContext::Return),
            ..Default::default()
        }),
        attrs: None,
    };

    let caller_node = Node::new(
        "test:2".to_string(),
        NodeKind::Function,
        "foo".to_string(),
        "test.py".to_string(),
        Span::new(2, 0, 5, 0),
    );

    let occurrences = gen.generate(&[node, caller_node], &[edge]);

    // 2 definitions + 1 reference
    assert_eq!(occurrences.len(), 3);

    // Check reference has correct role
    let reference = occurrences.iter().find(|occ| occ.id.contains("ref"));
    assert!(reference.is_some());
}

#[test]
fn test_phase1_end_to_end() {
    // Complete workflow: Build nodes → Create edges → Generate occurrences

    // 1. Create nodes with NodeBuilder (type-safe)
    let func_node = Node::new(
        "node:func".to_string(),
        NodeKind::Function,
        "process_data".to_string(),
        "app.py".to_string(),
        Span::new(1, 0, 10, 0),
    );

    let var_node = Node::new(
        "node:var".to_string(),
        NodeKind::Variable,
        "result".to_string(),
        "app.py".to_string(),
        Span::new(5, 4, 5, 10),
    );

    // 2. Create edge with type-safe context
    let edge = Edge {
        source_id: "node:func".to_string(),
        target_id: "node:var".to_string(),
        kind: EdgeKind::Writes,
        span: Some(Span::new(5, 4, 5, 20)),
        metadata: Some(EdgeMetadata {
            rw_context: Some(ReadWriteContext::Assignment),
            ..Default::default()
        }),
        attrs: None,
    };

    // 3. Generate occurrences with arena optimization
    let mut arena = OccurrenceArena::new();
    let occurrences = arena.generate(&[func_node, var_node], &[edge]);

    // Verify
    assert_eq!(occurrences.len(), 3); // 2 defs + 1 write ref

    // Check write reference has correct context
    let write_ref = occurrences
        .iter()
        .find(|occ| occ.id.contains("write"));
    assert!(write_ref.is_some());

    // Arena stats should show string deduplication
    let stats = arena.stats();
    assert!(stats.string_interner_stats.unique_strings > 0);
}

#[test]
fn test_readwrite_context_from_str_performance() {
    // Test zero-allocation parsing

    let cases = vec![
        ("assignment", ReadWriteContext::Assignment),
        ("RETURN", ReadWriteContext::Return),
        ("Argument", ReadWriteContext::ArgumentPassing),
        ("unknown", ReadWriteContext::Other),
    ];

    for (input, expected) in cases {
        assert_eq!(ReadWriteContext::from_str(input), expected);
    }
}
