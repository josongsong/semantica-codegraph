//! Lowering UseCase

/// Lowering UseCase Trait
pub trait LoweringUseCase: Send + Sync {
    fn lower_ast(&self, ast: &str) -> LoweringResult;
}

#[derive(Debug, Clone, Default)]
pub struct LoweringResult {
    pub success: bool,
    pub ir_size: usize,
}

/// Lowering UseCase Implementation
#[derive(Debug, Default)]
pub struct LoweringUseCaseImpl;

impl LoweringUseCaseImpl {
    pub fn new() -> Self {
        Self
    }
}

impl LoweringUseCase for LoweringUseCaseImpl {
    fn lower_ast(&self, _ast: &str) -> LoweringResult {
        LoweringResult::default()
    }
}
