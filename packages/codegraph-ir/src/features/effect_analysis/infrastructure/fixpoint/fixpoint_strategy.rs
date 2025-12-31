/// Fixpoint iteration strategy (existing implementation)
///
/// Wraps the existing EffectAnalyzer to provide the InterproceduralAnalysisPort interface.
/// This is the baseline strategy: fast full analysis but slower incremental updates.
use crate::features::cross_file::IRDocument;
use crate::features::effect_analysis::domain::{ports::*, EffectSet};
use crate::features::effect_analysis::infrastructure::EffectAnalyzer;
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Instant;

/// Fixpoint iteration strategy
///
/// Algorithm:
/// 1. Local analysis for all functions
/// 2. Build call graph
/// 3. Fixpoint iteration (max 10 rounds) to propagate effects
///
/// Performance:
/// - Full analysis: O(F × S + F × C × I) where F=functions, S=stmts, C=callees, I=iterations
/// - Incremental: Same as full (no incremental optimization yet)
pub struct FixpointStrategy {
    analyzer: EffectAnalyzer,
    metrics: Mutex<AnalysisMetrics>,
}

impl FixpointStrategy {
    pub fn new(analyzer: EffectAnalyzer) -> Self {
        Self {
            analyzer,
            metrics: Mutex::new(AnalysisMetrics::new()),
        }
    }
}

impl InterproceduralAnalysisPort for FixpointStrategy {
    fn analyze_all(&self, ir_doc: &IRDocument) -> HashMap<String, EffectSet> {
        let start = Instant::now();

        // Delegate to existing EffectAnalyzer (fixpoint iteration)
        let result = self.analyzer.analyze_all(ir_doc);

        // Calculate metrics
        let elapsed = start.elapsed().as_secs_f64() * 1000.0;
        let avg_confidence = if result.is_empty() {
            0.0
        } else {
            result.values().map(|e| e.confidence).sum::<f64>() / result.len() as f64
        };

        let mut metrics = self.metrics.lock().unwrap();
        metrics.total_time_ms = elapsed;
        metrics.functions_analyzed = result.len();
        metrics.iterations = 3; // Typical fixpoint convergence (estimate)
        metrics.avg_confidence = avg_confidence;

        result
    }

    fn analyze_incremental(
        &self,
        ir_doc: &IRDocument,
        _changed_functions: &[String],
        _cache: &HashMap<String, EffectSet>,
    ) -> HashMap<String, EffectSet> {
        let start = Instant::now();

        // Incremental analysis: re-analyze changed_functions + transitive callers
        // Algorithm: 1) Build reverse call graph 2) BFS from changed 3) Fixpoint on affected
        // Current: Full re-analysis (conservative, correct)
        let result = self.analyzer.analyze_all(ir_doc);

        let elapsed = start.elapsed().as_secs_f64() * 1000.0;

        let mut metrics = self.metrics.lock().unwrap();
        metrics.total_time_ms = elapsed;
        metrics.functions_analyzed = result.len();
        metrics.cache_hits = 0; // Full re-analysis = no cache hits
        metrics.cache_misses = result.len();

        result
    }

    fn strategy_name(&self) -> &'static str {
        "Fixpoint"
    }

    fn metrics(&self) -> AnalysisMetrics {
        self.metrics.lock().unwrap().clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::effect_analysis::infrastructure::LocalEffectAnalyzer;

    #[test]
    fn test_fixpoint_strategy_creation() {
        let local_analyzer = LocalEffectAnalyzer::new();
        let effect_analyzer = EffectAnalyzer::new();
        let strategy = FixpointStrategy::new(effect_analyzer);

        assert_eq!(strategy.strategy_name(), "Fixpoint");
    }

    #[test]
    fn test_fixpoint_metrics_initial() {
        let local_analyzer = LocalEffectAnalyzer::new();
        let effect_analyzer = EffectAnalyzer::new();
        let strategy = FixpointStrategy::new(effect_analyzer);

        let metrics = strategy.metrics();
        assert_eq!(metrics.total_time_ms, 0.0);
        assert_eq!(metrics.functions_analyzed, 0);
    }
}
