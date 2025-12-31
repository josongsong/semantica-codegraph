//! IR Document - the main output of IR generation
use crate::shared::models::{Edge, Node};

#[derive(Debug, Clone, Default)]
pub struct IRDocument {
    pub file_path: String,
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
}

impl IRDocument {
    pub fn new(file_path: String) -> Self {
        Self {
            file_path,
            nodes: Vec::new(),
            edges: Vec::new(),
        }
    }
}
