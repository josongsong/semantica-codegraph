/*
 * SSA Error Types
 *
 * Comprehensive error handling for SSA construction:
 * - Validation errors
 * - CFG errors
 * - Phi node errors
 */

use std::fmt;

/// SSA Error Type
#[derive(Debug, Clone, PartialEq)]
pub enum SSAError {
    /// Empty input (no blocks or statements)
    EmptyInput { message: String },

    /// Invalid function ID (empty or malformed)
    InvalidFunctionId { function_id: String },

    /// Invalid block ID (empty or malformed)
    InvalidBlockId { block_id: String },

    /// Block not found in CFG
    BlockNotFound { block_id: String },

    /// Invalid CFG structure (e.g., no entry block)
    InvalidCFG { reason: String },

    /// Variable not defined (use before def)
    UndefinedVariable { variable: String, block_id: String },

    /// Phi node construction error
    PhiNodeError { variable: String, reason: String },

    /// Circular dependency in SSA construction
    CircularDependency { variable: String },

    /// Internal error (shouldn't happen in production)
    Internal { message: String },
}

impl fmt::Display for SSAError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SSAError::EmptyInput { message } => {
                write!(f, "Empty input: {}", message)
            }
            SSAError::InvalidFunctionId { function_id } => {
                write!(f, "Invalid function ID: '{}'", function_id)
            }
            SSAError::InvalidBlockId { block_id } => {
                write!(f, "Invalid block ID: '{}'", block_id)
            }
            SSAError::BlockNotFound { block_id } => {
                write!(f, "Block not found: '{}'", block_id)
            }
            SSAError::InvalidCFG { reason } => {
                write!(f, "Invalid CFG: {}", reason)
            }
            SSAError::UndefinedVariable { variable, block_id } => {
                write!(
                    f,
                    "Undefined variable '{}' in block '{}'",
                    variable, block_id
                )
            }
            SSAError::PhiNodeError { variable, reason } => {
                write!(f, "Phi node error for '{}': {}", variable, reason)
            }
            SSAError::CircularDependency { variable } => {
                write!(
                    f,
                    "Circular dependency detected for variable '{}'",
                    variable
                )
            }
            SSAError::Internal { message } => {
                write!(f, "Internal error: {}", message)
            }
        }
    }
}

impl std::error::Error for SSAError {}

/// Result type for SSA operations
pub type SSAResult<T> = Result<T, SSAError>;
