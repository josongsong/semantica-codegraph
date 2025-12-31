//! Source location types
//!
//! These types represent positions in source code.
//! PyO3-compatible for direct Python creation.

#[cfg(feature = "python")]
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

/// Single location in source code
#[allow(dead_code)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Location {
    pub line: u32,
    pub column: u32,
}

impl Location {
    pub fn new(line: u32, column: u32) -> Self {
        Self { line, column }
    }
}

/// Span in source code (matches Python Span)
///
/// PyO3-enabled: Can be created directly from Python
#[cfg_attr(feature = "python", pyclass(get_all, set_all))]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Span {
    pub start_line: u32,
    pub start_col: u32,
    pub end_line: u32,
    pub end_col: u32,
}

impl Span {
    /// Create a new Span (available in both Rust and Python)
    pub fn new(start_line: u32, start_col: u32, end_line: u32, end_col: u32) -> Self {
        Self {
            start_line,
            start_col,
            end_line,
            end_col,
        }
    }

    /// Create a zero span (0:0-0:0)
    pub fn zero() -> Self {
        Self::new(0, 0, 0, 0)
    }

    pub fn contains_line(&self, line: u32) -> bool {
        self.start_line <= line && line <= self.end_line
    }

    pub fn contains(&self, other: &Span) -> bool {
        self.start_line <= other.start_line && other.end_line <= self.end_line
    }

    pub fn line_count(&self) -> u32 {
        if self.end_line >= self.start_line {
            self.end_line - self.start_line + 1
        } else {
            0
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl Span {
    #[new]
    fn py_new(start_line: u32, start_col: u32, end_line: u32, end_col: u32) -> Self {
        Self::new(start_line, start_col, end_line, end_col)
    }

    #[staticmethod]
    fn py_zero() -> Self {
        Self::zero()
    }

    pub fn __repr__(&self) -> String {
        format!(
            "Span({}:{}-{}:{})",
            self.start_line, self.start_col, self.end_line, self.end_col
        )
    }
}

impl Default for Span {
    fn default() -> Self {
        Self::zero()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_span_contains_line() {
        let span = Span::new(10, 0, 20, 0);
        assert!(span.contains_line(10));
        assert!(span.contains_line(15));
        assert!(span.contains_line(20));
        assert!(!span.contains_line(9));
        assert!(!span.contains_line(21));
    }

    #[test]
    fn test_span_line_count() {
        let span = Span::new(10, 0, 20, 0);
        assert_eq!(span.line_count(), 11);
    }
}
