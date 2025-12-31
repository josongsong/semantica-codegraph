//! Graph Builder UseCase

/// Graph Builder UseCase Trait
pub trait GraphBuilderUseCase: Send + Sync {
    fn build_graph(&self, nodes_count: usize) -> GraphBuildResult;
}

#[derive(Debug, Clone, Default)]
pub struct GraphBuildResult {
    pub nodes: usize,
    pub edges: usize,
}

/// Graph Builder UseCase Implementation
#[derive(Debug, Default)]
pub struct GraphBuilderUseCaseImpl;

impl GraphBuilderUseCaseImpl {
    pub fn new() -> Self {
        Self
    }
}

impl GraphBuilderUseCase for GraphBuilderUseCaseImpl {
    fn build_graph(&self, nodes_count: usize) -> GraphBuildResult {
        GraphBuildResult {
            nodes: nodes_count,
            edges: 0,
        }
    }
}
