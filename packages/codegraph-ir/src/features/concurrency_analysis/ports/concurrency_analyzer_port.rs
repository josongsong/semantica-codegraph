/// Concurrency analyzer port trait
use crate::features::concurrency_analysis::{RaceCondition, Result};
use crate::features::cross_file::IRDocument;

/// Port trait for concurrency analyzers
///
/// Allows for different implementations (e.g., RacerD-style, ThreadSanitizer-style).
pub trait ConcurrencyAnalyzerPort {
    /// Analyze async function for races
    fn analyze_async_function(
        &self,
        ir_doc: &IRDocument,
        func_fqn: &str,
    ) -> Result<Vec<RaceCondition>>;

    /// Analyze all async functions
    fn analyze_all(&self, ir_doc: &IRDocument) -> Result<Vec<RaceCondition>>;
}
