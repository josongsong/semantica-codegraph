//! Expression Builder Domain - Port/Adapter Interface

use crate::shared::models::Result;
use crate::shared::models::{Expression, ExpressionIR};

/// Expression Builder Trait (Port)
///
/// Multi-language expression extraction interface
pub trait ExpressionBuilderTrait {
    /// Build Expression IR from source code
    fn build(&mut self, source: &str, file_path: &str) -> Result<ExpressionIR>;

    /// Language name (e.g., "python", "typescript")
    fn language(&self) -> &str;
}

/// Builder Context (shared state during traversal)
pub struct BuilderContext {
    /// File path
    pub file_path: String,

    /// Next expression ID
    pub next_id: usize,

    /// Accumulated expressions
    pub expressions: Vec<Expression>,

    /// Current function ID (for expression.function_id)
    pub current_function: Option<String>,

    /// Current block ID (for expression.block_id)
    pub current_block: Option<String>,

    /// Parent expression stack (for expression.parent)
    pub parent_stack: Vec<usize>,
}

impl BuilderContext {
    pub fn new(file_path: String) -> Self {
        Self {
            file_path,
            next_id: 0,
            expressions: Vec::new(),
            current_function: None,
            current_block: None,
            parent_stack: Vec::new(),
        }
    }

    /// Allocate next expression ID
    pub fn next_id(&mut self) -> usize {
        let id = self.next_id;
        self.next_id += 1;
        id
    }

    /// Push parent (enter sub-expression)
    pub fn push_parent(&mut self, parent_id: usize) {
        self.parent_stack.push(parent_id);
    }

    /// Pop parent (exit sub-expression)
    pub fn pop_parent(&mut self) {
        self.parent_stack.pop();
    }

    /// Current parent ID (if any)
    pub fn current_parent(&self) -> Option<usize> {
        self.parent_stack.last().copied()
    }

    /// Add expression to result
    pub fn add_expression(&mut self, expr: Expression) {
        self.expressions.push(expr);
    }
}
