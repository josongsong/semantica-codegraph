/// PyO3 bindings for concurrency analysis
///
/// **PRODUCTION IMPLEMENTATION**: Edge-based race detection with msgpack interface.
///
/// ## API
/// - `analyze_async_races_msgpack`: Single async function analysis (msgpack I/O)
/// - `analyze_all_async_races_msgpack`: Batch analysis (msgpack I/O)
///
/// ## Performance
/// - Zero-copy msgpack interface (RFC-062)
/// - GIL released during Rust processing
/// - ~100ms per async function target

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList};

#[cfg(feature = "python")]
use crate::features::concurrency_analysis::application::analyze_concurrency::IRDocumentConcurrencyExt;
#[cfg(feature = "python")]
use crate::features::concurrency_analysis::domain::{RaceCondition, RaceSeverity, RaceVerdict};
#[cfg(feature = "python")]
use crate::features::concurrency_analysis::infrastructure::async_race_detector::AsyncRaceDetector;
#[cfg(feature = "python")]
use crate::features::cross_file::IRDocument;

// ═══════════════════════════════════════════════════════════════════════════════
// Production API: Msgpack Interface (Zero-Copy, RFC-062)
// ═══════════════════════════════════════════════════════════════════════════════

/// Analyze async function for race conditions (msgpack interface)
///
/// # Arguments
/// * `ir_doc_msgpack` - IRDocument serialized as msgpack bytes
/// * `func_fqn` - Fully qualified function name
///
/// # Returns
/// Msgpack-serialized list of RaceCondition
#[cfg(feature = "python")]
#[pyo3::pyfunction]
pub fn analyze_async_races_msgpack(
    py: Python,
    ir_doc_msgpack: Vec<u8>,
    func_fqn: &str,
) -> PyResult<Vec<u8>> {
    // Deserialize IR document
    let ir_doc: IRDocument = py
        .allow_threads(|| {
            rmp_serde::from_slice(&ir_doc_msgpack)
                .map_err(|e| format!("Failed to deserialize IRDocument: {}", e))
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))?;

    // Run analysis (GIL released)
    let func_fqn_owned = func_fqn.to_string();
    let races: Vec<RaceCondition> = py.allow_threads(|| {
        let detector = AsyncRaceDetector::new();
        detector
            .analyze_async_function(&ir_doc, &func_fqn_owned)
            .unwrap_or_else(|_| vec![])
    });

    // Serialize result
    rmp_serde::to_vec(&races).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Serialize error: {}", e))
    })
}

/// Analyze all async functions in IRDocument (msgpack interface)
///
/// # Arguments
/// * `ir_doc_msgpack` - IRDocument serialized as msgpack bytes
///
/// # Returns
/// Msgpack-serialized dict with "races" and "summary"
#[cfg(feature = "python")]
#[pyo3::pyfunction]
pub fn analyze_all_async_races_msgpack(py: Python, ir_doc_msgpack: Vec<u8>) -> PyResult<Vec<u8>> {
    // Deserialize IR document
    let ir_doc: IRDocument = py
        .allow_threads(|| {
            rmp_serde::from_slice(&ir_doc_msgpack)
                .map_err(|e| format!("Failed to deserialize IRDocument: {}", e))
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))?;

    // Find all async functions and analyze (GIL released)
    let (all_races, summary) = py.allow_threads(|| {
        let detector = AsyncRaceDetector::new();
        let async_funcs = ir_doc.find_async_functions();

        let mut all_races = Vec::new();
        let mut critical = 0u32;
        let mut high = 0u32;
        let mut medium = 0u32;
        let mut low = 0u32;

        for func in async_funcs {
            if let Ok(races) = detector.analyze_async_function(&ir_doc, &func.id) {
                for race in &races {
                    match race.severity {
                        RaceSeverity::Critical => critical += 1,
                        RaceSeverity::High => high += 1,
                        RaceSeverity::Medium => medium += 1,
                        RaceSeverity::Low => low += 1,
                    }
                }
                all_races.extend(races);
            }
        }

        let summary = RaceAnalysisSummary {
            total_races: all_races.len() as u32,
            critical,
            high,
            medium,
            low,
        };

        (all_races, summary)
    });

    // Build result struct
    let result = RaceAnalysisResult {
        races: all_races,
        summary,
    };

    // Serialize result
    rmp_serde::to_vec(&result).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Serialize error: {}", e))
    })
}

/// Race analysis result for serialization
#[cfg(feature = "python")]
#[derive(serde::Serialize, serde::Deserialize)]
struct RaceAnalysisResult {
    races: Vec<RaceCondition>,
    summary: RaceAnalysisSummary,
}

/// Race analysis summary
#[cfg(feature = "python")]
#[derive(serde::Serialize, serde::Deserialize)]
struct RaceAnalysisSummary {
    total_races: u32,
    critical: u32,
    high: u32,
    medium: u32,
    low: u32,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Legacy API: PyObject Interface (for backward compatibility)
// ═══════════════════════════════════════════════════════════════════════════════

/// Analyze async function for race conditions (legacy PyObject interface)
///
/// **Deprecated**: Use `analyze_async_races_msgpack` for better performance
#[cfg(feature = "python")]
#[pyo3::pyfunction]
pub fn analyze_async_races(py: Python, ir_doc_dict: &PyDict, func_fqn: &str) -> PyResult<PyObject> {
    // Convert PyDict to JSON string, then to IRDocument
    let json_str = python_dict_to_json_string(py, ir_doc_dict)?;
    let ir_doc: IRDocument = serde_json::from_str(&json_str).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("JSON parse error: {}", e))
    })?;

    // Run analysis
    let detector = AsyncRaceDetector::new();
    let races = detector
        .analyze_async_function(&ir_doc, func_fqn)
        .unwrap_or_else(|_| vec![]);

    // Convert to Python list of dicts
    let result = PyList::empty(py);
    for race in races {
        let race_dict = race_to_py_dict(py, &race)?;
        result.append(race_dict)?;
    }

    Ok(result.into())
}

/// Analyze all async functions (legacy PyObject interface)
///
/// **Deprecated**: Use `analyze_all_async_races_msgpack` for better performance
#[cfg(feature = "python")]
#[pyo3::pyfunction]
pub fn analyze_all_async_races(py: Python, ir_doc_dict: &PyDict) -> PyResult<PyObject> {
    // Convert PyDict to JSON string, then to IRDocument
    let json_str = python_dict_to_json_string(py, ir_doc_dict)?;
    let ir_doc: IRDocument = serde_json::from_str(&json_str).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("JSON parse error: {}", e))
    })?;

    // Find all async functions and analyze
    let detector = AsyncRaceDetector::new();
    let async_funcs = ir_doc.find_async_functions();

    let mut all_races = Vec::new();
    let mut critical = 0u32;
    let mut high = 0u32;
    let mut medium = 0u32;
    let mut low = 0u32;

    for func in async_funcs {
        if let Ok(races) = detector.analyze_async_function(&ir_doc, &func.id) {
            for race in &races {
                match race.severity {
                    RaceSeverity::Critical => critical += 1,
                    RaceSeverity::High => high += 1,
                    RaceSeverity::Medium => medium += 1,
                    RaceSeverity::Low => low += 1,
                }
            }
            all_races.extend(races);
        }
    }

    // Build result dict
    let result = PyDict::new(py);

    let races_list = PyList::empty(py);
    for race in all_races {
        let race_dict = race_to_py_dict(py, &race)?;
        races_list.append(race_dict)?;
    }
    result.set_item("races", races_list)?;

    let summary = PyDict::new(py);
    summary.set_item("total_races", critical + high + medium + low)?;
    summary.set_item("critical", critical)?;
    summary.set_item("high", high)?;
    summary.set_item("medium", medium)?;
    summary.set_item("low", low)?;
    result.set_item("summary", summary)?;

    Ok(result.into())
}

// ═══════════════════════════════════════════════════════════════════════════════
// Helper Functions
// ═══════════════════════════════════════════════════════════════════════════════

/// Convert Python dict to JSON string
#[cfg(feature = "python")]
fn python_dict_to_json_string(py: Python, dict: &PyDict) -> PyResult<String> {
    let json = py.import("json")?;
    let json_str: String = json.call_method1("dumps", (dict,))?.extract()?;
    Ok(json_str)
}

/// Convert RaceCondition to Python dict
#[cfg(feature = "python")]
fn race_to_py_dict<'py>(py: Python<'py>, race: &RaceCondition) -> PyResult<&'py PyDict> {
    use crate::features::concurrency_analysis::domain::AccessType;

    let dict = PyDict::new(py);

    dict.set_item("shared_var", &race.shared_var)?;
    dict.set_item("file_path", &race.file_path)?;
    dict.set_item("function_name", &race.function_name)?;
    dict.set_item("proof_trace", &race.proof_trace)?;
    dict.set_item("fix_suggestion", &race.fix_suggestion)?;

    // Severity enum to string
    let severity_str = match race.severity {
        RaceSeverity::Critical => "critical",
        RaceSeverity::High => "high",
        RaceSeverity::Medium => "medium",
        RaceSeverity::Low => "low",
    };
    dict.set_item("severity", severity_str)?;

    // Verdict enum to string
    let verdict_str = match race.verdict {
        RaceVerdict::Proven => "proven",
        RaceVerdict::Likely => "likely",
        RaceVerdict::Possible => "possible",
    };
    dict.set_item("verdict", verdict_str)?;

    // Access 1
    let access1_dict = PyDict::new(py);
    access1_dict.set_item("line", race.access1.line)?;
    let access1_type_str = match race.access1.access_type {
        AccessType::Read => "read",
        AccessType::Write => "write",
        AccessType::ReadWrite => "read_write",
    };
    access1_dict.set_item("access_type", access1_type_str)?;
    dict.set_item("access1", access1_dict)?;

    // Access 2
    let access2_dict = PyDict::new(py);
    access2_dict.set_item("line", race.access2.line)?;
    let access2_type_str = match race.access2.access_type {
        AccessType::Read => "read",
        AccessType::Write => "write",
        AccessType::ReadWrite => "read_write",
    };
    access2_dict.set_item("access_type", access2_type_str)?;
    dict.set_item("access2", access2_dict)?;

    // Await points
    let await_points = PyList::empty(py);
    for await_point in &race.await_points {
        let await_dict = PyDict::new(py);
        await_dict.set_item("line", await_point.line)?;
        await_dict.set_item("await_expr", &await_point.await_expr)?;
        await_dict.set_item("function_name", &await_point.function_name)?;
        await_dict.set_item("file_path", &await_point.file_path)?;
        await_points.append(await_dict)?;
    }
    dict.set_item("await_points", await_points)?;

    Ok(dict)
}

/// Register concurrency analysis functions with Python module
#[cfg(feature = "python")]
pub fn register_concurrency_bindings(_py: Python, m: &PyModule) -> PyResult<()> {
    // Production API (msgpack)
    m.add_function(pyo3::wrap_pyfunction!(analyze_async_races_msgpack, m)?)?;
    m.add_function(pyo3::wrap_pyfunction!(analyze_all_async_races_msgpack, m)?)?;

    // Legacy API (PyObject)
    m.add_function(pyo3::wrap_pyfunction!(analyze_async_races, m)?)?;
    m.add_function(pyo3::wrap_pyfunction!(analyze_all_async_races, m)?)?;

    Ok(())
}
