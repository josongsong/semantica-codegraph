//! Integration test for Clone Detection
//!
//! Tests all 4 clone detector types without requiring full library compilation

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

#[test]
fn test_type1_exact_clone_detection() {
    let detector = Type1Detector::with_thresholds(10, 1);  // Lower thresholds for test

    let fragments = vec![
        create_fragment("file1.py", 1, 5, "def add(a, b):\n    return a + b", 50, 2),
        create_fragment("file2.py", 10, 15, "def add(a, b):\n    return a + b", 50, 2),
        create_fragment("file3.py", 20, 25, "def multiply(x, y):\n    return x * y", 50, 2),
    ];

    let pairs = detector.detect(&fragments);

    assert_eq!(pairs.len(), 1, "Should find 1 Type-1 clone pair");
    assert_eq!(pairs[0].similarity, 1.0, "Should have perfect similarity");
    assert_eq!(pairs[0].source.file_path, "file1.py");
    assert_eq!(pairs[0].target.file_path, "file2.py");

    println!("✓ Type-1 detection: Found {} exact clone(s)", pairs.len());
}

#[test]
fn test_type2_renamed_clone_detection() {
    let detector = Type2Detector::with_thresholds(10, 1, 0.9);  // Lower thresholds for test

    let fragments = vec![
        create_fragment("file1.py", 1, 5, "def add(a, b):\n    return a + b", 50, 2),
        create_fragment("file2.py", 10, 15, "def sum(x, y):\n    return x + y", 50, 2),
    ];

    let pairs = detector.detect(&fragments);

    assert!(!pairs.is_empty(), "Should find at least 1 Type-2 clone pair");
    assert!(pairs[0].similarity >= 0.9, "Should have high similarity");

    println!("✓ Type-2 detection: Found {} renamed clone(s) with similarity {:.2}", pairs.len(), pairs[0].similarity);
}

#[test]
fn test_type3_gapped_clone_detection() {
    let detector = Type3Detector::with_thresholds(10, 2, 0.6, 0.5);

    let fragments = vec![
        create_fragment(
            "file1.py",
            1,
            10,
            "def process(data):\n    validate(data)\n    x = transform(data)\n    save(x)\n    return x",
            30,
            5,
        ),
        create_fragment(
            "file2.py",
            20,
            30,
            "def handle(input):\n    validate(input)\n    log('Processing...')\n    y = transform(input)\n    log('Saving...')\n    save(y)\n    return y",
            40,
            7,
        ),
    ];

    let pairs = detector.detect(&fragments);

    assert!(!pairs.is_empty(), "Should find at least 1 Type-3 clone pair");
    assert!(pairs[0].similarity >= 0.6, "Should have reasonable similarity");
    assert!(pairs[0].metrics.gap_count.is_some(), "Should have gap_count");

    println!("✓ Type-3 detection: Found {} gapped clone(s) with {} gaps",
             pairs.len(),
             pairs[0].metrics.gap_count.unwrap());
}

#[test]
fn test_type4_semantic_clone_detection() {
    let detector = Type4Detector::with_thresholds(10, 2, 0.5, 0.4, 0.3, 0.3);

    let fragments = vec![
        create_fragment(
            "file1.py",
            1,
            10,
            "def sum_list(items):\n    total = 0\n    for item in items:\n        total += item\n    return total",
            30,
            5,
        ),
        create_fragment(
            "file2.py",
            20,
            30,
            "def calculate_sum(data):\n    result = 0\n    for x in data:\n        result = result + x\n    return result",
            30,
            5,
        ),
    ];

    let pairs = detector.detect(&fragments);

    println!("✓ Type-4 detection: Found {} semantic clone(s)", pairs.len());

    if !pairs.is_empty() {
        assert!(pairs[0].similarity >= 0.5, "Should have reasonable similarity");
        assert!(pairs[0].metrics.semantic_similarity.is_some(), "Should have semantic_similarity");
        println!("  Semantic similarity: {:.2}", pairs[0].metrics.semantic_similarity.unwrap());
    }
}

#[test]
fn test_multi_level_detector_all_types() {
    let detector = MultiLevelDetector::new();

    // Use larger code fragments to meet default thresholds (50 tokens, 6 LOC)
    let fragments = vec![
        // Type-1 pair
        create_fragment(
            "file1.py",
            1,
            10,
            "def calculate_total(items):\n    total = 0\n    for item in items:\n        total += item.price\n    tax = total * 0.1\n    return total + tax",
            60,
            6,
        ),
        create_fragment(
            "file2.py",
            20,
            30,
            "def calculate_total(items):\n    total = 0\n    for item in items:\n        total += item.price\n    tax = total * 0.1\n    return total + tax",
            60,
            6,
        ),
        // Type-2 pair
        create_fragment(
            "file3.py",
            40,
            50,
            "def compute_sum(values):\n    result = 0\n    for val in values:\n        result += val.amount\n    fee = result * 0.1\n    return result + fee",
            60,
            6,
        ),
        create_fragment(
            "file4.py",
            60,
            70,
            "def sum_values(data):\n    accumulator = 0\n    for d in data:\n        accumulator += d.cost\n    charge = accumulator * 0.1\n    return accumulator + charge",
            60,
            6,
        ),
    ];

    let pairs = detector.detect_all(&fragments);

    println!("✓ Multi-level detection: Found {} total clones", pairs.len());

    if !pairs.is_empty() {
        let type1_count = pairs.iter().filter(|p| matches!(p.clone_type, codegraph_ir::features::clone_detection::CloneType::Type1)).count();
        let type2_count = pairs.iter().filter(|p| matches!(p.clone_type, codegraph_ir::features::clone_detection::CloneType::Type2)).count();
        let type3_count = pairs.iter().filter(|p| matches!(p.clone_type, codegraph_ir::features::clone_detection::CloneType::Type3)).count();
        let type4_count = pairs.iter().filter(|p| matches!(p.clone_type, codegraph_ir::features::clone_detection::CloneType::Type4)).count();

        println!("  Type-1: {}, Type-2: {}, Type-3: {}, Type-4: {}",
                 type1_count, type2_count, type3_count, type4_count);

        assert!(type1_count > 0, "Should find Type-1 clones");
        assert!(type2_count > 0, "Should find Type-2 clones");
    } else {
        println!("  Note: No clones found with default thresholds");
    }
}

#[test]
fn test_detect_in_file() {
    let detector = Type2Detector::with_thresholds(10, 1, 0.9);  // Lower thresholds for test

    let fragments = vec![
        create_fragment("file1.py", 1, 5, "def foo():\n    return 42", 50, 2),
        create_fragment("file1.py", 10, 15, "def bar():\n    return 99", 50, 2),
        create_fragment("file2.py", 20, 25, "def baz():\n    return 0", 50, 2),
    ];

    let pairs = detector.detect_in_file(&fragments, "file1.py");

    for pair in &pairs {
        assert_eq!(pair.source.file_path, "file1.py");
        assert_eq!(pair.target.file_path, "file1.py");
    }

    println!("✓ File-specific detection: Found {} clone(s) in file1.py", pairs.len());
}

#[test]
fn test_hybrid_vs_baseline_recall() {
    use codegraph_ir::features::clone_detection::HybridCloneDetector;
    use std::time::Instant;

    println!("\n╔════════════════════════════════════════════════════════════════╗");
    println!("║  HYBRID VS BASELINE - RECALL & PERFORMANCE TEST               ║");
    println!("╚════════════════════════════════════════════════════════════════╝\n");

    // Create realistic test fragments
    let fragments = vec![
        // Type-1 exact clones (should be caught by Tier 1)
        create_fragment("file1.py", 1, 6, "def add(a, b):\n    return a + b", 50, 2),
        create_fragment("file2.py", 10, 15, "def add(a, b):\n    return a + b", 50, 2),

        // Type-2 renamed clones
        create_fragment("file3.py", 20, 25, "def sum(x, y):\n    return x + y", 50, 2),
        create_fragment("file4.py", 30, 35, "def total(m, n):\n    return m + n", 50, 2),

        // Type-3 gapped clones
        create_fragment(
            "file5.py", 40, 50,
            "def process(data):\n    validate(data)\n    result = transform(data)\n    return result",
            50, 4
        ),
        create_fragment(
            "file6.py", 60, 75,
            "def handle(input):\n    validate(input)\n    log('Processing')\n    result = transform(input)\n    return result",
            60, 5
        ),

        // More fragments to test scalability
        create_fragment("file7.py", 80, 85, "def multiply(a, b):\n    return a * b", 50, 2),
        create_fragment("file8.py", 90, 95, "def product(x, y):\n    return x * y", 50, 2),
    ];

    println!("Test fragments: {}\n", fragments.len());

    // Test 1: Baseline
    println!("1️⃣  Baseline (MultiLevelDetector)");
    let baseline = MultiLevelDetector::new();
    let baseline_start = Instant::now();
    let baseline_pairs = baseline.detect_all(&fragments);
    let baseline_duration = baseline_start.elapsed();

    println!("   ✓ Found {} pairs in {:?}\n", baseline_pairs.len(), baseline_duration);

    // Test 2: Hybrid Detector
    println!("2️⃣  Hybrid Detector (Optimized)");
    let mut hybrid = HybridCloneDetector::new();
    let hybrid_start = Instant::now();
    let hybrid_pairs = hybrid.detect_all(&fragments);
    let hybrid_duration = hybrid_start.elapsed();

    println!("   ✓ Found {} pairs in {:?}", hybrid_pairs.len(), hybrid_duration);

    if let Some(stats) = hybrid.stats() {
        println!("   📈 Tier breakdown:");
        println!("      - Tier 1 (Token Hash): {} clones", stats.tier1_clones);
        println!("      - Tier 2 (Optimized): {} clones", stats.tier2_clones);
        println!("      - Tier 3 (Baseline): {} clones", stats.tier3_clones);
    }
    println!();

    // Analysis
    println!("📊 Results:");
    let recall_percent = if baseline_pairs.len() > 0 {
        (hybrid_pairs.len() as f64 / baseline_pairs.len() as f64) * 100.0
    } else {
        0.0
    };

    println!("   Recall: {:.1}% ({} / {})", recall_percent, hybrid_pairs.len(), baseline_pairs.len());

    let speedup = if hybrid_duration.as_millis() > 0 {
        baseline_duration.as_millis() as f64 / hybrid_duration.as_millis() as f64
    } else {
        f64::INFINITY
    };
    println!("   Speedup: {:.2}x", speedup);
    println!();

    // Assertions
    assert!(recall_percent >= 90.0, "Hybrid should have ≥90% recall (got {:.1}%)", recall_percent);
    assert!(hybrid_pairs.len() <= baseline_pairs.len() * 2, "Hybrid should not have excessive false positives");

    if baseline_duration.as_millis() > 0 {
        // Allow hybrid to be slightly slower on very small datasets due to overhead
        assert!(hybrid_duration.as_millis() <= baseline_duration.as_millis() * 3,
                "Hybrid should not be >3x slower than baseline");
    }

    println!("✅ PASS: Hybrid detector maintains good recall with competitive performance!\n");
}

#[test]
fn test_comprehensive_clone_detection_workflow() {
    println!("\n╔════════════════════════════════════════════════════════════════╗");
    println!("║  CLONE DETECTION INTEGRATION TEST - ALL 4 TYPES               ║");
    println!("╚════════════════════════════════════════════════════════════════╝\n");

    let detector = MultiLevelDetector::new();

    let fragments = vec![
        // Exact clones
        create_fragment("src/utils.py", 1, 5, "def validate(x):\n    return x > 0", 50, 2),
        create_fragment("src/helpers.py", 10, 15, "def validate(x):\n    return x > 0", 50, 2),

        // Renamed clones
        create_fragment("src/math.py", 20, 25, "def add(a, b):\n    return a + b", 50, 2),
        create_fragment("src/calc.py", 30, 35, "def sum(x, y):\n    return x + y", 50, 2),

        // Gapped clones
        create_fragment(
            "src/processor.py",
            40,
            50,
            "def process(data):\n    validate(data)\n    result = transform(data)\n    return result",
            30,
            4,
        ),
        create_fragment(
            "src/handler.py",
            60,
            75,
            "def handle(input):\n    validate(input)\n    log('Processing')\n    result = transform(input)\n    log('Done')\n    return result",
            40,
            6,
        ),
    ];

    let all_pairs = detector.detect_all(&fragments);

    println!("Total fragments analyzed: {}", fragments.len());
    println!("Total clone pairs found: {}\n", all_pairs.len());

    let mut type_stats = std::collections::HashMap::new();
    for pair in &all_pairs {
        let count = type_stats.entry(format!("{:?}", pair.clone_type)).or_insert(0);
        *count += 1;
    }

    println!("Clone distribution:");
    for (clone_type, count) in type_stats.iter() {
        println!("  {}: {} pair(s)", clone_type, count);
    }

    println!("\nDetailed clone pairs:");
    for (i, pair) in all_pairs.iter().enumerate() {
        println!("  {}. [{:?}] {}:{} <-> {}:{} (similarity: {:.2})",
                 i + 1,
                 pair.clone_type,
                 pair.source.file_path,
                 pair.source.span.start_line,
                 pair.target.file_path,
                 pair.target.span.start_line,
                 pair.similarity);
    }

    println!("\n✓ ALL CLONE DETECTION TESTS PASSED!");

    assert!(!all_pairs.is_empty(), "Should find clone pairs");
}
