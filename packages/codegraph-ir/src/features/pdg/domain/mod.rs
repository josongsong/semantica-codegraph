//! PDG (Program Dependence Graph) domain models
//!
//! Combines control flow and data flow dependencies.

/// PDG result summary (for Python serialization)
#[derive(Debug, Clone)]
pub struct PDGResult {
    pub function_id: String,
    pub node_count: usize,
    pub control_edges: usize,
    pub data_edges: usize,
}

impl PDGResult {
    pub fn new(
        function_id: String,
        node_count: usize,
        control_edges: usize,
        data_edges: usize,
    ) -> Self {
        Self {
            function_id,
            node_count,
            control_edges,
            data_edges,
        }
    }
}
