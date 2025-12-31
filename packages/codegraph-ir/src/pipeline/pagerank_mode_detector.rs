//! PageRank Mode Auto-Detection
//!
//! Automatically detects which PageRank algorithms to enable based on usage context.

use crate::features::repomap::infrastructure::PageRankSettings;

/// Detection signals for determining PageRank mode
#[derive(Debug, Clone, Default)]
pub struct ModeDetectionContext {
    /// User query or task description
    pub query: Option<String>,

    /// Target file for focused analysis
    pub target_file: Option<String>,

    /// Analysis type requested
    pub analysis_type: Option<AnalysisType>,

    /// Repository size (LOC)
    pub repo_size: Option<usize>,

    /// Is this for AI agent use?
    pub is_ai_agent: bool,

    /// Is this for architecture review?
    pub is_architecture_review: bool,

    /// Is this initial indexing?
    pub is_initial_indexing: bool,
}

/// Type of analysis being performed
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnalysisType {
    /// Initial repository scan
    InitialIndexing,

    /// Bug fixing with specific file context
    BugFix,

    /// Feature exploration
    FeatureExploration,

    /// Code navigation from specific file
    CodeNavigation,

    /// Architecture analysis
    ArchitectureReview,

    /// Refactoring planning
    RefactoringPlan,

    /// General query without specific context
    GeneralQuery,
}

/// Recommended PageRank mode
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RecommendedMode {
    /// Fast mode: PageRank only (fastest)
    Fast,

    /// AI mode: PageRank + Personalized PageRank
    AI,

    /// Architecture mode: PageRank + HITS
    Architecture,

    /// Full mode: All algorithms
    Full,
}

impl RecommendedMode {
    /// Apply this mode to PageRank settings
    pub fn apply_to_settings(&self, settings: &mut PageRankSettings) {
        match self {
            Self::Fast => {
                settings.enable_personalized = false;
                settings.enable_hits = false;
                settings.max_iterations = 5;
            }
            Self::AI => {
                settings.enable_personalized = true;
                settings.enable_hits = false;
                settings.max_iterations = 5;
            }
            Self::Architecture => {
                settings.enable_personalized = false;
                settings.enable_hits = true;
                settings.max_iterations = 5;
            }
            Self::Full => {
                settings.enable_personalized = true;
                settings.enable_hits = true;
                settings.max_iterations = 10;
            }
        }
    }

    /// Get mode description
    pub fn description(&self) -> &'static str {
        match self {
            Self::Fast => "Fast mode: Basic importance scoring (fastest)",
            Self::AI => "AI mode: Context-aware code navigation",
            Self::Architecture => "Architecture mode: Authority/Hub analysis",
            Self::Full => "Full mode: Complete analysis (slowest)",
        }
    }

    /// Get estimated time multiplier vs Fast mode
    pub fn time_multiplier(&self) -> f32 {
        match self {
            Self::Fast => 1.0,
            Self::AI => 2.0,
            Self::Architecture => 2.0,
            Self::Full => 3.5,
        }
    }
}

/// Auto-detect optimal PageRank mode
pub fn detect_mode(context: &ModeDetectionContext) -> RecommendedMode {
    // Rule 1: Initial indexing → Fast mode
    if context.is_initial_indexing {
        return RecommendedMode::Fast;
    }

    // Rule 2: Explicit analysis type
    if let Some(analysis_type) = context.analysis_type {
        return match analysis_type {
            AnalysisType::InitialIndexing => RecommendedMode::Fast,
            AnalysisType::BugFix => RecommendedMode::AI,
            AnalysisType::FeatureExploration => RecommendedMode::AI,
            AnalysisType::CodeNavigation => RecommendedMode::AI,
            AnalysisType::ArchitectureReview => RecommendedMode::Architecture,
            AnalysisType::RefactoringPlan => RecommendedMode::Full,
            AnalysisType::GeneralQuery => RecommendedMode::Fast,
        };
    }

    // Rule 3: Architecture review flag
    if context.is_architecture_review {
        return RecommendedMode::Architecture;
    }

    // Rule 4: AI agent flag
    if context.is_ai_agent {
        return RecommendedMode::AI;
    }

    // Rule 5: Has target file → AI mode (context-aware)
    if context.target_file.is_some() {
        return RecommendedMode::AI;
    }

    // Rule 6: Query-based detection
    if let Some(query) = &context.query {
        let query_lower = query.to_lowercase();

        // Bug fixing keywords
        if query_lower.contains("bug")
            || query_lower.contains("fix")
            || query_lower.contains("error")
            || query_lower.contains("related to")
            || query_lower.contains("depends on")
        {
            return RecommendedMode::AI;
        }

        // Architecture keywords
        if query_lower.contains("architecture")
            || query_lower.contains("structure")
            || query_lower.contains("refactor")
            || query_lower.contains("authority")
            || query_lower.contains("hub")
            || query_lower.contains("core library")
        {
            return RecommendedMode::Architecture;
        }

        // Navigation keywords
        if query_lower.contains("find")
            || query_lower.contains("related")
            || query_lower.contains("similar")
            || query_lower.contains("connected")
        {
            return RecommendedMode::AI;
        }
    }

    // Rule 7: Small repository → Full mode is acceptable
    if let Some(size) = context.repo_size {
        if size < 10_000 {
            // Small repo, Full mode is fast enough
            return RecommendedMode::Full;
        }
    }

    // Default: Fast mode (safest choice)
    RecommendedMode::Fast
}

/// Smart mode: Auto-detect and apply settings
pub fn configure_smart_mode(
    settings: &mut PageRankSettings,
    context: &ModeDetectionContext,
) -> RecommendedMode {
    let mode = detect_mode(context);
    mode.apply_to_settings(settings);
    mode
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_initial_indexing() {
        let context = ModeDetectionContext {
            is_initial_indexing: true,
            ..Default::default()
        };

        assert_eq!(detect_mode(&context), RecommendedMode::Fast);
    }

    #[test]
    fn test_bug_fix() {
        let context = ModeDetectionContext {
            analysis_type: Some(AnalysisType::BugFix),
            ..Default::default()
        };

        assert_eq!(detect_mode(&context), RecommendedMode::AI);
    }

    #[test]
    fn test_architecture_review() {
        let context = ModeDetectionContext {
            is_architecture_review: true,
            ..Default::default()
        };

        assert_eq!(detect_mode(&context), RecommendedMode::Architecture);
    }

    #[test]
    fn test_query_bug_keywords() {
        let context = ModeDetectionContext {
            query: Some("fix bug in auth module".to_string()),
            ..Default::default()
        };

        assert_eq!(detect_mode(&context), RecommendedMode::AI);
    }

    #[test]
    fn test_query_architecture_keywords() {
        let context = ModeDetectionContext {
            query: Some("analyze repository architecture".to_string()),
            ..Default::default()
        };

        assert_eq!(detect_mode(&context), RecommendedMode::Architecture);
    }

    #[test]
    fn test_target_file() {
        let context = ModeDetectionContext {
            target_file: Some("src/main.rs".to_string()),
            ..Default::default()
        };

        assert_eq!(detect_mode(&context), RecommendedMode::AI);
    }

    #[test]
    fn test_small_repo() {
        let context = ModeDetectionContext {
            repo_size: Some(5_000),
            ..Default::default()
        };

        assert_eq!(detect_mode(&context), RecommendedMode::Full);
    }

    #[test]
    fn test_ai_agent_flag() {
        let context = ModeDetectionContext {
            is_ai_agent: true,
            ..Default::default()
        };

        assert_eq!(detect_mode(&context), RecommendedMode::AI);
    }

    #[test]
    fn test_default_fast_mode() {
        let context = ModeDetectionContext::default();

        assert_eq!(detect_mode(&context), RecommendedMode::Fast);
    }

    #[test]
    fn test_configure_smart_mode() {
        let mut settings = PageRankSettings::default();
        let context = ModeDetectionContext {
            query: Some("find files related to authentication".to_string()),
            ..Default::default()
        };

        let mode = configure_smart_mode(&mut settings, &context);

        assert_eq!(mode, RecommendedMode::AI);
        assert_eq!(settings.enable_personalized, true);
        assert_eq!(settings.enable_hits, false);
    }

    #[test]
    fn test_mode_descriptions() {
        assert_eq!(
            RecommendedMode::Fast.description(),
            "Fast mode: Basic importance scoring (fastest)"
        );
        assert_eq!(
            RecommendedMode::AI.description(),
            "AI mode: Context-aware code navigation"
        );
    }

    #[test]
    fn test_time_multipliers() {
        assert_eq!(RecommendedMode::Fast.time_multiplier(), 1.0);
        assert_eq!(RecommendedMode::AI.time_multiplier(), 2.0);
        assert_eq!(RecommendedMode::Architecture.time_multiplier(), 2.0);
        assert_eq!(RecommendedMode::Full.time_multiplier(), 3.5);
    }
}
