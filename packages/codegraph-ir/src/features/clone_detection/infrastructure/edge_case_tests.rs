//! Edge Case Tests Module
//!
//! Tests for malicious inputs, extreme cases, and stress scenarios

#[cfg(test)]
mod tests {
    use super::super::super::domain::{ClonePair, CodeFragment};
    use super::super::{
        CloneDetector, MultiLevelDetector, Type1Detector, Type2Detector, Type3Detector,
        Type4Detector,
    };
    use crate::shared::models::Span;

    fn create_fragment(
        file: &str,
        start: u32,
        end: u32,
        content: &str,
        tokens: usize,
        loc: usize,
    ) -> CodeFragment {
        CodeFragment::new(
            file.to_string(),
            Span::new(start, 0, end, 0),
            content.to_string(),
            tokens,
            loc,
        )
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Malicious/Adversarial Input Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_very_long_file_path() {
        let detector = Type1Detector::with_thresholds(10, 1);

        // Create 8KB file path
        let long_path = "a/".repeat(4096);

        let fragments = vec![
            create_fragment(&long_path, 1, 5, "def foo(): pass", 50, 1),
            create_fragment(&long_path, 10, 15, "def foo(): pass", 50, 1),
        ];

        let pairs = detector.detect(&fragments);
        assert_eq!(pairs.len(), 1, "Should handle very long paths");
        assert_eq!(pairs[0].source.file_path.len(), long_path.len());
    }

    #[test]
    fn test_special_characters_in_path() {
        let detector = Type1Detector::with_thresholds(10, 1);

        let malicious_path = "../../../etc/passwd";

        let fragments = vec![
            create_fragment(malicious_path, 1, 5, "def foo(): pass", 50, 1),
            create_fragment(malicious_path, 10, 15, "def foo(): pass", 50, 1),
        ];

        let pairs = detector.detect(&fragments);
        assert_eq!(pairs.len(), 1);
        assert_eq!(pairs[0].source.file_path, malicious_path);
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
        // Type-1: Line endings are whitespace, so they should match
        // 3 fragments → 3 pairs: (unix, windows), (unix, mac), (windows, mac)
        assert_eq!(
            pairs.len(),
            3,
            "Line endings are whitespace - all fragments match as Type-1"
        );
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Extreme Size Tests
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
    }

    #[test]
    fn test_many_identical_fragments() {
        let detector = Type1Detector::with_thresholds(10, 1);

        // Create 100 identical fragments (should produce 100*99/2 = 4950 pairs)
        let fragments: Vec<_> = (0..100)
            .map(|i| create_fragment(&format!("file{}.py", i), 1, 5, "def foo(): pass", 50, 1))
            .collect();

        let pairs = detector.detect(&fragments);
        let expected_pairs = (100 * 99) / 2;
        assert_eq!(pairs.len(), expected_pairs, "Should find all clone pairs");
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Hash Collision Tests
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
    }

    #[test]
    fn test_similar_but_different_content() {
        let detector = Type1Detector::with_thresholds(10, 1);

        // Very similar strings that should NOT hash to same value
        let fragments = vec![
            create_fragment("file1.py", 1, 5, "def foo(): return 42", 50, 1),
            create_fragment("file2.py", 1, 5, "def foo(): return 43", 50, 1), // Only digit differs
            create_fragment("file3.py", 1, 5, "def foo(): return 42 ", 50, 1), // Trailing space
        ];

        let pairs = detector.detect(&fragments);
        // Fragment 1 and 3 differ only by trailing space (whitespace)
        // Type-1 normalizes whitespace, so they should match
        assert_eq!(
            pairs.len(),
            1,
            "Fragment 1 and 3 match (trailing space is whitespace)"
        );
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Floating Point Precision Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_similarity_threshold_edge_cases() {
        // Test exactly at threshold boundary
        let detector = Type2Detector::with_thresholds(10, 1, 0.95);

        let fragments = vec![
            create_fragment(
                "file1.py",
                1,
                5,
                "def add(a, b, c, d):\n    return a + b + c + d",
                50,
                2,
            ),
            create_fragment(
                "file2.py",
                1,
                5,
                "def sum(x, y, z, w):\n    return x + y + z + w",
                50,
                2,
            ),
        ];

        let pairs = detector.detect(&fragments);

        if !pairs.is_empty() {
            let similarity = pairs[0].similarity;
            // Verify no floating point precision issues
            assert!(similarity.is_finite(), "Similarity should be finite");
            assert!(
                similarity >= 0.0 && similarity <= 1.0,
                "Similarity should be in [0, 1]"
            );
        }
    }

    #[test]
    fn test_gap_ratio_boundary() {
        let detector = Type3Detector::with_thresholds(10, 2, 0.6, 0.3);

        // Create fragment with gaps
        let fragments = vec![
            create_fragment(
                "file1.py",
                1,
                10,
                "line1\nline2\nline3\nline4\nline5",
                50,
                5,
            ),
            create_fragment(
                "file2.py",
                1,
                13,
                "line1\nGAP1\nline2\nGAP2\nline3\nGAP3\nline4\nline5",
                50,
                8,
            ),
        ];

        let pairs = detector.detect(&fragments);

        if !pairs.is_empty() && pairs[0].metrics.gap_count.is_some() {
            let gap_count = pairs[0].metrics.gap_count.unwrap();
            // Verify gap metrics are reasonable
            assert!(gap_count > 0, "Should detect gaps");
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Concurrent Access Tests
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
                .map(|p| {
                    (
                        p.source.file_path.clone(),
                        p.target.file_path.clone(),
                        (p.similarity * 1000.0) as u64,
                    )
                })
                .collect();
            all_results.push(signature);
        }

        // All runs should produce identical results
        let first = &all_results[0];
        for (i, result) in all_results.iter().enumerate().skip(1) {
            assert_eq!(
                first,
                result,
                "Run {} produced different results (race condition?)",
                i + 1
            );
        }
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
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Memory Stress Tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    #[ignore] // Slow test
    fn test_memory_scalability() {
        let detector = Type1Detector::with_thresholds(10, 1);

        // Create 10K fragments
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

        let _pairs = detector.detect(&fragments);
        // Just verify it completes without OOM
    }

    #[test]
    fn test_empty_content_handling() {
        let detector = Type1Detector::with_thresholds(0, 0); // Allow empty

        let fragments = vec![
            create_fragment("file1.py", 1, 1, "", 0, 0),
            create_fragment("file2.py", 1, 1, "", 0, 0),
            create_fragment("file3.py", 1, 5, "def foo(): pass", 50, 1),
        ];

        let pairs = detector.detect(&fragments);
        // Empty content should match
        assert_eq!(pairs.len(), 1, "Empty content should form a clone pair");
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
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Comprehensive Stress Test
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_comprehensive_stress() {
        let fragments = vec![
            // Exact clones
            create_fragment("exact1.py", 1, 10, "def calc(x):\n    y = x * 2\n    z = y + 5\n    return z", 60, 6),
            create_fragment("exact2.py", 1, 10, "def calc(x):\n    y = x * 2\n    z = y + 5\n    return z", 60, 6),

            // Renamed clones
            create_fragment("renamed1.py", 1, 10, "def process(data):\n    result = data * 2\n    output = result + 5\n    return output", 60, 6),

            // Unique code
            create_fragment("unique1.py", 1, 5, "def unrelated():\n    return 'hello world'", 30, 3),
        ];

        // Test all detector types
        let type1 = Type1Detector::new();
        let type2 = Type2Detector::new();
        let type3 = Type3Detector::new();
        let type4 = Type4Detector::new();

        let pairs1 = type1.detect(&fragments);
        let pairs2 = type2.detect(&fragments);
        let pairs3 = type3.detect(&fragments);
        let pairs4 = type4.detect(&fragments);

        assert!(pairs1.len() > 0, "Type-1 should find exact clones");

        // Multi-level detection
        let multi = MultiLevelDetector::new();
        let all_pairs = multi.detect_all(&fragments);
        assert!(all_pairs.len() > 0, "Multi-level should find clones");
    }
}
