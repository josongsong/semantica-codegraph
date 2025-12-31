/*
 * Application: IR Processor Implementation
 *
 * Implements IrProcessor port from domain
 */

use crate::domain::models::{ProcessResult, SourceFile, ProcessingContext};
use crate::domain::ports::{IrProcessor, AstParser};
use crate::application::ir_builder::IRBuilder;
use rayon::prelude::*;

/// Default IR Processor implementation
pub struct DefaultIrProcessor<P: AstParser> {
    parser: P,
}

impl<P: AstParser> DefaultIrProcessor<P> {
    pub fn new(parser: P) -> Self {
        Self { parser }
    }
}

impl<P: AstParser> IrProcessor for DefaultIrProcessor<P> {
    fn process_file(
        &self,
        file: &SourceFile,
        context: &ProcessingContext,
    ) -> ProcessResult {
        // Parse AST
        let tree = match self.parser.parse(&file.content) {
            Ok(t) => t,
            Err(e) => return ProcessResult::with_error(e),
        };
        
        // Create IR builder
        let mut builder = IRBuilder::new(
            context.repo_id.clone(),
            file.path.clone(),
            context.language.clone(),
            file.module_path.clone(),
        );
        
        // Process AST
        let mut errors = Vec::new();
        let root = tree.root_node();
        process_node(&*root, &file.content, &mut builder, &mut errors);
        
        // Build result
        let (nodes, edges) = builder.build();
        
        ProcessResult {
            nodes,
            edges,
            errors,
        }
    }
    
    fn process_files(
        &self,
        files: Vec<SourceFile>,
        context: &ProcessingContext,
    ) -> Vec<ProcessResult> {
        // Parallel processing with Rayon
        files.par_iter()
            .map(|file| self.process_file(file, context))
            .collect()
    }
}

/// Process AST node recursively
fn process_node(
    node: &dyn crate::domain::ports::AstNode,
    source: &str,
    builder: &mut IRBuilder,
    errors: &mut Vec<String>,
) {
    match node.kind() {
        "function_definition" => {
            if let Err(e) = process_function(node, source, builder, false) {
                errors.push(e);
            }
        }
        
        "class_definition" => {
            if let Err(e) = process_class(node, source, builder) {
                errors.push(e);
            }
        }
        
        _ => {
            // Continue traversal
            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    process_node(&*child, source, builder, errors);
                }
            }
        }
    }
}

/// Process function node
fn process_function(
    node: &dyn crate::domain::ports::AstNode,
    source: &str,
    builder: &mut IRBuilder,
    is_method: bool,
) -> Result<(), String> {
    use crate::shared::models::Span;
    
    // Extract name
    let mut name = None;
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "identifier" {
                let start = child.start_byte();
                let end = child.end_byte();
                name = Some(source[start..end].to_string());
                break;
            }
        }
    }
    
    let name = name.ok_or_else(|| "Function name not found".to_string())?;
    
    // Extract span
    let span = Span::new(
        node.start_line(),
        node.start_column(),
        node.end_line(),
        node.end_column(),
    );
    
    // Extract source text
    let start = node.start_byte();
    let end = node.end_byte();
    let source_text = &source[start..end];
    
    // Extract docstring (simplified)
    let docstring = extract_docstring(node, source);
    
    // Create node
    builder.create_function_node(
        name,
        span,
        None,
        is_method,
        docstring,
        source_text,
        None, // return_type_annotation - TODO: extract from AST
    )?;
    
    builder.finish_scope();
    
    Ok(())
}

/// Process class node
fn process_class(
    node: &dyn crate::domain::ports::AstNode,
    source: &str,
    builder: &mut IRBuilder,
) -> Result<(), String> {
    use crate::shared::models::Span;
    
    // Extract name
    let mut name = None;
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "identifier" {
                let start = child.start_byte();
                let end = child.end_byte();
                name = Some(source[start..end].to_string());
                break;
            }
        }
    }
    
    let name = name.ok_or_else(|| "Class name not found".to_string())?;
    
    // Extract span
    let span = Span::new(
        node.start_line(),
        node.start_column(),
        node.end_line(),
        node.end_column(),
    );
    
    // Extract source text
    let start = node.start_byte();
    let end = node.end_byte();
    let source_text = &source[start..end];
    
    // Extract base classes (simplified)
    let base_classes = extract_base_classes(node, source);
    
    // Extract docstring
    let docstring = extract_docstring(node, source);
    
    // Create node
    builder.create_class_node(
        name,
        span,
        None,
        base_classes,
        docstring,
        source_text,
    )?;
    
    // Process class body
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "block" {
                for j in 0..child.child_count() {
                    if let Some(stmt) = child.child(j) {
                        match stmt.kind() {
                            "function_definition" => {
                                if let Err(e) = process_function(&*stmt, source, builder, true) {
                                    eprintln!("Error processing method: {}", e);
                                }
                            }
                            "class_definition" => {
                                if let Err(e) = process_class(&*stmt, source, builder) {
                                    eprintln!("Error processing nested class: {}", e);
                                }
                            }
                            "decorated_definition" => {
                                for k in 0..stmt.child_count() {
                                    if let Some(decorated) = stmt.child(k) {
                                        match decorated.kind() {
                                            "function_definition" => {
                                                if let Err(e) = process_function(&*decorated, source, builder, true) {
                                                    eprintln!("Error processing decorated method: {}", e);
                                                }
                                            }
                                            "class_definition" => {
                                                if let Err(e) = process_class(&*decorated, source, builder) {
                                                    eprintln!("Error processing decorated nested class: {}", e);
                                                }
                                            }
                                            _ => {}
                                        }
                                    }
                                }
                            }
                            _ => {}
                        }
                    }
                }
            }
        }
    }
    
    builder.finish_scope();
    
    Ok(())
}

/// Extract docstring from node
fn extract_docstring(node: &dyn crate::domain::ports::AstNode, source: &str) -> Option<String> {
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "block" {
                for j in 0..child.child_count() {
                    if let Some(stmt) = child.child(j) {
                        if stmt.kind() == "expression_statement" {
                            if let Some(string_node) = stmt.child(0) {
                                if string_node.kind() == "string" {
                                    let start = string_node.start_byte();
                                    let end = string_node.end_byte();
                                    let raw = &source[start..end];
                                    let trimmed = raw.trim_start_matches('"')
                                        .trim_end_matches('"')
                                        .trim_start_matches('\'')
                                        .trim_end_matches('\'');
                                    return Some(trimmed.to_string());
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    None
}

/// Extract base classes
fn extract_base_classes(node: &dyn crate::domain::ports::AstNode, source: &str) -> Vec<String> {
    let mut bases = Vec::new();
    
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "argument_list" {
                for j in 0..child.child_count() {
                    if let Some(base) = child.child(j) {
                        if base.kind() == "identifier" {
                            let start = base.start_byte();
                            let end = base.end_byte();
                            bases.push(source[start..end].to_string());
                        }
                    }
                }
            }
        }
    }
    
    bases
}

