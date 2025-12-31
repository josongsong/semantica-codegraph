/*
 * Data Flow Error Types
 *
 * Comprehensive error handling for DFG construction:
 * - Validation errors
 * - Empty input handling
 * - Invalid IDs
 */

use std::fmt;

/// DFG Error Type
#[derive(Debug, Clone, PartialEq)]
pub enum DFGError {
    /// Empty input (no nodes or edges provided)
    EmptyInput { message: String },

    /// Invalid function ID (empty or malformed)
    InvalidFunctionId { function_id: String },

    /// Invalid node data (missing required fields)
    InvalidNode { node_id: String, reason: String },

    /// Invalid edge data (missing required fields)
    InvalidEdge { edge_id: String, reason: String },

    /// Span validation error (invalid line/column numbers)
    InvalidSpan { reason: String },

    /// Circular dependency detected
    CircularDependency { variable: String },

    /// Internal error (shouldn't happen in production)
    Internal { message: String },
}

impl fmt::Display for DFGError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            DFGError::EmptyInput { message } => {
                write!(f, "Empty input: {}", message)
            }
            DFGError::InvalidFunctionId { function_id } => {
                write!(f, "Invalid function ID: '{}'", function_id)
            }
            DFGError::InvalidNode { node_id, reason } => {
                write!(f, "Invalid node '{}': {}", node_id, reason)
            }
            DFGError::InvalidEdge { edge_id, reason } => {
                write!(f, "Invalid edge '{}': {}", edge_id, reason)
            }
            DFGError::InvalidSpan { reason } => {
                write!(f, "Invalid span: {}", reason)
            }
            DFGError::CircularDependency { variable } => {
                write!(
                    f,
                    "Circular dependency detected for variable '{}'",
                    variable
                )
            }
            DFGError::Internal { message } => {
                write!(f, "Internal error: {}", message)
            }
        }
    }
}

impl std::error::Error for DFGError {}

/// Result type for DFG operations
pub type DFGResult<T> = Result<T, DFGError>;
