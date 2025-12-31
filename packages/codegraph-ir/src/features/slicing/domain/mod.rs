//! Program Slicing domain models
//!
//! Computes program slices for debugging and analysis.

/// Slice result summary (for Python serialization)
#[derive(Debug, Clone)]
pub struct SliceResult {
    pub function_id: String,
    pub criterion: String,
    pub slice_size: usize,
}

impl SliceResult {
    pub fn new(function_id: String, criterion: String, slice_size: usize) -> Self {
        Self {
            function_id,
            criterion,
            slice_size,
        }
    }
}
