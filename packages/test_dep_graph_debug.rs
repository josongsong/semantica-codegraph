// Quick test to debug DependencyGraph hang issue

use codegraph_ir::features::cache::{DependencyGraph, FileId, Fingerprint, Language};
use std::time::Instant;

fn main() {
    println!("Testing self-reference...");

    let mut graph = DependencyGraph::new();
    let file_a = FileId::from_path_str("a.py", Language::Python);

    // Register with self-reference
    graph.register_file(file_a.clone(), Fingerprint::compute(b"a"), &[file_a.clone()]);

    println!("Starting get_affected_files...");
    let start = Instant::now();

    let affected = graph.get_affected_files(&[file_a.clone()]);

    let duration = start.elapsed();
    println!("Completed in {:?}", duration);
    println!("Affected files: {}", affected.len());

    for f in &affected {
        println!("  - {:?}", f);
    }

    assert_eq!(affected.len(), 1, "Should only affect self");
}
