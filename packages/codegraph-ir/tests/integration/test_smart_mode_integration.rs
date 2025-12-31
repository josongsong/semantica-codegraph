//! Integration tests for Smart Mode auto-detection

use codegraph_ir::pipeline::{
    E2EPipelineConfig, ModeDetectionContext, AnalysisType, RecommendedMode,
};

#[test]
fn test_initial_indexing_selects_fast_mode() {
    let mut config = E2EPipelineConfig::default();

    let context = ModeDetectionContext {
        is_initial_indexing: true,
        ..Default::default()
    };

    let mode = config.configure_smart_pagerank(context);

    assert_eq!(mode, RecommendedMode::Fast);
    assert_eq!(config.pagerank_settings.enable_personalized, false);
    assert_eq!(config.pagerank_settings.enable_hits, false);
    assert_eq!(config.pagerank_settings.max_iterations, 5);
}

#[test]
fn test_bug_fix_selects_ai_mode() {
    let mut config = E2EPipelineConfig::default();

    let context = ModeDetectionContext {
        analysis_type: Some(AnalysisType::BugFix),
        target_file: Some("auth/login.rs".to_string()),
        ..Default::default()
    };

    let mode = config.configure_smart_pagerank(context);

    assert_eq!(mode, RecommendedMode::AI);
    assert_eq!(config.pagerank_settings.enable_personalized, true); // PPR enabled!
    assert_eq!(config.pagerank_settings.enable_hits, false);
}

#[test]
fn test_architecture_review_selects_architecture_mode() {
    let mut config = E2EPipelineConfig::default();

    let context = ModeDetectionContext {
        is_architecture_review: true,
        ..Default::default()
    };

    let mode = config.configure_smart_pagerank(context);

    assert_eq!(mode, RecommendedMode::Architecture);
    assert_eq!(config.pagerank_settings.enable_personalized, false);
    assert_eq!(config.pagerank_settings.enable_hits, true); // HITS enabled!
}

#[test]
fn test_query_with_bug_keyword_selects_ai_mode() {
    let mut config = E2EPipelineConfig::default();

    let context = ModeDetectionContext {
        query: Some("fix authentication bug in login flow".to_string()),
        ..Default::default()
    };

    let mode = config.configure_smart_pagerank(context);

    assert_eq!(mode, RecommendedMode::AI);
    assert_eq!(config.pagerank_settings.enable_personalized, true);
}

#[test]
fn test_query_with_architecture_keyword_selects_architecture_mode() {
    let mut config = E2EPipelineConfig::default();

    let context = ModeDetectionContext {
        query: Some("analyze repository architecture and identify core libraries".to_string()),
        ..Default::default()
    };

    let mode = config.configure_smart_pagerank(context);

    assert_eq!(mode, RecommendedMode::Architecture);
    assert_eq!(config.pagerank_settings.enable_hits, true);
}

#[test]
fn test_small_repo_selects_full_mode() {
    let mut config = E2EPipelineConfig::default();

    let context = ModeDetectionContext {
        repo_size: Some(5_000), // Small repo
        ..Default::default()
    };

    let mode = config.configure_smart_pagerank(context);

    assert_eq!(mode, RecommendedMode::Full);
    assert_eq!(config.pagerank_settings.enable_personalized, true);
    assert_eq!(config.pagerank_settings.enable_hits, true);
    assert_eq!(config.pagerank_settings.max_iterations, 10); // More precise
}

#[test]
fn test_ai_agent_flag_selects_ai_mode() {
    let mut config = E2EPipelineConfig::default();

    let context = ModeDetectionContext {
        is_ai_agent: true,
        ..Default::default()
    };

    let mode = config.configure_smart_pagerank(context);

    assert_eq!(mode, RecommendedMode::AI);
    assert_eq!(config.pagerank_settings.enable_personalized, true);
}

#[test]
fn test_default_context_selects_fast_mode() {
    let mut config = E2EPipelineConfig::default();
    let context = ModeDetectionContext::default();

    let mode = config.configure_smart_pagerank(context);

    assert_eq!(mode, RecommendedMode::Fast); // Safe default
}

#[test]
fn test_builder_pattern_with_smart_mode() {
    let config = E2EPipelineConfig::default().with_smart_pagerank(ModeDetectionContext {
        target_file: Some("src/main.rs".to_string()),
        ..Default::default()
    });

    // target_file triggers AI mode
    assert_eq!(config.pagerank_settings.enable_personalized, true);
}

#[test]
fn test_refactoring_plan_selects_full_mode() {
    let mut config = E2EPipelineConfig::default();

    let context = ModeDetectionContext {
        analysis_type: Some(AnalysisType::RefactoringPlan),
        ..Default::default()
    };

    let mode = config.configure_smart_pagerank(context);

    assert_eq!(mode, RecommendedMode::Full);
    assert_eq!(config.pagerank_settings.enable_personalized, true);
    assert_eq!(config.pagerank_settings.enable_hits, true);
}

#[test]
fn test_mode_descriptions() {
    let fast = RecommendedMode::Fast;
    let ai = RecommendedMode::AI;
    let arch = RecommendedMode::Architecture;
    let full = RecommendedMode::Full;

    assert!(fast.description().contains("Fast"));
    assert!(ai.description().contains("AI"));
    assert!(arch.description().contains("Architecture"));
    assert!(full.description().contains("Full"));
}

#[test]
fn test_time_multipliers() {
    assert_eq!(RecommendedMode::Fast.time_multiplier(), 1.0);
    assert_eq!(RecommendedMode::AI.time_multiplier(), 2.0);
    assert_eq!(RecommendedMode::Architecture.time_multiplier(), 2.0);
    assert_eq!(RecommendedMode::Full.time_multiplier(), 3.5);
}
