//! Template Parser - PyO3 Bridge to Python Parsers
//!
//! SOTA 2025: Zero-copy bridge to Python template parsers
//!
//! This module provides a Rust interface to Python template/document parsers.
//! Only available with the "python" feature flag.

#[cfg(feature = "python")]
mod python_impl {
    use pyo3::prelude::*;
    use pyo3::types::{PyDict, PyModule};
    use pythonize::depythonize;
    use std::collections::HashMap;
    use std::sync::{Arc, Mutex};

    use crate::shared::models::{CodegraphError, ParsedDocument, Result, TemplateDoc};

    /// Template preprocessor - bridges to Python parsers
    pub struct TemplatePreprocessor {
        parsers_module: Arc<Mutex<Option<Py<PyModule>>>>,
    }

    impl TemplatePreprocessor {
        pub fn new() -> Self {
            Self {
                parsers_module: Arc::new(Mutex::new(None)),
            }
        }

        pub fn parse_template(&self, file_path: &str, source: &str) -> Result<TemplateDoc> {
            Python::with_gil(|py| {
                let parsers = self.get_parsers_module(py)?;
                let parser = self.get_template_parser(&parsers, file_path)?;
                let result = parser
                    .call_method1("parse", (source, file_path, py.None()))
                    .map_err(|e| {
                        CodegraphError::parse(format!("Python template parser failed: {}", e))
                    })?;
                self.convert_template_doc(result)
            })
        }

        pub fn parse_document(&self, file_path: &str, source: &str) -> Result<ParsedDocument> {
            Python::with_gil(|py| {
                let parsers = self.get_parsers_module(py)?;
                let parser = self.get_document_parser(&parsers, file_path)?;
                let path_obj = py.import("pathlib")?.getattr("Path")?.call1((file_path,))?;
                let result = parser
                    .call_method1("parse", (path_obj, source))
                    .map_err(|e| {
                        CodegraphError::parse(format!("Python document parser failed: {}", e))
                    })?;
                self.convert_parsed_document(result)
            })
        }

        pub fn is_template_file(file_path: &str) -> bool {
            file_path.ends_with(".jsx")
                || file_path.ends_with(".tsx")
                || file_path.ends_with(".vue")
        }

        pub fn is_document_file(file_path: &str) -> bool {
            file_path.ends_with(".md")
                || file_path.ends_with(".markdown")
                || file_path.ends_with(".mdx")
                || file_path.ends_with(".ipynb")
                || file_path.ends_with(".rst")
                || file_path.ends_with(".txt")
                || file_path.ends_with(".pdf")
        }

        fn get_parsers_module<'py>(&self, py: Python<'py>) -> PyResult<&'py PyModule> {
            // Use independent codegraph-parsers package (not legacy codegraph-engine)
            py.import("codegraph_parsers")
        }

        fn get_template_parser<'py>(
            &self,
            parsers: &'py PyModule,
            file_path: &str,
        ) -> PyResult<&'py PyAny> {
            let parser_class = if file_path.ends_with(".jsx") || file_path.ends_with(".tsx") {
                parsers.getattr("JSXTemplateParser")?
            } else if file_path.ends_with(".vue") {
                parsers.getattr("VueSFCParser")?
            } else {
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "Unsupported template file: {}",
                    file_path
                )));
            };
            parser_class.call0()
        }

        fn get_document_parser<'py>(
            &self,
            parsers: &'py PyModule,
            file_path: &str,
        ) -> PyResult<&'py PyAny> {
            let parser_class = if file_path.ends_with(".md")
                || file_path.ends_with(".markdown")
                || file_path.ends_with(".mdx")
            {
                parsers.getattr("MarkdownParser")?
            } else if file_path.ends_with(".ipynb") {
                parsers.getattr("NotebookParser")?
            } else if file_path.ends_with(".rst") || file_path.ends_with(".rest") {
                parsers.getattr("RstParser")?
            } else if file_path.ends_with(".txt") {
                parsers.getattr("TextParser")?
            } else {
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "Unsupported document file: {}",
                    file_path
                )));
            };
            parser_class.call0()
        }

        fn convert_template_doc(&self, py_doc: &PyAny) -> Result<TemplateDoc> {
            let py_dict = py_doc
                .call_method0("to_dict")
                .or_else(|_| {
                    let py = py_doc.py();
                    let dict = PyDict::new(py);
                    dict.set_item("doc_id", py_doc.getattr("doc_id")?)?;
                    dict.set_item("engine", py_doc.getattr("engine")?)?;
                    dict.set_item("file_path", py_doc.getattr("file_path")?)?;
                    dict.set_item("root_element_ids", py_doc.getattr("root_element_ids")?)?;
                    dict.set_item("slots", py_doc.getattr("slots")?)?;
                    dict.set_item("elements", py_doc.getattr("elements")?)?;
                    dict.set_item("is_partial", py_doc.getattr("is_partial")?)?;
                    dict.set_item("is_virtual", py_doc.getattr("is_virtual")?)?;
                    dict.set_item(
                        "attrs",
                        py_doc.getattr("attrs").unwrap_or(PyDict::new(py).into()),
                    )?;
                    Ok(dict.into())
                })
                .map_err(|e: PyErr| {
                    CodegraphError::parse(format!("Failed to get template doc dict: {}", e))
                })?;

            let doc_dict: HashMap<String, serde_json::Value> =
                depythonize(py_dict).map_err(|e| {
                    CodegraphError::parse(format!("Failed to depythonize template doc: {}", e))
                })?;

            TemplateDoc::from_python_dict(doc_dict).map_err(|e| CodegraphError::parse(e))
        }

        fn convert_parsed_document(&self, py_doc: &PyAny) -> Result<ParsedDocument> {
            let py_dict = py_doc
                .call_method0("to_dict")
                .or_else(|_| {
                    let py = py_doc.py();
                    let dict = PyDict::new(py);
                    dict.set_item("file_path", py_doc.getattr("file_path")?)?;
                    dict.set_item("doc_type", py_doc.getattr("doc_type")?)?;
                    dict.set_item("raw_content", py_doc.getattr("raw_content")?)?;
                    dict.set_item("sections", py_doc.getattr("sections")?)?;
                    dict.set_item("code_blocks", py_doc.getattr("code_blocks")?)?;
                    dict.set_item("metadata", py_doc.getattr("metadata")?)?;
                    Ok(dict.into())
                })
                .map_err(|e: PyErr| {
                    CodegraphError::parse(format!("Failed to get document dict: {}", e))
                })?;

            let doc_dict: HashMap<String, serde_json::Value> =
                depythonize(py_dict).map_err(|e| {
                    CodegraphError::parse(format!("Failed to depythonize document: {}", e))
                })?;

            ParsedDocument::from_python_dict(doc_dict).map_err(|e| CodegraphError::parse(e))
        }
    }

    impl Default for TemplatePreprocessor {
        fn default() -> Self {
            Self::new()
        }
    }

    use lazy_static::lazy_static;

    lazy_static! {
        static ref TEMPLATE_PREPROCESSOR: TemplatePreprocessor = TemplatePreprocessor::new();
    }

    pub fn get_template_preprocessor() -> &'static TemplatePreprocessor {
        &TEMPLATE_PREPROCESSOR
    }
}

#[cfg(feature = "python")]
pub use python_impl::*;

// Stub implementation when python feature is disabled
#[cfg(not(feature = "python"))]
pub mod stub {
    use crate::shared::models::{CodegraphError, ParsedDocument, Result, TemplateDoc};

    pub struct TemplatePreprocessor;

    impl TemplatePreprocessor {
        pub fn new() -> Self {
            Self
        }

        pub fn parse_template(&self, _file_path: &str, _source: &str) -> Result<TemplateDoc> {
            Err(CodegraphError::parse(
                "Template parsing requires 'python' feature".to_string(),
            ))
        }

        pub fn parse_document(&self, _file_path: &str, _source: &str) -> Result<ParsedDocument> {
            Err(CodegraphError::parse(
                "Document parsing requires 'python' feature".to_string(),
            ))
        }

        pub fn is_template_file(file_path: &str) -> bool {
            file_path.ends_with(".jsx")
                || file_path.ends_with(".tsx")
                || file_path.ends_with(".vue")
        }

        pub fn is_document_file(file_path: &str) -> bool {
            file_path.ends_with(".md")
                || file_path.ends_with(".markdown")
                || file_path.ends_with(".mdx")
                || file_path.ends_with(".ipynb")
                || file_path.ends_with(".rst")
                || file_path.ends_with(".txt")
                || file_path.ends_with(".pdf")
        }
    }

    impl Default for TemplatePreprocessor {
        fn default() -> Self {
            Self::new()
        }
    }

    pub fn get_template_preprocessor() -> &'static TemplatePreprocessor {
        static PREPROCESSOR: TemplatePreprocessor = TemplatePreprocessor;
        &PREPROCESSOR
    }
}

#[cfg(not(feature = "python"))]
pub use stub::*;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_file_type_detection() {
        assert!(TemplatePreprocessor::is_template_file("App.tsx"));
        assert!(TemplatePreprocessor::is_template_file("component.jsx"));
        assert!(TemplatePreprocessor::is_template_file("Home.vue"));
        assert!(!TemplatePreprocessor::is_template_file("main.py"));

        assert!(TemplatePreprocessor::is_document_file("README.md"));
        assert!(TemplatePreprocessor::is_document_file("notebook.ipynb"));
        assert!(!TemplatePreprocessor::is_document_file("main.py"));
    }
}
