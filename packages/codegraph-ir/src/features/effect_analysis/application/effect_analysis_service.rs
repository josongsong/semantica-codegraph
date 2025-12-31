/// Application service for effect analysis
///
/// This service uses the Strategy pattern via InterproceduralAnalysisPort.
/// The actual strategy (Fixpoint/BiAbduction/Hybrid) is injected via DI.
use crate::features::cross_file::IRDocument;
use crate::features::effect_analysis::domain::{ports::*, EffectSet};
use std::collections::HashMap;
use std::sync::Arc;

/// Effect analysis service
///
/// Usage:
/// ```text
/// use codegraph_ir::features::effect_analysis::application::EffectAnalysisService;
/// use codegraph_ir::features::effect_analysis::infrastructure::create_strategy;
/// use codegraph_ir::features::effect_analysis::infrastructure::StrategyType;
///
/// // Create service with desired strategy
/// let strategy = create_strategy(StrategyType::Hybrid);
/// let service = EffectAnalysisService::new(strategy);
///
/// // Analyze IR document (ir_doc would be obtained from parsing)
/// let effects = service.analyze(&ir_doc);
/// ```
pub struct EffectAnalysisService {
    strategy: Arc<dyn InterproceduralAnalysisPort>,
}

impl EffectAnalysisService {
    /// Create new service with given strategy
    pub fn new(strategy: Arc<dyn InterproceduralAnalysisPort>) -> Self {
        Self { strategy }
    }

    /// Analyze all functions in IR document
    pub fn analyze(&self, ir_doc: &IRDocument) -> HashMap<String, EffectSet> {
        self.strategy.analyze_all(ir_doc)
    }

    /// Analyze incrementally (changed functions only)
    ///
    /// # Arguments
    /// * `ir_doc` - The IR document
    /// * `changed_functions` - List of function IDs that changed
    /// * `cache` - Previous analysis results to reuse
    pub fn analyze_incremental(
        &self,
        ir_doc: &IRDocument,
        changed_functions: &[String],
        cache: &HashMap<String, EffectSet>,
    ) -> HashMap<String, EffectSet> {
        self.strategy
            .analyze_incremental(ir_doc, changed_functions, cache)
    }

    /// Get performance metrics from last analysis
    pub fn metrics(&self) -> AnalysisMetrics {
        self.strategy.metrics()
    }

    /// Get strategy name
    pub fn strategy_name(&self) -> &'static str {
        self.strategy.strategy_name()
    }

    /// Print analysis summary
    pub fn print_summary(&self) {
        let metrics = self.metrics();
        metrics.print_summary(self.strategy_name());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::effect_analysis::infrastructure::{
        fixpoint::FixpointStrategy, EffectAnalyzer, LocalEffectAnalyzer,
    };

    #[test]
    fn test_service_creation() {
        let local_analyzer = LocalEffectAnalyzer::new();
        let effect_analyzer = EffectAnalyzer::new();
        let strategy = Arc::new(FixpointStrategy::new(effect_analyzer));

        let service = EffectAnalysisService::new(strategy);

        assert_eq!(service.strategy_name(), "Fixpoint");
    }

    #[test]
    fn test_service_empty_analysis() {
        let local_analyzer = LocalEffectAnalyzer::new();
        let effect_analyzer = EffectAnalyzer::new();
        let strategy = Arc::new(FixpointStrategy::new(effect_analyzer));

        let service = EffectAnalysisService::new(strategy);

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![],
            edges: vec![],
            repo_id: None,
        };

        let result = service.analyze(&ir_doc);
        assert!(result.is_empty());
    }
}
