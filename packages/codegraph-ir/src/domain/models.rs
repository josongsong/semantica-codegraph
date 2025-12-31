/*
 * Domain Models - Core entities
 *
 * Pure Rust types, no external dependencies
 */

use crate::shared::models::{Node, Edge, Span};

/// Processing result (domain model)
#[derive(Debug, Clone)]
pub struct ProcessResult {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub errors: Vec<String>,
}

impl ProcessResult {
    pub fn new() -> Self {
        Self {
            nodes: Vec::new(),
            edges: Vec::new(),
            errors: Vec::new(),
        }
    }
    
    pub fn with_error(error: String) -> Self {
        Self {
            nodes: Vec::new(),
            edges: Vec::new(),
            errors: vec![error],
        }
    }
    
    pub fn is_success(&self) -> bool {
        self.errors.is_empty()
    }
}

/// File to process (domain model)
#[derive(Debug, Clone)]
pub struct SourceFile {
    pub path: String,
    pub content: String,
    pub module_path: String,
}

impl SourceFile {
    pub fn new(path: String, content: String, module_path: String) -> Self {
        Self {
            path,
            content,
            module_path,
        }
    }
}

/// Processing context (domain model)
#[derive(Debug, Clone)]
pub struct ProcessingContext {
    pub repo_id: String,
    pub language: String,
}

impl ProcessingContext {
    pub fn new(repo_id: String) -> Self {
        Self {
            repo_id,
            language: "python".to_string(),
        }
    }
}

