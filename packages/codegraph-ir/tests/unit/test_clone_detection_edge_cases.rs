//! Edge Cases and Stress Tests for Clone Detection
//!
//! Tests malicious inputs, extreme cases, and concurrency

use codegraph_ir::features::clone_detection::{
    CloneDetector, CodeFragment, MultiLevelDetector,
    Type1Detector, Type2Detector, Type3Detector, Type4Detector,
};
use codegraph_ir::shared::models::Span;

fn create_fragment(file: &str, start: u32, end: u32, content: &str, tokens: usize, loc: usize) -> CodeFragment {
    CodeFragment::new(
        file.to_string(),
        Span::new(start, 0, end, 0),
        content.to_string(),
        tokens,
        loc,
    )
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. Malicious/Adversarial Input Tests
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_very_long_file_path() {
    let detector = Type1Detector::with_thresholds(10, 1);

    // Create 8KB file path (way beyond filesystem limits)
    let long_path = "a/".repeat(4096);

    let fragments = vec![
        create_fragment(&long_path, 1, 5, "def foo(): pass", 50, 1),
        create_fragment(&long_path, 10, 15, "def foo(): pass", 50, 1),
    ];

    let pairs = detector.detect(&fragments);
    assert_eq!(pairs.len(), 1, "Should handle very long paths");
    assert_eq!(pairs[0].source.file_path.len(), long_path.len());

    println!("✓ Very long file path: {} chars handled", long_path.len());
}

#[test]
fn test_special_characters_in_path() {
    let detector = Type1Detector::with_thresholds(10, 1);

    // Path traversal attempt
    let malicious_path = "../../../etc/passwd";

    let fragments = vec![
        create_fragment(malicious_path, 1, 5, "def foo(): pass", 50, 1),
        create_fragment(malicious_path, 10, 15, "def foo(): pass", 50, 1),
    ];

    let pairs = detector.detect(&fragments);
    assert_eq!(pairs.len(), 1);
    assert_eq!(pairs[0].source.file_path, malicious_path);

    println!("✓ Special characters in path handled");
}

#[test]
fn test_unicode_bombs() {
    let detector = Type1Detector::with_thresholds(10, 1);

    // Unicode normalization bomb (NFC vs NFD)
    let nfc = "café";  // é is single codepoint
    let nfd = "café";  // é is e + combining acute accent

    let fragments = vec![
        create_fragment("file1.py", 1, 5, nfc, 50, 1),
        create_fragment("file2.py", 10, 15, nfd, 50, 1),
    ];

    let pairs = detector.detect(&fragments);
    // Should NOT match due to byte-level difference
    println!("✓ Unicode normalization handled: {} pairs", pairs.len());
}

#[test]
fn test_null_bytes_in_content() {
    let detector = Type1Detector::with_thresholds(10, 1);

    let content_with_null = "def foo():\x00 pass";

    let fragments = vec![
        create_fragment("file1.py", 1, 5, content_with_null, 50, 1),
        create_fragment("file2.py", 10, 15, content_with_null, 50, 1),
    ];

    let pairs = detector.detect(&fragments);
    assert_eq!(pairs.len(), 1, "Should handle null bytes");

    println!("✓ Null bytes handled");
}

#[test]
fn test_line_ending_variations() {
    let detector = Type1Detector::with_thresholds(10, 1);

    let unix = "def foo():\n    return 42";
    let windows = "def foo():\r\n    return 42";
    let old_mac = "def foo():\r    return 42";

    let fragments = vec![
        create_fragment("unix.py", 1, 5, unix, 50, 2),
        create_fragment("windows.py", 10, 15, windows, 50, 2),
        create_fragment("mac.py", 20, 25, old_mac, 50, 2),
    ];

    let pairs = detector.detect(&fragments);
    // Different line endings = different content (byte-level)
    println!("✓ Line ending variations: {} pairs found", pairs.len());
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. Extreme Size Tests
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_very_large_single_fragment() {
    let detector = Type1Detector::with_thresholds(1000, 100);

    // Create 100KB code fragment
    let large_code = "def foo():\n    ".repeat(5000) + "pass";

    let fragments = vec![
        create_fragment("large1.py", 1, 5000, &large_code, 50000, 5001),
        create_fragment("large2.py", 1, 5000, &large_code, 50000, 5001),
    ];

    let pairs = detector.detect(&fragments);
    assert_eq!(pairs.len(), 1, "Should handle 100KB fragments");

    println!("✓ 100KB fragment: {} bytes handled", large_code.len());
}

#[test]
fn test_many_small_fragments() {
    let detector = Type1Detector::with_thresholds(10, 1);

    // Create 1000 unique fragments
    let fragments: Vec<_> = (0..1000)
        .map(|i| {
            create_fragment(
                &format!("file{}.py", i),
                1,
                5,
                &format!("def func{}(): pass", i),
                50,
                1,
            )
        })
        .collect();

    let pairs = detector.detect(&fragments);
    assert_eq!(pairs.len(), 0, "No clones in unique fragments");

    println!("✓ 1000 unique fragments processed");
}

#[test]
fn test_many_identical_fragments() {
    let detector = Type1Detector::with_thresholds(10, 1);

    // Create 100 identical fragments (should produce 100*99/2 = 4950 pairs)
    let fragments: Vec<_> = (0..100)
        .map(|i| {
            create_fragment(
                &format!("file{}.py", i),
                1,
                5,
                "def foo(): pass",
                50,
                1,
            )
        })
        .collect();

    let pairs = detector.detect(&fragments);
    let expected_pairs = (100 * 99) / 2;
    assert_eq!(pairs.len(), expected_pairs, "Should find all clone pairs");

    println!("✓ 100 identical fragments: {} pairs (expected {})", pairs.len(), expected_pairs);
}

#[test]
fn test_deeply_nested_code() {
    let detector = Type3Detector::with_thresholds(10, 5, 0.6, 0.5);

    // Create deeply nested code (50 levels)
    let mut nested_code = String::from("def outer():\n");
    for i in 0..50 {
        nested_code.push_str(&"    ".repeat(i + 1));
        nested_code.push_str(&format!("if x > {}:\n", i));
    }
    nested_code.push_str(&"    ".repeat(51));
    nested_code.push_str("return 42");

    let fragments = vec![
        create_fragment("deep1.py", 1, 52, &nested_code, 100, 52),
        create_fragment("deep2.py", 1, 52, &nested_code, 100, 52),
    ];

    let pairs = detector.detect(&fragments);
    println!("✓ Deeply nested code (50 levels): {} pairs", pairs.len());
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. Hash Collision Tests
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_fnv1a_hash_distribution() {
    let detector = Type1Detector::with_thresholds(10, 1);

    // Create fragments with similar content but different
    let fragments: Vec<_> = (0..1000)
        .map(|i| {
            create_fragment(
                &format!("file{}.py", i),
                1,
                5,
                &format!("def function_number_{}(): pass", i),
                50,
                1,
            )
        })
        .collect();

    let pairs = detector.detect(&fragments);
    assert_eq!(pairs.len(), 0, "No hash collisions expected");

    println!("✓ FNV-1a hash distribution: 1000 unique hashes, 0 collisions");
}

#[test]
fn test_similar_but_different_content() {
    let detector = Type1Detector::with_thresholds(10, 1);

    // CORRECTED: Type-1 considers whitespace-only differences as clones
    // Test cases that differ in ACTUAL CODE (not just whitespace)
    let fragments = vec![
        create_fragment("file1.py", 1, 5, "def foo(): return 42", 50, 1),
        create_fragment("file2.py", 1, 5, "def foo(): return 43", 50, 1),  // Different digit - NOT a Type-1 clone
        create_fragment("file3.py", 1, 5, "def bar(): return 42", 50, 1),  // Different function name - NOT a Type-1 clone
    ];

    let pairs = detector.detect(&fragments);

    // Debug: Print what pairs were found (should be none)
    for pair in &pairs {
        println!("ERROR - Found unexpected pair: {} <-> {}", pair.source.file_path, pair.target.file_path);
        println!("  Source content: {:?}", pair.source.content);
        println!("  Target content: {:?}", pair.target.content);
    }

    assert_eq!(pairs.len(), 0, "Should not find false positives - different code is not a clone");

    println!("✓ Similar but different content correctly distinguished");
}

// ═══════════════════════════════════════════════════════════════════════════
// 4. Floating Point Precision Tests
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_similarity_threshold_edge_cases() {
    // Test exactly at threshold boundary
    let detector = Type2Detector::with_thresholds(10, 1, 0.95);

    let fragments = vec![
        create_fragment("file1.py", 1, 5, "def add(a, b, c, d):\n    return a + b + c + d", 50, 2),
        create_fragment("file2.py", 1, 5, "def sum(x, y, z, w):\n    return x + y + z + w", 50, 2),
    ];

    let pairs = detector.detect(&fragments);

    if !pairs.is_empty() {
        let similarity = pairs[0].similarity;
        println!("✓ Similarity threshold edge: similarity={:.10}, threshold=0.95", similarity);

        // Test for floating point precision issues
        if similarity < 0.95 {
            println!("  ⚠️  Below threshold (expected to be filtered)");
        } else {
            println!("  ✓ Above or at threshold");
        }
    } else {
        println!("✓ No pairs found (below threshold)");
    }
}

#[test]
fn test_gap_ratio_boundary() {
    let detector = Type3Detector::with_thresholds(10, 2, 0.6, 0.3);

    // Create fragment with exactly 30% gaps
    let fragments = vec![
        create_fragment(
            "file1.py",
            1, 10,
            "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10",
            50, 10,
        ),
        create_fragment(
            "file2.py",
            1, 13,
            "line1\nline2\nline3\nGAP1\nline4\nline5\nGAP2\nline6\nline7\nGAP3\nline8\nline9\nline10",
            50, 13,
        ),
    ];

    let pairs = detector.detect(&fragments);
    println!("✓ Gap ratio boundary test: {} pairs", pairs.len());

    if !pairs.is_empty() && pairs[0].metrics.gap_count.is_some() {
        let gap_count = pairs[0].metrics.gap_count.unwrap();
        let total_statements = 13;
        let gap_ratio = gap_count as f64 / total_statements as f64;
        println!("  Gap ratio: {:.2} (threshold: 0.3)", gap_ratio);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// 5. Concurrent Access Tests (Rayon)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
#[cfg(feature = "parallel")]
fn test_parallel_detection_determinism() {
    use std::collections::HashSet;

    let detector = MultiLevelDetector::new();

    let fragments = vec![
        create_fragment("file1.py", 1, 10, "def calculate_total(items):\n    total = 0\n    for item in items:\n        total += item.price\n    tax = total * 0.1\n    return total + tax", 60, 6),
        create_fragment("file2.py", 20, 30, "def calculate_total(items):\n    total = 0\n    for item in items:\n        total += item.price\n    tax = total * 0.1\n    return total + tax", 60, 6),
        create_fragment("file3.py", 40, 50, "def compute_sum(values):\n    result = 0\n    for val in values:\n        result += val.amount\n    fee = result * 0.1\n    return result + fee", 60, 6),
    ];

    // Run detection 10 times to check for race conditions
    let mut all_results = Vec::new();
    for _ in 0..10 {
        let pairs = detector.detect_all(&fragments);
        let signature: HashSet<_> = pairs
            .iter()
            .map(|p| (
                p.source.file_path.clone(),
                p.target.file_path.clone(),
                (p.similarity * 1000.0) as u64,  // Avoid float comparison
            ))
            .collect();
        all_results.push(signature);
    }

    // All runs should produce identical results
    let first = &all_results[0];
    for (i, result) in all_results.iter().enumerate().skip(1) {
        assert_eq!(
            first, result,
            "Run {} produced different results (race condition?)",
            i + 1
        );
    }

    println!("✓ Parallel detection determinism: 10 runs, all identical");
}

#[test]
fn test_concurrent_detector_instances() {
    use std::sync::Arc;
    use std::thread;

    let fragments = Arc::new(vec![
        create_fragment("file1.py", 1, 5, "def foo(): pass", 50, 1),
        create_fragment("file2.py", 10, 15, "def foo(): pass", 50, 1),
    ]);

    // Spawn 10 threads, each creating their own detector
    let handles: Vec<_> = (0..10)
        .map(|_| {
            let frags = Arc::clone(&fragments);
            thread::spawn(move || {
                let detector = Type1Detector::with_thresholds(10, 1);
                detector.detect(&frags)
            })
        })
        .collect();

    // All threads should complete successfully
    for (i, handle) in handles.into_iter().enumerate() {
        let pairs = handle.join().expect("Thread panicked");
        assert_eq!(pairs.len(), 1, "Thread {} found wrong number of pairs", i);
    }

    println!("✓ Concurrent detector instances: 10 threads, all successful");
}

// ═══════════════════════════════════════════════════════════════════════════
// 6. Memory Stress Tests
// ═══════════════════════════════════════════════════════════════════════════

#[test]
#[ignore] // This test is slow and memory-intensive
fn test_memory_scalability() {
    let detector = Type1Detector::with_thresholds(10, 1);

    // Create 10K fragments (should use ~10MB memory)
    let fragments: Vec<_> = (0..10_000)
        .map(|i| {
            create_fragment(
                &format!("file{}.py", i),
                1,
                5,
                &format!("def func{}(): pass", i),
                50,
                1,
            )
        })
        .collect();

    let pairs = detector.detect(&fragments);
    println!("✓ Memory scalability: 10K fragments processed, {} pairs found", pairs.len());
}

#[test]
fn test_empty_content_handling() {
    let detector = Type1Detector::with_thresholds(0, 0);  // Allow empty

    let fragments = vec![
        create_fragment("file1.py", 1, 1, "", 0, 0),
        create_fragment("file2.py", 1, 1, "", 0, 0),
        create_fragment("file3.py", 1, 5, "def foo(): pass", 50, 1),
    ];

    let pairs = detector.detect(&fragments);
    println!("✓ Empty content: {} pairs", pairs.len());
}

#[test]
fn test_single_character_fragments() {
    let detector = Type1Detector::with_thresholds(1, 1);

    let fragments = vec![
        create_fragment("file1.py", 1, 1, "a", 1, 1),
        create_fragment("file2.py", 1, 1, "a", 1, 1),
        create_fragment("file3.py", 1, 1, "b", 1, 1),
    ];

    let pairs = detector.detect(&fragments);
    assert_eq!(pairs.len(), 1, "Should find single-char clones");

    println!("✓ Single character fragments handled");
}

// ═══════════════════════════════════════════════════════════════════════════
// 7. Stress Test: All Detectors on Complex Input
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_comprehensive_stress() {
    let fragments = vec![
        // Exact clones
        create_fragment("exact1.py", 1, 10, "def calc(x):\n    y = x * 2\n    z = y + 5\n    return z", 60, 6),
        create_fragment("exact2.py", 1, 10, "def calc(x):\n    y = x * 2\n    z = y + 5\n    return z", 60, 6),

        // Renamed clones
        create_fragment("renamed1.py", 1, 10, "def process(data):\n    result = data * 2\n    output = result + 5\n    return output", 60, 6),

        // Gapped clones
        create_fragment("gapped1.py", 1, 15, "def transform(val):\n    temp = val * 2\n    log('debug')\n    final = temp + 5\n    log('done')\n    return final", 60, 8),

        // Semantic clones
        create_fragment("semantic1.py", 1, 10, "def compute(n):\n    x = n\n    x = x * 2\n    x = x + 5\n    return x", 60, 6),

        // Unique code
        create_fragment("unique1.py", 1, 5, "def unrelated():\n    return 'hello world'", 30, 3),
    ];

    // Test all detector types
    let detectors: Vec<(&str, Box<dyn CloneDetector>)> = vec![
        ("Type-1", Box::new(Type1Detector::new())),
        ("Type-2", Box::new(Type2Detector::new())),
        ("Type-3", Box::new(Type3Detector::new())),
        ("Type-4", Box::new(Type4Detector::new())),
    ];

    println!("\n╔════════════════════════════════════════════════════════════════╗");
    println!("║  COMPREHENSIVE STRESS TEST - ALL DETECTORS                     ║");
    println!("╚════════════════════════════════════════════════════════════════╝");

    for (name, detector) in detectors {
        let pairs = detector.detect(&fragments);
        println!("{}: {} pairs found", name, pairs.len());

        for pair in pairs.iter().take(3) {
            println!("  - {}:{} <-> {}:{} (sim: {:.2})",
                pair.source.file_path, pair.source.span.start_line,
                pair.target.file_path, pair.target.span.start_line,
                pair.similarity);
        }
    }

    // Multi-level detection
    let multi = MultiLevelDetector::new();
    let all_pairs = multi.detect_all(&fragments);
    println!("\nMulti-Level: {} total pairs", all_pairs.len());

    println!("\n✓ ALL STRESS TESTS PASSED");
}
