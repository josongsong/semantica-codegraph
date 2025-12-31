/// Port for interprocedural effect analysis strategies
///
/// This trait defines the interface for different effect analysis strategies:
/// - Fixpoint: Fast full analysis with iterative propagation
/// - BiAbduction: Precise incremental analysis with compositional reasoning
/// - Hybrid: Combines both for optimal speed + accuracy
use crate::features::cross_file::IRDocument;
use crate::features::effect_analysis::domain::EffectSet;
use std::collections::HashMap;

/// Port for interprocedural effect analysis strategies
pub trait InterproceduralAnalysisPort: Send + Sync {
    /// Analyze all functions in IR document
    fn analyze_all(&self, ir_doc: &IRDocument) -> HashMap<String, EffectSet>;

    /// Analyze incremental (changed functions only)
    ///
    /// # Arguments
    /// * `ir_doc` - The IR document
    /// * `changed_functions` - List of function IDs that changed
    /// * `cache` - Previous analysis results to reuse
    fn analyze_incremental(
        &self,
        ir_doc: &IRDocument,
        changed_functions: &[String],
        cache: &HashMap<String, EffectSet>,
    ) -> HashMap<String, EffectSet>;

    /// Get strategy name (for logging/benchmarking)
    fn strategy_name(&self) -> &'static str;

    /// Get performance metrics
    fn metrics(&self) -> AnalysisMetrics;
}

/// Performance metrics for comparison
#[derive(Debug, Clone, Default)]
pub struct AnalysisMetrics {
    /// Total analysis time in milliseconds
    pub total_time_ms: f64,

    /// Number of functions analyzed
    pub functions_analyzed: usize,

    /// Number of fixpoint iterations (for Fixpoint strategy)
    pub iterations: usize,

    /// Number of cache hits (for incremental analysis)
    pub cache_hits: usize,

    /// Number of cache misses (re-analysis needed)
    pub cache_misses: usize,

    /// Average confidence across all functions
    pub avg_confidence: f64,
}

impl AnalysisMetrics {
    pub fn new() -> Self {
        Self::default()
    }

    /// Create metrics with total time
    pub fn with_time(total_time_ms: f64, functions_analyzed: usize) -> Self {
        Self {
            total_time_ms,
            functions_analyzed,
            iterations: 0,
            cache_hits: 0,
            cache_misses: 0,
            avg_confidence: 0.0,
        }
    }

    /// Calculate cache hit rate (0.0 - 1.0)
    pub fn cache_hit_rate(&self) -> f64 {
        let total = self.cache_hits + self.cache_misses;
        if total == 0 {
            0.0
        } else {
            self.cache_hits as f64 / total as f64
        }
    }

    /// Print summary
    pub fn print_summary(&self, strategy_name: &str) {
        println!("=== {} Metrics ===", strategy_name);
        println!("  Time: {:.2}ms", self.total_time_ms);
        println!("  Functions: {}", self.functions_analyzed);
        println!("  Iterations: {}", self.iterations);
        println!("  Cache hit rate: {:.1}%", self.cache_hit_rate() * 100.0);
        println!("  Avg confidence: {:.2}", self.avg_confidence);
    }
}
