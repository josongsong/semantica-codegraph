/*
 * Interprocedural Taint Analysis Errors
 *
 * Comprehensive error types for interprocedural taint analysis.
 */

use std::fmt;

/// Errors that can occur during interprocedural taint analysis
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InterproceduralTaintError {
    /// Empty or invalid call graph
    InvalidCallGraph(String),

    /// Empty input (no sources or sinks)
    EmptyInput(String),

    /// Function not found in call graph
    FunctionNotFound(String),

    /// Circular dependency detected (not an error, but logged)
    CircularDependency {
        function: String,
        cycle: Vec<String>,
    },

    /// Fixpoint did not converge
    FixpointNotConverged { rounds: usize, max_rounds: usize },

    /// Max depth exceeded
    MaxDepthExceeded {
        function: String,
        depth: usize,
        max_depth: usize,
    },

    /// Max paths exceeded
    MaxPathsExceeded { count: usize, max_paths: usize },

    /// Invalid source/sink specification
    InvalidSourceSink(String),

    /// Analysis internal error
    InternalError(String),
}

impl fmt::Display for InterproceduralTaintError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidCallGraph(msg) => {
                write!(f, "Invalid call graph: {}", msg)
            }
            Self::EmptyInput(msg) => {
                write!(f, "Empty input: {}", msg)
            }
            Self::FunctionNotFound(func) => {
                write!(f, "Function not found in call graph: {}", func)
            }
            Self::CircularDependency { function, cycle } => {
                write!(
                    f,
                    "Circular dependency detected: {} -> {}",
                    function,
                    cycle.join(" -> ")
                )
            }
            Self::FixpointNotConverged { rounds, max_rounds } => {
                write!(
                    f,
                    "Fixpoint did not converge after {} rounds (max: {})",
                    rounds, max_rounds
                )
            }
            Self::MaxDepthExceeded {
                function,
                depth,
                max_depth,
            } => {
                write!(
                    f,
                    "Max depth exceeded for {}: {} > {}",
                    function, depth, max_depth
                )
            }
            Self::MaxPathsExceeded { count, max_paths } => {
                write!(f, "Max paths exceeded: {} > {}", count, max_paths)
            }
            Self::InvalidSourceSink(msg) => {
                write!(f, "Invalid source/sink specification: {}", msg)
            }
            Self::InternalError(msg) => {
                write!(f, "Internal error: {}", msg)
            }
        }
    }
}

impl std::error::Error for InterproceduralTaintError {}

/// Result type for interprocedural taint analysis
pub type InterproceduralTaintResult<T> = Result<T, InterproceduralTaintError>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_display() {
        let err = InterproceduralTaintError::InvalidCallGraph("test".to_string());
        assert_eq!(err.to_string(), "Invalid call graph: test");
    }

    #[test]
    fn test_circular_dependency_display() {
        let err = InterproceduralTaintError::CircularDependency {
            function: "a".to_string(),
            cycle: vec!["b".to_string(), "c".to_string(), "a".to_string()],
        };
        assert!(err.to_string().contains("Circular dependency"));
        assert!(err.to_string().contains("b -> c -> a"));
    }

    #[test]
    fn test_fixpoint_not_converged() {
        let err = InterproceduralTaintError::FixpointNotConverged {
            rounds: 10,
            max_rounds: 10,
        };
        assert!(err.to_string().contains("did not converge"));
    }
}
