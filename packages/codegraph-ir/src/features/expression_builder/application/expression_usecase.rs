//! Expression Builder UseCase

/// Expression Builder UseCase Trait
pub trait ExpressionBuilderUseCase: Send + Sync {
    fn build_expression(&self, input: &str) -> String;
}

/// Expression Builder UseCase Implementation
#[derive(Debug, Default)]
pub struct ExpressionBuilderUseCaseImpl;

impl ExpressionBuilderUseCaseImpl {
    pub fn new() -> Self {
        Self
    }
}

impl ExpressionBuilderUseCase for ExpressionBuilderUseCaseImpl {
    fn build_expression(&self, input: &str) -> String {
        input.to_string()
    }
}
