/*
 * Domain Ports - Interfaces for external dependencies
 *
 * HEXAGONAL ARCHITECTURE:
 * - Domain defines interfaces
 * - Infrastructure implements them
 * - Dependency Inversion Principle
 */

use super::models::{ProcessResult, SourceFile, ProcessingContext};

/// Port: AST Parser (driven port)
///
/// Infrastructure will implement this with tree-sitter
pub trait AstParser: Send + Sync {
    fn parse(&self, content: &str) -> Result<Box<dyn AstTree>, String>;
}

/// AST Tree abstraction
pub trait AstTree {
    fn root_node(&self) -> Box<dyn AstNode>;
}

/// AST Node abstraction
pub trait AstNode {
    fn kind(&self) -> &str;
    fn child_count(&self) -> usize;
    fn child(&self, index: usize) -> Option<Box<dyn AstNode>>;
    fn start_byte(&self) -> usize;
    fn end_byte(&self) -> usize;
    fn start_line(&self) -> u32;
    fn start_column(&self) -> u32;
    fn end_line(&self) -> u32;
    fn end_column(&self) -> u32;
}

/// Port: IR Processor (driving port)
///
/// Application layer implements this
pub trait IrProcessor: Send + Sync {
    fn process_file(
        &self,
        file: &SourceFile,
        context: &ProcessingContext,
    ) -> ProcessResult;
    
    fn process_files(
        &self,
        files: Vec<SourceFile>,
        context: &ProcessingContext,
    ) -> Vec<ProcessResult>;
}

