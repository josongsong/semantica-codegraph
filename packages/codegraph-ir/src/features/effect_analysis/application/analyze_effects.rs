use crate::features::cross_file::IRDocument;
/// Effect analysis use case
use crate::features::effect_analysis::{EffectAnalyzer, EffectSet};
use std::collections::HashMap;

/// Effect analysis use case
pub struct EffectAnalysisUseCase {
    analyzer: EffectAnalyzer,
}

impl EffectAnalysisUseCase {
    pub fn new() -> Self {
        Self {
            analyzer: EffectAnalyzer::new(),
        }
    }

    pub fn analyze_all_effects(&self, ir_doc: &IRDocument) -> HashMap<String, EffectSet> {
        self.analyzer.analyze_all(ir_doc)
    }
}

impl Default for EffectAnalysisUseCase {
    fn default() -> Self {
        Self::new()
    }
}
