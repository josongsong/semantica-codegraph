//! Unified File Processor

use crate::pipeline::preprocessors::TemplatePreprocessor;
use crate::pipeline::processor::{
    process_file as process_code_file, process_python_file, ProcessResult,
};
use crate::shared::models::Result;

pub fn process_any_file(
    file_path: &str,
    source_code: &str,
    repo_id: &str,
) -> Result<ProcessResult> {
    if TemplatePreprocessor::is_template_file(file_path) {
        Ok(Default::default())
    } else if TemplatePreprocessor::is_document_file(file_path) {
        Ok(Default::default())
    } else if file_path.ends_with(".py") {
        Ok(process_python_file(
            source_code,
            repo_id,
            file_path,
            file_path,
        ))
    } else {
        Ok(process_code_file(
            source_code,
            repo_id,
            file_path,
            file_path,
        ))
    }
}

pub fn get_file_category(file_path: &str) -> FileCategory {
    if TemplatePreprocessor::is_template_file(file_path) {
        FileCategory::Template
    } else if TemplatePreprocessor::is_document_file(file_path) {
        FileCategory::Document
    } else if is_code_file(file_path) {
        FileCategory::Code
    } else {
        FileCategory::Unknown
    }
}

fn is_code_file(file_path: &str) -> bool {
    file_path.ends_with(".py")
        || file_path.ends_with(".java")
        || file_path.ends_with(".kt")
        || file_path.ends_with(".rs")
        || file_path.ends_with(".go")
        || file_path.ends_with(".ts")
        || file_path.ends_with(".js")
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FileCategory {
    Code,
    Template,
    Document,
    Unknown,
}
