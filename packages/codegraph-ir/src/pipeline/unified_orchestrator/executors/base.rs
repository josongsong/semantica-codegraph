//! Base StageExecutor Trait
//!
//! All pipeline stages implement this trait for pluggable execution.

use crate::pipeline::dag::StageId;
use crate::shared::models::CodegraphError;
use super::context::PipelineContext;
use std::time::Duration;

/// Result of stage execution
pub struct StageResult {
    /// Stage ID
    pub stage_id: StageId,

    /// Execution duration
    pub duration: Duration,

    /// Success status
    pub success: bool,

    /// Error message (if failed)
    pub error: Option<String>,

    /// Items processed (for stats)
    pub items_processed: usize,

    /// Custom metrics
    pub metrics: Vec<(String, MetricValue)>,
}

impl StageResult {
    pub fn success(stage_id: StageId, duration: Duration, items_processed: usize) -> Self {
        Self {
            stage_id,
            duration,
            success: true,
            error: None,
            items_processed,
            metrics: Vec::new(),
        }
    }

    pub fn failure(stage_id: StageId, duration: Duration, error: String) -> Self {
        Self {
            stage_id,
            duration,
            success: false,
            error: Some(error),
            items_processed: 0,
            metrics: Vec::new(),
        }
    }

    pub fn with_metric(mut self, key: String, value: MetricValue) -> Self {
        self.metrics.push((key, value));
        self
    }
}

/// Metric value types
#[derive(Debug, Clone)]
pub enum MetricValue {
    Int(i64),
    Float(f64),
    String(String),
    Duration(Duration),
    Bool(bool),
}

/// Stage Executor Trait
///
/// Each pipeline stage (L1-L37) implements this trait.
///
/// # Responsibilities
/// - Execute stage logic
/// - Read from context (Arc references)
/// - Write results back to context
/// - Report metrics
///
/// # Example
/// ```ignore
/// pub struct ChunkingExecutor {
///     config: ChunkingConfig,
/// }
///
/// impl StageExecutor for ChunkingExecutor {
///     fn stage_id(&self) -> StageId {
///         StageId::L2Chunking
///     }
///
///     fn execute(&self, ctx: &mut PipelineContext) -> Result<StageResult, CodegraphError> {
///         let start = Instant::now();
///
///         // Get nodes from context (Arc reference, no copy!)
///         let nodes = ctx.get_nodes()?;
///
///         // Build chunks
///         let chunks = self.build_chunks(&nodes)?;
///
///         // Store in context
///         ctx.set_chunks(chunks)?;
///
///         Ok(StageResult::success(
///             StageId::L2Chunking,
///             start.elapsed(),
///             chunks.len(),
///         ))
///     }
///
///     fn dependencies(&self) -> Vec<StageId> {
///         vec![StageId::L1IrBuild]
///     }
/// }
/// ```
pub trait StageExecutor: Send + Sync {
    /// Stage ID
    fn stage_id(&self) -> StageId;

    /// Execute stage
    ///
    /// # Arguments
    /// * `context` - Mutable pipeline context (for reading & writing)
    ///
    /// # Returns
    /// * `Ok(StageResult)` - Success with metrics
    /// * `Err(CodegraphError)` - Execution failure
    fn execute(&self, context: &mut PipelineContext) -> Result<StageResult, CodegraphError>;

    /// Dependencies (stages that must complete before this one)
    fn dependencies(&self) -> Vec<StageId>;

    /// Human-readable name
    fn name(&self) -> &'static str {
        self.stage_id().name()
    }

    /// Description
    fn description(&self) -> &'static str {
        self.stage_id().description()
    }

    /// Is this stage enabled? (RFC-001 integrated)
    fn is_enabled(&self, config: &crate::pipeline::E2EPipelineConfig) -> bool {
        // Use RFC-001 compatible method accessors
        match self.stage_id() {
            StageId::L1IrBuild => config.enable_ir_build(),
            StageId::L2Chunking => config.enable_chunking(),
            StageId::L2_5Lexical => config.enable_lexical(),
            StageId::L3CrossFile => config.enable_cross_file(),
            StageId::L4Occurrences => config.enable_symbols(), // occurrences uses symbols
            StageId::L5Symbols => config.enable_symbols(),
            StageId::L6PointsTo => config.enable_points_to(),
            StageId::L10CloneDetection => config.enable_clone_detection(),
            StageId::L13EffectAnalysis => config.enable_effect_analysis(),
            StageId::L14TaintAnalysis => config.enable_taint(),
            StageId::L15CostAnalysis => config.enable_effect_analysis(), // cost uses effects
            StageId::L16RepoMap => config.enable_repomap(),
            StageId::L18ConcurrencyAnalysis => config.enable_concurrency_analysis(),
            StageId::L21SmtVerification => config.enable_heap_analysis(), // smt uses heap
            StageId::L33GitHistory => config.enable_cross_file(), // git uses cross_file
            StageId::L37QueryEngine => config.enable_chunking() && config.enable_lexical(),
        }
    }
}

/// Boxed executor (for dynamic dispatch)
pub type BoxedExecutor = Box<dyn StageExecutor>;

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn test_stage_result() {
        let result = StageResult::success(
            StageId::L2Chunking,
            Duration::from_secs(5),
            100,
        ).with_metric("chunks_created".to_string(), MetricValue::Int(100));

        assert!(result.success);
        assert_eq!(result.items_processed, 100);
        assert_eq!(result.metrics.len(), 1);
    }
}
