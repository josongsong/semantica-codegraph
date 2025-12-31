//! SMT UseCase

/// SMT UseCase Trait
pub trait SmtUseCase: Send + Sync {
    fn solve(&self, formula: &str) -> SmtResult;
}

#[derive(Debug, Clone, Default)]
pub struct SmtResult {
    pub sat: Option<bool>,
    pub model: Option<String>,
}

/// SMT UseCase Implementation
#[derive(Debug, Default)]
pub struct SmtUseCaseImpl;

impl SmtUseCaseImpl {
    pub fn new() -> Self {
        Self
    }
}

impl SmtUseCase for SmtUseCaseImpl {
    fn solve(&self, _formula: &str) -> SmtResult {
        SmtResult::default()
    }
}
