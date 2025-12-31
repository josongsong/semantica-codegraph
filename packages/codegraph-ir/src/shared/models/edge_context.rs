//! Edge Context Types - Type-safe edge metadata contexts
//!
//! Replaces string-based context with strongly-typed enums for better type safety.

#[cfg(feature = "python")]
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

/// Read/Write context - replaces Option<String> in EdgeMetadata
#[cfg_attr(feature = "python", pyclass)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ReadWriteContext {
    /// Variable assignment (x = value)
    Assignment,
    /// Return statement (return value)
    Return,
    /// Argument passing (func(arg))
    ArgumentPassing,
    /// Array indexing (arr[i])
    ArrayIndexing,
    /// Attribute access (obj.attr)
    AttributeAccess,
    /// Augmented assignment (x += 1)
    AugmentedAssignment,
    /// Conditional expression (x if cond else y)
    ConditionalExpression,
    /// List comprehension ([x for x in ...])
    Comprehension,
    /// Global/nonlocal declaration
    Declaration,
    /// Unknown/other context
    Other,
}

impl ReadWriteContext {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Assignment => "assignment",
            Self::Return => "return",
            Self::ArgumentPassing => "argument_passing",
            Self::ArrayIndexing => "array_indexing",
            Self::AttributeAccess => "attribute_access",
            Self::AugmentedAssignment => "augmented_assignment",
            Self::ConditionalExpression => "conditional_expression",
            Self::Comprehension => "comprehension",
            Self::Declaration => "declaration",
            Self::Other => "other",
        }
    }

    /// Parse from string (for backward compatibility)
    ///
    /// **Performance**: Zero-allocation case-insensitive matching
    pub fn from_str(s: &str) -> Self {
        // Use eq_ignore_ascii_case to avoid .to_lowercase() allocation
        if s.eq_ignore_ascii_case("assignment") {
            Self::Assignment
        } else if s.eq_ignore_ascii_case("return") {
            Self::Return
        } else if s.eq_ignore_ascii_case("argument_passing") || s.eq_ignore_ascii_case("argument") {
            Self::ArgumentPassing
        } else if s.eq_ignore_ascii_case("array_indexing") || s.eq_ignore_ascii_case("indexing") {
            Self::ArrayIndexing
        } else if s.eq_ignore_ascii_case("attribute_access") || s.eq_ignore_ascii_case("attribute")
        {
            Self::AttributeAccess
        } else if s.eq_ignore_ascii_case("augmented_assignment")
            || s.eq_ignore_ascii_case("augmented")
        {
            Self::AugmentedAssignment
        } else if s.eq_ignore_ascii_case("conditional_expression")
            || s.eq_ignore_ascii_case("conditional")
        {
            Self::ConditionalExpression
        } else if s.eq_ignore_ascii_case("comprehension") {
            Self::Comprehension
        } else if s.eq_ignore_ascii_case("declaration") {
            Self::Declaration
        } else {
            Self::Other
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl ReadWriteContext {
    #[pyo3(name = "__str__")]
    fn py_str(&self) -> &'static str {
        self.as_str()
    }

    #[pyo3(name = "__repr__")]
    fn py_repr(&self) -> String {
        format!("ReadWriteContext.{:?}", self)
    }
}

impl std::fmt::Display for ReadWriteContext {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

/// Control flow context for control flow edges
#[cfg_attr(feature = "python", pyclass)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ControlFlowContext {
    /// Sequential execution (next statement)
    Sequential,
    /// True branch of if/while
    TrueBranch,
    /// False branch of if/while
    FalseBranch,
    /// Loop back edge
    LoopBack,
    /// Loop exit
    LoopExit,
    /// Exception handler
    ExceptionHandler,
    /// Finally block
    Finally,
    /// Function call (control transfer)
    Call,
    /// Return from function
    Return,
}

impl ControlFlowContext {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Sequential => "sequential",
            Self::TrueBranch => "true_branch",
            Self::FalseBranch => "false_branch",
            Self::LoopBack => "loop_back",
            Self::LoopExit => "loop_exit",
            Self::ExceptionHandler => "exception_handler",
            Self::Finally => "finally",
            Self::Call => "call",
            Self::Return => "return",
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl ControlFlowContext {
    #[pyo3(name = "__str__")]
    fn py_str(&self) -> &'static str {
        self.as_str()
    }

    #[pyo3(name = "__repr__")]
    fn py_repr(&self) -> String {
        format!("ControlFlowContext.{:?}", self)
    }
}

impl std::fmt::Display for ControlFlowContext {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_read_write_context_str() {
        assert_eq!(ReadWriteContext::Assignment.as_str(), "assignment");
        assert_eq!(ReadWriteContext::Return.as_str(), "return");
    }

    #[test]
    fn test_read_write_context_from_str() {
        assert_eq!(
            ReadWriteContext::from_str("assignment"),
            ReadWriteContext::Assignment
        );
        assert_eq!(
            ReadWriteContext::from_str("RETURN"),
            ReadWriteContext::Return
        );
        assert_eq!(
            ReadWriteContext::from_str("unknown"),
            ReadWriteContext::Other
        );
    }

    #[test]
    fn test_control_flow_context() {
        assert_eq!(ControlFlowContext::Sequential.as_str(), "sequential");
        assert_eq!(ControlFlowContext::TrueBranch.as_str(), "true_branch");
    }

    #[test]
    fn test_serde() {
        let ctx = ReadWriteContext::Assignment;
        let json = serde_json::to_string(&ctx).unwrap();
        assert_eq!(json, r#""Assignment""#);

        let parsed: ReadWriteContext = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed, ReadWriteContext::Assignment);
    }
}
