//! PyO3 Bindings for Clone Detection
//!
//! Exposes all 4 clone detector types to Python:
//! - Type-1: Exact clones (string hashing)
//! - Type-2: Renamed clones (AST normalization)
//! - Type-3: Gapped clones (PDG + edit distance)
//! - Type-4: Semantic clones (graph isomorphism)
//!
//! # Python API
//!
//! ```python
//! import codegraph_ir
//!
//! # Detect all clone types
//! fragments = [
//!     {"file_path": "file1.py", "start_line": 1, "end_line": 5, "content": "...", "token_count": 50, "loc": 4},
//!     {"file_path": "file2.py", "start_line": 10, "end_line": 15, "content": "...", "token_count": 50, "loc": 4},
//! ]
//!
//! # Detect all clone types
//! result = codegraph_ir.detect_clones_all(fragments)
//!
//! # Detect specific clone type
//! result = codegraph_ir.detect_clones_type1(fragments)
//! result = codegraph_ir.detect_clones_type2(fragments)
//! result = codegraph_ir.detect_clones_type3(fragments)
//! result = codegraph_ir.detect_clones_type4(fragments)
//! ```

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde::{Deserialize, Serialize};

use crate::features::clone_detection::{
    CodeFragment, CloneDetector, Type1Detector, Type2Detector, Type3Detector, Type4Detector,
    MultiLevelDetector, CloneType,
};
use crate::shared::models::Span;

/// Python-compatible code fragment input
#[derive(Debug, Clone, Deserialize)]
struct PyCodeFragment {
    file_path: String,
    start_line: u32,
    start_col: u32,
    end_line: u32,
    end_col: u32,
    content: String,
    token_count: usize,
    loc: usize,
}

impl From<PyCodeFragment> for CodeFragment {
    fn from(py_frag: PyCodeFragment) -> Self {
        CodeFragment::new(
            py_frag.file_path,
            Span::new(py_frag.start_line, py_frag.start_col, py_frag.end_line, py_frag.end_col),
            py_frag.content,
            py_frag.token_count,
            py_frag.loc,
        )
    }
}

/// Python-compatible clone pair output
#[derive(Debug, Clone, Serialize)]
struct PyClonePair {
    clone_type: String,
    source_file: String,
    source_start_line: u32,
    source_end_line: u32,
    target_file: String,
    target_start_line: u32,
    target_end_line: u32,
    similarity: f64,
    token_count: usize,
    loc: usize,
    confidence: Option<f64>,
    detection_method: String,
    detection_time_ms: Option<u64>,
    // Metrics
    edit_distance: Option<usize>,
    normalized_edit_distance: Option<f64>,
    gap_count: Option<usize>,
    gap_size: Option<usize>,
    semantic_similarity: Option<f64>,
}

impl From<crate::features::clone_detection::domain::ClonePair> for PyClonePair {
    fn from(pair: crate::features::clone_detection::domain::ClonePair) -> Self {
        PyClonePair {
            clone_type: match pair.clone_type {
                CloneType::Type1 => "Type-1".to_string(),
                CloneType::Type2 => "Type-2".to_string(),
                CloneType::Type3 => "Type-3".to_string(),
                CloneType::Type4 => "Type-4".to_string(),
            },
            source_file: pair.source.file_path.clone(),
            source_start_line: pair.source.span.start_line,
            source_end_line: pair.source.span.end_line,
            target_file: pair.target.file_path.clone(),
            target_start_line: pair.target.span.start_line,
            target_end_line: pair.target.span.end_line,
            similarity: pair.similarity,
            token_count: pair.metrics.clone_length_tokens,
            loc: pair.metrics.clone_length_loc,
            confidence: pair.detection_info.confidence,
            detection_method: pair.detection_info.algorithm.clone(),
            detection_time_ms: pair.detection_info.detection_time_ms,
            edit_distance: pair.metrics.edit_distance,
            normalized_edit_distance: pair.metrics.normalized_edit_distance,
            gap_count: pair.metrics.gap_count,
            gap_size: pair.metrics.gap_size,
            semantic_similarity: pair.metrics.semantic_similarity,
        }
    }
}

/// Convert Python list to Rust CodeFragment vector
fn parse_fragments(py: Python, fragments: &PyList) -> PyResult<Vec<CodeFragment>> {
    let mut result = Vec::with_capacity(fragments.len());

    for item in fragments.iter() {
        let dict = item.downcast::<PyDict>()?;

        let file_path = dict.get_item("file_path")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Missing 'file_path'"))?
            .extract::<String>()?;

        let start_line = dict.get_item("start_line")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Missing 'start_line'"))?
            .extract::<u32>()?;

        let start_col = dict.get_item("start_col")
            .ok()
            .and_then(|opt| opt)
            .and_then(|v| v.extract::<u32>().ok())
            .unwrap_or(0);

        let end_line = dict.get_item("end_line")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Missing 'end_line'"))?
            .extract::<u32>()?;

        let end_col = dict.get_item("end_col")
            .ok()
            .and_then(|opt| opt)
            .and_then(|v| v.extract::<u32>().ok())
            .unwrap_or(0);

        let content = dict.get_item("content")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Missing 'content'"))?
            .extract::<String>()?;

        let token_count = dict.get_item("token_count")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Missing 'token_count'"))?
            .extract::<usize>()?;

        let loc = dict.get_item("loc")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Missing 'loc'"))?
            .extract::<usize>()?;

        result.push(CodeFragment::new(
            file_path,
            Span::new(start_line, start_col, end_line, end_col),
            content,
            token_count,
            loc,
        ));
    }

    Ok(result)
}

/// Convert clone pairs to Python dict list
fn pairs_to_py_list(py: Python, pairs: Vec<crate::features::clone_detection::domain::ClonePair>) -> PyResult<Py<PyList>> {
    let py_pairs: Vec<PyClonePair> = pairs.into_iter().map(PyClonePair::from).collect();
    let list = PyList::empty(py);

    for pair in py_pairs {
        let dict = PyDict::new(py);
        dict.set_item("clone_type", pair.clone_type)?;
        dict.set_item("source_file", pair.source_file)?;
        dict.set_item("source_start_line", pair.source_start_line)?;
        dict.set_item("source_end_line", pair.source_end_line)?;
        dict.set_item("target_file", pair.target_file)?;
        dict.set_item("target_start_line", pair.target_start_line)?;
        dict.set_item("target_end_line", pair.target_end_line)?;
        dict.set_item("similarity", pair.similarity)?;
        dict.set_item("token_count", pair.token_count)?;
        dict.set_item("loc", pair.loc)?;
        dict.set_item("detection_method", pair.detection_method)?;

        if let Some(confidence) = pair.confidence {
            dict.set_item("confidence", confidence)?;
        }
        if let Some(time) = pair.detection_time_ms {
            dict.set_item("detection_time_ms", time)?;
        }
        if let Some(dist) = pair.edit_distance {
            dict.set_item("edit_distance", dist)?;
        }
        if let Some(norm_dist) = pair.normalized_edit_distance {
            dict.set_item("normalized_edit_distance", norm_dist)?;
        }
        if let Some(gap_count) = pair.gap_count {
            dict.set_item("gap_count", gap_count)?;
        }
        if let Some(gap_size) = pair.gap_size {
            dict.set_item("gap_size", gap_size)?;
        }
        if let Some(sem_sim) = pair.semantic_similarity {
            dict.set_item("semantic_similarity", sem_sim)?;
        }

        list.append(dict)?;
    }

    Ok(list.into())
}

/// Detect all clone types (Type-1 through Type-4)
///
/// # Arguments
/// * `fragments` - List of code fragments (dicts with file_path, start_line, end_line, content, token_count, loc)
///
/// # Returns
/// List of clone pairs with metadata
///
/// # Example
/// ```python
/// fragments = [
///     {"file_path": "file1.py", "start_line": 1, "end_line": 5, "content": "def foo(): return 42", "token_count": 50, "loc": 1},
///     {"file_path": "file2.py", "start_line": 10, "end_line": 15, "content": "def foo(): return 42", "token_count": 50, "loc": 1},
/// ]
/// pairs = codegraph_ir.detect_clones_all(fragments)
/// ```
#[pyfunction]
#[pyo3(name = "detect_clones_all")]
pub fn detect_clones_all_py(py: Python, fragments: &PyList) -> PyResult<Py<PyList>> {
    let fragments = parse_fragments(py, fragments)?;

    let pairs = py.allow_threads(|| {
        let detector = MultiLevelDetector::new();
        detector.detect_all(&fragments)
    });

    pairs_to_py_list(py, pairs)
}

/// Detect Type-1 clones (exact clones)
///
/// # Arguments
/// * `fragments` - List of code fragments
/// * `min_tokens` - Minimum token threshold (default: 50)
/// * `min_loc` - Minimum LOC threshold (default: 6)
///
/// # Returns
/// List of Type-1 clone pairs
#[pyfunction]
#[pyo3(name = "detect_clones_type1", signature = (fragments, min_tokens=50, min_loc=6))]
pub fn detect_clones_type1_py(
    py: Python,
    fragments: &PyList,
    min_tokens: usize,
    min_loc: usize,
) -> PyResult<Py<PyList>> {
    let fragments = parse_fragments(py, fragments)?;

    let pairs = py.allow_threads(|| {
        let detector = Type1Detector::with_thresholds(min_tokens, min_loc);
        detector.detect(&fragments)
    });

    pairs_to_py_list(py, pairs)
}

/// Detect Type-2 clones (renamed clones)
///
/// # Arguments
/// * `fragments` - List of code fragments
/// * `min_tokens` - Minimum token threshold (default: 50)
/// * `min_loc` - Minimum LOC threshold (default: 6)
/// * `min_similarity` - Minimum similarity threshold (default: 0.95)
///
/// # Returns
/// List of Type-2 clone pairs
#[pyfunction]
#[pyo3(name = "detect_clones_type2", signature = (fragments, min_tokens=50, min_loc=6, min_similarity=0.95))]
pub fn detect_clones_type2_py(
    py: Python,
    fragments: &PyList,
    min_tokens: usize,
    min_loc: usize,
    min_similarity: f64,
) -> PyResult<Py<PyList>> {
    let fragments = parse_fragments(py, fragments)?;

    let pairs = py.allow_threads(|| {
        let detector = Type2Detector::with_thresholds(min_tokens, min_loc, min_similarity);
        detector.detect(&fragments)
    });

    pairs_to_py_list(py, pairs)
}

/// Detect Type-3 clones (gapped clones)
///
/// # Arguments
/// * `fragments` - List of code fragments
/// * `min_tokens` - Minimum token threshold (default: 30)
/// * `min_loc` - Minimum LOC threshold (default: 4)
/// * `min_similarity` - Minimum similarity threshold (default: 0.7)
/// * `max_gap_ratio` - Maximum gap ratio (default: 0.3)
///
/// # Returns
/// List of Type-3 clone pairs
#[pyfunction]
#[pyo3(name = "detect_clones_type3", signature = (fragments, min_tokens=30, min_loc=4, min_similarity=0.7, max_gap_ratio=0.3))]
pub fn detect_clones_type3_py(
    py: Python,
    fragments: &PyList,
    min_tokens: usize,
    min_loc: usize,
    min_similarity: f64,
    max_gap_ratio: f64,
) -> PyResult<Py<PyList>> {
    let fragments = parse_fragments(py, fragments)?;

    let pairs = py.allow_threads(|| {
        let detector = Type3Detector::with_thresholds(min_tokens, min_loc, min_similarity, max_gap_ratio);
        detector.detect(&fragments)
    });

    pairs_to_py_list(py, pairs)
}

/// Detect Type-4 clones (semantic clones)
///
/// # Arguments
/// * `fragments` - List of code fragments
/// * `min_tokens` - Minimum token threshold (default: 20)
/// * `min_loc` - Minimum LOC threshold (default: 3)
/// * `min_similarity` - Minimum similarity threshold (default: 0.6)
/// * `node_weight` - Weight for node similarity (default: 0.4)
/// * `edge_weight` - Weight for edge similarity (default: 0.3)
/// * `pattern_weight` - Weight for pattern similarity (default: 0.3)
///
/// # Returns
/// List of Type-4 clone pairs
#[pyfunction]
#[pyo3(name = "detect_clones_type4", signature = (fragments, min_tokens=20, min_loc=3, min_similarity=0.6, node_weight=0.4, edge_weight=0.3, pattern_weight=0.3))]
pub fn detect_clones_type4_py(
    py: Python,
    fragments: &PyList,
    min_tokens: usize,
    min_loc: usize,
    min_similarity: f64,
    node_weight: f64,
    edge_weight: f64,
    pattern_weight: f64,
) -> PyResult<Py<PyList>> {
    let fragments = parse_fragments(py, fragments)?;

    let pairs = py.allow_threads(|| {
        let detector = Type4Detector::with_thresholds(
            min_tokens,
            min_loc,
            min_similarity,
            node_weight,
            edge_weight,
            pattern_weight,
        );
        detector.detect(&fragments)
    });

    pairs_to_py_list(py, pairs)
}

/// Detect clones within a specific file
///
/// # Arguments
/// * `fragments` - List of code fragments
/// * `file_path` - File path to analyze
/// * `clone_type` - Clone type to detect ("type1", "type2", "type3", "type4", or "all")
///
/// # Returns
/// List of clone pairs within the file
#[pyfunction]
#[pyo3(name = "detect_clones_in_file", signature = (fragments, file_path, clone_type="all"))]
pub fn detect_clones_in_file_py(
    py: Python,
    fragments: &PyList,
    file_path: &str,
    clone_type: &str,
) -> PyResult<Py<PyList>> {
    let fragments = parse_fragments(py, fragments)?;

    let pairs = py.allow_threads(|| {
        match clone_type {
            "type1" => {
                let detector = Type1Detector::new();
                detector.detect_in_file(&fragments, file_path)
            }
            "type2" => {
                let detector = Type2Detector::new();
                detector.detect_in_file(&fragments, file_path)
            }
            "type3" => {
                let detector = Type3Detector::new();
                detector.detect_in_file(&fragments, file_path)
            }
            "type4" => {
                let detector = Type4Detector::new();
                detector.detect_in_file(&fragments, file_path)
            }
            "all" => {
                let detector = MultiLevelDetector::new();
                let all_pairs = detector.detect_all(&fragments);
                all_pairs.into_iter()
                    .filter(|pair| {
                        pair.source.file_path == file_path && pair.target.file_path == file_path
                    })
                    .collect()
            }
            _ => Vec::new(),
        }
    });

    pairs_to_py_list(py, pairs)
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyo3::types::IntoPyDict;

    #[test]
    fn test_py_code_fragment_conversion() {
        let py_frag = PyCodeFragment {
            file_path: "test.py".to_string(),
            start_line: 1,
            start_col: 0,
            end_line: 5,
            end_col: 0,
            content: "def foo(): pass".to_string(),
            token_count: 50,
            loc: 1,
        };

        let frag: CodeFragment = py_frag.into();
        assert_eq!(frag.file_path, "test.py");
        assert_eq!(frag.span.start_line, 1);
        assert_eq!(frag.token_count, 50);
    }

    #[test]
    fn test_detect_type1_basic() {
        pyo3::prepare_freethreaded_python();

        Python::with_gil(|py| {
            let fragments = PyList::new(
                py,
                &[
                    [
                        ("file_path", "file1.py"),
                        ("start_line", "1"),
                        ("end_line", "2"),
                        ("content", "def foo(): return 42"),
                        ("token_count", "50"),
                        ("loc", "1"),
                    ]
                    .into_py_dict(py),
                    [
                        ("file_path", "file2.py"),
                        ("start_line", "10"),
                        ("end_line", "11"),
                        ("content", "def foo(): return 42"),
                        ("token_count", "50"),
                        ("loc", "1"),
                    ]
                    .into_py_dict(py),
                ],
            );

            let result = detect_clones_type1_py(py, fragments, 10, 1);
            assert!(result.is_ok());

            let pairs = result.unwrap();
            let pairs_ref = pairs.as_ref(py);
            assert!(pairs_ref.len() > 0);
        });
    }
}
