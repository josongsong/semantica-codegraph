//! Query UseCase Implementation
//!
//! Provides application-level interface for query operations.
//! External callers should use this UseCase, not QueryEngine directly.

use crate::features::ir_generation::domain::ir_document::IRDocument;
use crate::features::query_engine::domain::{PathQuery, PathResult};
use crate::features::query_engine::query_engine::{QueryEngine, QueryEngineStats};

/// Input for query execution
pub struct QueryInput<'a> {
    /// IR document to query
    pub ir_doc: &'a IRDocument,
    /// Query to execute
    pub query: PathQuery,
}

/// Output from query execution
#[derive(Debug, Clone)]
pub struct QueryOutput {
    /// Found paths
    pub paths: Vec<PathResult>,
    /// Query statistics
    pub stats: QueryStats,
}

/// Query execution statistics
#[derive(Debug, Clone, Default)]
pub struct QueryStats {
    pub paths_found: usize,
    pub nodes_visited: usize,
    pub execution_time_ms: u64,
}

/// Query UseCase Trait (Port)
///
/// Defines the contract for query operations.
/// External callers should depend on this trait.
pub trait QueryUseCase: Send + Sync {
    /// Execute a path query on IR document
    ///
    /// # Arguments
    /// * `ir_doc` - IR document to query
    /// * `query` - Path query to execute
    ///
    /// # Returns
    /// * `QueryOutput` - Found paths and statistics
    fn execute_query(&self, ir_doc: &IRDocument, query: PathQuery) -> QueryOutput;

    /// Execute multiple queries (batch)
    fn execute_queries(&self, ir_doc: &IRDocument, queries: Vec<PathQuery>) -> Vec<QueryOutput>;

    /// Get engine statistics
    fn get_stats(&self, ir_doc: &IRDocument) -> QueryEngineStats;
}

/// Query UseCase Implementation
#[derive(Debug, Default)]
pub struct QueryUseCaseImpl;

impl QueryUseCaseImpl {
    /// Create new QueryUseCase
    pub fn new() -> Self {
        Self
    }
}

impl QueryUseCase for QueryUseCaseImpl {
    fn execute_query(&self, ir_doc: &IRDocument, query: PathQuery) -> QueryOutput {
        let start = std::time::Instant::now();

        let engine = QueryEngine::new(ir_doc);
        let paths = engine.execute(query);

        let elapsed = start.elapsed();

        QueryOutput {
            stats: QueryStats {
                paths_found: paths.len(),
                nodes_visited: 0, // TODO: Track in engine
                execution_time_ms: elapsed.as_millis() as u64,
            },
            paths,
        }
    }

    fn execute_queries(&self, ir_doc: &IRDocument, queries: Vec<PathQuery>) -> Vec<QueryOutput> {
        queries
            .into_iter()
            .map(|q| self.execute_query(ir_doc, q))
            .collect()
    }

    fn get_stats(&self, ir_doc: &IRDocument) -> QueryEngineStats {
        let engine = QueryEngine::new(ir_doc);
        engine.stats()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_query_usecase_creation() {
        let _usecase = QueryUseCaseImpl::new();
    }

    #[test]
    fn test_empty_ir_doc() {
        let usecase = QueryUseCaseImpl::new();
        let ir_doc = IRDocument::new("test.py".to_string());

        use crate::features::query_engine::domain::{FlowExpr, Q, TraversalDirection};

        let flow = FlowExpr {
            source: Q::any(),
            target: Q::any(),
            edge_type: None,
            direction: TraversalDirection::Forward,
            depth_range: (1, 10),
        };
        let query = PathQuery::from_flow_expr(flow);

        let output = usecase.execute_query(&ir_doc, query);

        assert_eq!(output.paths.len(), 0);
        assert_eq!(output.stats.paths_found, 0);
    }
}
