//! Taint Path - Tracks taint flow across functions
//!
//! Example: get_input() -> process(x) -> execute(x)
//!          [Source]   -> [Propagation] -> [Sink]

use serde::{Deserialize, Serialize};

/// Taint propagation path across functions
///
/// Represents a complete path from source to sink through intermediate functions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaintPath {
    /// Source function/location
    pub source: String,

    /// Sink function/location
    pub sink: String,

    /// Intermediate functions
    pub path: Vec<String>,

    /// Tainted value/variable name
    pub taint_value: Option<String>,

    /// Path constraints for SMT verification
    pub path_condition: Option<Vec<String>>,

    /// Confidence score (0.0-1.0)
    pub confidence: f64,
}

impl TaintPath {
    /// Create new taint path
    pub fn new(source: String, sink: String) -> Self {
        Self {
            source,
            sink,
            path: Vec::new(),
            taint_value: None,
            path_condition: None,
            confidence: 1.0,
        }
    }

    /// Add intermediate function to path
    pub fn add_intermediate(&mut self, func: String) {
        self.path.push(func);
    }

    /// Set tainted value
    pub fn with_value(mut self, value: String) -> Self {
        self.taint_value = Some(value);
        self
    }

    /// Set confidence score
    pub fn with_confidence(mut self, confidence: f64) -> Self {
        self.confidence = confidence;
        self
    }
}
