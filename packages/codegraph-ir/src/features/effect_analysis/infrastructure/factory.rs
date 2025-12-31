/// Strategy factory for Dependency Injection
///
/// Creates effect analysis strategies based on configuration.
use crate::features::effect_analysis::domain::ports::InterproceduralAnalysisPort;
use crate::features::effect_analysis::infrastructure::{
    biabduction::BiAbductionStrategy, fixpoint::FixpointStrategy, hybrid::HybridStrategy,
    EffectAnalyzer, LocalEffectAnalyzer,
};
use std::sync::Arc;

/// Strategy type selector
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum StrategyType {
    /// Fixpoint iteration (fast full analysis, slower incremental)
    Fixpoint,
    /// Bi-abduction (slower full analysis, very fast incremental) - STUB
    BiAbduction,
    /// Hybrid (combines both for optimal speed + accuracy) - RECOMMENDED
    Hybrid,
}

impl StrategyType {
    /// Parse from string
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "fixpoint" => Some(Self::Fixpoint),
            "biabduction" | "bi-abduction" | "biab" => Some(Self::BiAbduction),
            "hybrid" => Some(Self::Hybrid),
            _ => None,
        }
    }
}

/// Create strategy with default configuration
pub fn create_strategy(strategy_type: StrategyType) -> Arc<dyn InterproceduralAnalysisPort> {
    match strategy_type {
        StrategyType::Fixpoint => create_fixpoint_strategy(),
        StrategyType::BiAbduction => create_biabduction_strategy(),
        StrategyType::Hybrid => create_hybrid_strategy(),
    }
}

/// Create Fixpoint strategy
pub fn create_fixpoint_strategy() -> Arc<dyn InterproceduralAnalysisPort> {
    let effect_analyzer = EffectAnalyzer::new();
    Arc::new(FixpointStrategy::new(effect_analyzer))
}

/// Create Bi-abduction strategy (stub)
pub fn create_biabduction_strategy() -> Arc<dyn InterproceduralAnalysisPort> {
    let local_analyzer = LocalEffectAnalyzer::new();
    Arc::new(BiAbductionStrategy::new(local_analyzer))
}

/// Create Hybrid strategy (RECOMMENDED)
pub fn create_hybrid_strategy() -> Arc<dyn InterproceduralAnalysisPort> {
    create_hybrid_strategy_with_threshold(0.8)
}

/// Create Hybrid strategy with custom confidence threshold
pub fn create_hybrid_strategy_with_threshold(
    threshold: f64,
) -> Arc<dyn InterproceduralAnalysisPort> {
    let local_analyzer_biabduction = LocalEffectAnalyzer::new();

    let effect_analyzer = EffectAnalyzer::new();
    let fixpoint = FixpointStrategy::new(effect_analyzer);
    let biabduction = BiAbductionStrategy::new(local_analyzer_biabduction);

    Arc::new(HybridStrategy::new(fixpoint, biabduction).with_threshold(threshold))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_strategy_type_from_str() {
        assert_eq!(
            StrategyType::from_str("fixpoint"),
            Some(StrategyType::Fixpoint)
        );
        assert_eq!(
            StrategyType::from_str("Fixpoint"),
            Some(StrategyType::Fixpoint)
        );
        assert_eq!(
            StrategyType::from_str("biabduction"),
            Some(StrategyType::BiAbduction)
        );
        assert_eq!(
            StrategyType::from_str("bi-abduction"),
            Some(StrategyType::BiAbduction)
        );
        assert_eq!(StrategyType::from_str("hybrid"), Some(StrategyType::Hybrid));
        assert_eq!(StrategyType::from_str("invalid"), None);
    }

    #[test]
    fn test_create_fixpoint_strategy() {
        let strategy = create_strategy(StrategyType::Fixpoint);
        assert_eq!(strategy.strategy_name(), "Fixpoint");
    }

    #[test]
    fn test_create_biabduction_strategy() {
        let strategy = create_strategy(StrategyType::BiAbduction);
        assert_eq!(strategy.strategy_name(), "BiAbduction(SeparationLogic)");
    }

    #[test]
    fn test_create_hybrid_strategy() {
        let strategy = create_strategy(StrategyType::Hybrid);
        assert_eq!(strategy.strategy_name(), "Hybrid(Fixpoint+BiAbduction)");
    }

    #[test]
    fn test_create_hybrid_with_custom_threshold() {
        let strategy = create_hybrid_strategy_with_threshold(0.9);
        assert_eq!(strategy.strategy_name(), "Hybrid(Fixpoint+BiAbduction)");
    }
}
