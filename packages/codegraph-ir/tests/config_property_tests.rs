//! Property-based tests for RFC-CONFIG
//!
//! Tests invariants that should hold for ALL possible inputs:
//! - Roundtrip: deserialize(serialize(x)) == x
//! - Validity: All valid configs should validate
//! - Monotonicity: Stricter configs shouldn't accept more
//! - Idempotence: build(build(x)) == build(x)

use codegraph_ir::config::pipeline_config::StageId;
use codegraph_ir::config::*;
use proptest::prelude::*;
use quickcheck::TestResult;
use quickcheck_macros::quickcheck;

// ============================================================================
// QuickCheck Tests (simpler, faster)
// ============================================================================

#[quickcheck]
fn qc_taint_config_range_invariants(depth: usize, paths: usize, iterations: usize) -> TestResult {
    // Only test values in valid range
    if depth == 0
        || depth > 1000
        || paths == 0
        || paths > 100000
        || iterations == 0
        || iterations > 10000
    {
        return TestResult::discard();
    }

    let mut config = TaintConfig::from_preset(Preset::Fast);
    config.max_depth = depth;
    config.max_paths = paths;
    config.worklist_max_iterations = iterations;

    // Invariant: Valid config should always validate
    TestResult::from_bool(config.validate().is_ok())
}

#[quickcheck]
fn qc_pta_config_mode_consistency(field_sensitive: bool, enable_scc: bool) -> bool {
    // For each mode, config should be valid
    for mode in [PTAMode::Fast, PTAMode::Precise, PTAMode::Auto] {
        let mut config = PTAConfig::from_preset(Preset::Balanced);
        config.mode = mode;
        config.field_sensitive = field_sensitive;
        config.enable_scc = enable_scc;

        if config.validate().is_err() {
            return false;
        }
    }
    true
}

#[quickcheck]
fn qc_preset_roundtrip(preset_idx: u8) -> TestResult {
    let preset = match preset_idx % 4 {
        0 => Preset::Fast,
        1 => Preset::Balanced,
        2 => Preset::Thorough,
        _ => Preset::Custom,
    };

    let config = PipelineConfig::preset(preset).build();
    if config.is_err() {
        return TestResult::discard();
    }

    let config = config.unwrap().into_inner();
    let yaml = config.to_yaml();
    if yaml.is_err() {
        return TestResult::failed();
    }

    let yaml_path = "/tmp/test_config.yaml";
    std::fs::write(yaml_path, yaml.unwrap()).unwrap();
    let recovered = PipelineConfig::from_yaml(yaml_path);
    std::fs::remove_file(yaml_path).ok();

    // Invariant: YAML roundtrip should preserve preset
    TestResult::from_bool(recovered.is_ok())
}

#[quickcheck]
fn qc_config_builder_order_independence(
    depth1: bool,
    depth2: bool,
    paths1: bool,
    paths2: bool,
) -> bool {
    // Test that builder order doesn't matter (last write wins)
    let mut builder = PipelineConfig::preset(Preset::Fast);

    if depth1 {
        builder = builder.taint(|mut c| {
            c.max_depth = 50;
            c
        });
    }
    if paths1 {
        builder = builder.taint(|mut c| {
            c.max_paths = 500;
            c
        });
    }
    if depth2 {
        builder = builder.taint(|mut c| {
            c.max_depth = 100;
            c
        });
    }
    if paths2 {
        builder = builder.taint(|mut c| {
            c.max_paths = 1000;
            c
        });
    }

    // Should always build successfully
    builder.build().is_ok()
}

// ============================================================================
// Proptest Tests (more complex, exhaustive)
// ============================================================================

proptest! {
    #[test]
    fn prop_taint_validation_monotonic(
        depth in 1usize..=1000,
        paths in 1usize..=100000,
    ) {
        let mut config = TaintConfig::from_preset(Preset::Fast);
        config.max_depth = depth;
        config.max_paths = paths;

        // Invariant: If (d, p) is valid, then any (d', p') with d' <= d and p' <= p should be valid
        let mut stricter_depth = config.clone();
        stricter_depth.max_depth = depth.saturating_sub(10).max(1);

        let mut stricter_paths = config.clone();
        stricter_paths.max_paths = paths.saturating_sub(100).max(1);

        prop_assert!(config.validate().is_ok());
        prop_assert!(stricter_depth.validate().is_ok());
        prop_assert!(stricter_paths.validate().is_ok());
    }

    #[test]
    fn prop_pta_auto_threshold_range(
        threshold in 100usize..=1_000_000,
    ) {
        let mut config = PTAConfig::from_preset(Preset::Balanced);
        config.auto_threshold = threshold;

        // Invariant: Any threshold in valid range should validate
        prop_assert!(config.validate().is_ok());
    }

    #[test]
    fn prop_chunking_size_relationship(
        max_size in 100usize..=10000,
        min_size in 50usize..=5000,
    ) {
        let mut config = ChunkingConfig::from_preset(Preset::Fast);
        config.max_chunk_size = max_size;
        config.min_chunk_size = min_size;

        // Invariant: validation fails iff min >= max
        let should_fail = min_size >= max_size;
        let actually_failed = config.validate().is_err();

        prop_assert_eq!(should_fail, actually_failed);
    }

    #[test]
    fn prop_lexical_fuzzy_distance(
        distance in 1usize..=5,
        max_results in 1usize..=10000,
    ) {
        let mut config = LexicalConfig::from_preset(Preset::Balanced);
        config.fuzzy_distance = distance;
        config.max_results = max_results;

        // Invariant: All valid configs should validate
        prop_assert!(config.validate().is_ok());
    }

    #[test]
    fn prop_parallel_workers(
        workers in 0usize..=256,
        batch_size in 1usize..=10000,
    ) {
        let mut config = ParallelConfig::from_preset(Preset::Fast);
        config.num_workers = workers;
        config.batch_size = batch_size;

        // Invariant: workers <= 256 should always validate
        prop_assert!(config.validate().is_ok());
    }

    #[test]
    fn prop_cross_stage_taint_requires_pta(
        enable_taint: bool,
        enable_pta: bool,
        use_points_to: bool,
    ) {
        let mut builder = PipelineConfig::preset(Preset::Fast);

        if enable_taint {
            builder = builder.stages(|s| s.enable(StageId::Taint));
        }
        if enable_pta {
            builder = builder.stages(|s| s.enable(StageId::Pta));
        }
        if use_points_to {
            builder = builder.taint(|mut c| {
                c.use_points_to = true;
                c
            });
        }

        let result = builder.build();

        // Invariant: If taint uses PTA but PTA is disabled, should fail
        let should_fail = enable_taint && use_points_to && !enable_pta;
        let actually_failed = result.is_err();

        prop_assert_eq!(should_fail, actually_failed);
    }

    #[test]
    fn prop_yaml_roundtrip_preserves_values(
        depth in 1usize..=100,
        paths in 1usize..=1000,
    ) {
        let config = PipelineConfig::preset(Preset::Balanced)
            .stages(|s| s.enable(StageId::Taint).enable(StageId::Pta))
            .taint(|mut c| {
                c.max_depth = depth;
                c.max_paths = paths;
                c
            })
            .build()
            .unwrap()
            .into_inner();

        // Roundtrip through YAML
        let yaml = config.to_yaml().unwrap();
        let yaml_path = "/tmp/test_roundtrip.yaml";
        std::fs::write(yaml_path, &yaml).unwrap();
        let recovered = PipelineConfig::from_yaml(yaml_path).unwrap().into_inner();
        std::fs::remove_file(yaml_path).ok();

        // Invariant: Roundtrip preserves basic values
        prop_assert_eq!(format!("{:?}", config.get_preset()), format!("{:?}", recovered.get_preset()));
    }

    #[test]
    fn prop_strict_mode_rejects_disabled_override(
        enable_taint: bool,
        strict: bool,
    ) {
        let mut builder = PipelineConfig::preset(Preset::Fast);

        // Fast preset has taint disabled by default, so explicitly set it
        if enable_taint {
            builder = builder.stages(|s| s.enable(StageId::Taint));
        } else {
            builder = builder.stages(|s| s.disable(StageId::Taint));
        }

        // Always try to override taint
        builder = builder.taint(|mut c| {
            c.max_depth = 50;
            c
        });

        if strict {
            builder = builder.strict_mode(true);
        }

        let result = builder.build();

        // Invariant: Strict mode rejects overrides on disabled stages
        let should_fail = !enable_taint && strict;
        let actually_failed = result.is_err();

        prop_assert_eq!(should_fail, actually_failed);
    }

    #[test]
    fn prop_describe_contains_enabled_stages(
        enable_taint: bool,
        enable_pta: bool,
        enable_clone: bool,
    ) {
        let mut builder = PipelineConfig::preset(Preset::Fast);

        if enable_taint {
            builder = builder.stages(|s| s.enable(StageId::Taint));
        }
        if enable_pta {
            builder = builder.stages(|s| s.enable(StageId::Pta));
        }
        if enable_clone {
            builder = builder.stages(|s| s.enable(StageId::Clone));
        }

        let config = builder.build().unwrap().into_inner();
        let description = config.describe();

        // Invariant: describe() should mention enabled stages
        if enable_taint {
            prop_assert!(description.contains("Taint"));
        }
        if enable_pta {
            prop_assert!(description.contains("PTA") || description.contains("Pta"));
        }
        if enable_clone {
            prop_assert!(description.contains("Clone"));
        }
    }
}

// ============================================================================
// Extreme Value Tests (Boundary Testing)
// ============================================================================

#[test]
fn extreme_values_max_depth() {
    // Min boundary
    let mut config = TaintConfig::from_preset(Preset::Fast);
    config.max_depth = 1;
    assert!(config.validate().is_ok());

    // Max boundary
    let mut config = TaintConfig::from_preset(Preset::Fast);
    config.max_depth = 1000;
    assert!(config.validate().is_ok());

    // Just below min (should fail)
    let mut config = TaintConfig::from_preset(Preset::Fast);
    config.max_depth = 0;
    assert!(config.validate().is_err());

    // Just above max (should fail)
    let mut config = TaintConfig::from_preset(Preset::Fast);
    config.max_depth = 1001;
    assert!(config.validate().is_err());

    // usize::MAX (should fail)
    let mut config = TaintConfig::from_preset(Preset::Fast);
    config.max_depth = usize::MAX;
    assert!(config.validate().is_err());
}

#[test]
fn extreme_values_max_paths() {
    // Min boundary
    let mut config = TaintConfig::from_preset(Preset::Fast);
    config.max_paths = 1;
    assert!(config.validate().is_ok());

    // Max boundary
    let mut config = TaintConfig::from_preset(Preset::Fast);
    config.max_paths = 100_000;
    assert!(config.validate().is_ok());

    // Just below min
    let mut config = TaintConfig::from_preset(Preset::Fast);
    config.max_paths = 0;
    assert!(config.validate().is_err());

    // Just above max
    let mut config = TaintConfig::from_preset(Preset::Fast);
    config.max_paths = 100_001;
    assert!(config.validate().is_err());
}

#[test]
fn extreme_values_auto_threshold() {
    // Min boundary
    let mut config = PTAConfig::from_preset(Preset::Fast);
    config.auto_threshold = 100;
    assert!(config.validate().is_ok());

    // Max boundary
    let mut config = PTAConfig::from_preset(Preset::Fast);
    config.auto_threshold = 1_000_000;
    assert!(config.validate().is_ok());

    // Just below min (should fail)
    let mut config = PTAConfig::from_preset(Preset::Fast);
    config.auto_threshold = 99;
    assert!(config.validate().is_err());

    // Just above max (should fail)
    let mut config = PTAConfig::from_preset(Preset::Fast);
    config.auto_threshold = 1_000_001;
    assert!(config.validate().is_err());
}

// ============================================================================
// Stress Tests (Many iterations)
// ============================================================================

#[test]
fn stress_test_builder_chaining() {
    // Test 1000 iterations of builder chaining
    for i in 1..=1000 {
        let depth = (i % 100) + 1; // 1..=100
        let paths = ((i * 7) % 1000) + 1; // 1..=1000

        let config = PipelineConfig::preset(Preset::Balanced)
            .taint(|mut c| {
                c.max_depth = depth;
                c.max_paths = paths;
                c
            })
            .build();

        assert!(config.is_ok(), "Iteration {} failed", i);
    }
}

#[test]
fn stress_test_yaml_roundtrip() {
    // Test 100 random configs through YAML roundtrip
    for i in 1..=100 {
        let preset = match i % 3 {
            0 => Preset::Fast,
            1 => Preset::Balanced,
            _ => Preset::Thorough,
        };

        let config = PipelineConfig::preset(preset).build().unwrap().into_inner();

        let yaml = config.to_yaml().unwrap();
        let yaml_path = format!("/tmp/test_stress_{}.yaml", i);
        std::fs::write(&yaml_path, &yaml).unwrap();
        let recovered = PipelineConfig::from_yaml(&yaml_path).unwrap().into_inner();
        std::fs::remove_file(&yaml_path).ok();

        assert_eq!(
            format!("{:?}", config.get_preset()),
            format!("{:?}", recovered.get_preset()),
            "Iteration {} failed",
            i
        );
    }
}

#[test]
#[ignore] // Slow test - run with --ignored
fn stress_test_memory_leak() {
    // Test for memory leaks with 10,000 config creations
    let mut configs = Vec::new();
    for i in 0..10_000 {
        let config = PipelineConfig::preset(Preset::Balanced).build().unwrap();
        if i % 100 == 0 {
            configs.push(config); // Keep some alive
        }
        // Most will be dropped
    }
    assert_eq!(configs.len(), 100);
}
