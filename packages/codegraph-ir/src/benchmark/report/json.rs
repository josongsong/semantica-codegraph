//! JSON report generation

use crate::benchmark::{BenchmarkReport, BenchmarkResult2};
use std::path::PathBuf;

pub struct JsonReporter;

impl JsonReporter {
    pub fn save(report: &BenchmarkReport, output_dir: &PathBuf) -> BenchmarkResult2<PathBuf> {
        let path = output_dir.join("result.json");
        let json = serde_json::to_string_pretty(report)?;
        std::fs::write(&path, json)?;
        Ok(path)
    }
}
