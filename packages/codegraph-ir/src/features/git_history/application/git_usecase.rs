//! Git History UseCase Implementation

use crate::features::git_history::domain::{ChurnMetrics, CoChangePattern};

/// Git History UseCase Trait
pub trait GitHistoryUseCase: Send + Sync {
    fn get_churn_metrics(&self, repo_path: &str, file_path: &str) -> Option<ChurnMetrics>;
    fn get_co_change_patterns(&self, repo_path: &str) -> Vec<CoChangePattern>;
}

/// Git History UseCase Implementation
#[derive(Debug, Default)]
pub struct GitHistoryUseCaseImpl;

impl GitHistoryUseCaseImpl {
    pub fn new() -> Self {
        Self
    }
}

impl GitHistoryUseCase for GitHistoryUseCaseImpl {
    fn get_churn_metrics(&self, _repo_path: &str, _file_path: &str) -> Option<ChurnMetrics> {
        // TODO: Delegate to GitExecutor when API stabilizes
        None
    }

    fn get_co_change_patterns(&self, _repo_path: &str) -> Vec<CoChangePattern> {
        // TODO: Delegate to GitExecutor when API stabilizes
        Vec::new()
    }
}
